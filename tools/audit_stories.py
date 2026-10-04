"""Compact reference audit for the ready-made stories (data/story_*.json).

Checks, per story: scene/step counts, choices, speakers and `characters[].id` that are not in the
cast, emotions outside the known set, backgrounds with no image file under game/. A missing
asset is reported, never papered over. Output is small on purpose (one line per finding group).

    python3 tools/audit_stories.py [--strict]
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "game"))
import story_external  # noqa: E402

EMOTIONS = {"neutral", "happy", "sad", "angry", "surprised", "embarrassed", "afraid", "thinking",
            "smile", "serious", "worried", "excited", "tired", "calm"}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def image_stems():
    stems = set()
    for base, dirs, files in os.walk(os.path.join(ROOT, "game")):
        dirs[:] = [d for d in dirs if d not in ("cache", "__pycache__", "saves")]
        for name in files:
            if name.lower().endswith(IMAGE_EXT):
                stems.add(os.path.splitext(name)[0].lower())
    return stems


def audit(path, stems):
    story = story_external.load_story(path)
    if not story:
        return ["UNUSABLE: %s" % path], 1
    world, steps = story["world"], story["steps"]
    cast = {c["id"] for c in world["characters"]} | {"player", "narrator"}
    locs = set(world["locations"])
    speakers, emotions, bgs, music = set(), set(), set(), set()
    for st in steps:
        if st.get("speaker"):
            speakers.add(str(st["speaker"]))
        for c in st.get("characters") or []:
            if isinstance(c, dict) and c.get("id"):
                speakers.add(str(c["id"]))
                if c.get("emotion"):
                    emotions.add(str(c["emotion"]))
        if st.get("emotion"):
            emotions.add(str(st["emotion"]))
        if st.get("background"):
            bgs.add(str(st["background"]))
        if st.get("music_intent"):
            music.add(str(st["music_intent"]))
    out, bad = [], 0
    out.append("steps=%d choices=%d cast=%d locations=%d issues=%d" % (
        len(steps), sum(1 for s in steps if s.get("choices")), len(world["characters"]),
        len(locs), len(story["issues"])))
    unknown = sorted(speakers - cast)
    if unknown:
        bad += 1
        out.append("speakers not in cast: " + ", ".join(unknown))
    odd = sorted(emotions - EMOTIONS)
    if odd:
        out.append("emotions outside the usual set: " + ", ".join(odd))
    nofile = sorted(b for b in bgs if b.lower() not in stems)
    if nofile:
        out.append("backgrounds with no image (placeholder will show): " + ", ".join(nofile))
    out.append("music intents: " + (", ".join(sorted(music)) or "none"))
    return out, bad


def main():
    strict = "--strict" in sys.argv
    stems = image_stems()
    total = 0
    for name, path in sorted(story_external.story_files(os.path.join(ROOT, "game")).items()):
        lines, bad = audit(path, stems)
        print("== story_%s" % name)
        for line in lines:
            print("  " + line)
        total += bad
    return 1 if (strict and total) else 0


if __name__ == "__main__":
    sys.exit(main())
