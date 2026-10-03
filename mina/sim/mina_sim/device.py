"""Comportamento do aparelho, no computador.

Metade do I2S continua aqui: enquanto o speaker toca, o microfone não sai
para o backend. O toque cancela a resposta. Isto não é o CoreS3.
"""

from __future__ import annotations

import base64
import binascii
import json
import math

from mina_backend.protocol import build_audio_frame

SAMPLE_RATE_HZ = 24_000
FRAME_SAMPLES = 480
FRAME_BYTES = FRAME_SAMPLES * 2
LOOPBACK_SAMPLES = SAMPLE_RATE_HZ * 3
LOOPBACK_BYTES = LOOPBACK_SAMPLES * 2

STATUS = {
    "listening": "ouvindo",
    "thinking": "pensando",
    "speaking": "falando",
}


def rms_int(pcm: bytes) -> int:
    count = len(pcm) // 2
    if count == 0:
        return 0
    total = 0
    for index in range(count):
        sample = int.from_bytes(pcm[index * 2 : index * 2 + 2], "little", signed=True)
        total += sample * sample
    return int(math.sqrt(total / count))


class HostDevice:
    def __init__(self) -> None:
        self.now_ms = 0
        self.seq = 0
        self.backend_up = False
        self.mic_on = False
        self.speaking = False
        self.ignore_play = False
        self.local_only = False
        self.loopback_recording = False
        self.loopback_playing = False
        self.play_end = False
        self.latency_pending = False
        self.heard_ms = 0
        self.error_until = 0
        self.base_mood = "thinking"
        self.mood = "thinking"
        self.mouth = 0
        self.status = "sem backend"
        self.note = ""
        self.play_generation = 1
        self.outstanding = 0
        self.last_release_ms = -20
        self.last_decay_ms: int | None = None
        self.stop_speaker = False
        self.mic_pending = bytearray()
        self.loop_buf = bytearray()
        self.speaker_buf = bytearray()
        self.to_backend: list[str] = []
        self.to_speaker: list[tuple[int, bytes]] = []
        self.logs: list[str] = []

    def face_message(self) -> dict:
        return {
            "t": "face",
            "mood": self.mood,
            "mouth": self.mouth,
            "mic": self.mic_on,
            "status": self.status,
            "note": self.note,
            "logs": list(self.logs[-8:]),
        }

    def take_backend(self) -> list[str]:
        queued = self.to_backend
        self.to_backend = []
        return queued

    def take_speaker(self) -> list[tuple[int, bytes]]:
        queued = self.to_speaker
        self.to_speaker = []
        return queued

    def take_stop(self) -> bool:
        stop = self.stop_speaker
        self.stop_speaker = False
        return stop

    def set_backend(self, up: bool, now_ms: int | None = None) -> None:
        self._at(now_ms)
        self.backend_up = up
        if self.speaking or self.loopback_recording or self.loopback_playing:
            return
        if up:
            self.mic_on = True
            self._show("listening")
            self.status = "ouvindo"
            return
        self.mic_on = False
        self.mic_pending.clear()
        self._show("thinking")
        self.status = "sem backend"

    def begin_loopback(self, now_ms: int | None = None) -> None:
        self._at(now_ms)
        if self.speaking or self.loopback_playing or self.loopback_recording:
            self._drop_playback(send_cancel=False)
        self.local_only = True
        self.ignore_play = True
        self.loopback_recording = True
        self.loop_buf.clear()
        self.mic_on = True
        self._show("listening")
        self.status = "gravando 3 s"
        self._log("gravando 3 s neste computador")

    def mic_pcm(self, pcm: bytes, now_ms: int | None = None) -> None:
        self._at(now_ms)
        if not pcm:
            return
        if len(pcm) % 2:
            pcm = pcm[:-1]
        if self.loopback_recording:
            self.loop_buf.extend(pcm)
            if len(self.loop_buf) >= LOOPBACK_BYTES:
                captured = bytes(self.loop_buf[:LOOPBACK_BYTES])
                self.loop_buf.clear()
                self._play_captured(captured)
            return
        if not self.mic_on or not self.backend_up or self.speaking or self.local_only:
            return
        self.mic_pending.extend(pcm)
        while len(self.mic_pending) >= FRAME_BYTES:
            frame = bytes(self.mic_pending[:FRAME_BYTES])
            del self.mic_pending[:FRAME_BYTES]
            self.seq += 1
            self.to_backend.append(build_audio_frame(frame, seq=self.seq))

    def server_text(self, text: str, now_ms: int | None = None) -> None:
        self._at(now_ms)
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(message, dict):
            return
        kind = message.get("t")
        if kind == "ack":
            return
        if kind == "cancelled":
            self._drop_playback(send_cancel=False)
            return
        if kind in {"play", "play_end"} and (self.ignore_play or self.local_only):
            return
        if kind == "play_end":
            self.play_end = True
            self._maybe_finish()
            return
        if kind == "play":
            encoded = message.get("pcm")
            if not isinstance(encoded, str):
                return
            try:
                pcm = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                return
            if self.latency_pending:
                waited = max(0, self.now_ms - self.heard_ms)
                self.note = f"espera depois do fim de fala: {waited} ms"
                self.latency_pending = False
                self._log(self.note)
            self.speaker_buf.extend(pcm)
            self._begin_audio()
            return
        if kind == "state":
            name = message.get("name")
            if name == "thinking" and not self.local_only:
                self.ignore_play = False
                if not self.speaking:
                    self._show("thinking")
                    self.status = "pensando"
            elif name == "heard" and not self.local_only:
                self.heard_ms = self.now_ms
                self.latency_pending = True
            return
        if kind == "error":
            reason = message.get("reason")
            self.note = reason if isinstance(reason, str) and reason else "erro"
            self.error_until = self.now_ms + 2500
            self._refresh_mood()
            self._log(f"erro: {self.note}")

    def touch(self, now_ms: int | None = None) -> None:
        self._at(now_ms)
        waiting_reply = self.backend_up and self.base_mood == "thinking"
        active = self.speaking or self.loopback_recording or self.loopback_playing or waiting_reply
        if not active:
            return
        send_cancel = self.backend_up and not self.local_only and (self.speaking or waiting_reply)
        self._drop_playback(send_cancel=send_cancel)
        self._log("interrupcao por toque")

    def speaker_finished(self, nbytes: int, generation: int, now_ms: int | None = None) -> None:
        self._at(now_ms)
        if generation != self.play_generation or nbytes <= 0:
            return
        self.outstanding = max(0, self.outstanding - nbytes)
        self._maybe_finish()

    def tick(self, now_ms: int) -> None:
        self._at(now_ms)
        if self.last_decay_ms is None:
            self.last_decay_ms = self.now_ms
        else:
            elapsed = self.now_ms - self.last_decay_ms
            if elapsed >= 40:
                steps = min(elapsed // 40, 30)
                self.last_decay_ms += steps * 40
                drop = 28 * steps
                self.mouth = self.mouth - drop if self.mouth > drop else 0
        if self.speaker_buf and self.now_ms - self.last_release_ms >= 20:
            count = min(len(self.speaker_buf), FRAME_BYTES)
            chunk = bytes(self.speaker_buf[:count])
            del self.speaker_buf[:count]
            self.last_release_ms = self.now_ms
            level = rms_int(chunk)
            if level > 6000:
                level = 6000
            self.mouth = level * 255 // 6000
            self.outstanding += len(chunk)
            self.to_speaker.append((self.play_generation, chunk))
        was_error = self.mood == "error"
        self._refresh_mood()
        if was_error and self.mood != "error":
            self.status = STATUS[self.base_mood]
        self._maybe_finish()

    def _at(self, now_ms: int | None) -> None:
        if now_ms is not None:
            self.now_ms = now_ms

    def _show(self, mood: str) -> None:
        self.base_mood = mood
        self._refresh_mood()

    def _refresh_mood(self) -> None:
        if self.now_ms < self.error_until:
            self.mood = "error"
        else:
            self.mood = self.base_mood

    def _begin_audio(self) -> None:
        if not self.speaking:
            self.speaking = True
            self.mic_on = False
            self.mic_pending.clear()
        self._show("speaking")
        if not self.loopback_playing:
            self.status = "falando"

    def _play_captured(self, pcm: bytes) -> None:
        self.loopback_recording = False
        self.loopback_playing = True
        self.local_only = True
        self.speaker_buf = bytearray(pcm)
        self.play_end = True
        self._begin_audio()
        self.status = "tocando 3 s"
        self._log("tocando 3 s neste computador")

    def _drop_playback(self, *, send_cancel: bool) -> None:
        self.ignore_play = True
        self.play_end = False
        self.speaking = False
        self.loopback_recording = False
        self.loopback_playing = False
        self.local_only = False
        self.speaker_buf.clear()
        self.loop_buf.clear()
        self.to_speaker.clear()
        self.outstanding = 0
        self.mouth = 0
        self.play_generation += 1
        self.stop_speaker = True
        self.latency_pending = False
        self.mic_pending.clear()
        if self.backend_up:
            self.mic_on = True
            self._show("listening")
            self.status = "ouvindo"
        else:
            self.mic_on = False
            self._show("thinking")
            self.status = "sem backend"
        if send_cancel:
            self.to_backend.append('{"t":"cancel"}')

    def _maybe_finish(self) -> None:
        if self.speaking and self.play_end and not self.speaker_buf and self.outstanding <= 0:
            self._finish_speaking()

    def _finish_speaking(self) -> None:
        self.speaking = False
        self.play_end = False
        self.loopback_playing = False
        self.local_only = False
        self.ignore_play = False
        self.mouth = 0
        if self.backend_up:
            self.mic_on = True
            self._show("listening")
            self.status = "ouvindo"
        else:
            self.mic_on = False
            self._show("thinking")
            self.status = "sem backend"
        self._log("mic de volta")

    def _log(self, text: str) -> None:
        self.logs.append(text)
        del self.logs[:-12]
