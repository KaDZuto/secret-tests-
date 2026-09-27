"""Offline smoke test for the Поглотитель, including `.rpa` archives.

Builds a real RPA-3.0 archive with the standard format so the reader is exercised
the same way a Ren'Py game exercises it, and checks the cases that must not go
wrong: byte-exact extraction, no filename collision, a refused protected
container, model formats Ren'Py cannot display, and sprites landing as one
character pack with its own manifest.
"""
import json
import os
import pickle
import struct
import sys
import tempfile
import zipfile
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "game"))
import cannibalism
import rpa_index


def build_rpa(path, entries, key=0x42424242):
    """Write a standard RPA-3.0 container. Format only, no obfuscation tricks."""
    header = b"RPA-3.0 "
    index = {}
    body = b""
    for name, data in entries.items():
        # Offsets are absolute file positions, so the 40-byte header counts.
        index[name] = [(40 + len(body) ^ key, len(data) ^ key, "")]
        body += data
    index_blob = zlib.compress(pickle.dumps(index))
    index_offset = 40 + len(body)
    head = header + ("%016X" % index_offset).encode("ascii") + b" " + ("%08X" % key).encode("ascii")
    head = head.ljust(40, b"\x00")
    assert len(head) == 40, len(head)
    with open(path, "wb") as fh:
        fh.write(head)
        fh.write(body)
        fh.write(index_blob)


def build_rpa_variant(path, magic, entries, key):
    """An RPA-3.x container under a non-standard name, for the unrpa fallback."""
    prefix_len = len(magic) + 1 + 16 + 1 + 8 + 1
    index = {}
    body = b""
    for name, data in entries.items():
        offset = prefix_len + len(body)
        index[name] = [(offset ^ key, len(data) ^ key, b"")]
        body += data
    blob = zlib.compress(pickle.dumps(index))
    head = b"%s %016X %08X\n" % (magic, prefix_len + len(body), key)
    assert len(head) == prefix_len, (len(head), prefix_len)
    with open(path, "wb") as fh:
        fh.write(head)
        fh.write(body)
        fh.write(blob)


def build_rpi(path, entries):
    """The official RPA-1.0 layout: index at offset 0, data behind it, no key."""
    offset = 0
    for _ in range(8):
        offset = len(zlib.compress(pickle.dumps(
            {n: [(offset, len(d))] for n, d in entries.items()})))
    index = {n: [(offset, len(d))] for n, d in entries.items()}
    with open(path, "wb") as fh:
        fh.write(zlib.compress(pickle.dumps(index)))
        for data in entries.values():
            fh.write(data)


def check_rpa_readers():
    """The built-in reader takes the standard formats, unrpa the unofficial ones."""
    payload = b"\x89PNG\r\n\x1a\n" + b"asuna-sprite-bytes"
    entries = {"images/sprites/asuna/happy.png": payload}
    expected = {
        "rpa-1.0-rpi": (".rpi", lambda p: build_rpi(p, entries), "unrpa"),
        "rpa-3.2": (".rpa", lambda p: build_rpa_variant(p, b"RPA-3.2", entries, 0x0BADF00D), "unrpa"),
        "rpa-4.0": (".rpa", lambda p: build_rpa_variant(p, b"RPA-4.0", entries, 0x00C0FFEE), "unrpa"),
    }
    if not rpa_index.unrpa_available():
        print("  unrpa: not importable, unofficial variants untested")
    with tempfile.TemporaryDirectory() as work:
        for label, (suffix, build, want_reader) in expected.items():
            if want_reader == "unrpa" and not rpa_index.unrpa_available():
                continue
            path = os.path.join(work, "variant%s" % suffix)
            build(path)
            index, reader = rpa_index.read_index_with_reader(path)
            assert reader.startswith("unrpa"), (label, reader)
            for name in index:
                assert rpa_index.read_entry(path, name, index) == payload, label
            print("  rpa %-12s reader=%-16s byte-exact" % (label, reader))
        # A container nothing may open stays refused.
        junk = os.path.join(work, "junk.rpa")
        with open(junk, "wb") as fh:
            fh.write(b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64)
        report = rpa_index.describe(junk)
        assert not report["ok"] and report["reason"], report
        print("  rpa %-12s refused: %s" % ("junk", report["reason"]))


