"""Drawing a layered character: a composed body plus interchangeable face parts.

A layered pack has no finished sprites. It has one body per pose, plus strips of eyes and
mouth that the source engine drew over the face. The importer measured where those parts
land on each body and wrote the numbers into the pack manifest, so drawing one means
showing the body and the two chosen parts at the recorded offsets, in that order.

Ren'Py has no single displayable that stacks images at fixed offsets, and its
`layeredimage` statement only resolves attributes from the script side, so the parts are
shown as separate sprites on the same layer. Show order is the draw order, which is why
the body goes first.
"""

import os

# The display and loader functions live in renpy.exports, not on the package itself, so
# they are imported by name. `renpy.hide` and `renpy.loadable` raise AttributeError.
from renpy.exports.displayexports import hide as _hide, show as _show
from renpy.exports.loaderexports import loadable as _renpy_loadable

PART_TAGS = ("face_eyes", "face_mouth")


def _pack_dir(record):
    """The pack folder on disk. `pack_path` is game-relative; `pack_dir` is not."""
    prefix = (record or {}).get("pack_path") or (record or {}).get("pack_dir")
    if not prefix:
        return None
    from store import config

    return os.path.join(config.gamedir, prefix)


def _load_manifest(record):
    """The pack's `character.json`, which holds the poses, offsets and emotions."""
    folder = _pack_dir(record)
    if not folder:
        return None
    path = os.path.join(folder, "character.json")
    if not os.path.exists(path):
        return None
    try:
        import json

        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _attribute(manifest, emotion):
    table = (manifest or {}).get("expressions") or {}
    if emotion in table:
        return table[emotion]
    # The source packs name their faces differently; fall back on the closest neutral one.
    for fallback in ("smile", "neutral"):
        if fallback in table:
            return table[fallback]
    return {}


def _pose_with_face(manifest, wanted=None):
    poses = ((manifest or {}).get("visual") or {}).get("poses") or {}
    if not poses:
        return None
    if wanted and wanted in poses:
        return wanted
    for pose, info in sorted(poses.items()):
        if isinstance(info, dict) and info.get("eyes_set"):
            return pose
    return sorted(poses)[0]


def layered_parts(record, emotion="neutral", pose=None):
    """(body, eyes, mouth) with offsets, or None when the pack is not layered."""
    manifest = _load_manifest(record)
    if not manifest or ((manifest.get("visual") or {}).get("type") != "layered"):
        return None

    pose = _pose_with_face(manifest, pose)
    if not pose:
        return None
    info = ((manifest.get("visual") or {}).get("poses") or {}).get(pose) or {}
    body = _loadable("%s/%s" % (record.get("pack_path") or record.get("pack_dir") or "",
                                info.get("base") or ""))
    if not body:
        return None

    attributes = _attribute(manifest, emotion)
    pack_dir = str(record.get("pack_path") or record.get("pack_dir") or "")
    parts = []
    for part, tag in (("eyes", "face_eyes"), ("mouth", "face_mouth")):
        set_dir = info.get(part + "_set")
        name = attributes.get(part)
        if not set_dir or not name:
            parts.append(None)
            continue
        parts.append((_loadable("%s/%s/%s/%s.png" % (pack_dir, part, set_dir, name)),
                      _offset(manifest, set_dir, part), tag))

    if not any(parts):
        return None
    return {"body": body, "eyes": parts[0], "mouth": parts[1], "pose": pose}


def _offset(manifest, set_dir, part):
    entry = ((manifest or {}).get("layer_sets") or {}).get(set_dir) or {}
    found = entry.get(part) or {}
    offset = found.get("offset") or [0, 0]
    return (int(offset[0]), int(offset[1]))


def _loadable(relative):
    if not relative:
        return None
    text = str(relative)
    return text if _renpy_loadable(text) else None


def _displayables():
    from store import Fixed, Image, Transform

    return Fixed, Image, Transform


def clear_face(tag):
    """Hide the face overlays of a character that is no longer on stage."""
    for part in PART_TAGS:
        _hide(tag + "_" + part)


def draw_layered(tag, record, transform, emotion="neutral", pose=None):
    """Show a layered character. Returns True when it drew one."""
    parts = layered_parts(record, emotion=emotion, pose=pose)
    if not parts:
        return False

    Fixed, Image, Transform = _displayables()
    import sprite_fit

    # One displayable holding body, eyes and mouth: shown as separate sprites they did not
    # travel together, and the parts were left at their raw offsets in the corner of the
    # screen while the body moved.
    body_size = sprite_fit.image_size(parts["body"])
    children = [Image(parts["body"])]
    for part in (parts["eyes"], parts["mouth"]):
        if not part:
            continue
        path, (offset_x, offset_y), suffix = part
        if not path:
            continue
        children.append(Transform(Image(path), xpos=offset_x, ypos=offset_y))

    # The box is the body's own size, so the parts are measured against the body and the
    # position transform aligns the character, not the union of the children. `xysize` is
    # what makes that true; without it the box grew to fit the offset parts and the
    # character drifted away from the position it was given.
    group = Fixed(*children, **({"xysize": body_size} if body_size else {}))
    zoom = sprite_fit.fit_zoom(parts["body"])
    # The scale goes on its own transform, not on one that also carries the group: a child
    # inside the transform made Ren'Py scale the group a second time, which is what left
    # the character half height and cut off at the waist.
    at_list = ([transform] if transform else []) + [Transform(zoom=zoom)]
    _show(tag, what=group, at_list=at_list)
    return True
