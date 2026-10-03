from fastapi.testclient import TestClient

from nira_backend.app import app
from nira_backend.protocol import CHUNK_SAMPLES, build_audio_frame


def test_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_websocket_acks_a_chunk_and_rejects_garbage():
    pcm = b"\x00\x00" * CHUNK_SAMPLES
    frame = build_audio_frame(pcm, seq=7)
    client = TestClient(app)
    with client.websocket_connect("/v1/audio") as ws:
        ws.send_text(frame)
        ack = ws.receive_json()
        assert ack["t"] == "ack"
        assert ack["seq"] == 7
        assert ack["samples"] == CHUNK_SAMPLES
        assert ack["rms"] == 0.0

        ws.send_text("nao-json")
        err = ws.receive_json()
        assert err["t"] == "error"
