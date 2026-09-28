#!/usr/bin/env python3
"""Turn a measured draft plus a naming sheet into the config `import_layered_pack.py` wants.

`measure_face_strips.py` knows the geometry -- the frame height, how many frames there are,
where the strip starts -- and cannot know what any of them mean. The naming passes supply the
meaning: a sheet was looked at and each frame was identified. Neither half is complete alone,
so this joins them and then adds the emotion table, which is the part the game actually
reads: nine emotions, each a pair of one eye frame and one mouth frame.

Not every pack has every frame. Klein's eyes have no half-lidded state, Argo's mouths have no
teeth, PoH has no eye layer at all behind the mask. An emotion whose frames are missing falls
back to the nearest one that exists, in a fixed order, so a character is never left without an
expression it could have had -- and the fallback is written into the config, so what the game
plays is visible in the file rather than decided at draw time.

    python3 tools/apply_face_naming.py
"""

import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAFTS = os.path.join(REPO, "tools", "face_sets")
NAMING = os.path.join(REPO, "tools", "face_naming")

## The emotions the game asks for, as the eyes and mouth that carry them. The same table the
## measured Asuna pack uses, so every baked character answers the same names.
EMOTIONS = {
    "neutral": ("open", "neutral"),
    "smile": ("open", "smile"),
    "happy": ("happy", "grin"),
    "laugh": ("happy", "laugh"),
    "surprised": ("wide", "surprise"),
    "sad": ("half", "frown"),
    "closed": ("closed", "neutral"),
    "think": ("up", "small"),
    "shy": ("half", "small"),
}

## What to use when a pack has no frame of the wanted kind. The chain follows the wanted
## name, not a single global order: a pack without teeth has no `grin`, and `grin` falls back
## to `smile` so a happy face still smiles, while `frown` falls back to `neutral` so a sad
## face never ends up grinning. One global order would have to put `smile` first, and then
## `sad` would be the smiling one.
EYES_FALLBACK = {
    "open": ("open", "wide", "closed"),
    "closed": ("closed", "half", "open"),
    "happy": ("happy", "wide", "half", "open"),
    "half": ("half", "open", "closed"),
    "wide": ("wide", "open", "happy"),
    "up": ("up", "open", "half"),
    "down": ("down", "open", "half"),
}
MOUTH_FALLBACK = {
    "neutral": ("neutral", "small", "smile"),
    "smile": ("smile", "small", "neutral"),
    "grin": ("grin", "smile", "open", "neutral"),
    "laugh": ("laugh", "grin", "open", "smile", "neutral"),
    "open": ("open", "small", "neutral"),
    "frown": ("frown", "neutral", "small"),
    "small": ("small", "neutral", "smile"),
    "surprise": ("surprise", "open", "grin", "small", "neutral"),
}


def resolve(wanted, available, chains):
    for name in chains.get(wanted, (wanted,)):
        if name in available:
            return name
    return None


def main():
    drafts = sorted(glob.glob(os.path.join(DRAFTS, "*.draft.json")))
    if not drafts:
        sys.exit("No drafts in %s -- run measure_face_strips.py first" % DRAFTS)

    named = {}
    for path in sorted(glob.glob(os.path.join(NAMING, "*.json"))):
        with open(path, encoding="utf-8") as handle:
            for set_key, entry in json.load(handle).items():
                if set_key in named:
                    raise SystemExit("Layer set %s named twice: %s" % (set_key, path))
                named[set_key] = entry

    written = 0
    for draft_path in drafts:
        name = os.path.basename(draft_path)[: -len(".draft.json")]
        with open(draft_path, encoding="utf-8") as handle:
            draft = json.load(handle)
        out = {}
        for set_key, entry in draft.items():
            meaning = named.get(set_key)
            if not meaning:
                print("SKIP %s: layer set %s was never named" % (name, set_key))
                continue
            result = {"poses": entry["poses"]}
            available = {}
            for part in ("eyes", "mouth"):
                spec = entry.get(part)
                if not spec:
                    continue
                count = spec["count"]
                chosen = meaning.get(part) or {}
                bad = {k: v for k, v in chosen.items() if not 0 <= int(v) < count}
                if bad:
                    raise SystemExit("%s/%s %s: frame index outside 0..%d: %s"
                                     % (name, set_key, part, count - 1, bad))
                frames = {}
                for frame_name, index in chosen.items():
                    frames[frame_name] = int(index)
                result[part] = {"frame": spec["frame"], "margin": spec["margin"],
                                "frames": frames}
                available[part] = set(frames)
            if not available:
                print("SKIP %s: layer set %s has no named part" % (name, set_key))
                continue
            emotions = {}
            for emotion, (eyes, mouth) in EMOTIONS.items():
                pair = {}
                eye_name = resolve(eyes, available.get("eyes", set()), EYES_FALLBACK) \
                    if "eyes" in available else None
                mouth_name = resolve(mouth, available.get("mouth", set()), MOUTH_FALLBACK) \
                    if "mouth" in available else None
                if eye_name:
                    pair["eyes"] = eye_name
                if mouth_name:
                    pair["mouth"] = mouth_name
                if pair:
                    emotions[emotion] = pair
            if emotions:
                result["emotions"] = emotions
            out[set_key] = result
        if not out:
            print("SKIP %s: nothing named" % name)
            continue
        target = os.path.join(DRAFTS, name + ".json")
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(out, handle, ensure_ascii=False, indent=1)
        sets = ", ".join(sorted(out))
        print("%-12s %d набор(ов): %s" % (name, len(out), sets))
        written += 1
    print("\n%d конфиг(ов) готово" % written)


if __name__ == "__main__":
    main()
