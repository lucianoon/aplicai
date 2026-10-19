import base64
import json

import pytest

from mina_backend.protocol import (
    CHUNK_MS,
    CHUNK_SAMPLES,
    SAMPLE_RATE_HZ,
    ProtocolError,
    ack_payload,
    build_audio_frame,
    cancelled_message,
    is_cancel_message,
    parse_audio_message,
    rms,
)


def test_chunk_size_matches_firmware():
    assert SAMPLE_RATE_HZ == 24000
    assert CHUNK_MS == 20
    assert CHUNK_SAMPLES == 480


def test_frame_prefix_matches_firmware_snprintf():
    frame = build_audio_frame(b"\x00\x00", seq=1)
    assert frame.startswith('{"t":"audio","sr":24000,"n":1,"seq":1,"pcm":"')
    assert frame.endswith('"}')


def test_roundtrip_of_silence():
    pcm = b"\x00\x00" * CHUNK_SAMPLES
    frame = build_audio_frame(pcm, seq=1)
    chunk = parse_audio_message(frame)
    assert chunk.seq == 1
    assert chunk.sample_rate == SAMPLE_RATE_HZ
    assert chunk.samples == CHUNK_SAMPLES
    assert chunk.pcm == pcm
    assert json.loads(frame)["t"] == "audio"
    assert ack_payload(chunk)["rms"] == 0.0


def test_rms_of_constant_sample():
    sample = (1000).to_bytes(2, "little", signed=True)
    assert rms(sample * 4) == pytest.approx(1000.0)


def test_rejects_bad_base64():
    frame = build_audio_frame(b"\x00\x00", seq=1)
    broken = frame.replace(base64.b64encode(b"\x00\x00").decode(), "!!!!")
    with pytest.raises(ProtocolError):
        parse_audio_message(broken)


def test_rejects_length_mismatch():
    pcm = b"\x01\x00\x02\x00"
    frame = build_audio_frame(pcm, seq=2)
    payload = json.loads(frame)
    payload["n"] = 1
    with pytest.raises(ProtocolError, match="tamanho"):
        parse_audio_message(json.dumps(payload, separators=(",", ":")))


def test_rejects_other_type():
    with pytest.raises(ProtocolError):
        parse_audio_message('{"t":"ping"}')


def test_cancel_message_is_not_audio():
    assert is_cancel_message('{"t":"cancel"}')
    assert not is_cancel_message('{"t":"audio"}')
    assert not is_cancel_message("nao-json")
    assert cancelled_message() == {"t": "cancelled"}
