#!/usr/bin/env python3
"""Import a layered character pack: composed bodies plus interchangeable face parts.

Some source games ship no finished sprites. They ship a composed body image and vertical
strips of interchangeable face parts, and the player picks eyes and mouth at runtime.
The layers are baked into the body at import time rather than composited while the game
runs. Compositing at draw time means offsets live in two places at once, the face parts
have to be re-scaled together with the body, and a small error in either shows up as a
visible seam on the face. Baking writes one full-height image per expression instead, so
the game draws an ordinary sprite per emotion and the result can be inspected as a file.

Source layout, read from the Sword Art Online portrait set:

    <pose>/ch<chapter>_<pose>_out.png    composed body, enough to play on its own
    <pose>/<pose>_Eyes.png               strip of face frames, stacked vertically
    <pose>/<pose>_Mouth.png              strip of mouth frames
    <pose>/<pose>_Option<n>.png          small accessory strips

Two things have to be measured per character, and neither can be derived from the files:

* frame geometry -- the strip is frames of width x height stacked with an unknown
  height and an unknown top margin. Across one character the height already changes
  between outfit sets (124, 126), and a set with few frames carries a 4px margin;
* the face offset -- where the strip lands on that particular body image.

A pixel metric is not trustworthy for the offset. A face layer *replaces* the face
underneath it rather than matching it, so comparing pixels slides the layer toward
where the mismatch is smallest instead of where the hair lines up. The offset was found
by looking at composited candidates, which is why it lives in a config file.

Poses whose strips are byte-identical share one layer set, so the strip is sliced once
and every pose in the set points at the result. That is detected by content hash; the
config is keyed by the same hash, which is printed when a set is missing from it.

    python3 tools/import_layered_pack.py \\
        --source "/path/to/Asuna" --id asuna --name Asuna --pack SAO \\
        --sets tools/face_sets_asuna.json

The config looks like:

    {
      "e1807_mbfa8": {
        "poses": ["000", "003"],
        "eyes": {"frame": [248, 124], "margin": [0, 0], "offset": [235, 187],
                 "frames": {"open": 1, "closed": 0, "happy": 12}},
        "mouth": {"frame": [90, 90], "margin": [2, 4], "offset": [310, 328],
                  "frames": {"neutral": 15, "smile": 19}}
      }
    }
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def digest(path):
    with open(path, "rb") as handle:
        return hashlib.md5(handle.read()).hexdigest()[:8]


def image_size(path):
    out = subprocess.run(["magick", "identify", "-format", "%w %h", path],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
    return tuple(int(x) for x in out.stdout.split()[:2])


def classify(folder):
    """One pose folder: the composed body, the two face strips, any accessory strips."""
    found = {"base": None, "eyes": None, "mouth": None, "options": []}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isfile(path) or not name.lower().endswith(".png"):
            continue
        if re.search(r"_out\.png$", name, re.IGNORECASE):
            found["base"] = path
        elif re.search(r"_eyes\.png$", name, re.IGNORECASE):
            found["eyes"] = path
        elif re.search(r"_mouth\.png$", name, re.IGNORECASE):
            found["mouth"] = path
        elif re.search(r"_option\d*\.png$", name, re.IGNORECASE):
            found["options"].append(path)
    return found


def pose_key(base_path):
    """`ch01_000_out.png` -> `pose_000`: a name that is safe in a Ren'Py image name."""
    stem = os.path.splitext(os.path.basename(base_path))[0]
    stem = re.sub(r"^ch", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_out$", "", stem, flags=re.IGNORECASE)
    return "pose_" + stem.lstrip("_")


def set_key(found):
    return "e%s_m%s" % (digest(found["eyes"])[:4] if found["eyes"] else "none",
                        digest(found["mouth"])[:4] if found["mouth"] else "none")


def slice_part(strip, spec, dest_dir):
    """Cut the frames a config asks for and name each file after its expression.

    Ren'Py picks a layer file by attribute name, so the frame for `closed` eyes has to
    be called `closed.png`. Frame indices come from the config; the index is kept in the
    name as well so the same strip can carry two attributes from one frame.
    """
    width, height = spec["frame"]
    margin_x, margin_y = spec.get("margin", [0, 0])
    strip_w, strip_h = image_size(strip)
    if strip_w < width:
        raise SystemExit("Frame %dx%d is wider than the %dx%d strip %s"
                         % (width, height, strip_w, strip_h, os.path.basename(strip)))

    os.makedirs(dest_dir, exist_ok=True)
    for name, index in sorted(spec["frames"].items()):
        y = margin_y + index * height
        if y + height > strip_h:
            raise SystemExit("Frame %d of %s does not fit: strip %dx%d, frame %dx%d at y=%d"
                             % (index, os.path.basename(strip), strip_w, strip_h,
                                width, height, y))
        subprocess.run(["magick", strip, "-crop", "%dx%d+%d+%d" % (width, height, margin_x, y),
                        "+repage", "-depth", "8", os.path.join(dest_dir, name + ".png")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return sorted(spec["frames"])


def load_rgba(path):
    """Raw RGBA bytes, so the offset search can work on pixels instead of files."""
    result = subprocess.run(["magick", path, "-depth", "8", "rgba:-"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
    return result.stdout


def changed_pixels(base, layer, dx, dy, scratch):
    """Exact count of pixels that differ, used to confirm the search's winner."""
    subprocess.run(["magick", base, layer, "-geometry", "+%d+%d" % (dx, dy),
                    "-composite", scratch],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    result = subprocess.run(["magick", "compare", "-metric", "AE", base, scratch, "null:"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        return float(result.stderr.decode().split()[0])
    except (ValueError, IndexError):
        return float("inf")


def varying_mask(frames, width, height):
    """Which pixels of a face strip the animation actually changes.

    Every frame of an eyes or mouth strip carries the same face around the moving part, so
    the pixels that differ from frame to frame are the expression and everything else is
    background. That split is what makes the offset measurable: the background has to land
    on the body *exactly*, and the expression is free to differ, because it is supposed to.
    """

    def row_bytes(buf, r):
        start = r * width * 4
        return buf[start:start + width * 4]

    mask = bytearray(width * height)
    reference = frames[0]
    for other in frames[1:]:
        for r in range(height):
            left = row_bytes(reference, r)
            right = row_bytes(other, r)
            if left == right:
                continue
            for c in range(width):
                if left[c * 4:c * 4 + 4] != right[c * 4:c * 4 + 4]:
                    mask[r * width + c] = 1
    return mask


def background_misses(base, base_w, layer, layer_w, layer_h, mask, dx, dy):
    """Pixels outside the face that the layer would cover wrongly at this offset.

    This is the metric that works, and it is worth being precise about why the earlier ones
    did not. Comparing the layer against the body rewards the offset where the hair strands
    fall on the same hair strands, which is usually right; but it is a soft signal, and with
    a seed more than a few pixels off it settles on a local optimum and stays there. Counting
    only the *background* makes the signal sharp instead: at the true offset the count is
    exactly zero, because the layer's unchanged face is the same artwork as the body's face.
    """
    misses = 0
    for r in range(layer_h):
        start = ((dy + r) * base_w + dx) * 4
        here = base[start:start + layer_w * 4]
        there = layer[r * layer_w * 4:(r + 1) * layer_w * 4]
        if here == there:
            continue
        merged = (int.from_bytes(here, "big") ^ int.from_bytes(there, "big")).to_bytes(
            layer_w * 4, "big")
        row = r * layer_w
        for c in range(layer_w):
            if merged[c * 4:c * 4 + 4] == b"\0\0\0\0":
                continue
            if not mask[row + c]:
                misses += 1
    return misses


def find_offset(base, layer_path, frames, guess, scratch, window, step=2, fine=3):
    """Where a face part belongs on this body, measured instead of guessed.

    `frames` are the strip's own frames, used to tell the expression from the background.
    The search is coarse then fine, and the winner is confirmed with an exact pixel count
    against the composited result. `window` is wide for the first pose of a set, where
    nothing is known yet, and narrow afterwards: poses of one outfit share a head position,
    so the first correct answer is the best seed for the rest.
    """
    base_w, base_h = image_size(base)
    layer_w, layer_h = image_size(layer_path)
    layer = load_rgba(layer_path)
    mask = varying_mask(frames, layer_w, layer_h)

    base_pixels = load_rgba(base)
    best = None
    for dy in range(max(0, int(guess[1]) - window), min(base_h - layer_h, int(guess[1]) + window) + 1, step):
        for dx in range(max(0, int(guess[0]) - window), min(base_w - layer_w, int(guess[0]) + window) + 1, step):
            value = background_misses(base_pixels, base_w, layer, layer_w, layer_h, mask, dx, dy)
            if best is None or value < best[0]:
                best = (value, dx, dy)
    if best:
        for dy in range(best[2] - fine, best[2] + fine + 1):
            for dx in range(max(0, best[1] - fine), best[1] + fine + 1):
                value = background_misses(base_pixels, base_w, layer, layer_w, layer_h, mask, dx, dy)
                if value < best[0]:
                    best = (value, dx, dy)
    if not best:
        return None
    exact = changed_pixels(base, layer_path, best[1], best[2], scratch)
    return (exact, best[1], best[2])


def _layer_files(pack_dir, part, entry, expressions):
    """The layer's own frames on disk, which is what the offset is measured against."""
    names = entry.get("names") or []
    picked = []
    for value in expressions.values():
        name = value.get(part)
        if name and name in names and name not in picked:
            picked.append(name)
    return [os.path.join(pack_dir, part, entry["dir"], name + ".png") for name in picked]


def _available_frame(wanted, part, available):
    """The frame to paste for this expression, or None when the set has none.

    The expression table is shared by every layer set, but the sets do not carry the same
    frames: one outfit has three eye shapes and no mouth strip at all, so the frame the table
    asks for is simply not on disk. Asking for the one it does have keeps every pose
    expressible, and skipping the part entirely leaves the body's own face in place, which is
    what happened when the missing file was handed to the compositor instead.
    """
    name = wanted.get(part)
    if not name or not available:
        return None
    if name in available:
        return name
    for fallback in (("open", "closed") if part == "eyes" else ("neutral", "smile")):
        if fallback in available:
            return fallback
    return None


def bake_pose(base_path, pack_dir, layers, expressions, dest_dir, pose):
    """Write `<pose>_<emotion>.png` for every expression, face parts already composited.

    ImageMagick does the compositing rather than the game, so a wrong offset shows up as a
    seam in a file that can be opened and looked at, instead of only on screen. The result
    is a full-height body, not a patch, which is what the stage expects.

    `layers` maps a part to (folder under the pack, (offset_x, offset_y)).
    """
    written = {}
    for emotion in sorted(expressions):
        command = ["magick", base_path]
        for part in ("eyes", "mouth"):
            entry = layers.get(part)
            if not entry:
                continue
            name = _available_frame(expressions.get(emotion) or {}, part, entry[2])
            if not name:
                continue
            set_dir, offset = entry[0], entry[1]
            path = os.path.join(pack_dir, part, set_dir, name + ".png")
            command += ["(", path, ")",
                        "-geometry", "+%d+%d" % (int(offset[0]), int(offset[1])),
                        "-composite"]
        out_name = "%s_%s.png" % (pose, emotion)
        command += ["-depth", "8", os.path.join(dest_dir, out_name)]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        written[emotion] = out_name
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--sets", required=True, help="JSON with measured geometry and offsets")
    parser.add_argument("--dest-root", default=os.path.join(REPO, "game", "absorbed"))
    parser.add_argument("--no-auto-offset", dest="auto_offset", action="store_false",
                        help="trust the offsets in the config instead of measuring each pose")
    parser.set_defaults(auto_offset=True)
    parser.add_argument("--offset-window", type=int, default=12,
                        help="search radius around a known offset, in pixels")
    parser.add_argument("--first-offset-window", type=int, default=56,
                        help="search radius for the first pose of a layer set")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.path.isdir(args.source):
        sys.exit("Source folder not found: %s" % args.source)
    with open(args.sets, encoding="utf-8") as handle:
        sets_config = json.load(handle)

    # `discovered` keeps what is on disk; `poses` becomes the manifest, and mixing the
    # two cost a KeyError on the second pass.
    discovered = {}
    folders = [os.path.join(args.source, e) for e in sorted(os.listdir(args.source))
               if os.path.isdir(os.path.join(args.source, e))]
    if not folders:
        folders = [args.source]

    for folder in folders:
        found = classify(folder)
        if not found["base"]:
            continue
        discovered[pose_key(found["base"])] = found

    if not discovered:
        sys.exit("No pose with a composed body under %s" % args.source)

    used_sets = {}
    for pose, found in discovered.items():
        used_sets.setdefault(set_key(found), []).append(pose)

    missing = sorted(set(used_sets) - set(sets_config))
    extra = sorted(set(sets_config) - set(used_sets))
    for key in missing:
        print("WARN: layer set %s has no entry in %s; its poses import as plain bodies"
              % (key, args.sets))
    for key in extra:
        print("WARN: %s describes poses that are not in this source" % key)

    pack_dir = os.path.join(args.dest_root, args.pack, "character_art", args.id)
    layer_sets = {}
    expressions = {}

    for key, pose_names in sorted(used_sets.items()):
        config = sets_config.get(key, {})
        record = {"poses": sorted(pose_names)}
        sample = discovered[pose_names[0]]

        if key in sets_config:
            for part, strip in (("eyes", sample["eyes"]), ("mouth", sample["mouth"])):
                spec = config.get(part)
                if not spec or not strip:
                    continue
                if not args.dry_run:
                    names = slice_part(strip, spec, os.path.join(pack_dir, part, key))
                else:
                    names = sorted(spec["frames"])
                record[part] = {"dir": key, "names": names, "offset": spec["offset"]}
                for emotion, value in config.get("emotions", {}).items():
                    if part in value:
                        expressions.setdefault(emotion, {})[part] = value[part]
        layer_sets[key] = record

    poses = {}
    for pose, found in sorted(discovered.items()):
        key = set_key(found)
        options = {}
        if not args.dry_run:
            os.makedirs(os.path.join(pack_dir, "base"), exist_ok=True)
            shutil.copy2(found["base"], os.path.join(pack_dir, "base", pose + ".png"))
            for index, option in enumerate(found["options"]):
                shutil.copy2(option, os.path.join(pack_dir, "base", "option%d.png" % index))
                options["option%d" % index] = "base/option%d.png" % index
        poses[pose] = {
            "base": "base/%s.png" % pose,
            "eyes_set": key if layer_sets.get(key, {}).get("eyes") else "",
            "mouth_set": key if layer_sets.get(key, {}).get("mouth") else "",
            "options": options,
        }

    # Every expression becomes a full-height image, so the game draws a normal sprite and
    # nothing about the face depends on offsets at run time.
    states = {}
    scratch = os.path.join("/tmp", "livingvn_offset_%s.png" % args.id)
    measured = {}
    for pose, found in sorted(discovered.items()):
        states[pose] = "base/%s.png" % pose
        key = set_key(found)
        record = layer_sets.get(key, {})
        layers = {}
        for part in ("eyes", "mouth"):
            entry = record.get(part)
            if not entry:
                continue
            offset = entry.get("offset")
            if args.auto_offset:
                # Seed from the first pose of the set: the head sits in the same place on
                # every pose of one outfit, so the search only has to correct a little.
                known = measured.setdefault(key, {}).get(part)
                seed = known or offset or (200, 150)
                # The first pose of a set has nothing to trust, so it gets a wide search.
                # A narrow one is not a shortcut here: it is what left the first pose stuck
                # in a local optimum while the poses after it walked onto the right answer.
                window = args.offset_window if known else args.first_offset_window
                layer_files = [p for p in _layer_files(pack_dir, part, entry, expressions)
                               if os.path.exists(p)]
                if layer_files:
                    found_offset = find_offset(found["base"], layer_files[0],
                                               [load_rgba(p) for p in layer_files],
                                               seed, scratch, window=window)
                    if found_offset:
                        measured[key][part] = [found_offset[1], found_offset[2]]
                        offset = [found_offset[1], found_offset[2]]
                        entry["offset_measured"] = offset
            if offset:
                layers[part] = (entry["dir"], offset, set(entry.get("names") or ()))
        if not layers:
            continue
        written = bake_pose(found["base"], pack_dir, layers, expressions,
                            os.path.join(pack_dir, "base"), pose)
        for emotion, out_name in written.items():
            states["%s_%s" % (pose, emotion)] = "base/%s" % out_name
            # A bare emotion maps to the first pose that has it, so resolve_state finds it.
            states.setdefault(emotion, "base/%s" % out_name)

    if args.dry_run:
        print(json.dumps({"poses": poses, "layer_sets": layer_sets, "states": states,
                          "expressions": expressions}, ensure_ascii=False, indent=1))
        return

    manifest = {
        "id": args.id,
        "name": args.name,
        "source": os.path.dirname(args.source.rstrip("/")),
        "pack": args.pack,
        "third_party": True,
        "redistributable": False,
        "visual": {
            "type": "sprite",
            "poses": poses,
            "baked_expressions": sorted(expressions),
        },
        "states": states,
        "layer_sets": layer_sets,
        "expressions": expressions,
    }
    layered = sum(1 for info in poses.values() if info["eyes_set"] or info["mouth_set"])
    # The same state map goes into `visual` as well as the top level. The catalog
    # normaliser reads `visual.states` and only falls back to folding the pose bodies
    # together when that key is missing, so without it every emotion resolved to the
    # first bare body and the character never changed her face.
    manifest["visual"]["states"] = dict(states)
    manifest["state_count"] = len(states)
    with open(os.path.join(pack_dir, "character.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=1)
        handle.write("\n")

    total = sum(os.path.getsize(os.path.join(root, name))
                for root, _d, names in os.walk(pack_dir) for name in names)
    print("Imported %s: %d poses (%d with face parts), %d layer sets, %.1f MB -> %s"
          % (args.id, len(poses), layered, len(layer_sets), total / 1048576.0, pack_dir))


if __name__ == "__main__":
    main()
