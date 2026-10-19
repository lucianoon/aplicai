import asyncio
import base64
import json

from starlette.websockets import WebSocketDisconnect

from mina_backend.protocol import (
    CHUNK_SAMPLES,
    DEVICE_WS_TEXT_LIMIT,
    build_audio_frame,
)
from mina_backend.realtime import (
    RealtimeSettings,
    append_audio_event,
    build_session_update,
    device_messages,
    public_error_reason,
    run_bridge,
)


def _settings() -> RealtimeSettings:
    return RealtimeSettings(
        api_key="sk-test",
        model="gpt-realtime-2.1",
        voice="marin",
        instructions="Fale pouco.",
    )


def test_session_update_sets_voice_instructions_and_server_vad():
    event = build_session_update(_settings())
    assert event["type"] == "session.update"
    session = event["session"]
    assert session["type"] == "realtime"
    assert session["instructions"] == "Fale pouco."
    assert session["audio"]["output"]["voice"] == "marin"
    assert session["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert session["audio"]["output"]["format"]["rate"] == 24000
    assert session["audio"]["input"]["turn_detection"]["type"] == "server_vad"
    assert "sk-test" not in json.dumps(event)


def test_headers_carry_the_key_only_on_the_server_side():
    headers = _settings().headers()
    assert headers == {"Authorization": "Bearer sk-test"}
    assert _settings().websocket_url().endswith("model=gpt-realtime-2.1")


def test_append_event_is_base64_pcm():
    event = append_audio_event(b"\x01\x00")
    assert event["type"] == "input_audio_buffer.append"
    assert base64.b64decode(event["audio"]) == b"\x01\x00"


def test_device_messages_split_playback_under_the_firmware_limit():
    pcm = b"\x00\x01" * 20000
    messages = device_messages(
        {
            "type": "response.output_audio.delta",
            "delta": base64.b64encode(pcm).decode("ascii"),
        }
    )
    assert len(messages) > 1
    restored = b""
    for message in messages:
        assert message["t"] == "play"
        text = json.dumps(message, separators=(",", ":"))
        assert len(text.encode("utf-8")) < DEVICE_WS_TEXT_LIMIT
        restored += base64.b64decode(message["pcm"])
    assert restored == pcm


def test_device_messages_for_turn_boundaries_and_errors():
    assert device_messages({"type": "response.created"}) == [
        {"t": "state", "name": "thinking"}
    ]
    assert device_messages({"type": "response.output_audio.done"}) == [{"t": "play_end"}]
    assert device_messages({"type": "input_audio_buffer.speech_stopped"}) == [
        {"t": "state", "name": "heard"}
    ]
    assert device_messages({"type": "response.output_audio.delta", "delta": "!!!!"}) == []
    reason = public_error_reason(
        {"type": "error", "error": {"code": "invalid_api_key", "message": "sk-secret"}}
    )
    assert reason == "invalid_api_key"
    assert "sk-secret" not in reason
    leaked = device_messages(
        {"type": "error", "error": {"message": "Bearer sk-secret", "code": "bad key!"}}
    )
    assert leaked == [{"t": "error", "reason": "badkey"}]


class FakeDevice:
    def __init__(self):
        self.incoming: asyncio.Queue[str | None] = asyncio.Queue()
        self.outgoing: list[dict] = []

    async def receive_text(self) -> str:
        item = await self.incoming.get()
        if item is None:
            raise WebSocketDisconnect()
        return item

    async def send_json(self, data: dict) -> None:
        self.outgoing.append(data)

    def push(self, text: str) -> None:
        self.incoming.put_nowait(text)

    def close(self) -> None:
        self.incoming.put_nowait(None)


class FakeUpstream:
    def __init__(self):
        self.sent: list[dict] = []
        self.incoming: asyncio.Queue[str | None] = asyncio.Queue()
        self._sent = asyncio.Event()

    async def send(self, text: str) -> None:
        self.sent.append(json.loads(text))
        self._sent.set()

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        item = await self.incoming.get()
        if item is None:
            raise StopAsyncIteration
        return item

    def push(self, event: dict) -> None:
        self.incoming.put_nowait(json.dumps(event))

    def close(self) -> None:
        self.incoming.put_nowait(None)

    async def wait_sent(self, count: int) -> None:
        while len(self.sent) < count:
            self._sent.clear()
            if len(self.sent) >= count:
                return
            await self._sent.wait()


def test_bridge_holds_audio_until_session_updated_then_plays():
    asyncio.run(_bridge_scenario())


async def _bridge_scenario() -> None:
    device = FakeDevice()
    upstream = FakeUpstream()
    task = asyncio.create_task(run_bridge(device, _settings(), upstream))
    await upstream.wait_sent(1)
    assert upstream.sent[0]["type"] == "session.update"
    assert "sk-test" not in json.dumps(upstream.sent)

    pcm = b"\x00\x00" * CHUNK_SAMPLES
    device.push(build_audio_frame(pcm, seq=3))
    for _ in range(20):
        await asyncio.sleep(0)
        if device.outgoing:
            break
    assert device.outgoing[0]["t"] == "ack"
    assert len(upstream.sent) == 1

    upstream.push({"type": "session.updated", "session": {}})
    await upstream.wait_sent(2)
    assert upstream.sent[1]["type"] == "input_audio_buffer.append"
    assert base64.b64decode(upstream.sent[1]["audio"]) == pcm

    upstream.push({"type": "response.created"})
    upstream.push(
        {
            "type": "response.output_audio.delta",
            "delta": base64.b64encode(b"\x02\x00").decode("ascii"),
        }
    )
    upstream.push({"type": "response.output_audio.done"})
    for _ in range(20):
        await asyncio.sleep(0)
        kinds = [item["t"] for item in device.outgoing]
        if "play_end" in kinds:
            break
    kinds = [item["t"] for item in device.outgoing]
    assert kinds == ["ack", "state", "play", "play_end"]
    assert device.outgoing[2]["pcm"] == base64.b64encode(b"\x02\x00").decode("ascii")

    device.close()
    upstream.close()
    await asyncio.wait_for(task, timeout=2)


def test_bridge_cancel_drops_the_rest_of_the_response():
    asyncio.run(_cancel_scenario())


async def _cancel_scenario() -> None:
    device = FakeDevice()
    upstream = FakeUpstream()
    task = asyncio.create_task(run_bridge(device, _settings(), upstream))
    await upstream.wait_sent(1)

    upstream.push({"type": "session.updated", "session": {}})
    upstream.push({"type": "response.created"})
    upstream.push(
        {
            "type": "response.output_audio.delta",
            "delta": base64.b64encode(b"\x02\x00").decode("ascii"),
        }
    )
    for _ in range(20):
        await asyncio.sleep(0)
        if any(item["t"] == "play" for item in device.outgoing):
            break

    device.push('{"t":"cancel"}')
    await upstream.wait_sent(2)
    assert upstream.sent[-1]["type"] == "response.cancel"

    upstream.push(
        {
            "type": "response.output_audio.delta",
            "delta": base64.b64encode(b"\x03\x00").decode("ascii"),
        }
    )
    upstream.push({"type": "response.output_audio.done"})
    upstream.push({"type": "response.done", "response": {"status": "cancelled"}})
    upstream.push({"type": "response.created"})
    upstream.push(
        {
            "type": "response.output_audio.delta",
            "delta": base64.b64encode(b"\x04\x00").decode("ascii"),
        }
    )
    for _ in range(30):
        await asyncio.sleep(0)
        plays = [item["pcm"] for item in device.outgoing if item["t"] == "play"]
        if base64.b64encode(b"\x04\x00").decode("ascii") in plays:
            break

    plays = [item["pcm"] for item in device.outgoing if item["t"] == "play"]
    assert base64.b64encode(b"\x02\x00").decode("ascii") in plays
    assert base64.b64encode(b"\x03\x00").decode("ascii") not in plays
    assert plays[-1] == base64.b64encode(b"\x04\x00").decode("ascii")
    assert any(item["t"] == "cancelled" for item in device.outgoing)

    device.close()
    upstream.close()
    await asyncio.wait_for(task, timeout=2)
