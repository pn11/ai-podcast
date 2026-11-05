"""aipodcast CLI.

  aipodcast check                       privacy / consistency checks
  aipodcast audio [--existing DIR]      synthesize MP3s that are new or changed
  aipodcast site  --audio DIR           build feed.xml + HTML into build/site
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .model import ROOT, audio_fingerprint, load_episodes, load_podcast


def cmd_check(args) -> int:
    from .privacy import check
    podcast = load_podcast()
    eps = load_episodes(podcast)
    for e in eps:
        for l in e.lines:
            if l.speaker not in podcast["tts"]["voices"]:
                print(f"{e.slug}: unknown speaker {l.speaker}")
                return 1
    problems = check()
    for p in problems:
        print("PRIVACY:", p)
    print(f"{len(eps)} episodes, {sum(len(e.lines) for e in eps)} lines, {len(problems)} problems")
    return 1 if problems else 0


def cmd_audio(args) -> int:
    from .audio import render_episode
    from .tts import make_tts
    podcast = load_podcast()
    eps = load_episodes(podcast)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    existing = Path(args.existing) if args.existing else None
    todo = []
    for ep in eps:
        prev = existing / f"{ep.code}.json" if existing else None
        if prev and prev.exists():
            info = json.loads(prev.read_text(encoding="utf-8"))
            if info.get("fingerprint") == audio_fingerprint(ep, podcast["tts"]) and not args.force:
                shutil.copy(prev, out / prev.name)
                print(f"[{ep.code}] unchanged, reusing published audio")
                continue
        todo.append(ep)
    (out / "new.txt").write_text("".join(f"{e.code}\n" for e in todo))
    if not todo:
        print("nothing to synthesize")
        return 0
    tts = make_tts(podcast["tts"], args.tts, args.tts_url)
    for ep in todo:
        print(f"[{ep.code}] synthesizing {ep.meta['title']}")
        info = render_episode(ep, podcast, tts, out)
        print(f"[{ep.code}] {info['duration_sec']}s, {info['bytes']} bytes")
    return 0


def cmd_site(args) -> int:
    from .site import build_site
    podcast = load_podcast()
    eps = load_episodes(podcast)
    audio = {}
    for ep in eps:
        f = Path(args.audio) / f"{ep.code}.json"
        if f.exists():
            audio[ep.number] = json.loads(f.read_text(encoding="utf-8"))
        else:
            print(f"[{ep.code}] no audio yet, skipped from feed")
    build_site(podcast, eps, audio, Path(args.out))
    print(f"site written to {args.out} ({len(audio)} episodes in feed)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aipodcast")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    a = sub.add_parser("audio")
    a.add_argument("--out", default=str(ROOT / "build" / "audio"))
    a.add_argument("--existing", help="dir with already-published NNNN.json files")
    a.add_argument("--tts", help="override provider (voicevox|dummy)")
    a.add_argument("--tts-url", help="TTS engine URL")
    a.add_argument("--force", action="store_true")
    a.set_defaults(fn=cmd_audio)
    s = sub.add_parser("site")
    s.add_argument("--audio", default=str(ROOT / "build" / "audio"))
    s.add_argument("--out", default=str(ROOT / "build" / "site"))
    s.set_defaults(fn=cmd_site)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
