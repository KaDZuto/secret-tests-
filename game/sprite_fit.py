"""Scaling a character sprite so it fits the stage.

Full body sprites are taller than the window, so without scaling the top of the head is
cut off: one 1064px character on a 720px stage lost her forehead. A fixed zoom cannot
cover that either, because the packs differ by hundreds of pixels.

The size therefore comes from the file itself. It is read out of the PNG header rather than
asked of Ren'Py, because a Ren'Py `Image` has no size until it is loaded, and the earlier
version of this assumed `Image(path).height` existed, caught the failure, and quietly
returned 1.0 for every sprite, which is why nothing was ever scaled.
"""

import struct

MAX_STAGE_FRACTION = 0.98
# Below this a "sprite" is a placeholder, not a character, and drawing it looks like a bug.
MIN_USABLE_SIDE = 32


def png_size(path):
    """(width, height) from a PNG header, or None for any other format."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(24)
    except (OSError, IOError):
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def image_size(path):
    """The size of an image on disk, resolved against the game directory."""
    import os

    from store import config

    if not path:
        return None
    for candidate in (str(path), os.path.join(config.gamedir, str(path))):
        size = png_size(candidate)
        if size:
            return size
    return None


def is_usable(path, min_side=MIN_USABLE_SIDE):
    """False for a missing file or a placeholder too small to be a character."""
    size = image_size(path)
    if not size:
        return False
    return size[0] >= min_side and size[1] >= min_side


def fit_zoom(path, fraction=MAX_STAGE_FRACTION):
    """The zoom that makes `path` fit the stage height, or 1.0 if it already does."""
    from store import config

    size = image_size(path)
    if not size:
        return 1.0
    height = size[1]
    available = config.screen_height * fraction
    if height <= available:
        return 1.0
    return available / float(height)
