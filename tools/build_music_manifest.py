#!/usr/bin/env python3
"""Build a dependency-light music catalog for Living VN.

The script only uses the Python standard library. It does not decode compressed
formats; instead it records path/name metadata and derives conservative tags
from filenames/directories. Later agents can plug in richer audio analysis.
"""
import json
import os
import sys

KEYWORDS = {
    "calm": ("calm", "quiet", "ambient", "peace", "morning", "night"),
    "romance": ("love", "romance", "date", "heart", "sweet"),
    "nostalgia": ("nostalgia", "summer", "memory", "old", "retro"),
    "tension": ("tension", "danger", "chase", "urgent", "battle", "fight"),
    "mystery": ("mystery", "secret", "clue", "strange", "investigation"),
    "sad": ("sad", "sorrow", "tear", "lonely", "melancholy", "goodbye"),
    "comedy": ("fun", "funny", "comedy", "comic", "school", "daily"),
    "horror": ("horror", "dark", "fear", "creepy", "nightmare"),
    "triumph": ("victory", "triumph", "finale", "win", "hero"),
}
EXT = {".ogg", ".opus", ".mp3", ".wav"}


def tags(text):
    low = text.lower()
    found = []
    for tag, words in KEYWORDS.items():
        if any(word in low for word in words):
            found.append(tag)
    return found or ["calm"]


def scan(root):
    result = []
    for base, _dirs, files in os.walk(root):
        for fn in files:
            if os.path.splitext(fn)[1].lower() not in EXT:
                continue
            path = os.path.abspath(os.path.join(base, fn))
            result.append({
                "path": path,
                "name": fn,
                "tags": tags(path),
                "source": "external",
            })
    return result


def main(argv):
    if len(argv) < 2:
        print("usage: build_music_manifest.py OUTPUT.json FOLDER [FOLDER ...]")
        return 2
    output = argv[0]
    entries = []
    for root in argv[1:]:
        if os.path.isdir(root):
            entries.extend(scan(root))
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=2)
    print(f"wrote {len(entries)} tracks to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
