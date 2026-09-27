"""Smoke tests for the real asset manager and the Live2D pack loader.

Runs without Ren'Py: `renpy` is stubbed, and a temporary game directory holds a
sprite pack, a Live2D pack, a location and a broken pack. The tests cover the
cases that must never break a scene: a missing pack, a missing model, a manifest
that lies about its files, and a Live2D build on a platform without Cubism.
"""
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "game"

PNG = b"\x89PNG\r\n\x1a\n"


def stub_renpy(gamedir):
    renpy = types.ModuleType("renpy")
    renpy.config = types.SimpleNamespace(gamedir=str(gamedir))
    renpy.list_files = lambda: []
    renpy.loadable = lambda name, **kwargs: False
    renpy.has_live2d = lambda: False
    # A real module object, not None: `import renpy.loader` fails on a None entry.
    loader = types.ModuleType("renpy.loader")
    loader.loadable = renpy.loadable

    def _no_archive(name, directory=None, tl=True):
        raise IOError("no archive in the smoke test: " + str(name))

    loader.load = _no_archive
    sys.modules["renpy"] = renpy
    sys.modules["renpy.config"] = renpy.config
    sys.modules["renpy.loader"] = loader
    renpy.loader = loader
    return renpy


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def write(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)

        # --- a sprite pack with a manifest that over-promises a state ---
        pack = os.path.join(tmp, "characters", "asuna")
        write(os.path.join(pack, "character.json"), json.dumps({
            "schema_version": 1,
            "id": "asuna",
            "name": {"ru": "Асуна"},
            "sprite_dir": "sprites",
            "states": {"happy": "sprites/happy.png", "missing": "sprites/ghost.png"},
        }).encode("utf-8"))
        write(os.path.join(pack, "sprites", "happy.png"), PNG)
        write(os.path.join(pack, "sprites", "sad.png"), PNG)

        # --- a Live2D pack with real motion/expression files ---
        live = os.path.join(tmp, "live2d", "asuna")
        write(os.path.join(live, "asuna.model3.json"), json.dumps({
            "FileReferences": {
                "Motions": {"Idle": [{"File": "asuna_idle.motion3.json"}]},
                "Expressions": [{"Name": "happy", "File": "asuna_happy.exp3.json"}],
            },
        }).encode("utf-8"))
        write(os.path.join(live, "asuna_idle.motion3.json"), b"{}")
        write(os.path.join(live, "asuna_happy.exp3.json"), b"{}")

        # --- a location background ---
        write(os.path.join(tmp, "locations", "camp", "bg.png"), PNG)

        # --- a pack whose files simply are not there ---
        write(os.path.join(tmp, "characters", "ghost", "character.json"), json.dumps({
            "schema_version": 1, "id": "ghost", "name": {"ru": "Призрак"},
            "sprite_dir": "sprites", "states": {"neutral": "sprites/none.png"},
        }).encode("utf-8"))

        # --- what the Поглотитель produces: one folder per absorbed character ---
        # Two characters of the same source game, in the `absorbed/<pack>/` shape,
        # with their own manifests, so their states cannot be merged by name.
        for group, name, states in (
            ("dv", "Dv", ["dv_3_pioneer.png", "dv_3_angry.png"]),
            ("us", "Us", ["us_3_body.png"]),
        ):
            folder = os.path.join(tmp, "absorbed", "everlasting_summer", "character_art", group)
            write(os.path.join(folder, "character.json"), json.dumps({
                "schema_version": 1,
                "id": group,
                "name": {"ru": name},
                "third_party": True,
                "redistributable": False,
                "visual": {"type": "sprite", "states": {s: s for s in states}},
            }, ensure_ascii=False).encode("utf-8"))
            for state in states:
                write(os.path.join(folder, state), PNG)

        # A pack whose expressions are baked into full-height sprites, the shape the layered
        # importer writes. Two things have to hold, and both broke in the game before they
        # were pinned here: every emotion has to resolve to its own finished file, and the
        # state map has to sit inside `visual`, because the normaliser folds the pose bodies
        # together only when that key is missing, which flattened every emotion onto the
        # first bare body and left the character with one face for the whole scene.
        folder = os.path.join(tmp, "absorbed", "SAO", "character_art", "asuna_baked")
        poses = {
            "pose_a": {"base": "base/pose_a.png", "eyes_set": "e1", "mouth_set": "e1"},
            "pose_b": {"base": "base/pose_b.png", "eyes_set": "", "mouth_set": ""},
        }
        baked = {"pose_a": "base/pose_a.png", "pose_b": "base/pose_b.png"}
        for emotion in ("neutral", "happy", "sad"):
            baked[emotion] = "base/pose_a_%s.png" % emotion
            baked["pose_a_%s" % emotion] = "base/pose_a_%s.png" % emotion
        write(os.path.join(folder, "character.json"), json.dumps({
            "schema_version": 1,
            "id": "asuna_baked",
            "name": {"ru": "Асуна"},
            "third_party": True,
            "redistributable": False,
            "visual": {"type": "sprite", "poses": poses, "states": baked},
            "states": baked,
        }, ensure_ascii=False).encode("utf-8"))
        for state in set(baked.values()):
            write(os.path.join(folder, state), PNG)

        stub_renpy(tmp)
        assets = load("assets_smoke", GAME / "assets.py")
        live2d = load("live2d_pack_smoke", GAME / "live2d_pack.py")

        catalog = assets.build_catalog()
        ids = sorted(c["id"] for c in catalog["characters"])
        assert "asuna" in ids and "ghost" in ids, ids
        assert any(b.get("location") == "camp" for b in catalog["backgrounds"]), catalog["backgrounds"]

        asuna = assets.find_character(catalog, "asuna")
        assert asuna, "the sprite pack must be discovered"
        assert asuna["display_name"], "the manifest name must be used"
        path, reason = assets.resolve_state(asuna, "happy")
        assert path.endswith("happy.png") and reason == "ok", (path, reason)
        # A state the manifest promises but that is missing must fall back.
        path, reason = assets.resolve_state(asuna, "missing")
        assert path and path.endswith((".png",)), (path, reason)
        assert assets.resolve_state(asuna, "unknown-emotion")[0]

        # --- a baked pack: one finished file per emotion, all inside the pack ---
        baked_pack = assets.find_character(catalog, "asuna_baked")
        assert baked_pack, "a pack with baked expressions must be discovered"
        happy, reason = assets.resolve_state(baked_pack, "happy")
        sad, _ = assets.resolve_state(baked_pack, "sad")
        assert reason == "ok" and happy.endswith("pose_a_happy.png"), (happy, reason)
        assert sad.endswith("pose_a_sad.png"), sad
        assert happy != sad, "every emotion needs its own file, not the first one found"
        # An unbaked pose is still drawable as a body, and a fallback never leaves the pack.
        assert assets.resolve_state(baked_pack, "pose_b")[0].endswith("pose_b.png")
        fallback, _ = assets.resolve_state(baked_pack, "no-such-emotion")
        assert fallback and "asuna_baked" in fallback, fallback

        # --- backgrounds resolve by location id, with a demo fallback ---
        path, reason = assets.resolve_background(catalog, "camp")
        assert path.endswith("bg.png") and reason == "ok", (path, reason)
        path, reason = assets.resolve_background(catalog, "nowhere")
        assert path is None or reason in ("demo", "fuzzy"), (path, reason)

        # A pack with no loadable file is still listed, but never reported ready.
        ghost = assets.find_character(catalog, "ghost")
        assert ghost is not None
        assert assets.resolve_state(ghost, "neutral")[0] is None
        assert assets.status_of(ghost) == "missing", assets.status_of(ghost)
        assert assets.status_of(asuna) == "sprite", assets.status_of(asuna)

        # --- binding: known id attaches, unknown id is not invented ---
        world = {"characters": [{"id": "asuna", "name": "Асуна"}], "locations": {}}
        assets.bind_all(world, catalog)
        visual = world["characters"][0]["visual"]
        assert visual.get("states", {}).get("happy"), visual
        assert assets.find_character(catalog, "nobody") is None

        world2 = {"characters": [{"id": "nobody", "name": "Никто"}], "locations": {}}
        assets.bind_all(world2, catalog, add_missing=True)
        assert world2["characters"][0]["name"] == "Никто", "a missing pack must not rename anybody"

        # --- absorbed characters: one pack each, and no merged "everlasting_summer" ---
        assert "dv" in ids and "us" in ids, ids
        assert "everlasting_summer" not in ids, "the group folder must not become a character"
        assert "character_art" not in ids, ids
        dv = assets.find_character(catalog, "dv")
        us = assets.find_character(catalog, "us")
        assert dv and us, (ids, catalog["characters"])
        assert dv["third_party"] is True and dv["redistributable"] is False, dv
        # An emotion in the file name is usable directly, and resolves to the file.
        path, reason = assets.resolve_state(dv, "angry")
        assert path and path.endswith("character_art/dv/dv_3_angry.png"), (path, reason)
        # A state that is not an emotion falls back inside the same character only.
        path, reason = assets.resolve_state(dv, "pioneer")
        assert path and "character_art/dv/" in path, (path, reason)
        other, _ = assets.resolve_state(us, "pioneer")
        assert other is None or "character_art/us/" in other, other
        world3 = {"characters": [{"id": "dv", "name": "Dv"}], "locations": {}}
        report3 = assets.bind_all(world3, catalog)
        assert "dv" in report3["bound"], report3
        assert world3["characters"][0]["visual"].get("states"), world3["characters"][0]

        # --- Live2D naming must match Ren'Py's own prefix-stripping rule ---
        assert live2d.model_name_of("live2d/asuna/asuna.model3.json") == "asuna"
        assert live2d.cubism_name("asuna_happy.exp3.json", "asuna") == "happy"
        assert live2d.cubism_name("breath.motion3.json", "asuna") == "breath"
        assert live2d.cubism_name("asuna_extra_happy.exp3.json", "asuna") == "extra_happy"

        visual = {
            "type": "live2d",
            "model": "live2d/asuna/asuna.model3.json",
            "expressions": {"happy": "asuna_happy.exp3.json", "ghost": "asuna_ghost.exp3.json"},
            "motions": {"idle": "asuna_idle.motion3.json"},
            "outfits": {"casual": "asuna_casual.exp3.json"},
            "aliases": {"happy": "happy", "idle": "idle"},
        }
        pack_out = live2d.get_pack(visual)
        assert pack_out["ok"], pack_out["issues"]
        assert "happy" in pack_out["expressions"], pack_out["expressions"]
        assert "idle" in pack_out["motions"], pack_out["motions"]
        # An unresolvable outfit must be reported, never silently accepted.
        assert any(i.startswith("outfit_unresolved") for i in pack_out["issues"]), pack_out["issues"]

        motion, is_idle = live2d.motion_for(pack_out, "idle")
        assert motion == "idle" and is_idle
        assert live2d.expression_for(pack_out, "happy") == "happy"
        assert live2d.expression_for(pack_out, "nobody") in (None, "neutral", "normal")

        # A manifest that promises a model file which is not there is not a pack.
        missing = live2d.get_pack({"type": "live2d", "model": "live2d/asuna/ghost.model3.json"})
        assert not missing["ok"] and "model_unreadable" in missing["issues"]

        # Non-Live2D visuals and a platform without Cubism must build nothing.
        assert live2d.build_displayable({"type": "sprites"}) is None
        assert live2d.build_displayable(visual) is None
        assert live2d.build_displayable(None) is None
        assert live2d.live2d_available() is False

        # --- external roots are inspected, never bound and never portable ---
        with tempfile.TemporaryDirectory() as outside:
            outside = os.path.realpath(outside)
            write(os.path.join(outside, "sprites", "smile.png"), PNG)
            write(os.path.join(outside, "backgrounds", "city_night.png"), PNG)
            roots = assets.parse_extra_roots(outside)
            assert roots, "an absolute folder must be accepted as an extra root"
            ext_catalog = assets.build_catalog(roots)
            external = [c for c in ext_catalog["characters"] if c["root_kind"] == "external"]
            assert external, "an external folder with sprites must be inspected"
            record = external[0]
            assert record["third_party"] is True, record
            assert record["redistributable"] is False, record
            path, reason = assets.resolve_state(record, "smile")
            assert path and os.path.isabs(path), (path, reason)
            # The pack is visible, but binding must refuse to install it.
            world3 = {"characters": [{"id": record["id"], "name": record["name"]}],
                      "locations": {"camp": {"name": "Лагерь"}, "city": {"name": "Город"}}}
            outcome = assets.bind_all(world3, ext_catalog)
            assert record["id"] in outcome["inspect_only"], outcome
            assert "visual" not in world3["characters"][0], world3
            assert assets.visual_for_world(record)["inspect_only"] is True
            # The packaged background binds; the external one does not.
            bound = assets.bind_backgrounds(world3, ext_catalog)
            assert "camp" in bound, bound
            assert "city" not in bound, bound
            assert "background" not in world3["locations"]["city"]

        # --- a corrupt manifest must not raise or empty the catalog ---
        write(os.path.join(tmp, "characters", "broken", "character.json"), b"{not json")
        corrupt = assets.build_catalog()
        assert any(c["id"] == "asuna" for c in corrupt["characters"]), "a broken pack must not hide a good one"
        assert any(c["id"] == "broken" for c in corrupt["characters"]), "a broken pack is still listed"

        print("ASSETS SMOKE OK: catalog, state fallback, binding, live2d naming, no-Cubism fallback")


if __name__ == "__main__":
    main()
