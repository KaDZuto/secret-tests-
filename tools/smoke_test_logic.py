"""Dependency-light smoke tests for core logic without launching Ren'Py."""
import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Minimal Ren'Py stub for pure helper modules.
renpy = types.ModuleType("renpy")
renpy.config = types.SimpleNamespace(gamedir=str(ROOT / "game"))
renpy.list_files = lambda: [
    "music/nostalgia_daylight.wav",
    "images/bg_demo.png",
]
renpy.fetch = lambda *args, **kwargs: None
sys.modules["renpy"] = renpy
sys.modules["renpy.config"] = renpy.config


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# world.py imports ai_client; provide a stub module because no network is used here.
ai = types.ModuleType("ai_client")
ai.generate_world = lambda *args, **kwargs: {}
sys.modules["ai_client"] = ai

world = load("world_smoke", ROOT / "game" / "world.py")
music = load("music_smoke", ROOT / "game" / "music.py")
ai.generate_world = lambda *args, **kwargs: world.default_world()

w = world.default_world()
assert w["characters"] and w["locations"]
r = world.random_world(8)
assert 1 <= len(r["characters"]) <= 8

catalog = music.scan_music([])
assert any(x["path"] == "music/nostalgia_daylight.wav" for x in catalog)
assert music.choose_track(catalog, "nostalgia") == "music/nostalgia_daylight.wav"

out = ROOT / "game" / "data" / "story_example.json"
json.loads(out.read_text(encoding="utf-8"))
print("SMOKE OK: world generation and music catalog helpers")
