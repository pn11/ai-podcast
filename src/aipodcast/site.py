"""Static HTML pages for GitHub Pages."""
from __future__ import annotations

import json
import shutil
from html import escape
from pathlib import Path

from .feed import _dt, _hms, audio_url, build_feed, chapters_json, show_notes
from .model import ROOT, Episode

_STYLE_HREF = "style.css"


def _page(title: str, body: str, depth: int, podcast: dict) -> str:
    up = "../" * depth
    return f"""<!doctype html>
<html lang="{podcast['language']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{'<meta name="robots" content="noindex, nofollow">' + chr(10) if podcast.get("noindex") else ""}<title>{escape(title)}</title>
<link rel="alternate" type="application/rss+xml" title="{escape(podcast['title'])}" href="{up}feed.xml">
<link rel="icon" href="{up}artwork.png">
<link rel="stylesheet" href="{up}{_STYLE_HREF}">
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""


def _notes_html(text: str) -> str:
    out = []
    for para in text.split("\n\n"):
        lines = [escape(l) for l in para.splitlines()]
        lines = [l if "http" not in l else _linkify(l) for l in lines]
        out.append("<p>" + "<br>".join(lines) + "</p>")
    return "\n".join(out)


def _linkify(line: str) -> str:
    import re
    return re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', line)


def build_site(podcast: dict, episodes: list[Episode], audio: dict[int, dict], out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for f in (ROOT / "site").iterdir():
        shutil.copy(f, out / f.name)
    (out / ".nojekyll").write_text("")
    if podcast.get("noindex"):
        # 注意: プロジェクトサイト（<user>.github.io/<repo>/）では、クローラーが読むのはホスト直下の
        # /robots.txt だけなので、このファイル単体では効かない。各ページの meta robots が本命。
        (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    (out / "feed.xml").write_text(build_feed(podcast, episodes, audio), encoding="utf-8")

    published = sorted((e for e in episodes if e.number in audio),
                       key=lambda e: _dt(e.meta["published_at"]), reverse=True)
    feed_url = podcast["site_url"].rstrip("/") + "/feed.xml"

    cards = []
    for ep in published:
        info = audio[ep.number]
        date = _dt(ep.meta["published_at"]).strftime("%Y-%m-%d")
        cards.append(f"""<article class="ep">
  <p class="meta">#{ep.number} · {date} · {_hms(info['duration_sec'])}</p>
  <h2><a href="episodes/{ep.code}/">{escape(ep.meta['title'])}</a></h2>
  <p>{escape(ep.meta['summary'].strip())}</p>
  <audio controls preload="none" src="{escape(audio_url(podcast, ep))}"></audio>
</article>""")
    index = f"""<header class="hero">
  <img src="artwork.png" alt="" width="160" height="160">
  <div>
    <h1>{escape(podcast['title'])}</h1>
    <p>{escape(podcast['description'])}</p>
    <p class="subscribe">購読: ポッドキャストアプリに RSS の URL を登録してください<br>
      <input readonly value="{escape(feed_url)}" onclick="this.select()" aria-label="RSS フィード URL">
      <a href="feed.xml">RSS</a></p>
  </div>
</header>
{''.join(cards) or '<p>まだエピソードはありません。</p>'}"""
    (out / "index.html").write_text(_page(podcast["title"], index, 0, podcast), encoding="utf-8")

    for ep in published:
        info = audio[ep.number]
        transcript = "\n".join(
            f'<p class="line"><span class="who">{escape(l.speaker)}</span>{escape(l.text)}</p>' for l in ep.lines)
        if not ep.lines:
            transcript_section = ""
        elif ep.audio_source:
            transcript_section = f'<h2>参考：台本メモ</h2>\n<p class="meta">音声はこの台本を読み上げたものではありません。</p>\n<div class="transcript">\n{transcript}\n</div>'
        else:
            transcript_section = f'<h2>文字起こし（台本）</h2>\n<div class="transcript">\n{transcript}\n</div>'
        body = f"""<p><a href="../../">← {escape(podcast['title'])}</a></p>
<h1>#{ep.number} {escape(ep.meta['title'])}</h1>
<audio controls preload="none" src="{escape(audio_url(podcast, ep))}"></audio>
{_notes_html(show_notes(podcast, ep, info))}
{transcript_section}"""
        d = out / "episodes" / ep.code
        d.mkdir(parents=True)
        if info.get("chapters"):
            (d / "chapters.json").write_text(json.dumps(chapters_json(ep, info), ensure_ascii=False, indent=1),
                                             encoding="utf-8")
        (d / "index.html").write_text(_page(ep.meta["title"], body, 2, podcast), encoding="utf-8")
