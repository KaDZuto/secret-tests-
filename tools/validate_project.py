#!/usr/bin/env python3
"""Offline validation for the Living VN MVP.

This does not replace Ren'Py lint. It catches the most common errors before
opening the project in the Ren'Py launcher.
"""
import ast
import json
import os
import re
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(ROOT, "game")


def check_python():
    errors = []
    for base, _dirs, files in os.walk(GAME):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(base, fn)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    ast.parse(fh.read(), filename=path)
            except Exception as exc:
                errors.append(f"Python: {path}: {exc}")
    return errors


def check_json():
    errors = []
    for base, _dirs, files in os.walk(ROOT):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            path = os.path.join(base, fn)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    json.load(fh)
            except Exception as exc:
                errors.append(f"JSON: {path}: {exc}")
    return errors


def check_audio():
    errors = []
    for base, _dirs, files in os.walk(GAME):
        for fn in files:
            if not fn.endswith(".wav"):
                continue
            path = os.path.join(base, fn)
            try:
                with wave.open(path, "rb") as wf:
                    if wf.getnframes() <= 0 or wf.getframerate() <= 0:
                        raise ValueError("empty WAV")
            except Exception as exc:
                errors.append(f"WAV: {path}: {exc}")
    return errors


def check_references():
    errors = []
    required = [
        "images/bg_demo.png",
        "images/char_demo.png",
        "data/story_example.json",
    ]
    for rel in required:
        if not os.path.exists(os.path.join(GAME, rel)):
            errors.append(f"Missing demo asset: game/{rel}")
    text = open(os.path.join(GAME, "engine.py"), encoding="utf-8").read()
    ## The network adapter moved to `ai_client` on purpose: `renpy.fetch` is not an attribute
    ## of the `renpy` package in this project, so every call written that way raised at runtime
    ## and the story request never left the machine. The transport is checked where it lives.
    if "ai_client" not in text:
        errors.append("engine.py does not reach the AI client")
    if "supervise(" not in text:
        errors.append("engine.py does not invoke the plot supervisor")
    client_path = os.path.join(GAME, "ai_client.py")
    if not os.path.exists(client_path):
        errors.append("Missing AI transport: game/ai_client.py")
    else:
        client = open(client_path, encoding="utf-8").read()
        for needle, what in (
            ("urlopen", "the HTTP transport"),
            ("call_chat", "the OpenAI-compatible chat call"),
            ("post_bytes", "the TTS transport"),
        ):
            if needle not in client:
                errors.append(f"ai_client.py does not contain {what}")
    return errors


def main():
    errors = check_python() + check_json() + check_audio() + check_references()
    rpy = [
        os.path.join(base, fn)
        for base, _dirs, files in os.walk(GAME)
        for fn in files if fn.endswith(".rpy")
    ]
    for path in rpy:
        text = open(path, encoding="utf-8").read()
        if text.count("{") != text.count("}"):
            errors.append(f"Possible RPY brace mismatch: {path}")
    if errors:
        print("VALIDATION FAILED")
        for item in errors:
            print(" -", item)
        return 1
    print(f"OK: {len(rpy)} RPY files, Python/JSON/WAV checks passed.")
    print("Next: run Ren'Py lint against the project with Ren'Py 8.3.7.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
