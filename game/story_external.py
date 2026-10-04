"""Loader for ready-made stories shipped as JSON (`data/story_*.json`).

The format is the one the world already uses, nothing new:

    {"title", "characters": [...], "locations": {...} | [...], "lore": [...],
     "scenes": [{"id", "background", "music_intent", "steps": [...]}, ...]}

A step is the dict the engine already plays (`type`, `speaker`, `text`, `emotion`, `characters`,
`background`, `choices`, ...). The file is played linearly, through the same buffer and the same
drawing path as an AI-written scene.

Nothing in here raises: a missing file is `None`, a broken file is `None` with the reason in
`issues`, and a broken step is skipped and counted. The game keeps running either way.
"""

import json
import os

STEP_TYPES = ("narration", "dialogue", "scene", "choice", "thought", "system", "wait")

_CACHE = {"path": None, "mtime": None, "story": None}


def _clean_choices(raw, issues, where):
    out = []
    for index, choice in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(choice, dict) or not str(choice.get("text") or "").strip():
            issues.append("%s: choice %d skipped" % (where, index))
            continue
        item = dict(choice)
        item["id"] = str(item.get("id") or "opt%d" % (index + 1))
        effects = item.get("effects")
        if isinstance(effects, dict):
            # `effects.world_flag` is how the stories are written; the engine reads `world_flag`.
            if effects.get("world_flag") and not item.get("world_flag"):
                item["world_flag"] = str(effects["world_flag"])
        out.append(item)
    return out


def _clean_step(step, issues, where):
    """One engine-shaped step, or None when it cannot be played."""
    if not isinstance(step, dict):
        issues.append("%s: not an object" % where)
        return None
    item = dict(step)
    text = item.get("text")
    if text is not None and not isinstance(text, str):
        item["text"] = str(text)
    choices = _clean_choices(item.get("choices"), issues, where) if item.get("choices") else []
    kind = str(item.get("type") or "").strip().lower()
    if choices:
        item["choices"] = choices
        kind = "choice"
    else:
        item.pop("choices", None)
        if kind == "choice":
            issues.append("%s: choice without options skipped" % where)
            return None
    if not kind:
        if item.get("background") and not item.get("text"):
            kind = "scene"
        elif item.get("text"):
            kind = "dialogue" if item.get("speaker") else "narration"
    if kind not in STEP_TYPES:
        issues.append("%s: unknown type %r skipped" % (where, kind))
        return None
    if kind in ("narration", "dialogue", "thought") and not str(item.get("text") or "").strip():
        issues.append("%s: empty text skipped" % where)
        return None
    if kind == "dialogue" and not item.get("speaker"):
        kind = "narration"
    item["type"] = kind
    if item.get("speaker") and not item.get("who"):
        item["who"] = item["speaker"]
    return item


def _locations(raw):
    if isinstance(raw, dict):
        return {str(k): (dict(v) if isinstance(v, dict) else {"description": str(v)})
                for k, v in raw.items()}
    out = {}
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, dict) and entry.get("id"):
            item = dict(entry)
            out[str(item.pop("id"))] = item
    return out


def parse_story(data):
    """Validate a decoded story. Returns {"world", "steps", "issues"} or None when unusable."""
    issues = []
    if not isinstance(data, dict):
        return None
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return None

    characters = []
    for entry in data.get("characters") if isinstance(data.get("characters"), list) else []:
        if isinstance(entry, dict) and entry.get("id"):
            characters.append(dict(entry))
        else:
            issues.append("character skipped")

    steps = []
    for s_index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or not isinstance(scene.get("steps"), list):
            issues.append("scene %d skipped" % s_index)
            continue
        label = str(scene.get("id") or s_index)
        first = True
        for index, raw in enumerate(scene["steps"]):
            step = _clean_step(raw, issues, "%s/%d" % (label, index))
            if step is None:
                continue
            if first and scene.get("background") and step["type"] != "scene" \
                    and not step.get("background"):
                # A scene that never names its place would keep the previous background.
                steps.append({"type": "scene", "background": str(scene["background"])})
            first = False
            steps.append(step)
    if not steps:
        return None

    locations = _locations(data.get("locations"))
    world = {
        "title": str(data.get("title") or "История"),
        "genre": data.get("genre") if isinstance(data.get("genre"), list) else
        ([str(data["genre"])] if data.get("genre") else []),
        "tone": str(data.get("tone") or ""),
        "premise": str(data.get("premise") or data.get("description") or ""),
        "characters": characters,
        "locations": locations,
        "lore": [str(x) for x in data.get("lore") or [] if isinstance(x, (str, int, float))],
        "flags": {},
        "history": [],
        "player_choices": [],
        "buffer": [],
        "turn": 0,
        "time": str(data.get("time") or "09:00"),
        "location": next(iter(locations), "start"),
        "memory_summary": "История только начинается.",
    }
    return {"world": world, "steps": steps, "issues": issues}


def story_files(gamedir):
    """`{name: path}` of the ready-made stories: `game/data/story_*.json`, then `../data/`.

    A name found in `game/data` wins, because that folder is what ends up in a build.
    """
    found = {}
    for folder in (os.path.join(gamedir, "data"), os.path.join(os.path.dirname(gamedir), "data")):
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            if name.startswith("story_") and name.endswith(".json"):
                found.setdefault(name[len("story_"):-len(".json")], os.path.join(folder, name))
    return found


def load_story(path):
    """Read, validate and cache one story file. `None` for a missing or unusable file.

    One story is kept in memory at a time; a second one replaces it.
    """
    try:
        path = os.path.abspath(str(path))
        mtime = os.path.getmtime(path)
    except (OSError, TypeError, ValueError):
        return None
    if _CACHE["path"] == path and _CACHE["mtime"] == mtime:
        return _CACHE["story"]
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    story = parse_story(data)
    _CACHE.update(path=path, mtime=mtime, story=story)
    return story


def next_steps(path, cursor, want=2):
    """Up to `want` steps from `cursor["index"]`; stops after a choice. Moves the cursor."""
    story = load_story(path)
    if not story:
        cursor["done"] = True
        return []
    steps = story["steps"]
    out = []
    index = int(cursor.get("index", 0))
    while index < len(steps) and len(out) < max(1, int(want)):
        step = steps[index]
        index += 1
        out.append(dict(step))
        if step.get("choices"):
            break
    cursor["index"] = index
    if index >= len(steps):
        cursor["done"] = True
    return out
