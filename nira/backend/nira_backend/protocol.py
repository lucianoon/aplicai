"""Contrato do áudio que o firmware manda no WebSocket.

O quadro JSON é o mesmo snprintf de nira/src/main.cpp. PCM16 little-endian,
24 kHz, um bloco por mensagem.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
from dataclasses import dataclass

SAMPLE_RATE_HZ = 24_000
CHUNK_MS = 20
CHUNK_SAMPLES = SAMPLE_RATE_HZ * CHUNK_MS // 1000


class ProtocolError(ValueError):
    """Mensagem que não é um bloco de áudio válido."""


@dataclass(frozen=True)
class AudioChunk:
    seq: int
    sample_rate: int
    samples: int
    pcm: bytes


def build_audio_frame(pcm: bytes, *, seq: int, sample_rate: int = SAMPLE_RATE_HZ) -> str:
    if len(pcm) % 2 != 0:
        raise ProtocolError("PCM16 precisa de número par de bytes")
    samples = len(pcm) // 2
    encoded = base64.b64encode(pcm).decode("ascii")
    return (
        f'{{"t":"audio","sr":{sample_rate},"n":{samples},"seq":{seq},"pcm":"{encoded}"}}'
    )


def parse_audio_message(text: str) -> AudioChunk:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("JSON inválido") from exc
    if not isinstance(payload, dict):
        raise ProtocolError("a mensagem precisa ser um objeto")
    if payload.get("t") != "audio":
        raise ProtocolError("tipo diferente de audio")

    try:
        seq = int(payload["seq"])
        sample_rate = int(payload["sr"])
        samples = int(payload["n"])
        encoded = payload["pcm"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError("campos sr, n, seq ou pcm ausentes") from exc

    if seq < 1 or sample_rate < 1 or samples < 1:
        raise ProtocolError("seq, sr e n precisam ser positivos")
    if not isinstance(encoded, str):
        raise ProtocolError("pcm precisa ser texto base64")

    try:
        pcm = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProtocolError("base64 inválido") from exc

    if len(pcm) != samples * 2:
        raise ProtocolError("tamanho do PCM não confere com n")
    return AudioChunk(seq=seq, sample_rate=sample_rate, samples=samples, pcm=pcm)


def rms(pcm: bytes) -> float:
    count = len(pcm) // 2
    if count == 0:
        return 0.0
    total = 0
    for i in range(count):
        sample = int.from_bytes(pcm[i * 2 : i * 2 + 2], "little", signed=True)
        total += sample * sample
    return math.sqrt(total / count)


def ack_payload(chunk: AudioChunk) -> dict:
    return {
        "t": "ack",
        "seq": chunk.seq,
        "samples": chunk.samples,
        "rms": round(rms(chunk.pcm), 2),
    }
