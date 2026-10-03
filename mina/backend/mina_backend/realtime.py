"""Ponte com a OpenAI Realtime API.

A chave só entra por OPENAI_API_KEY no ambiente do servidor. Ela não vai
para o firmware, para o quadro enviado ao CoreS3 nem para o repositório.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import inspect
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from starlette.websockets import WebSocketDisconnect

from mina_backend.protocol import (
    ProtocolError,
    ack_payload,
    error_message,
    parse_audio_message,
    play_end_message,
    play_frames,
    state_message,
)

DEFAULT_INSTRUCTIONS = (
    "Você é a Mina, uma presença de voz breve e calorosa. "
    "Responda em português do Brasil, em poucas frases."
)
DEFAULT_MODEL = "gpt-realtime-2.1"
DEFAULT_VOICE = "marin"
REALTIME_URL = "wss://api.openai.com/v1/realtime"
MAX_BUFFERED_CHUNKS = 250


@dataclass(frozen=True)
class RealtimeSettings:
    api_key: str
    model: str = DEFAULT_MODEL
    voice: str = DEFAULT_VOICE
    instructions: str = DEFAULT_INSTRUCTIONS
    url: str = REALTIME_URL

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> RealtimeSettings:
        return cls(
            api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            model=os.environ.get("MINA_REALTIME_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            voice=os.environ.get("MINA_REALTIME_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE,
            instructions=os.environ.get("MINA_REALTIME_INSTRUCTIONS", DEFAULT_INSTRUCTIONS).strip()
            or DEFAULT_INSTRUCTIONS,
        )

    def websocket_url(self) -> str:
        return f"{self.url}?model={self.model}"

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}


def build_session_update(settings: RealtimeSettings) -> dict:
    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "output_modalities": ["audio"],
            "instructions": settings.instructions,
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "turn_detection": {"type": "server_vad"},
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "voice": settings.voice,
                },
            },
        },
    }


def append_audio_event(pcm: bytes) -> dict:
    return {
        "type": "input_audio_buffer.append",
        "audio": base64.b64encode(pcm).decode("ascii"),
    }


def public_error_reason(event: dict) -> str:
    err = event.get("error")
    code = ""
    if isinstance(err, dict):
        code = str(err.get("code") or err.get("type") or "")
    cleaned = "".join(ch for ch in code if ch.isalnum() or ch in "._-")
    return cleaned[:40] or "realtime"


def device_messages(event: object) -> list[dict]:
    if not isinstance(event, dict):
        return []
    kind = event.get("type")
    if kind == "response.output_audio.delta":
        delta = event.get("delta")
        if not isinstance(delta, str) or not delta:
            return []
        try:
            pcm = base64.b64decode(delta, validate=True)
        except (binascii.Error, ValueError):
            return []
        try:
            return play_frames(pcm)
        except ProtocolError:
            return []
    if kind == "response.output_audio.done":
        return [play_end_message()]
    if kind == "response.created":
        return [state_message("thinking")]
    if kind == "error":
        return [error_message(public_error_reason(event))]
    return []


class Upstream:
    async def send(self, text: str) -> None: ...

    def __aiter__(self) -> AsyncIterator[str]: ...


async def run_bridge(device, settings: RealtimeSettings, upstream: Upstream) -> None:
    """Encaminha o microfone e devolve o áudio da resposta.

    `device` precisa de receive_text() e send_json(), como um WebSocket do FastAPI.
    O áudio que chega antes de session.updated fica retido e sai em ordem.
    """
    send_lock = asyncio.Lock()
    ready = asyncio.Event()
    buffered: list[bytes] = []

    async def send_upstream(payload: dict) -> None:
        await upstream.send(json.dumps(payload, separators=(",", ":")))

    await send_upstream(build_session_update(settings))

    async def from_device() -> None:
        try:
            while True:
                text = await device.receive_text()
                try:
                    chunk = parse_audio_message(text)
                except ProtocolError:
                    await device.send_json(error_message("audio"))
                    continue
                await device.send_json(ack_payload(chunk))
                async with send_lock:
                    if not ready.is_set():
                        buffered.append(chunk.pcm)
                        if len(buffered) > MAX_BUFFERED_CHUNKS:
                            del buffered[0]
                        continue
                    await send_upstream(append_audio_event(chunk.pcm))
        except WebSocketDisconnect:
            return

    async def from_upstream() -> None:
        async for raw in upstream:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            async with send_lock:
                if isinstance(event, dict) and event.get("type") == "session.updated":
                    ready.set()
                    queued = list(buffered)
                    buffered.clear()
                    for pcm in queued:
                        await send_upstream(append_audio_event(pcm))
            for message in device_messages(event):
                await device.send_json(message)

    device_task = asyncio.create_task(from_device())
    upstream_task = asyncio.create_task(from_upstream())
    try:
        done, pending = await asyncio.wait(
            {device_task, upstream_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                raise exc
    finally:
        for task in (device_task, upstream_task):
            if not task.done():
                task.cancel()


@asynccontextmanager
async def connect_openai(settings: RealtimeSettings):
    import websockets

    signature = inspect.signature(websockets.connect)
    header_arg = (
        "additional_headers" if "additional_headers" in signature.parameters else "extra_headers"
    )
    async with websockets.connect(
        settings.websocket_url(),
        max_size=8 * 1024 * 1024,
        **{header_arg: settings.headers()},
    ) as upstream:
        yield upstream
