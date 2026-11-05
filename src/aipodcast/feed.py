"""RSS 2.0 + iTunes/podcast namespace feed."""
from __future__ import annotations

from datetime import datetime
from email.utils import format_datetime
from xml.sax.saxutils import escape, quoteattr

from .model import Episode


def _dt(value) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def _hms(sec: int) -> str:
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def audio_url(podcast: dict, ep: Episode) -> str:
    return f"{podcast['audio_base_url'].rstrip('/')}/{ep.tag}/{ep.code}.mp3"


def page_url(podcast: dict, ep: Episode) -> str:
    return f"{podcast['site_url'].rstrip('/')}/episodes/{ep.code}/"


def show_notes(podcast: dict, ep: Episode, info: dict) -> str:
    """Plain-text-ish description used in the feed and on the episode page."""
    parts = [ep.meta["summary"].strip(), "", "紹介した論文:"]
    for p in ep.meta.get("papers", []):
        authors = f" ({p['authors']})" if p.get("authors") else ""
        parts.append(f"・{p['title']}{authors} {p['url']}")
    parts += ["", "台本は AI が生成したものです。誤りを含む可能性があるため、正確な内容は原論文をご確認ください。"]
    if info.get("credits"):
        parts.append("音声: " + "、".join(info["credits"]))
    return "\n".join(parts)


def build_feed(podcast: dict, episodes: list[Episode], audio: dict[int, dict]) -> str:
    site = podcast["site_url"].rstrip("/") + "/"
    published = [e for e in episodes if e.number in audio]
    published.sort(key=lambda e: _dt(e.meta["published_at"]), reverse=True)
    last = format_datetime(_dt(published[0].meta["published_at"])) if published else None

    cats = []
    for c in podcast.get("categories", []):
        c = c if isinstance(c, list) else [c]
        inner = "".join(f"<itunes:category text={quoteattr(s)}/>" for s in c[1:])
        cats.append(f"    <itunes:category text={quoteattr(c[0])}>{inner}</itunes:category>")

    items = []
    for ep in published:
        info = audio[ep.number]
        notes = show_notes(podcast, ep, info)
        page = page_url(podcast, ep)
        transcript = ("" if ep.audio_source else
                      f'      <podcast:transcript url={quoteattr(page)} type="text/html" language="{podcast["language"]}"/>\n')
        html_notes = "<p>" + escape(notes).replace("\n\n", "</p><p>").replace("\n", "<br/>") + "</p>"
        items.append(f"""    <item>
      <title>{escape(ep.meta['title'])}</title>
      <guid isPermaLink="false">{escape(ep.meta['guid'])}</guid>
      <link>{escape(page)}</link>
      <pubDate>{format_datetime(_dt(ep.meta['published_at']))}</pubDate>
      <description>{escape(notes)}</description>
      <content:encoded><![CDATA[{html_notes}]]></content:encoded>
      <enclosure url={quoteattr(audio_url(podcast, ep))} length="{info['bytes']}" type="audio/mpeg"/>
      <itunes:duration>{_hms(info['duration_sec'])}</itunes:duration>
      <itunes:episode>{ep.number}</itunes:episode>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:explicit>{'true' if podcast.get('explicit') else 'false'}</itunes:explicit>
{transcript}    </item>""")

    block = "\n    <itunes:block>Yes</itunes:block>" if podcast.get("block") else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:podcast="https://podcastindex.org/namespace/1.0"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(podcast['title'])}</title>
    <link>{escape(site)}</link>
    <atom:link href={quoteattr(site + 'feed.xml')} rel="self" type="application/rss+xml"/>
    <description>{escape(podcast['description'])}</description>
    <language>{podcast['language']}</language>
    <copyright>{escape(podcast.get('copyright', ''))}</copyright>
    {f'<lastBuildDate>{last}</lastBuildDate>' if last else ''}
    <generator>aipodcast</generator>
    <image><url>{escape(site + 'artwork.png')}</url><title>{escape(podcast['title'])}</title><link>{escape(site)}</link></image>
    <itunes:image href={quoteattr(site + 'artwork.png')}/>
    <itunes:author>{escape(podcast['author'])}</itunes:author>
    <itunes:subtitle>{escape(podcast.get('subtitle', ''))}</itunes:subtitle>
    <itunes:summary>{escape(podcast['description'])}</itunes:summary>
    <itunes:explicit>{'true' if podcast.get('explicit') else 'false'}</itunes:explicit>
    <itunes:type>episodic</itunes:type>{block}
{chr(10).join(cats)}
{chr(10).join(items)}
  </channel>
</rss>
"""
