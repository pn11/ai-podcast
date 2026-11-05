"""Load podcast / episode metadata and parse scripts."""
from __future__ import annotations

import hashlib
import os
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Repository root: run commands from the repo, or set AIPODCAST_ROOT.
ROOT = Path(os.environ.get("AIPODCAST_ROOT", os.getcwd())).resolve()


@dataclass
class Line:
    speaker: str
    text: str


@dataclass
class Episode:
    dir: Path
    meta: dict
    lines: list[Line] = field(default_factory=list)

    @property
    def number(self) -> int:
        return int(self.meta["number"])

    @property
    def code(self) -> str:
        return f"{self.number:04d}"

    @property
    def tag(self) -> str:
        return f"ep-{self.code}"

    @property
    def slug(self) -> str:
        return self.dir.name


def load_podcast(root: Path = ROOT) -> dict:
    return yaml.safe_load((root / "podcast.yaml").read_text(encoding="utf-8"))


_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_LINE = re.compile(r"^\s*([^\s:：]+)\s*[:：]\s*(\S.*)$")


def parse_script(text: str, speakers: set[str]) -> list[Line]:
    """Return spoken lines. Only `<speaker>: text` lines for known speakers are read;
    headings, cast lists, and other notes are ignored."""
    text = _FRONT_MATTER.sub("", text, count=1)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines = []
    for raw in text.splitlines():
        m = _LINE.match(raw)
        if m and m.group(1) in speakers:
            lines.append(Line(m.group(1), m.group(2).strip()))
    return lines


def load_episodes(podcast: dict, root: Path = ROOT) -> list[Episode]:
    speakers = set(podcast["tts"]["voices"])
    eps = []
    for meta_path in sorted((root / "episodes").glob("*/episode.yaml")):
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        script = (meta_path.parent / "script.md").read_text(encoding="utf-8")
        lines = parse_script(script, speakers)
        if not lines:
            raise ValueError(f"{meta_path.parent}: no spoken lines found in script.md")
        intro = podcast.get("intro")
        if intro:
            lines.insert(0, Line(intro["speaker"], intro["text"]))
        eps.append(Episode(meta_path.parent, meta, lines))
    numbers = [e.number for e in eps]
    if len(numbers) != len(set(numbers)):
        raise ValueError(f"duplicate episode numbers: {numbers}")
    guids = [e.meta["guid"] for e in eps]
    if len(guids) != len(set(guids)):
        raise ValueError("duplicate episode guids")
    return sorted(eps, key=lambda e: e.number)


def audio_fingerprint(ep: Episode, tts: dict) -> str:
    """Hash of everything that affects the audio. Unchanged hash → reuse published MP3."""
    payload = {
        "lines": [[l.speaker, l.text] for l in ep.lines],
        "tts": tts,
        "title": ep.meta["title"],
        "number": ep.number,
        "v": 1,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
