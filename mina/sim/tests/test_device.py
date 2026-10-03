import base64

from mina_backend.protocol import build_audio_frame
from mina_sim.device import FRAME_BYTES, LOOPBACK_BYTES, HostDevice


def _play(pcm: bytes) -> str:
    encoded = base64.b64encode(pcm).decode("ascii")
    return f'{{"t":"play","pcm":"{encoded}"}}'


def test_mic_frame_matches_the_firmware_contract():
    device = HostDevice()
    device.set_backend(True)
    pcm = b"\x01\x00" * 480
    device.mic_pcm(pcm)
    assert device.take_backend() == [build_audio_frame(pcm, seq=1)]


def test_mic_stays_quiet_while_the_speaker_is_on():
    device = HostDevice()
    device.set_backend(True, now_ms=0)
    device.server_text(_play(b"\x02\x00" * 480), now_ms=10)
    device.mic_pcm(b"\x00\x00" * 480, now_ms=20)
    assert device.take_backend() == []
    assert device.mic_on is False
    assert device.speaking is True


def test_touch_cancels_and_later_audio_is_ignored_until_the_next_reply():
    device = HostDevice()
    device.set_backend(True, now_ms=0)
    device.server_text('{"t":"state","name":"thinking"}', now_ms=10)
    device.touch(now_ms=20)
    assert device.take_backend() == ['{"t":"cancel"}']
    assert device.take_stop() is True
    device.server_text(_play(b"\x02\x00"), now_ms=30)
    assert device.speaking is False
    device.server_text('{"t":"state","name":"thinking"}', now_ms=40)
    device.server_text(_play(b"\x03\x00"), now_ms=50)
    assert device.speaking is True


def test_latency_note_uses_the_heard_mark():
    device = HostDevice()
    device.set_backend(True, now_ms=0)
    device.server_text('{"t":"state","name":"heard"}', now_ms=1000)
    device.server_text(_play(b"\x00\x00"), now_ms=1800)
    assert device.note == "espera depois do fim de fala: 800 ms"


def test_error_face_lasts_two_and_a_half_seconds():
    device = HostDevice()
    device.set_backend(True, now_ms=0)
    device.server_text('{"t":"error","reason":"proxy"}', now_ms=0)
    assert device.mood == "error"
    device.tick(2499)
    assert device.mood == "error"
    device.tick(2500)
    assert device.mood == "listening"


def test_loopback_plays_three_seconds_then_returns_the_mic():
    device = HostDevice()
    device.begin_loopback(now_ms=0)
    loud = (8000).to_bytes(2, "little", signed=True) * (LOOPBACK_BYTES // 2)
    device.mic_pcm(loud, now_ms=0)
    assert device.status == "tocando 3 s"
    assert device.take_backend() == []
    now = 0
    released = 0
    while device.speaking and now < 10_000:
        device.tick(now)
        for generation, pcm in device.take_speaker():
            released += len(pcm)
            device.speaker_finished(len(pcm), generation, now)
        now += 20
    assert released == LOOPBACK_BYTES
    assert device.speaking is False
    assert device.status == "sem backend"


def test_playback_waits_for_the_speaker_to_finish():
    device = HostDevice()
    device.set_backend(True, now_ms=0)
    device.server_text(_play(b"\x00\x00" * 480), now_ms=0)
    device.server_text('{"t":"play_end"}', now_ms=0)
    device.tick(0)
    queued = device.take_speaker()
    assert len(queued) == 1
    assert device.speaking is True
    generation, pcm = queued[0]
    assert len(pcm) == FRAME_BYTES
    device.speaker_finished(len(pcm), generation, now_ms=20)
    assert device.speaking is False
    assert device.mic_on is True


def test_disconnected_click_does_not_send_cancel():
    device = HostDevice()
    device.touch(now_ms=0)
    assert device.take_backend() == []
