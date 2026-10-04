"""Sizes that follow the window instead of assuming one resolution.

Every panel used to be a fixed number of pixels, tuned against 1280x720. That works while the
window is exactly that, and breaks the moment it is not: on a 1366x768 screen a 720-tall
window does not fit under the title bar, the bottom of the interface is cut off, and there is
nothing in the layout to absorb the difference. On a 1440p screen the same numbers leave the
panels floating in the middle of a large window.

So the numbers are expressed as a share of what the game actually has. `ui.init` has already
run by the time these are read, so `config.screen_width` and `config.screen_height` are the
real ones, and every value is an integer number of pixels: Ren'Py's layout code does not
accept a fraction where a size is expected.

The shares are chosen so the 1280x720 result is the layout that was tuned and reviewed before,
which keeps this a change of scale rather than a redesign.
"""

from renpy.store import config

## The design resolution. Shares below were chosen against it, so at 1280x720 every panel comes
## out at the pixel size it had before, and a different resolution scales from there.
BASE_W, BASE_H = 1280, 720

## How much of the window a full-height panel may take. The margin is the window edge plus
## room for the title bar, so the panel never ends up under the decoration.
WIDTH_SHARE = 0.92
## A full-height panel is not wanted anyway: a panel that reaches the window edge has nowhere
## to put a shadow, and on a short screen it is the first thing to be clipped. The share leaves
## a margin at the top and bottom at every resolution.
HEIGHT_SHARE = 0.88


def width(share=1.0):
    """`share` of the window width, in whole pixels."""
    return int(round(getattr(config, "screen_width", BASE_W) * share))


def height(share=1.0):
    """`share` of the window height, in whole pixels."""
    return int(round(getattr(config, "screen_height", BASE_H) * share))


def panel_width():
    return width(WIDTH_SHARE)


def panel_height():
    return height(HEIGHT_SHARE)


## Fixed parts of the two tall screens, in pixels: the panel's own padding, the title block and
## the row of buttons around it. Their height comes from the font, not from the resolution, so
## they are the one thing that does not scale — and therefore the reason the scrolling areas
## below are measured against the panel instead of against the window.
##
## The padding is part of this number on purpose. Leaving it out put the settings screen's
## closing row exactly on the panel's edge, which is where "the interface does not fit" comes
## from: the last row is present and still cannot be seen.
PANEL_PAD_Y = 40          # style vn_panel_settings: padding (26, 20)
CREATOR_PAD_Y = 52        # style vn_panel: padding (30, 26)
SETTINGS_CHROME_H = PANEL_PAD_Y + 46 + 36 + 3 * 8
CREATOR_CHROME_H = CREATOR_PAD_Y + 44 + 24 + 40 + 46 + 4 * 10

## Floors, so a very short window leaves a scrollable area rather than a sliver.
MIN_STATUS_H = 76
MIN_SECTION_H = 120
MIN_CREATOR_H = 280


def status_h():
    """The verdict strip at the top of the settings screen."""
    return max(MIN_STATUS_H, min(160, int(round(panel_height() * 0.17))))


def section_h():
    """The scrolling section area: whatever the panel has left once the chrome is placed."""
    return max(MIN_SECTION_H, panel_height() - SETTINGS_CHROME_H - status_h() - 8)


def creator_scroll_h():
    """The scrolling form area of the creator screen."""
    return max(MIN_CREATOR_H, panel_height() - CREATOR_CHROME_H)


def screen_width():
    return int(getattr(config, "screen_width", BASE_W))


def screen_height():
    return int(getattr(config, "screen_height", BASE_H))


## The window never opens larger than this, however big the screen is: past 1440p the interface
## is scaled from a 720p image far enough that the text starts to look soft, and nobody needs a
## visual novel filling a 4K monitor.
MAX_WINDOW_W, MAX_WINDOW_H = 2560, 1440


def fit_window(virtual_w, virtual_h, max_w, max_h, margin=56):
    """The window to open with: the largest 16:9 box that fits the screen, and by how much.

    Two failure modes, and this is the difference between them. A window that is taller than
    the screen has its bottom under the title bar, which is how the interface stopped fitting on
    a 1366x768 laptop; a window stuck at 720p on a 1440p monitor is the other extreme, tiny in
    the middle of a large screen. So the window takes the largest box of the game's own shape
    that the display can hold, is scaled down when even that does not fit, and is never
    stretched: Ren'Py letterboxes the rest.
    """
    limit_w = min(int(max_w) - margin, MAX_WINDOW_W)
    limit_h = min(int(max_h) - margin, MAX_WINDOW_H)
    aspect = float(virtual_w) / float(virtual_h)
    scale = min(limit_w / float(virtual_w), limit_h / float(virtual_h))
    if scale < 1.0:
        # The display cannot hold the game even at its own size, so the window is smaller and
        # Ren'Py scales the game into it. This is the case that used to clip the interface.
        return (max(640, int(virtual_w * scale)), max(400, int(virtual_h * scale)), True)
    # There is room, so grow to the display while keeping the aspect and whole pixels.
    grown_w = min(limit_w, MAX_WINDOW_W)
    grown_h = int(round(grown_w / aspect))
    if grown_h > limit_h:
        grown_h = limit_h
        grown_w = int(round(grown_h * aspect))
    return (int(round(grown_w / 2) * 2), int(round(grown_h / 2) * 2), False)


def display_bounds():
    """(width, height) of the screen the game opened on, or None when it cannot be read."""
    try:
        import renpy

        info = renpy.get_display_info()
    except Exception:
        return None
    if not info:
        return None
    try:
        return int(info["width"]), int(info["height"])
    except (KeyError, TypeError, ValueError):
        return None
