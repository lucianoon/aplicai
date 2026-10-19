"""Receptor dos blocos de áudio do CoreS3.

Sem OPENAI_API_KEY, só confere o quadro e devolve ack.
Com a chave no ambiente, abre a Realtime API e devolve o áudio da resposta.
A chave não sai do servidor.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from mina_backend.protocol import (
    ProtocolError,
    ack_payload,
    cancelled_message,
    error_message,
    is_cancel_message,
    parse_audio_message,
)
from mina_backend.realtime import RealtimeSettings, connect_openai, run_bridge

logger = logging.getLogger("mina.audio")

app = FastAPI(title="Mina audio", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "realtime": RealtimeSettings.from_env().enabled}


async def ack_only(ws: WebSocket) -> None:
    received = 0
    try:
        while True:
            text = await ws.receive_text()
            if is_cancel_message(text):
                await ws.send_json(cancelled_message())
                continue
            try:
                chunk = parse_audio_message(text)
            except ProtocolError:
                await ws.send_json(error_message("audio"))
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


@app.websocket("/v1/audio")
async def audio(ws: WebSocket) -> None:
    await ws.accept()
    settings = RealtimeSettings.from_env()
    if not settings.enabled:
        await ack_only(ws)
        return
    logger.info("realtime model=%s voice=%s", settings.model, settings.voice)
    try:
        async with connect_openai(settings) as upstream:
            await run_bridge(ws, settings, upstream)
    except WebSocketDisconnect:
        logger.info("dispositivo desconectou")
    except Exception as exc:
        logger.error("proxy realtime encerrou: %s", type(exc).__name__)
        try:
            await ws.send_json(error_message("proxy"))
        except Exception:
            pass
