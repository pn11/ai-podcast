"""Assemble synthesized speech into a podcast MP3."""
from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import tempfile
import wave
from pathlib import Path

from .model import Episode, audio_fingerprint
from .tts import TTS

_SENT = re.compile(r"(?<=[。！？!?])")
MAX_CHARS = 120


def split_sentences(text: str) -> list[str]:
    out = []
    for s in (p.strip() for p in _SENT.split(text)):
        while len(s) > MAX_CHARS:  # very long sentence: break at a comma near the limit
            cut = s.rfind("、", 0, MAX_CHARS)
            cut = cut + 1 if cut > 0 else MAX_CHARS
            out.append(s[:cut])
            s = s[cut:].strip()
        if s:
            out.append(s)
    return out


def _read_wav(data: bytes) -> tuple[tuple, bytes]:
    with wave.open(io.BytesIO(data)) as w:
        return (w.getnchannels(), w.getsampwidth(), w.getframerate()), w.readframes(w.getnframes())


def render_episode(ep: Episode, podcast: dict, tts: TTS, out_dir: Path, log=print) -> dict:
    cfg = podcast["tts"]
    voices = cfg["voices"]
    pause_s = cfg.get("pause_sentence_ms", 250) / 1000
    pause_t = cfg.get("pause_turn_ms", 500) / 1000

    params = None
    frames: list[bytes] = []
    total = sum(len(split_sentences(l.text)) for l in ep.lines)
    done = 0
    prev = None
    for line in ep.lines:
        for i, sent in enumerate(split_sentences(line.text)):
            p, pcm = _read_wav(tts.synth(sent, voices[line.speaker]))
            if params is None:
                params = p
            elif p != params:
                raise ValueError(f"inconsistent WAV format {p} != {params}")
            if prev is not None:
                gap = pause_t if i == 0 else pause_s  # new turn vs. next sentence
                frames.append(b"\0" * (int(params[2] * gap) * params[0] * params[1]))
            frames.append(pcm)
            prev = line.speaker
            done += 1
            if done % 25 == 0 or done == total:
                log(f"  [{ep.code}] {done}/{total} sentences")

    out_dir.mkdir(parents=True, exist_ok=True)
    mp3 = out_dir / f"{ep.code}.mp3"
    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "full.wav"
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(params[0])
            w.setsampwidth(params[1])
            w.setframerate(params[2])
            w.writeframes(b"".join(frames))
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_path),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-ac", "1",
            "-c:a", "libmp3lame", "-b:a", "64k",
            # drop all inherited metadata, then set only what we choose to publish
            "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact",
            "-id3v2_version", "3", "-write_xing", "1",
            "-metadata", f"title={ep.meta['title']}",
            "-metadata", f"artist={podcast['author']}",
            "-metadata", f"album={podcast['title']}",
            "-metadata", f"track={ep.number}",
            "-metadata", "genre=Podcast",
            str(mp3),
        ], check=True)

    info = {
        "number": ep.number,
        "fingerprint": audio_fingerprint(ep, cfg),
        "bytes": mp3.stat().st_size,
        "duration_sec": probe_duration(mp3),
        "sha256": hashlib.sha256(mp3.read_bytes()).hexdigest(),
        "credits": tts.credits(voices),
    }
    (out_dir / f"{ep.code}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


def probe_duration(path: Path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], check=True, capture_output=True, text=True)
    return round(float(out.stdout.strip()))
