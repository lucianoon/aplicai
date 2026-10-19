"""Página local e ponte com o backend.

O navegador empresta o microfone e o speaker. Este processo faz o papel
do aparelho: corta o mic enquanto fala e fala o protocolo da Mina.
"""

from __future__ import annotations

import asyncio
import json
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets

from mina_sim.device import HostDevice

PAGE_PATH = Path(__file__).resolve().parent / "static" / "index.html"


class Bridge:
    def __init__(self, backend_url: str) -> None:
        self.backend_url = backend_url
        self.device = HostDevice()
        self.browser = None
        self.backend_queue: asyncio.Queue[str | None] = asyncio.Queue()
        # O cadeado do aparelho não pode ficar preso durante um send():
        # a leitura do navegador precisa do laço livre para esvaziar o socket.
        self.device_lock = asyncio.Lock()
        self.io_lock = asyncio.Lock()

    def _snapshot(self) -> tuple:
        backend = self.device.take_backend()
        speaker = self.device.take_speaker()
        stop = self.device.take_stop()
        face = json.dumps(self.device.face_message())
        return backend, speaker, stop, face, self.browser

    async def publish(self) -> None:
        async with self.device_lock:
            snapshot = self._snapshot()
        await self._send(snapshot)

    async def _send(self, snapshot: tuple) -> None:
        backend, speaker, stop, face, browser = snapshot
        for text in backend:
            self.backend_queue.put_nowait(text)
        if browser is None:
            return
        async with self.io_lock:
            try:
                for generation, pcm in speaker:
                    await browser.send(struct.pack("<I", generation) + pcm)
                if stop:
                    await browser.send(json.dumps({"t": "stop"}))
                await browser.send(face)
            except websockets.ConnectionClosed:
                async with self.device_lock:
                    if self.browser is browser:
                        self.browser = None

    async def browser_connected(self, websocket) -> None:
        async with self.device_lock:
            previous = self.browser
            self.browser = websocket
            snapshot = self._snapshot()
        if previous is not None and previous is not websocket:
            await previous.close()
        await self._send(snapshot)
        try:
            async for message in websocket:
                async with self.device_lock:
                    now = int(time.time() * 1000)
                    if isinstance(message, bytes):
                        self.device.mic_pcm(message, now)
                    else:
                        self._on_text(message, now)
                    snapshot = self._snapshot()
                await self._send(snapshot)
        finally:
            async with self.device_lock:
                if self.browser is websocket:
                    self.browser = None

    def _on_text(self, message: str, now: int) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        kind = payload.get("t")
        if kind == "cancel":
            self.device.touch(now)
        elif kind == "loopback":
            self.device.begin_loopback(now)
        elif kind == "played":
            nbytes = payload.get("bytes")
            generation = payload.get("gen")
            if isinstance(nbytes, int) and isinstance(generation, int):
                self.device.speaker_finished(nbytes, generation, now)

    async def tick_forever(self) -> None:
        while True:
            await asyncio.sleep(0.02)
            async with self.device_lock:
                self.device.tick(int(time.time() * 1000))
                snapshot = self._snapshot()
            await self._send(snapshot)

    async def backend_forever(self) -> None:
        while True:
            try:
                async with websockets.connect(self.backend_url, open_timeout=5, proxy=None) as upstream:
                    async with self.device_lock:
                        self.device.set_backend(True, int(time.time() * 1000))
                        snapshot = self._snapshot()
                    await self._send(snapshot)
                    sender = asyncio.create_task(self._send_upstream(upstream))
                    try:
                        async for incoming in upstream:
                            if isinstance(incoming, bytes):
                                incoming = incoming.decode("utf-8", errors="replace")
                            async with self.device_lock:
                                self.device.server_text(incoming, int(time.time() * 1000))
                                snapshot = self._snapshot()
                            await self._send(snapshot)
                    finally:
                        sender.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"backend indisponivel ({type(exc).__name__}), nova tentativa em 5 s")
            async with self.device_lock:
                self.device.set_backend(False, int(time.time() * 1000))
                snapshot = self._snapshot()
            await self._send(snapshot)
            await self._drain_backend_queue()
            await asyncio.sleep(5)

    async def _send_upstream(self, upstream) -> None:
        while True:
            text = await self.backend_queue.get()
            if text is None:
                return
            await upstream.send(text)

    async def _drain_backend_queue(self) -> None:
        while not self.backend_queue.empty():
            try:
                self.backend_queue.get_nowait()
            except asyncio.QueueEmpty:
                return


def serve_page(port: int, ws_port: int) -> ThreadingHTTPServer:
    token = str(ws_port).encode("ascii")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in {"/", "/index.html"}:
                self.send_error(404)
                return
            page = PAGE_PATH.read_bytes().replace(b"__WS_PORT__", token)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, fmt: str, *args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def main(web_port: int, ws_port: int, backend_url: str) -> None:
    bridge = Bridge(backend_url)
    serve_page(web_port, ws_port)
    print(f"Mina no computador: http://127.0.0.1:{web_port}")
    print(f"Backend: {backend_url}")
    print("Isto usa o microfone e o speaker desta máquina. Não é o CoreS3.")
    async with websockets.serve(
        bridge.browser_connected,
        "127.0.0.1",
        ws_port,
        max_queue=64,
        max_size=2**20,
    ):
        await asyncio.gather(bridge.tick_forever(), bridge.backend_forever())
