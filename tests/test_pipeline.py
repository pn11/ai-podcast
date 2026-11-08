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


def test_parse_script_chapters():
    text = "# 番組タイトル（h1 はチャプターにしない）\n## 前半\nミナ: あ。\nケン: い。\n## 後半\n\nケン: う。\n"
    lines = parse_script(text, {"ミナ", "ケン"})
    assert [l.chapter for l in lines] == ["前半", None, "後半"]


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
    assert 'name="robots" content="noindex' in (site / "index.html").read_text()
    assert 'name="robots" content="noindex' in (site / "episodes" / "0001" / "index.html").read_text()
    assert (site / "robots.txt").read_text().startswith("User-agent: *")
    # chapters: embedded in the MP3 (ID3 CHAP) and published as Podcasting 2.0 JSON
    chaps = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "json",
                                       str(audio / "0002.mp3")], capture_output=True, text=True).stdout)["chapters"]
    info = json.loads((audio / "0002.json").read_text())
    assert len(chaps) == len(info["chapters"]) > 1
    assert chaps[0]["tags"]["title"] == "オープニング" and float(chaps[0]["start_time"]) == 0
    assert [c["start"] for c in info["chapters"]] == sorted(c["start"] for c in info["chapters"])
    cj = json.loads((site / "episodes" / "0002" / "chapters.json").read_text())
    assert cj["chapters"][1]["title"] == "ACT / ALOHA"
    assert "podcast:chapters" in (site / "feed.xml").read_text()


@pytest.mark.skipif(subprocess.run(["which", "ffmpeg"], capture_output=True).returncode, reason="ffmpeg missing")
def test_supplied_audio(tmp_path):
    import shutil
    root = tmp_path / "repo"
    (root / "episodes" / "0009-byo").mkdir(parents=True)
    shutil.copy(ROOT / "podcast.yaml", root / "podcast.yaml")
    shutil.copytree(ROOT / "site", root / "site")
    ep = root / "episodes" / "0009-byo"
    (ep / "episode.yaml").write_text(
        "number: 9\nguid: test-guid-9\ntitle: 持ち込み音声\nsummary: テスト\n"
        "published_at: 2026-11-05T22:00:00+09:00\naudio_credit: NotebookLM で生成\n"
        "chapters: [{start: '0:00', title: 'A=1;#'}, {start: '0:01', title: 後半}]\n"
        "papers: [{title: X, url: https://arxiv.org/abs/0000.00000}]\n", encoding="utf-8")
    # a 2-second tone carrying metadata that must not survive re-encoding
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-metadata", "comment=PRIVATE-NOTE", "-c:a", "aac", str(ep / "audio.m4a")], check=True)
    env = {**os.environ, "AIPODCAST_ROOT": str(root)}
    run = lambda *a: subprocess.run(["python", "-m", "aipodcast.cli", *a], cwd=root, env=env, check=True)
    # no VOICEVOX needed: provider would fail to connect if it were used
    run("audio", "--out", str(root / "a"), "--tts-url", "http://127.0.0.1:9")
    info = json.loads((root / "a" / "0009.json").read_text())
    assert info["supplied"] and info["duration_sec"] == 2 and info["credits"] == ["NotebookLM で生成"]
    tags = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json",
                           str(root / "a" / "0009.mp3")], capture_output=True, text=True).stdout
    assert "PRIVATE-NOTE" not in tags and "持ち込み音声" in tags
    chaps = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "json",
                                       str(root / "a" / "0009.mp3")], capture_output=True, text=True).stdout)["chapters"]
    assert [c["tags"]["title"] for c in chaps] == ["A=1;#", "後半"]
    run("site", "--audio", str(root / "a"), "--out", str(root / "s"))
    feed = (root / "s" / "feed.xml").read_text()
    assert "podcast:transcript" not in feed and "NotebookLM で生成" in feed
