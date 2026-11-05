import json
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from aipodcast.audio import split_sentences
from aipodcast.model import parse_script

ROOT = Path(__file__).resolve().parents[1]


def test_parse_script_reads_only_speaker_lines():
    text = "---\nx: 1\n---\n# タイトル\n出演：ミナ（聞き手）\n\nミナ: こんにちは。\nケン：どうも。\n<!-- メモ: 読まない -->\n知らない: 無視\n"
    lines = parse_script(text, {"ミナ", "ケン"})
    assert [(l.speaker, l.text) for l in lines] == [("ミナ", "こんにちは。"), ("ケン", "どうも。")]


def test_split_sentences():
    assert split_sentences("はい。そうです！本当？") == ["はい。", "そうです！", "本当？"]
    long = "あ" * 100 + "、" + "い" * 100 + "。"
    parts = split_sentences(long)
    assert len(parts) == 2 and all(len(p) <= 120 for p in parts)


@pytest.mark.skipif(subprocess.run(["which", "ffmpeg"], capture_output=True).returncode, reason="ffmpeg missing")
def test_end_to_end_dummy(tmp_path):
    env = {**os.environ, "AIPODCAST_ROOT": str(ROOT)}
    run = lambda *a: subprocess.run(["python", "-m", "aipodcast.cli", *a], cwd=ROOT, env=env, check=True)
    run("check")
    audio, site = tmp_path / "audio", tmp_path / "site"
    run("audio", "--tts", "dummy", "--out", str(audio))
    run("audio", "--tts", "dummy", "--out", str(tmp_path / "audio2"), "--existing", str(audio))
    assert (tmp_path / "audio2" / "new.txt").read_text() == ""  # nothing re-synthesized
    run("site", "--audio", str(audio), "--out", str(site))
    rss = ET.parse(site / "feed.xml").getroot()
    items = rss.findall("./channel/item")
    assert len(items) == len(list((ROOT / "episodes").glob("*/episode.yaml")))
    for item in items:
        enc = item.find("enclosure")
        num = int(item.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}episode").text)
        info = json.loads((audio / f"{num:04d}.json").read_text())
        assert int(enc.get("length")) == (audio / f"{num:04d}.mp3").stat().st_size == info["bytes"]
        assert enc.get("url").endswith(f"/ep-{num:04d}/{num:04d}.mp3")
    assert (site / "index.html").exists() and (site / "artwork.png").exists()