def main():
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 64
    ogg = b"OggS\x00\x02" + b"y" * 64

    with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
        os.makedirs(os.path.join(source, "images", "char"), exist_ok=True)
        os.makedirs(os.path.join(source, "music"), exist_ok=True)
        open(os.path.join(source, "images", "char", "hero_happy.png"), "wb").write(b"img")
        open(os.path.join(source, "music", "nostalgia.ogg"), "wb").write(b"aud")
        open(os.path.join(source, "story.rpy"), "w", encoding="utf-8").write(
            'define hero = Character("Hero")\n# calm and curious\n')

        # A standard archive, a protected-looking one, and a model set.
        os.makedirs(os.path.join(source, "game"), exist_ok=True)
        build_rpa(os.path.join(source, "game", "archive.rpa"), {
            "images/sprites/hero/hero_happy.png": png,
            "images/sprites/hero/hero_sad.png": png,      # same base name, different file
            "images/sprites/hero/hero_angry.png": png,
            "images/sprites/hero/hero_thinking.png": png,
            # Only two states, so this folder is art, not a character.
            "images/sprites/stranger/stranger_a.png": png,
            "images/sprites/stranger/stranger_b.png": png,
            # Interface art must never become a character.
            "gui/scrollbar/frame.png": png,
            "gui/button/base.png": png,
            # Cutscene art is art too, but not a character.
            "images/cg/scene01.png": png,
            # A scene folder inside a character folder is still that character.
            "images/yuri/0a.png": png,
            "images/yuri/0b.png": png,
            "images/yuri/0c.png": png,
            "images/yuri/0d.png": png,
            "images/yuri/stab/1.png": png,
            "images/yuri/stab/2.png": png,
            "sound/bgm/theme.ogg": ogg,
            "script.rpy": b'define other = Character("Other")\n',
        })
        with open(os.path.join(source, "game", "protected.rpa"), "wb") as fh:
            fh.write(b"XX-1.0 " + b"\x00" * 64)
        # A Cubism 2 model set and a real MMD model set.
        os.makedirs(os.path.join(source, "live2d"), exist_ok=True)
        open(os.path.join(source, "live2d", "asuna.model.json"), "w", encoding="utf-8").write(
            '{"version":"Sample 1.0.0","model":"moc/asuna.moc"}\n')
        open(os.path.join(source, "live2d", "asuna.moc"), "wb").write(b"moc\n")
        open(os.path.join(source, "live2d", "asuna.mtn"), "wb").write(b"$fps=30\n")
        open(os.path.join(source, "live2d", "asuna.physics.json"), "w", encoding="utf-8").write("{}\n")
        os.makedirs(os.path.join(source, "mmd"), exist_ok=True)
        open(os.path.join(source, "mmd", "asuna.pmx"), "wb").write(b"OggS-pmx")
        open(os.path.join(source, "mmd", "asuna.vmd"), "wb").write(b"Vmd")

        scan = cannibalism.scan_source(source)
        paths = sorted(f["path"] for f in scan["files"])
        assert "images/sprites/hero/hero_happy.png" in paths, paths
        assert "images/sprites/hero/hero_sad.png" in paths, paths
        assert "sound/bgm/theme.ogg" in paths, paths
        assert "script.rpy" in paths, paths
        assert scan["archives"] and scan["archives"][0]["entries"] == 17, scan["archives"]

        # A container that is not a standard Ren'Py archive is refused, not unpacked.
        assert any(w.startswith("archive_refused:") for w in scan["warnings"]), scan["warnings"]
        refused = [w for w in scan["warnings"] if w.startswith("archive_refused:")][0]
        assert "protected.rpa" in refused, refused

        # Cubism 2 is real Live2D but Ren'Py 8.x needs Cubism 4, and MMD is a
        # different format entirely. Both are catalogued, neither is Live2D, and
        # neither is ever copied into the game.
        kinds = {f["path"]: f["kind"] for f in scan["files"]}
        assert kinds.get("live2d/asuna.model.json") == "live2d2", kinds
        assert kinds.get("live2d/asuna.moc") == "live2d2", kinds
        assert kinds.get("live2d/asuna.mtn") == "live2d2", kinds
        assert kinds.get("mmd/asuna.pmx") == "other_model", kinds
        assert kinds.get("mmd/asuna.vmd") == "other_model", kinds
        assert not any(f["kind"] == "live2d" for f in scan["files"]), kinds

        # A text candidate is read out of the archive for the absorber.
        packet = cannibalism.build_absorber_packet(scan)
        assert any("Other" in s["text"] for s in packet["text_samples"]), packet["text_samples"]
        assert packet["archives"], packet

        # --- absorb everything into a temporary target, never the repository ---
        ids = [f["id"] for f in scan["files"]]
        assessment = {
            "selected_ids": ids,
            "characters": [{"id": "hero", "name": "Hero", "personality": "calm and curious",
                            "goals": ["find the truth"],
                            "visual_asset_ids": [kinds and ids[0]]}],
            "summary": "test",
        }
        cannibalism.config.gamedir = target
        manifest = cannibalism.absorb_selected(scan, assessment, "TestGame")

        assert manifest["redistributable"] is False
        assert manifest["third_party"] is True
        assert manifest["archives"], manifest

        copied = {a["path"]: a for a in manifest["assets"] if a.get("copied_path")}
        # Two files with the same base name must both survive, byte-exact.
        # Content is compared too: a shifted read keeps the size and loses the data.
        for name, expected in (("images/sprites/hero/hero_happy.png", png),
                               ("images/sprites/hero/hero_sad.png", png),
                               ("sound/bgm/theme.ogg", ogg)):
            item = copied[name]
            full = os.path.join(target, item["copied_path"])
            assert os.path.isfile(full), (name, full)
            with open(full, "rb") as fh:
                data = fh.read()
            assert data == expected, (name, data[:16], expected[:16])
        assert len({copied[n]["copied_path"] for n in
                    ("images/sprites/hero/hero_happy.png", "images/sprites/hero/hero_sad.png")}) == 2
        # The stem is slugged once, not twice.
        assert copied["images/sprites/hero/hero_happy.png"]["copied_path"].endswith("hero_happy.png")
        # A model Ren'Py cannot display is never copied into the game.
        assert "live2d/asuna.moc" not in copied
        assert "live2d/asuna.model.json" not in copied
        assert "mmd/asuna.pmx" not in copied

        # --- sprites land as one character pack, not as a pile of files ---
        # `hero` has four states of its own, `stranger` only two, and `yuri` owns a
        # scene folder that folds back into it.
        assert manifest["character_packs"] == ["hero", "yuri"], manifest["character_packs"]
        # Interface art is catalogued but never pulled in as a character.
        assert "gui/scrollbar/frame.png" not in copied, "gui art must not be pulled in"
        assert "gui/button/base.png" not in copied, "gui art must not be pulled in"
        copied_kinds = {a["path"]: a["kind"] for a in copied.values()}
        assert copied_kinds.get("images/cg/scene01.png") == "scene_art", copied_kinds
        # A scene folder under a character must not create a second character.
        dest = {a["path"]: a["copied_path"] for a in copied.values()}
        assert dest["images/yuri/stab/1.png"] == "absorbed/TestGame/character_art/yuri/1.png", dest
        assert dest["images/yuri/stab/2.png"] == "absorbed/TestGame/character_art/yuri/2.png", dest
        assert not os.path.exists(os.path.join(target, "absorbed", "TestGame",
                                               "character_art", "stab")), "stab must not exist"
        # Two states are art, not a character, so they stay out of the pack folders.
        assert dest["images/sprites/stranger/stranger_a.png"] == \
            "absorbed/TestGame/character_art/stranger_a.png", dest
        assert manifest["character_manifests"] == [
            "absorbed/TestGame/character_art/hero/character.json",
            "absorbed/TestGame/character_art/yuri/character.json",
        ], manifest["character_manifests"]
        char_dir = os.path.join(target, *manifest["character_manifests"][0].split("/")[:-1])
        with open(os.path.join(target, *manifest["character_manifests"][0].split("/")),
                  encoding="utf-8") as fh:
            char_manifest = json.load(fh)
        assert char_manifest["id"] == "hero", char_manifest
        assert char_manifest["third_party"] is True, char_manifest
        # Five states, not four: the loose folder file and the archive entry with
        # the same base name both survive, under distinct names.
        states = char_manifest["visual"]["states"]
        assert set(states) == {"hero_happy.png", "hero_happy_1.png", "hero_sad.png",
                               "hero_angry.png", "hero_thinking.png"}, states
        assert all(value == key for key, value in states.items()), states
        # The absorber's own name for the character wins over the folder guess.
        assert char_manifest["name"] == "Hero", char_manifest
        for state in states:
            assert os.path.isfile(os.path.join(char_dir, state)), state

        world = {"characters": [], "flags": {}}
        added = cannibalism.import_characters_into_world(world, manifest, ids)
        assert added == ["hero"]
        assert world["characters"][0]["visual_assets"]
        assert world["absorbed_packs"][0]["redistributable"] is False

        # A plain ZIP source keeps working.
        zip_path = os.path.join(source, "bundle.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("images/char/hero.png", b"img")
            zf.writestr("script.rpy", "define hero = Character(\"Hero\")\n")
        zip_scan = cannibalism.scan_source(zip_path)
        assert sorted(f["path"] for f in zip_scan["files"]) == ["images/char/hero.png", "script.rpy"]

        print("CANNIBALISM SMOKE OK: folders, zip, rpa archives, refusals, byte-exact absorb")

    check_rpa_readers()
    print("RPA READERS OK: builtin for standard, vendored unrpa for unofficial variants")


if __name__ == "__main__":
    main()
