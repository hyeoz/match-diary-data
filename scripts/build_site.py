#!/usr/bin/env python3
"""Build the minimal GitHub Pages artifact."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

if SITE.exists():
    shutil.rmtree(SITE)
SITE.mkdir()
shutil.copy2(ROOT / "latest.json", SITE / "latest.json")
shutil.copytree(ROOT / "schedules", SITE / "schedules")
shutil.copy2(ROOT / ".nojekyll", SITE / ".nojekyll")
(SITE / "index.html").write_text(
    "<!doctype html><meta charset=\"utf-8\"><title>Match Diary Data</title>"
    "<h1>Match Diary KBO Schedule Data</h1><p><a href=\"latest.json\">latest.json</a></p>\n",
    encoding="utf-8",
)

