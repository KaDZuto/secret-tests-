#!/usr/bin/env python3
"""Import a folder of character sprites as a character pack.

The absorbed packs all follow the same manifest shape, whatever the source game looked
like, so importing a new one is a copy plus a `character.json`. Sprites that live in
per-pose subfolders are flattened, because Ren'Py addresses files by one relative path
and a nested source layout would otherwise have to be carried into the manifest.

Only files matching `--pattern` are taken, so a source folder of layered parts (eyes,
mouth, options) can contribute just its composed sprite.

    python3 tools/import_sprite_pack.py \\
        --source "/path/to/character_art/Asuna" \\
        --id asuna --name Asuna --pack SAO --pattern "*_out.png"
"""

import argparse
import fnmatch
import json
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def collect(source, pattern):
    """Every matching file below `source`, as (absolute path, flat name) pairs."""
    found = []
    for root, _dirs, files in os.walk(source):
        for name in sorted(files):
            if not fnmatch.fnmatch(name, pattern):
                continue
            if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                found.append((os.path.join(root, name), name))
    return found


def flat_name(character_id, name):
    """`01_Asuna_000/ch01_000_out.png` -> `asuna_000.png`."""
    stem = os.path.splitext(name)[0]
    if stem.lower().startswith("ch"):
        stem = stem[2:]
    parts = [p for p in stem.split("_") if p]
    parts = [p for p in parts if p.lower() != character_id.lower()]
    tail = parts[-1] if parts else stem
    return "%s_%s.png" % (character_id, tail)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--pattern", default="*.png")
    parser.add_argument("--dest-root", default=os.path.join(REPO, "game", "absorbed"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.path.isdir(args.source):
        sys.exit("Source folder not found: %s" % args.source)

    files = collect(args.source, args.pattern)
    if not files:
        sys.exit("Nothing matched %r under %s" % (args.pattern, args.source))

    dest_dir = os.path.join(args.dest_root, args.pack, "character_art", args.id)
    states = {}
    for absolute, name in files:
        target_name = flat_name(args.id, name)
        states[target_name] = target_name

    manifest = {
        "id": args.id,
        "name": args.name,
        "source": os.path.dirname(args.source.rstrip("/")),
        "pack": args.pack,
        "third_party": True,
        "redistributable": False,
        "visual": {"type": "sprite", "states": dict(sorted(states.items()))},
        "poses": sorted(states),
    }

    if args.dry_run:
        print(json.dumps(manifest, ensure_ascii=False, indent=1))
        print("\n%d files, destination %s" % (len(files), dest_dir))
        return

    os.makedirs(dest_dir, exist_ok=True)
    for absolute, name in files:
        shutil.copy2(absolute, os.path.join(dest_dir, flat_name(args.id, name)))

    with open(os.path.join(dest_dir, "character.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=1)
        handle.write("\n")

    total = sum(os.path.getsize(os.path.join(dest_dir, n)) for n in os.listdir(dest_dir))
    print("Imported %s: %d sprites, %.1f MB -> %s" % (args.id, len(files), total / 1048576.0, dest_dir))


if __name__ == "__main__":
    main()
