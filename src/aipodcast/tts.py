"""Text-to-speech providers. Each returns mono 16-bit PCM WAV bytes."""
from __future__ import annotations

import io
import json
import math
import struct
import time
import urllib.parse
import urllib.request
import wave


class TTS:
    def synth(self, text: str, voice: dict) -> bytes:
        raise NotImplementedError

    def credits(self, voices: dict) -> list[str]:
        return []


class VoicevoxTTS(TTS):
    """VOICEVOX ENGINE (https://voicevox.hiroshiba.jp/) over HTTP.

    Voices are given by character name + style name and resolved via /speakers,
    so speaker IDs never need to be hard-coded."""

    def __init__(self, url: str = "http://localhost:50021", speed_scale: float = 1.0):
        self.url = url.rstrip("/")
        self.speed_scale = speed_scale
        self._ids: dict[tuple[str, str], int] | None = None

    def _get(self, path: str):
        with urllib.request.urlopen(self.url + path, timeout=60) as r:
            return json.load(r)

    def _post(self, path: str, params: dict, body: bytes | None = None, ctype="application/json") -> bytes:
        q = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{self.url}{path}?{q}", data=body or b"", method="POST",
                                     headers={"Content-Type": ctype})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    return r.read()
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        raise AssertionError

    def wait_ready(self, timeout: float = 180) -> None:
        deadline = time.time() + timeout
        while True:
            try:
                self._get("/version")
                return
            except Exception:
                if time.time() > deadline:
                    raise
                time.sleep(2)

    def speaker_id(self, voice: dict) -> int:
        if self._ids is None:
            self._ids = {(s["name"], st["name"]): st["id"] for s in self._get("/speakers") for st in s["styles"]}
        key = (voice["speaker"], voice.get("style", "ノーマル"))
        if key not in self._ids:
            raise KeyError(f"VOICEVOX voice not found: {key}")
        return self._ids[key]

    def synth(self, text: str, voice: dict) -> bytes:
        sid = self.speaker_id(voice)
        query = json.loads(self._post("/audio_query", {"text": text, "speaker": sid}))
        query["speedScale"] = self.speed_scale
        query["outputStereo"] = False
        query["prePhonemeLength"] = 0.05
        query["postPhonemeLength"] = 0.05
        return self._post("/synthesis", {"speaker": sid}, json.dumps(query).encode())

    def credits(self, voices: dict) -> list[str]:
        names = list(dict.fromkeys(v["speaker"] for v in voices.values()))
        return [f"VOICEVOX:{n}" for n in names]


class DummyTTS(TTS):
    """Offline stand-in for tests: a short tone whose length scales with the text."""

    def synth(self, text: str, voice: dict) -> bytes:
        rate = 24000
        n = int(rate * min(0.02 * len(text), 2.0))
        freq = 220 + (hash(voice.get("speaker", "")) % 200)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n)))
        return buf.getvalue()

    def credits(self, voices: dict) -> list[str]:
        return ["dummy"]


def make_tts(tts_cfg: dict, provider: str | None = None, url: str | None = None) -> TTS:
    provider = provider or tts_cfg.get("provider", "voicevox")
    if provider == "voicevox":
        t = VoicevoxTTS(url or "http://localhost:50021", float(tts_cfg.get("speed_scale", 1.0)))
        t.wait_ready()
        return t
    if provider == "dummy":
        return DummyTTS()
    raise ValueError(f"unknown TTS provider: {provider}")
