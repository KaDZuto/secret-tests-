"""Helpers for the settings screen: asset browsing and provider feedback.

Ren'Py screens cannot do real work inline, so anything that walks the catalog, hits the
network or touches the filesystem lives here as a plain function and the screen calls it
through `Function` or a screen variable. Every function returns display-safe text instead
of raising, because a broken catalog must not take the settings screen down with it.
"""

import os

# See the note in layered_sprite.py: these live in renpy.exports, not on the package.
import renpy
from renpy.exports.loaderexports import loadable as _loadable

ASSET_PREVIEW_WIDTH = 380
CHARACTER_PREVIEW_WIDTH = 260


def _catalog():
    try:
        import engine

        catalog = engine.asset_catalog()
    except Exception as exc:
        return {"characters": [], "backgrounds": [], "issues": [{"path": str(exc)}]}
    if not isinstance(catalog, dict):
        return {"characters": [], "backgrounds": [], "issues": []}
    return catalog


def _game_path(relative):
    """A catalog path turned into something Ren'Py can load, or None.

    Catalog paths are already relative to the game directory, which is how Ren'Py
    addresses files, so the path is tried as it stands before any fallback.
    """
    if not relative:
        return None
    text = str(relative).lstrip("./")
    for candidate in (text, "images/" + text):
        if _loadable(candidate):
            return candidate
    return None


def _notify(message):
    """`renpy.notify` is a display export, so it is imported by name."""
    from renpy.exports.displayexports import notify

    notify(message)


def _preview_for(path, width, height=None):
    """A scaled copy, so a grid of 3.8k-wide backgrounds does not eat all the memory."""
    if not path:
        return None
    from store import Image, Transform

    try:
        image = Image(path)
        scale = min(1.0, float(width) / max(1, image.width))
        if scale < 1.0:
            transform = Transform(image, xzoom=scale, yzoom=scale)
        else:
            transform = image
        if height:
            return Transform(transform, xsize=width, ysize=height, xalign=0.5, yalign=0.5)
        return transform
    except Exception:
        return None


def asset_background_cards():
    """Background tiles for the browser: id plus a downscaled preview."""
    cards = []
    for item in _catalog().get("backgrounds") or []:
        if not isinstance(item, dict):
            continue
        path = _game_path(item.get("path") or item.get("file"))
        preview = _preview_for(path, ASSET_PREVIEW_WIDTH, 200)
        if not preview:
            continue
        cards.append({"id": str(item.get("id") or item.get("name") or "?"), "preview": preview})
    return cards


def asset_character_cards():
    """Character tiles, using the first available state as the portrait."""
    cards = []
    for item in _catalog().get("characters") or []:
        if not isinstance(item, dict):
            continue
        states = ((item.get("visual") or {}).get("states") or {})
        path = None
        for value in states.values():
            candidate = _game_path(value)
            if candidate:
                path = candidate
                break
        preview = _preview_for(path, CHARACTER_PREVIEW_WIDTH, 150)
        if not preview:
            continue
        cards.append({"id": str(item.get("id") or "?"), "preview": preview})
    return cards


def asset_preview_path():
    """The full-size image for the currently selected catalog entry."""
    wanted = getattr(renpy.store, "asset_preview_id", "")
    if not wanted:
        return None
    catalog = _catalog()
    for item in catalog.get("backgrounds") or []:
        if isinstance(item, dict) and str(item.get("id") or item.get("name")) == wanted:
            return _game_path(item.get("path") or item.get("file"))
    for item in catalog.get("characters") or []:
        if not isinstance(item, dict) or str(item.get("id") or "") != wanted:
            continue
        states = ((item.get("visual") or {}).get("states") or {})
        for value in states.values():
            candidate = _game_path(value)
            if candidate:
                return candidate
    return None


def asset_preview_kind():
    """A short description of where the selected entry comes from."""
    wanted = getattr(renpy.store, "asset_preview_id", "")
    if not wanted:
        return ""
    catalog = _catalog()
    for group, key in (("backgrounds", "Фон"), ("characters", "Персонаж")):
        for item in catalog.get(group) or []:
            if isinstance(item, dict) and str(item.get("id") or item.get("name")) == wanted:
                parts = [key]
                if item.get("pack_id"):
                    parts.append("пак: " + str(item.get("pack_id")))
                if item.get("root_label"):
                    parts.append("источник: " + str(item.get("root_label")))
                if item.get("third_party"):
                    parts.append("сторонний, не для распространения")
                if item.get("state_count"):
                    parts.append("состояний: " + str(item.get("state_count")))
                return " • ".join(parts)
    return ""


def ai_test_click():
    """Run the provider test and store the message for the screen to display."""
    import ai_provider

    ok, message = ai_provider.test_connection()
    renpy.store.provider_test = ("OK: " if ok else "Ошибка: ") + message


def set_screen_var(name, value):
    renpy.store.__dict__[name] = value


def shell_open_gamedir():
    """Open the project folder in the desktop file manager."""
    import subprocess
    import sys

    folder = os.path.join(renpy.config.gamedir, "")
    if sys.platform.startswith("darwin"):
        command = ["open", folder]
    elif os.name == "nt":
        os.startfile(folder)
        _notify("Открыта папка: " + folder)
        return
    else:
        command = ["xdg-open", folder]
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        _notify("Не удалось открыть папку: " + str(exc)[:80])
        return
    _notify("Открыта папка: " + folder)


def ai_provider_refresh_models():
    """Ask the endpoint for its model list and show it in the settings screen."""
    import ai_provider

    models, note = ai_provider.model_ids()
    renpy.store.provider_models = models
    renpy.store.provider_models_note = note
