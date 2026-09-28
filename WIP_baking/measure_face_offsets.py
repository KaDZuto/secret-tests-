#!/usr/bin/env python3
"""Measure where a face strip belongs on its body, and write it into the import config.

`import_layered_pack.py` refines the offset for every pose, but it starts from something: a
number in the config, or a hardcoded guess, searched in a 56px window. A body drawn at another
scale puts the face outside that window, the first pose lands in a local optimum, and every
pose after it inherits the mistake -- which is how a baked face ends up with a second pair of
eyes on the cheeks.

So the offset is measured here instead of guessed, in two stages. The coarse stage asks the
question on images shrunk eight times, where every position on the body can be tried in
seconds. The fine stage hands the winner to the importer's own `background_misses`, which
counts only the pixels outside the changing expression, because that count is exactly zero at
the true offset: the strip's unchanged face is the same artwork as the body's face. The fine
stage is the importer's function, not a re-implementation of it, so both agree by
construction.

    python3 tools/measure_face_offsets.py --config tools/face_sets/klein.json \\
        --draft tools/face_sets/klein.draft.json --source "/path/to/Characters - Klein"
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_layered_pack import (  # noqa: E402
    background_misses, classify, find_offset, image_size, load_rgba, pose_key, set_key,
    varying_mask,
)
from measure_face_strips import discover_poses  # noqa: E402

## The coarse stage walks the whole body in steps of this many pixels, the fine stage then
## takes every neighbouring position. A cheap stage on shrunken images was tried first and is
## wrong: shrinking averages the face into the same flat tone as an empty corner, and the
## corner then matches better than the face. At full size with the expression masked out, the
## face is the only place the layer's unchanged artwork can land.
COARSE_STEP = 8
FINE_STEP = 1
FINE_RADIUS = 10
## How far to keep looking for the exact position when the local search did not find it. At the
## true offset the count of mismatching background pixels is zero, so anything above zero
## means the search stopped short.
POLISH_RADIUS = 28


def slice_frames(strip, spec, width, height):
    """The frames the config names, as raw RGBA, so the mask describes the pack's own
    expressions rather than every frame the strip happens to carry."""
    frames = []
    for index in sorted(set(spec["frames"].values())):
        sliced = "/tmp/opencode/_slice.png"
        subprocess.run(["magick", strip, "-crop",
                        "%dx%d+%d+%d" % (width, height, spec["margin"][0],
                                        spec["margin"][1] + index * height),
                        "+repage", "-depth", "8", sliced],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        frames.append(load_rgba(sliced))
    return frames


def scan(base, base_w, base_h, layer, layer_w, layer_h, mask, step, radius=None, seed=None):
    """The position where the layer's unchanged face lands on the same face."""
    if radius is None:
        xs = range(0, max(1, base_w - layer_w + 1), step)
        ys = range(0, max(1, base_h - layer_h + 1), step)
    else:
        xs = range(max(0, seed[0] - radius), min(base_w - layer_w, seed[0] + radius) + 1, step)
        ys = range(max(0, seed[1] - radius), min(base_h - layer_h, seed[1] + radius) + 1, step)
    best = None
    for dy in ys:
        for dx in xs:
            value = background_misses(base, base_w, layer, layer_w, layer_h, mask, dx, dy)
            if best is None or value < best[0]:
                best = (value, dx, dy)
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, help="the config to add offsets to")
    parser.add_argument("--draft", required=True, help="the measured draft it was built from")
    parser.add_argument("--source", required=True, help="the character's sprite folder")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as handle:
        config = json.load(handle)
    with open(args.draft, encoding="utf-8") as handle:
        draft = json.load(handle)

    discovered = discover_poses(args.source)
    sample_of = {}
    for pose, found in discovered.items():
        sample_of.setdefault(set_key(found), found)

    for key in sorted(config):
        spec_draft = draft.get(key) or {}
        sample = sample_of.get(key)
        if not sample:
            print("WARN: %s has no pose in %s" % (key, args.source))
            continue
        for part in ("eyes", "mouth"):
            spec = config[key].get(part)
            strip = sample.get(part)
            if not spec or not strip:
                continue
            width, height = spec["frame"]
            frames = slice_frames(strip, spec, width, height)
            layer = frames[0]
            mask = varying_mask(frames, width, height)
            base = load_rgba(sample["base"])
            base_w, base_h = image_size(sample["base"])
            coarse = scan(base, base_w, base_h, layer, width, height, mask, COARSE_STEP)
            if coarse is None:
                print("WARN: %s/%s: no position on the body" % (key, part))
                continue
            fine = scan(base, base_w, base_h, layer, width, height, mask, FINE_STEP,
                        radius=FINE_RADIUS, seed=(coarse[1], coarse[2]))
            # The coarse step can leave the winner a few pixels off, and a position a few
            # pixels off still scores well: the count is small but not zero, and a baked face
            # a few pixels off shows as a seam. The true position scores exactly zero, so a
            # wider local search is worth running whenever the count is not zero.
            if fine[0] > 0:
                polished = scan(base, base_w, base_h, layer, width, height, mask, FINE_STEP,
                                radius=POLISH_RADIUS, seed=(fine[1], fine[2]))
                if polished[0] < fine[0]:
                    fine = polished
            spec["offset"] = [fine[1], fine[2]]
            spec["misses"] = fine[0]
            print("%-12s %-6s грубо=(%d,%d,%d) -> offset=[%d, %d]  промахов=%d"
                  % (key, part, coarse[1], coarse[2], coarse[0], fine[1], fine[2], fine[0]))
        if config[key].get("eyes", {}).get("misses") or config[key].get("mouth", {}).get("misses"):
            config[key]["geometry"] = "measured"

    with open(args.config, "w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=1)
    print("offsets -> %s" % args.config)


if __name__ == "__main__":
    main()
