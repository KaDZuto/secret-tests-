#!/usr/bin/env python3
"""Bake layered character sprites from Everlasting Summer.

Source format (per character, per pose):
    {char}_{N}_body.png           base body without face or clothes
    {char}_{N}_{costume}.png      clothing layer (dress, pioneer, sport, swim)
    {char}_{N}_{expr}.png         face layer (normal, serious, smile, happy, ...)
    {char}_{N}_{accessory}.png    accessory layer (glasses, stethoscope)
    {char}_{N}_{expr}_1.png       left part of the face layer
    {char}_{N}_{expr}_2.png       right part of the face layer

Clothing layers: mean.a ~0.1-0.16
Face layers: mean.a ~0.002-0.005
Accessories: mean.a ~0.001-0.007

Baking composites base + costume + face + accessory for every combination.

    python3 tools/bake_es_layered.py
"""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ES_DIR = os.path.join(REPO, "game", "absorbed", "Everlasting_Summer", "character_art")

FACE_MAX = 0.02
ACCESSORY_NAMES = {"glasses", "stethoscope"}


def list_pngs(directory):
    return sorted(f for f in os.listdir(directory) if f.endswith(".png"))


def mean_alpha(path):
    result = subprocess.run(
        ["magick", path, "-format", "%[fx:mean.a]", "info:"],
        capture_output=True, text=True, check=True
    )
    return float(result.stdout.strip())


def parse_filename(name, char_id):
    """Parse a filename into (pose_num, layer_name)."""
    prefix = char_id + "_"
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):-4]

    if rest.startswith("-") or rest.startswith("emo"):
        return None
    if rest in ("body", "body_1", "body_2"):
        return None

    parts = rest.split("_")
    if len(parts) < 2:
        return None

    pose_num = parts[0]
    if not pose_num.isdigit():
        return None

    if parts[-1] in ("1", "2") and len(parts) >= 3:
        return None

    layer_name = "_".join(parts[1:])

    if layer_name == "body":
        return None

    return (pose_num, layer_name)


def composite(base_path, layer_path, out_path):
    subprocess.run([
        "magick", base_path,
        "(", layer_path, "+repage", ")",
        "-composite", "-depth", "8", out_path
    ], check=True)


def bake_character(char_id, source_dir):
    """Bake all costumes × expressions for one character."""
    pngs = list_pngs(source_dir)

    poses = {}
    for name in pngs:
        parsed = parse_filename(name, char_id)
        if parsed is None:
            continue
        pose_num, layer_name = parsed
        poses.setdefault(pose_num, {})[layer_name] = name

    if not poses:
        print(f"  {char_id}: no layers found")
        return None

    out_base = os.path.join(source_dir, "base")
    os.makedirs(out_base, exist_ok=True)

    states = {}
    poses_manifest = {}

    for pose_num in sorted(poses.keys()):
        body_name = f"{char_id}_{pose_num}_body.png"
        body_path = os.path.join(source_dir, body_name)

        layers = poses[pose_num]
        costumes = []
        faces = []
        accessories = []

        for layer_name, filename in sorted(layers.items()):
            path = os.path.join(source_dir, filename)
            alpha = mean_alpha(path)
            if layer_name in ACCESSORY_NAMES:
                accessories.append(layer_name)
            elif alpha <= FACE_MAX:
                faces.append(layer_name)
            else:
                costumes.append(layer_name)

        pose_key = f"pose_{pose_num}"
        poses_manifest[pose_key] = {"base": f"base/{pose_key}.png", "costumes": {}}

        if os.path.exists(body_path):
            subprocess.run(["cp", body_path, os.path.join(out_base, f"{pose_key}.png")], check=True)
            states[pose_key] = f"base/{pose_key}.png"
            base_for_baking = body_path
        else:
            if not costumes:
                continue
            base_for_baking = os.path.join(source_dir, layers[costumes[0]])
            costumes = costumes[1:]
            subprocess.run(["cp", base_for_baking, os.path.join(out_base, f"{pose_key}.png")], check=True)
            states[pose_key] = f"base/{pose_key}.png"

        for costume in costumes:
            costume_key = f"{pose_key}_{costume}"
            costume_layer = os.path.join(source_dir, layers[costume])
            costume_path = os.path.join(out_base, f"{costume_key}.png")

            composite(base_for_baking, costume_layer, costume_path)

            states[costume_key] = f"base/{costume_key}.png"
            poses_manifest[pose_key]["costumes"][costume] = f"base/{costume_key}.png"

            for face in faces:
                face_key = f"{costume_key}_{face}"
                face_layer = os.path.join(source_dir, layers[face])
                face_path = os.path.join(out_base, f"{face_key}.png")

                composite(costume_path, face_layer, face_path)

                states[face_key] = f"base/{face_key}.png"
                states.setdefault(face, f"base/{face_key}.png")

                for accessory in accessories:
                    acc_key = f"{face_key}_{accessory}"
                    acc_layer = os.path.join(source_dir, layers[accessory])
                    acc_path = os.path.join(out_base, f"{acc_key}.png")

                    composite(face_path, acc_layer, acc_path)

                    states[acc_key] = f"base/{acc_key}.png"

        if not costumes:
            for face in faces:
                face_key = f"{pose_key}_{face}"
                face_layer = os.path.join(source_dir, layers[face])
                face_path = os.path.join(out_base, f"{face_key}.png")

                composite(base_for_baking, face_layer, face_path)

                states[face_key] = f"base/{face_key}.png"
                states.setdefault(face, f"base/{face_key}.png")

                for accessory in accessories:
                    acc_key = f"{face_key}_{accessory}"
                    acc_layer = os.path.join(source_dir, layers[accessory])
                    acc_path = os.path.join(out_base, f"{acc_key}.png")

                    composite(face_path, acc_layer, acc_path)

                    states[acc_key] = f"base/{acc_key}.png"

    return {"poses": poses_manifest, "states": states}


def main():
    if not os.path.isdir(ES_DIR):
        sys.exit(f"Directory not found: {ES_DIR}")

    characters = sorted(d for d in os.listdir(ES_DIR)
                       if os.path.isdir(os.path.join(ES_DIR, d)))

    for char_id in characters:
        char_dir = os.path.join(ES_DIR, char_id)
        print(f"Processing {char_id}...")

        result = bake_character(char_id, char_dir)
        if result is None:
            continue

        manifest = {
            "id": char_id,
            "name": char_id.upper(),
            "source": "Everlasting Summer",
            "pack": "Everlasting_Summer",
            "third_party": True,
            "redistributable": False,
            "visual": {
                "type": "sprite",
                "poses": result["poses"],
            },
            "states": result["states"],
        }

        manifest_path = os.path.join(char_dir, "character.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
            f.write("\n")

        pose_count = len(result["poses"])
        expr_count = len(result["states"])
        print(f"  {char_id}: {pose_count} poses, {expr_count} states")

    print("Done.")


if __name__ == "__main__":
    main()
