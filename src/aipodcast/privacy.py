"""Pre-publish checks: everything committed here is public."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .model import ROOT

PATTERNS = {
    "email address": re.compile(r"[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "API key-like string": re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})\b"),
    "local file path": re.compile(r"(/Users/[^/\s]+|/home/[^/\s]+|[A-Za-z]:\\Users\\)"),
    "phone number": re.compile(r"\b0\d{1,4}-\d{1,4}-\d{3,4}\b"),
}
SCAN_GLOBS = ["podcast.yaml", "episodes/**/*.md", "episodes/**/*.yaml", "queue/**/*"]
ALLOW = {"noreply@anthropic.com"}


def check(root: Path = ROOT) -> list[str]:
    problems = []
    deny = []
    denyfile = root / "denylist.txt"  # local only (gitignored): your name, affiliation, etc.
    if denyfile.exists():
        deny = [w.strip() for w in denyfile.read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")]
    files = sorted({p for g in SCAN_GLOBS for p in root.glob(g) if p.is_file()})
    for path in files:
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for label, pat in PATTERNS.items():
                for m in pat.finditer(line):
                    if m.group(0) not in ALLOW:
                        problems.append(f"{path.relative_to(root)}:{n}: {label}: {m.group(0)}")
            for w in deny:
                if w in line:
                    problems.append(f"{path.relative_to(root)}:{n}: denylisted word")
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.split()
        for f in tracked:
            if f.lower().endswith((".pdf", ".wav")) or f.startswith("private/") or f in (".env", "denylist.txt"):
                problems.append(f"{f}: must not be committed")
    except (OSError, subprocess.CalledProcessError):
        pass
    return problems
