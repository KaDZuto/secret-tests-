#!/usr/bin/env python3
"""Проверка того, что интерфейс помещается на любом разрешении.

Панели когда-то были числами в пикселях, подогнанными под 1280x720. На другом разрешении они
не становились больше или меньше, а просто занимали часть окна, и на низком экране низ
панелей уходил под заголовок окна. Теперь размеры считаются как доли окна, и этот тест
следит за тем, чтобы доли остались такими: панель помещается в окно, а её части — в панель,
на каждом разрешении от 1024x600 до 2560x1440.

Запуск: python3 tools/smoke_test_layout.py
"""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "game"

RESOLUTIONS = ((1024, 600), (1280, 720), (1366, 768), (1920, 1080), (2560, 1440), (3440, 1440))

FAIL = []


def check(name, cond, detail=""):
    print("  %s %s%s" % ("ok  " if cond else "FAIL", name,
                         "" if cond else "  -- " + str(detail)))
    if not cond:
        FAIL.append(name)
    return cond


def load_layout(width, height):
    """`vn_layout` with a stand-in for Ren'Py's config, so every share can be measured."""
    renpy = types.ModuleType("renpy")
    store = types.ModuleType("renpy.store")
    store.config = types.SimpleNamespace(screen_width=width, screen_height=height)
    renpy.store = store
    renpy.get_display_info = lambda: None
    sys.modules["renpy"] = renpy
    sys.modules["renpy.store"] = store
    spec = importlib.util.spec_from_file_location("vn_layout_under_test", GAME / "vn_layout.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


settings_layout = None


def layout_chrome(_module, name):
    """The fixed part of a screen, taken from the module so the test cannot drift from it."""
    return int(getattr(settings_layout, name))


def store_sizes(width, height):
    """The store variables `vn_styles` computes, by the same formulas."""
    global settings_layout
    layout = load_layout(width, height)
    settings_layout = layout
    return {
        "panel_w": layout.panel_width(),
        "panel_h": layout.panel_height(),
        "nav_w": int(round(width * 0.23)),
        "check_w": int(round(width * 0.30)),
        "box_w": int(round(width * 0.735)),
        "status_h": layout.status_h(),
        "section_h": layout.section_h(),
        "creator_scroll_h": layout.creator_scroll_h(),
    }


def main():
    print("A. Панель помещается в окно")
    for width, height in RESOLUTIONS:
        sizes = store_sizes(width, height)
        check("%dx%d: панель %dx%d в окне" % (width, height, sizes["panel_w"], sizes["panel_h"]),
              sizes["panel_w"] <= width and sizes["panel_h"] <= height, sizes)

    print("\nB. Настройки: полоса статуса и разделы помещаются в панель")
    for width, height in RESOLUTIONS:
        s = store_sizes(width, height)
        # Заголовок, подзаголовок-строка и нижняя кнопка — фиксированной высоты, потому что их
        # размер задаёт шрифт, а не разрешение.
        chrome = layout_chrome(settings_layout, "SETTINGS_CHROME_H")
        used = chrome + s["status_h"] + s["section_h"]
        check("%dx%d: %d + %d + %d = %d в панели %d" % (
            width, height, chrome, s["status_h"], s["section_h"], used, s["panel_h"]),
            used <= s["panel_h"], (used, s["panel_h"]))
        # Область разделов должна быть основной частью панели, а не полоской.
        check("%dx%d: разделам достаётся не меньше трети панели" % (width, height),
              s["section_h"] >= s["panel_h"] * 0.33, (s["section_h"], s["panel_h"]))

    print("\nC. Экран создания: форма помещается в панель")
    for width, height in RESOLUTIONS:
        s = store_sizes(width, height)
        chrome = layout_chrome(settings_layout, "CREATOR_CHROME_H")
        used = chrome + s["creator_scroll_h"]
        check("%dx%d: %d + %d = %d в панели %d" % (
            width, height, chrome, s["creator_scroll_h"], used, s["panel_h"]),
            used <= s["panel_h"], (used, s["panel_h"]))

    print("\nD. Боковые колонки не выталкивают содержимое")
    for width, height in RESOLUTIONS:
        s = store_sizes(width, height)
        inner = s["panel_w"] - 2 * 26
        check("%dx%d: навигация %d + раздел в %d" % (width, height, s["nav_w"], inner),
              s["nav_w"] + 120 < inner, (s["nav_w"], inner))
        check("%dx%d: кнопка проверки %d помещается в полосу статуса" % (width, height, s["check_w"]),
              s["check_w"] + 20 < inner, (s["check_w"], inner))

    print("\nE. Окно подстраивается под экран")
    layout = load_layout(1280, 720)
    for display_w, display_h in ((1280, 720), (1366, 768), (1920, 1080), (2560, 1440),
                                 (3440, 1440), (1024, 600)):
        win_w, win_h, scaled = layout.fit_window(1280, 720, display_w, display_h)
        check("экран %dx%d -> окно %dx%d%s" % (
            display_w, display_h, win_w, win_h, " (масштаб)" if scaled else ""),
            win_w <= display_w and win_h <= display_h, (win_w, win_h))
        # Пропорции сохраняются, иначе окно растягивает картинку.
        aspect_ok = abs((win_w / float(win_h)) - (1280 / 720.0)) < 0.02
        check("экран %dx%d: пропорции 16:9 сохранены" % (display_w, display_h), aspect_ok,
              (win_w / float(win_h)))

    print("\nИТОГ: провалено %d" % len(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
