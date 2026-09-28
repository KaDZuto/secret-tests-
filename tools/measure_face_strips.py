#!/usr/bin/env python3
"""Measure the frame geometry of a layered character's face strips.

`import_layered_pack.py` composites the face into the body at import time and takes its
geometry from a config file, because that geometry is not written anywhere in the source:
the strip is a column of frames of an unknown height with an unknown top margin. Hand
measuring it per character is where the mistakes come from, so this measures it instead.

The frame height is found by the one signal these strips actually carry. The background of
a face strip is one solid block that is identical in every frame, and the expression is
the part that changes, so for a candidate height:

* rows that are the same in every frame are background, and they are the same rows for any
  multiple of the true height -- which is why "how many rows are stable" cannot pick the
  height, only confirm a candidate;
* the number of rows that DIFFER between frames, per row of the frame, is smallest for the
  true height. Split a frame in half and every frame starts showing the other half of an
  expression, so the differing rows explode; double it and two expressions sit in one
  frame, so the count grows with the height. Measured against the Asuna packs, whose
  geometry is known, this recovers 124/90 and 146/72 exactly.

The horizontal margin is not measured: it is set to zero with a frame as wide as the strip.
The known packs crop 0-16px off the side, and the offset search absorbs that, whereas a
guessed margin that is too large cuts the face off.

    python3 tools/measure_face_strips.py --source "/path/to/Characters - Klein" --out sets.json
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_layered_pack import classify, pose_key, set_key  # noqa: E402

MIN_PITCH = 40
MIN_FRAMES = 3
## How close to the best score a smaller period has to be to count as a tie rather than as a
## wrong answer. Measured on four strips whose frame is known, the true frame always scores
## within 0.0031 of the best and a half-frame always scores 0.010 to 0.016 below it, so 0.005
## sits in the gap between the two populations.
AGREEMENT_EPSILON = 0.005
MAX_PITCH = 260
MAX_FRAMES = 48

def image_size(path):
    out = subprocess.run(["magick", path, "-format", "%w %h", "info:"],
                         capture_output=True, text=True, check=True).stdout.split()
    return int(out[0]), int(out[1])


def load_rgba(path):
    return subprocess.run(["magick", path, "-depth", "8", "rgba:-"],
                          capture_output=True, check=True).stdout


def measure(strip):
    """`(frame_height, frame_count, margin_y, frame_width)` for one face strip."""
    width, height = image_size(strip)
    raw = load_rgba(strip)
    stride = width * 4

    def row(y):
        return raw[y * stride:(y + 1) * stride]

    margin_y = 0
    while margin_y < height and not any(row(margin_y)):
        margin_y += 1
    usable = height - margin_y
    if usable <= 0:
        raise SystemExit("Strip is blank: %s" % strip)
    rows = [row(margin_y + y) for y in range(usable)]

    # The strip is one drawing repeated: the face is there in every frame and only the
    # expression is redrawn, so the drawing's background is the row most frames share. Mark
    # every row that is not that background, and the frame height is the period of that
    # marked pattern: a row and the row one frame below it belong to the same part of the
    # drawing, while any other offset compares a lip against a cheek.
    #
    # Three earlier measures were tried and each was wrong in a way that looked right.
    # Comparing frames to each other doubles the frame wherever the expressions are strongly
    # drawn -- Agil's eyes came out as 6 frames of 250px, each holding two pairs of eyes.
    # Comparing rows under a shift picks that same double on a mouth strip, where the drawing
    # is mostly background and every multiple of the real period lines up equally well --
    # Heathcliff's mouth came out as 3 frames of 234px, each holding two mouths. Taking the
    # most common gap between expression bands collapses on a mouth as well, because a mouth
    # is two bands (upper and lower lip) and the gap between the lips can be the most common
    # one -- Asuna's mouth came out as 30 frames of 65px.
    #
    # Agreement between the pattern and a shift of one frame survives all three: it peaks at
    # the frame for eyes and for mouths alike. But a period is also a period of each of its
    # multiples, so several candidates tie: Asuna's eyes score 1.000 at both 124 and 248, and
    # Yui's mouth scores 0.846 at 198 and 0.843 at the 66 that the contact sheet shows is the
    # real frame. The tie is broken towards the smallest height, but only within a narrow
    # margin -- at 62 Asuna's eyes drop to 0.984, and that half-frame is a real wrong answer,
    # not a tie. So the frame is the smallest height within AGREEMENT_EPSILON of the best.
    background = _most_common(rows)
    active = [0 if r == background else 1 for r in rows]
    scored = []
    for period in range(MIN_PITCH, MAX_PITCH + 1):
        if usable % period:
            continue
        count = usable // period
        if count < MIN_FRAMES or count > MAX_FRAMES:
            continue
        agree = sum(1 for y in range(usable - period) if active[y] == active[y + period])
        scored.append((agree / float(usable - period), period, count))
    if not scored:
        raise SystemExit("No frame height divides %s (%dx%d usable)" % (strip, width, usable))
    best = max(score for score, _p, _c in scored)
    for score, period, count in sorted(scored, key=lambda item: item[1]):
        if score >= best - AGREEMENT_EPSILON:
            return period, count, margin_y, width
    return scored[0][1], scored[0][2], margin_y, width


def _most_common(rows):
    counts = {}
    for r in rows:
        counts[r] = counts.get(r, 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0]



def sheet(strip, dest, frame_height, count, margin_y, label):
    """A contact sheet of every frame, so the frames can be named by looking at them."""
    columns = min(count, 8)
    strip_w, _ = image_size(strip)
    cell = 96
    scaled_w = max(1, int(round(cell * float(strip_w) / max(1, frame_height))))
    # Slice the strip into frames, tile them, and label each with its index.
    parts = []
    for index in range(count):
        out = "/tmp/opencode/_frame_%d.png" % index
        subprocess.run(["magick", strip, "-crop",
                        "%dx%d+0+%d" % (strip_w, frame_height, margin_y + index * frame_height),
                        "+repage", "-resize", "%dx%d" % (scaled_w, cell), out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        labelled = "/tmp/opencode/_lab_%d.png" % index
        subprocess.run(["magick", out, "-background", "#101010", "-fill", "#7fe0ff",
                        "-pointsize", "18", "-gravity", "north",
                        "label:%02d" % index, "+swap", "-append", labelled],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        parts.append(labelled)
    subprocess.run(["montage"] + parts + ["-tile", "%dx" % columns, "-geometry", "+4+4",
                                          "-background", "#101010", dest],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    for path in parts + ["/tmp/opencode/_frame_%d.png" % i for i in range(count)]:
        try:
            os.remove(path)
        except OSError:
            pass
    for i in range(count):
        try:
            os.remove("/tmp/opencode/_frame_%d.png" % i)
        except OSError:
            pass
    return scaled_w


def discover_poses(source):
    """Every pose folder under a character's sprite folder, keyed by pose name.

    A character folder holds one folder per pose. Some source trees nest a chapter folder in
    between (`08_Klein/08_Klein_000`), which is the level Asuna was imported from, so both
    shapes are accepted rather than the caller having to know which one it has.
    """
    roots = []
    for entry in sorted(os.listdir(source)):
        path = os.path.join(source, entry)
        if not os.path.isdir(path):
            continue
        nested = [os.path.join(path, sub) for sub in sorted(os.listdir(path))
                  if os.path.isdir(os.path.join(path, sub))]
        if any(classify(folder)["base"] for folder in nested):
            roots.extend(nested)
        elif classify(path)["base"]:
            roots.append(path)
    found_by_pose = {}
    for root in roots:
        found = classify(root)
        if found["base"]:
            found_by_pose[pose_key(found["base"])] = found
    return found_by_pose


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="the character's sprite folder")
    parser.add_argument("--out", required=True, help="draft config for import_layered_pack.py")
    parser.add_argument("--sheets", help="folder for the per-set contact sheets")
    args = parser.parse_args()

    if not os.path.isdir(args.source):
        sys.exit("Source folder not found: %s" % args.source)

    discovered = discover_poses(args.source)
    if not discovered:
        sys.exit("No pose folder with a composed body under %s" % args.source)

    used = {}
    for pose, found in discovered.items():
        used.setdefault(set_key(found), []).append(pose)

    config = {}
    for key in sorted(used):
        sample = next(discovered[p] for p in sorted(used[key]))
        entry = {"poses": sorted(used[key])}
        for part in ("eyes", "mouth"):
            strip = sample.get(part)
            if not strip:
                continue
            height, count, margin_y, width = measure(strip)
            frames = {"f%02d" % index: index for index in range(count)}
            entry[part] = {"frame": [width, height], "margin": [0, margin_y],
                           "frames": frames, "count": count}
            print("%s %s: %dx%d, %d frames, margin_y=%d"
                  % (key, part, width, height, count, margin_y))
            if args.sheets:
                os.makedirs(args.sheets, exist_ok=True)
                dest = os.path.join(args.sheets, "%s_%s.png" % (key, part))
                sheet(strip, dest, height, count, margin_y, key)
                print("    sheet: %s" % dest)
        config[key] = entry

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=1)
    print("\n%d layer sets -> %s" % (len(config), args.out))


if __name__ == "__main__":
    main()
