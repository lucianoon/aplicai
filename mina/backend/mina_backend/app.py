"""Receptor dos blocos de áudio do CoreS3.

Não chama a OpenAI e não lê chave de API. Só confere o quadro e devolve ack.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from mina_backend.protocol import ProtocolError, ack_payload, parse_audio_message

logger = logging.getLogger("mina.audio")

app = FastAPI(title="Mina audio", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.websocket("/v1/audio")
async def audio(ws: WebSocket) -> None:
    await ws.accept()
    received = 0
    try:
        while True:
            text = await ws.receive_text()
            try:
                chunk = parse_audio_message(text)
            except ProtocolError as exc:
                await ws.send_json({"t": "error", "reason": str(exc)})
                continue
            received += 1
            if received == 1 or received % 50 == 0:
                logger.info(
                    "bloco seq=%s amostras=%s taxa=%s",
                    chunk.seq,
                    chunk.samples,
                    chunk.sample_rate,
                )
            await ws.send_json(ack_payload(chunk))
    except WebSocketDisconnect:
        logger.info("socket fechado depois de %s blocos", received)
