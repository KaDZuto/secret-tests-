#!/usr/bin/env python3
"""Bake layered character sprites from Doki Doki Literature Club.

Source format (per character):
    {N}l.png / {N}r.png     left/right halves of a body pose
    {N}bl.png / {N}br.png   left/right halves of the casual-outfit pose
    {letter}.png            head with an expression
    {other}.png             complete pre-baked sprites

Baking composites body halves + head for every valid combination and copies
complete sprites as-is. Glitch art and horror overlays are excluded.

ImageMagick note: layers must be composited with parenthesized operands,
the flat form `magick A B C -composite` zeroes the RGB of top layers.

    python3 tools/bake_ddlc.py
"""

import json
import os
import re
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DDLC_DIR = os.path.join(
    REPO, "game", "absorbed", "Doki_Doki_Literature_Club", "character_art"
)

EXCLUDE = {
    # glitch art
    "g1", "g2", "g3", "g4",
    "glitch1", "glitch2", "glitch3", "glitch4", "glitch5",
    "end-glitch1", "end-glitch2",
    "4_wipe", "za", "zb", "zc", "zd",
    # horror overlays and detached parts
    "eye", "mouth", "blackeyes", "ghost1", "ghost2", "ghost3",
    "ghost_blood", "vomit", "noface1", "noface1b", "noface2",
    "eyes1", "eyes2", "oneeye2", "6-eyes", "6-mask",
    # blank and corrupted faces
    "0a", "0b",
}

# Full-canvas files that are actually headless bodies and need heads.
FORCE_BODIES = {"yuri": {"3", "3b"}}

BODY_PAIR_RE = re.compile(r"^(\d+[a-z]?)l$")
TRIM_RE = re.compile(r"(\d+)x(\d+)\++(-?\d+)\++(-?\d+)")


def list_names(char_dir):
    return sorted(f[:-4] for f in os.listdir(char_dir) if f.endswith(".png"))


def trim(path):
    out = subprocess.run(
        ["magick", path, "-trim", "-format", "%wx%h+%X+%Y", "info:"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    m = TRIM_RE.match(out)
    if not m:
        raise ValueError(f"cannot parse trim of {path}: {out}")
    return tuple(int(g) for g in m.groups())


def composite(paths, out_path):
    cmd = ["magick", paths[0]]
    for p in paths[1:]:
        cmd += ["(", p, "+repage", ")", "-composite"]
    cmd += ["-depth", "8", out_path]
    subprocess.run(cmd, check=True)


def natsuki_head_group(head):
    """Map a Natsuki head to the body pose it belongs to."""
    if re.fullmatch(r"2bt[a-i]?", head):
        return "2b"
    if re.fullmatch(r"2t[a-i]?", head):
        return "2"
    return "1"


def natsuki_body_group(stem, is_torso=False):
    if is_torso or stem in ("1", "1b"):
        return "1"
    return stem


def classify(char_dir, char_id):
    names = [n for n in list_names(char_dir) if n not in EXCLUDE]
    name_set = set(names)

    bodies = {}
    heads = []
    completes = []
    torsos = []

    for n in names:
        m = BODY_PAIR_RE.match(n)
        if m and (m.group(1) + "r") in name_set:
            bodies[m.group(1)] = (n + ".png", m.group(1) + "r.png")
            continue
        if re.fullmatch(r"\d+[a-z]?r", n):
            continue

        w, h, x, y = trim(os.path.join(char_dir, n + ".png"))
        if y < 250 and h >= 700 and n not in FORCE_BODIES.get(char_id, ()):
            completes.append(n)
        elif y < 250 and n not in FORCE_BODIES.get(char_id, ()):
            heads.append(n)
        else:
            torsos.append(n)

    return bodies, heads, completes, torsos


def bake_character(char_id, char_dir):
    bodies, heads, completes, torsos = classify(char_dir, char_id)
    if not (bodies or completes or torsos):
        print(f"  {char_id}: no layers found")
        return None

    out_base = os.path.join(char_dir, "base")
    os.makedirs(out_base, exist_ok=True)

    states = {}

    for stem, (l_name, r_name) in sorted(bodies.items()):
        group = natsuki_body_group(stem)
        for head in heads:
            if char_id == "natsuki" and natsuki_head_group(head) != group:
                continue
            key = f"pose_{stem}_{head}"
            composite(
                [os.path.join(char_dir, n) for n in (l_name, r_name, head + ".png")],
                os.path.join(out_base, key + ".png"),
            )
            states[key] = f"base/{key}.png"

    for torso in torsos:
        for head in heads:
            if char_id == "natsuki" and natsuki_head_group(head) != "1":
                continue
            key = f"torso_{torso}_{head}"
            composite(
                [os.path.join(char_dir, n) for n in (torso + ".png", head + ".png")],
                os.path.join(out_base, key + ".png"),
            )
            states[key] = f"base/{key}.png"

    for c in completes:
        out_name = f"complete_{c}.png"
        shutil.copy2(os.path.join(char_dir, c + ".png"), os.path.join(out_base, out_name))
        states[f"complete_{c}"] = f"base/{out_name}"

    return states


def main():
    if not os.path.isdir(DDLC_DIR):
        sys.exit(f"Directory not found: {DDLC_DIR}")

    characters = sorted(
        d for d in os.listdir(DDLC_DIR)
        if os.path.isdir(os.path.join(DDLC_DIR, d)) and d != "poem_special"
    )

    for char_id in characters:
        char_dir = os.path.join(DDLC_DIR, char_id)
        print(f"Processing {char_id}...")

        states = bake_character(char_id, char_dir)
        if states is None:
            continue

        manifest = {
            "id": char_id,
            "name": char_id.capitalize(),
            "source": "Doki Doki Literature Club",
            "pack": "Doki_Doki_Literature_Club",
            "third_party": True,
            "redistributable": False,
            "visual": {"type": "sprite", "states": states},
            "states": states,
        }

        with open(os.path.join(char_dir, "character.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
            f.write("\n")

        print(f"  {char_id}: {len(states)} states")

    print("Done.")


if __name__ == "__main__":
    main()
