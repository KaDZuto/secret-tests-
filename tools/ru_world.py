#!/usr/bin/env python3
"""Reading a story out of a file, and the checks that only need the file.

A story in this project is written in three different shapes, and all three have to be
reviewable by the same rules:

- `data/*.json` -- a world plus `scenes[].steps[]`, the shape the story agent writes;
- `game/story_chapter.py` -- the hand-written first chapter, built by `s()` / `opt()` calls
  in a dict literal, where the text is a Python string;
- `game/*.rpy` -- `renpy.say(...)` and `define` lists, which are not valid Python at all.

So a unit is extracted first, with a stable id, and every later check works on units rather
than on the file format. The unit id is what the controller agent quotes in its verdict, which
is the whole point: the model never has to count lines or re-read the file to talk about a
line.

The engine checks read the real engine instead of trusting a copy of it. `ENGINE_CONTRACT`
lists the field names `engine.py` really reads, and `check_contract` greps `engine.py` for
them: if someone renames a key, the checker says so instead of quietly passing a story the
game cannot play.
"""

import ast
import io
import json
import os
import re

import ru_text as rt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEP_TYPES = ("narration", "dialogue", "choice", "scene", "wait", "music", "narrator")
FALLBACK_EMOTIONS = ("neutral", "smile", "happy", "laugh", "surprised", "sad", "closed",
                      "think", "shy")
# `engine.apply_choice` reads these off a choice; anything else is ignored at runtime.
CHOICE_KEYS = ("id", "text", "flag", "world_flag", "goto")
# `story_pipeline.normalize` keeps the model's own fields, `engine._play_step` reads these.
ENGINE_STEP_KEYS = ("type", "speaker", "character", "text", "background", "characters",
                    "choices", "music_intent", "state_patch")
ENGINE_CONTRACT = ("apply_choice", "state_patch", "music_intent", "player_choices", "speaker")

_STR = r'"(?:[^"\\]|\\.)*"'
_SAY_RE = re.compile(
    r"renpy\.say\(\s*([^,]+?)\s*,\s*((?:%s)(?:\s*\n\s*%s)*)" % (_STR, _STR), re.S)
_DEFINE_RE = re.compile(r"^(?:define|default)\s+([A-Za-z_][\w.]*)\s*=\s*(\[|\{)", re.M)
_HELPER_NAMES = {"s": "step", "opt": "option", "scene": "step", "dialogue": "step",
                 "narration": "step", "beat": "step"}


def _as_str(value, env):
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    if isinstance(value, ast.Name) and value.id in env:
        return env[value.id]
    if isinstance(value, ast.BinOp):
        left = _as_str(value.left, env)
        right = _as_str(value.right, env)
        if left is not None and right is not None:
            return left + right
    return None


def _kwarg(call, name, env):
    for keyword in call.keywords:
        if keyword.arg == name:
            return _as_str(keyword.value, env)
    return None


class Unit(dict):
    """One reviewable line of the story, with the address it came from."""

    def __init__(self, uid, scene, index, kind, text, **kw):
        super().__init__(uid=uid, scene=scene, index=index, kind=kind, text=text, **kw)


class Story(dict):
    """A whole file: its units, its cast, its places and its own text fields."""

    def __init__(self, path, units, characters, locations, fields, blocks, referenced,
                 has_world=True):
        super().__init__(path=path, units=units, characters=characters, locations=locations,
                         fields=fields, blocks=blocks, referenced=referenced,
                         has_world=has_world)

    @property
    def name(self):
        return os.path.basename(self["path"])


# --------------------------------------------------------------------- loading

def load(path):
    path = os.path.abspath(path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return _load_json(path)
    if ext == ".py":
        return _load_py(path)
    if ext == ".rpy":
        return _load_rpy(path)
    raise ValueError("unsupported story file: %s (expected .json, .py or .rpy)" % path)


# Keys that hold data for the engine, not prose for the player: an id, an asset path, a type
# tag. Reading them as text produces 90 false findings about "английское слово images".
_SKIP_FIELD = ("id", "visual", "type", "state", "pose", "path", "asset", "file", "icon", "src",
               "background", "speaker", "emotion", "position", "goto", "flag", "world_flag",
               "music_intent", "state_patch", "checkpoint", "role", "relationships", "name",
               "short_name", "title_ru")
_ASSET_SUFFIX = (".png", ".jpg", ".jpeg", ".webp", ".ogg", ".wav", ".mp3", ".rpy", ".json",
                 ".rpa", ".rpyc", ".ttf", ".otf", ".model3.json", ".moc3", ".mtn")


def _is_prose(prefix, value):
    if not isinstance(value, str) or len(value.strip()) <= 2:
        return False
    tail = prefix.rsplit(".", 1)[-1]
    if tail in _SKIP_FIELD:
        return False
    if "/" in value or "\\" in value:
        return False
    if value.strip().lower().endswith(_ASSET_SUFFIX):
        return False
    if not re.search(r"[\wа-яё]", value):
        return False
    # A machine name, not prose: `start_plaza`, `opt1`, `kirito_investigates`, `scene_1`.
    if " " not in value.strip() and ("_" in value or re.fullmatch(r"[a-z0-9.]+", value)):
        return False
    return True


def _collect_fields(data, out, prefix=""):
    """Every string in the world's own prose: title, description, personality, lore."""
    if isinstance(data, str):
        if _is_prose(prefix, data):
            out.append((prefix, data))
    elif isinstance(data, dict):
        for key, value in data.items():
            if key in ("steps", "beats", "choices"):
                continue
            _collect_fields(value, out, prefix + "." + str(key) if prefix else str(key))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            _collect_fields(value, out, "%s[%d]" % (prefix, index))
    return out


def _load_json(path):
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    units = []
    fields = _collect_fields(data, [])
    cast = data.get("characters") if isinstance(data, dict) else None
    if isinstance(cast, list):
        characters = {}
        for record in cast:
            if isinstance(record, dict) and record.get("id"):
                characters[str(record["id"])] = record.get("name") or record["id"]
    else:
        characters = {}
    locations = data.get("locations") if isinstance(data, dict) else None

    scenes = []
    if isinstance(data, dict):
        if isinstance(data.get("scenes"), list):
            scenes = [(str(s.get("id") or ("scene_%d" % (i + 1))), s)
                      for i, s in enumerate(data["scenes"]) if isinstance(s, dict)]
        elif isinstance(data.get("beats"), list):
            scenes = [("bundle", {"steps": data["beats"]})]
        elif isinstance(data.get("steps"), list):
            scenes = [("steps", data)]
    elif isinstance(data, list):
        scenes = [("beats", data)]
    if not scenes:
        # A world without scenes is a real file in this project (`game/data/story_example.json`):
        # its prose is still worth reviewing, it just has no steps to walk.
        return Story(path, [], characters, locations, fields, [], _referenced_by_engine(path),
                     has_world=True)

    for scene_id, scene in scenes:
        background = scene.get("background")
        if background and not _has_scene_step(scene.get("steps")):
            pass  # reported by the engine check, not here
        steps = scene.get("steps") or scene.get("beats") or []
        for index, step in enumerate(steps):
            units.append(_unit_from_dict("%s/%s/%d" % (os.path.basename(path), scene_id, index),
                                        scene_id, index, step, background))
    return Story(path, units, characters, locations, fields, [], _referenced_by_engine(path),
                 has_world=True)


def _has_scene_step(steps):
    return any(isinstance(s, dict) and s.get("type") == "scene" for s in (steps or []))


def _unit_from_dict(uid, scene_id, index, step, scene_background=None, line=None):
    if not isinstance(step, dict):
        return Unit(uid, scene_id, index, "unknown", "", raw=step)
    kind = str(step.get("type") or "").strip() or _guess_kind(step)
    choices = []
    for pos, choice in enumerate(step.get("choices") or []):
        if isinstance(choice, dict):
            choices.append({"id": str(choice.get("id") or "opt%d" % pos),
                            "text": str(choice.get("text") or ""),
                            "world_flag": choice.get("world_flag"),
                            "flag": choice.get("flag"),
                            "goto": choice.get("goto"),
                            "shape": sorted(k for k in choice.keys()),
                            "raw": choice})
        else:
            choices.append({"id": "opt%d" % pos, "text": str(choice), "shape": []})
    return Unit(uid, scene_id, index, kind, str(step.get("text") or "").strip(),
                line=index if line is None else line,
                speaker=step.get("speaker") or step.get("who"),
                character=step.get("character"),
                emotion=step.get("emotion"),
                position=step.get("position"),
                background=step.get("background") or scene_background,
                choices=choices,
                music_intent=step.get("music_intent"),
                state_patch=bool(step.get("state_patch")),
                checkpoint=bool(step.get("checkpoint")),
                keys=sorted(step.keys()))


def _guess_kind(step):
    if step.get("choices"):
        return "choice"
    if step.get("speaker") or step.get("who"):
        return "dialogue"
    if step.get("text"):
        return "narration"
    return "unknown"


def _load_py(path):
    with io.open(path, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, filename=path)
    env = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    env[target.id] = node.value.value
    blocks = {}
    units = []
    name = os.path.basename(path)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Dict, ast.List)):
            target = node.targets[0] if node.targets else None
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Dict):
                try:
                    literal = ast.literal_eval(node.value)
                except Exception:
                    literal = None
                if isinstance(literal, dict):
                    blocks[target.id] = sorted(k for k in literal.keys() if isinstance(k, str))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        fname = getattr(func, "id", "") or getattr(func, "attr", "")
        role = _HELPER_NAMES.get(fname)
        if role is None or not node.args:
            continue
        text = _as_str(node.args[0], env)
        if role == "option":
            parent = _enclosing(scene=blocks, node=node, source=source)
            # `opt("ask", "Сказать правду.", goto=...)`: the first argument is the id, the
            # player's answer is the second.
            answer = _as_str(node.args[1], env) if len(node.args) > 1 else None
            ident = _as_str(node.args[0], env)
            if answer is None:
                continue
            units.append(Unit("%s:opt@%d" % (name, node.lineno), parent, node.lineno, "option",
                              answer, line=node.lineno, choice_id=ident,
                              flag=_kwarg(node, "flag", env), goto=_kwarg(node, "goto", env),
                              world_flag="ch1_" + (ident or "opt")))
            continue
        if text is None and fname not in ("scene",):
            continue
        who = _kwarg(node, "who", env) or _kwarg(node, "speaker", env)
        parent = _enclosing(scene=blocks, node=node, source=source)
        kind = _kind_of(text or "", who, bool(_kwarg(node, "choices", env)))
        if fname == "scene":
            continue
        units.append(Unit("%s:%s@%d" % (name, parent, node.lineno), parent, node.lineno, kind,
                          (text or "").strip(), line=node.lineno, speaker=who, character=who,
                          emotion=_kwarg(node, "emotion", env),
                          background=_kwarg(node, "bg", env) or _kwarg(node, "background", env),
                          music_intent=_kwarg(node, "music", env),
                          goto=_kwarg(node, "goto", env)))
    units += _load_banks(tree, env, name)
    units.sort(key=lambda u: u["line"])
    # The cast of a hand-written chapter is whoever it gives the floor to, not every asset id
    # the module happens to define.
    cast = {}
    for unit in units:
        speaker = unit.get("speaker")
        if speaker:
            cast.setdefault(str(speaker), str(speaker))
    # A hand-written chapter is a block of steps, not a world object: the world-field contract in
    # WORLD_SCHEMA.md does not apply to it.
    return Story(path, units, cast, {}, [], sorted(blocks), _referenced_by_engine(path),
                 has_world=False)


_ATTRIBUTION = re.compile(
    r"\b(говорит|сказал|сказала|спросил|спросила|ответил|ответила|повторяет|повторял|"
    r"повторила|думает|думал|шепчет|шепчет|кричит|вспоминает|замечает)\b")


def _kind_of(text, who, has_choices):
    """`story_pipeline._type_of` in spirit: a step with an attribution verb is narration even
    when it names who is on screen, which is how `story_chapter.py` is written."""
    if has_choices:
        return "choice"
    if not text:
        return "scene" if who else "wait"
    if _ATTRIBUTION.search(text):
        return "narration"
    return "dialogue" if who else "narration"


def _load_banks(tree, env, name):
    """Module-level line banks: a list of narration lines, or (question, [answers]) pairs.

    `local_story.py` keeps its offline lines in lists rather than in steps, and those lines are
    read by the player exactly like a step, so they are reviewed as units too.
    """
    out = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        target = node.targets[0] if node.targets else None
        if not isinstance(target, ast.Name):
            continue
        try:
            values = ast.literal_eval(node.value)
        except Exception:
            continue
        if not isinstance(values, list) or not values:
            continue
        if all(isinstance(v, str) for v in values):
            kind = "option" if "CHOICE" in target.id else (
                "dialogue" if "LINE" in target.id or "CHARACTER" in target.id else "narration")
            for index, value in enumerate(values):
                out.append(Unit("%s:%s[%d]" % (name, target.id, index), target.id, index, kind,
                                value.strip(), line=node.lineno))
            continue
        for index, pair in enumerate(values):
            if isinstance(pair, (list, tuple)) and pair and isinstance(pair[0], str):
                out.append(Unit("%s:%s[%d]" % (name, target.id, index), target.id, index,
                                "choice", pair[0].strip(), line=node.lineno))
                for pos, answer in enumerate(pair[1] or []):
                    if isinstance(answer, str):
                        out.append(Unit("%s:%s[%d].%d" % (name, target.id, index, pos),
                                        target.id, index, "option", answer.strip(),
                                        line=node.lineno))
    return out


# Container names carry no place, so a call inside `"steps": [` is not in a place called steps.
_GENERIC_KEYS = {"steps", "beats", "choices", "characters", "locations", "scenes", "visual",
                 "states", "lore", "goals", "secrets", "blocks", "chapters", "scenes_data"}


def _enclosing(scene, node, source):
    """The dict key the call sits under, read from the source text above the line."""
    lines = source.splitlines()
    for offset in range(min(node.lineno, len(lines)) - 1, -1, -1):
        match = re.match(r'\s*"([A-Za-z_][\w]*)"\s*:\s*[\[{]', lines[offset])
        if match and match.group(1) not in _GENERIC_KEYS:
            return match.group(1)
    return "root"


def _load_rpy(path):
    with io.open(path, encoding="utf-8") as fh:
        source = fh.read()
    units = []
    name = os.path.basename(path)
    for index, match in enumerate(_SAY_RE.finditer(source)):
        line = source.count("\n", 0, match.start()) + 1
        text = _unquote(match.group(2))
        speaker = match.group(1).strip()
        units.append(Unit("%s:say@%d" % (name, line), "say", line,
                          "dialogue" if speaker not in ("None", "n", "") else "narration",
                          text.strip(), line=line,
                          speaker=None if speaker == "None" else speaker))
    for match in _DEFINE_RE.finditer(source):
        literal_text, ok = _balanced_literal(source, match.end() - 1)
        if not ok:
            continue
        try:
            data = ast.literal_eval(literal_text)
        except Exception:
            continue
        offset = source.count("\n", 0, match.start()) + 1
        for step in _walk_steps(data):
            step = dict(step)
            step.setdefault("type", _guess_kind(step))
            units.append(_unit_from_dict("%s:%s#%d" % (name, match.group(1), offset + len(units)),
                                        match.group(1), offset + len(units), step, None,
                                        line=offset + len(units)))
    units.sort(key=lambda u: u["line"])
    return Story(path, units, {}, {}, [], [], _referenced_by_engine(path), has_world=False)


def _unquote(literal):
    try:
        return ast.literal_eval(literal)
    except Exception:
        return literal.strip('"')


def _balanced_literal(source, start):
    opener = source[start]
    closer = {"[": "]", "{": "}"}[opener]
    depth = 0
    in_string = None
    for index in range(start, len(source)):
        ch = source[index]
        if in_string:
            if ch == "\\":
                continue
            if ch == in_string:
                in_string = None
            continue
        if ch in "\"'":
            in_string = ch
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return source[start:index + 1], True
    return "", False


def _walk_steps(data):
    out = []
    if isinstance(data, dict):
        if isinstance(data.get("text"), str):
            out.append(data)
        for value in data.values():
            out.extend(_walk_steps(value))
    elif isinstance(data, list):
        for value in data:
            out.extend(_walk_steps(value))
    return out


def _referenced_by_engine(path):
    """Whether any game source names this file, which decides whether it can even be played."""
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    hits = []
    if os.path.dirname(os.path.abspath(path)).endswith(os.path.join("", "game")):
        # A module inside game/ is importable as itself; the engine only has to mention the
        # name, not the file name.
        try:
            with io.open(os.path.join(ROOT, "game", "engine.py"), encoding="utf-8") as fh:
                if re.search(r"\bimport\s+%s\b|\bfrom\s+%s\b" % (stem, stem), fh.read()):
                    hits.append("game/engine.py")
        except Exception:
            pass
    for base, dirs, files in os.walk(os.path.join(ROOT, "game")):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "absorbed", "vendor", "cache", "saves")]
        for filename in files:
            if not filename.endswith((".py", ".rpy", ".json", ".rpyc")):
                continue
            if filename.endswith(".rpyc"):
                continue
            full = os.path.join(base, filename)
            if os.path.abspath(full) == os.path.abspath(path):
                continue
            try:
                with io.open(full, encoding="utf-8") as fh:
                    if name in fh.read() or re.search(r"\b%s\b" % re.escape(stem), fh.read()):
                        hits.append(os.path.relpath(full, ROOT))
            except Exception:
                continue
    return hits


# --------------------------------------------------------------------- checks

def emotions():
    """The emotion list the prompt really offers, read from the game when it is importable."""
    game = os.path.join(ROOT, "game")
    if game not in sys_path():
        sys_path().append(game)
    try:
        import prompts_story
        return tuple(prompts_story.DEFAULT_EMOTIONS)
    except Exception:
        return FALLBACK_EMOTIONS


def sys_path():
    import sys
    return sys.path


def check_structure(story, game_dir=None):
    out = []

    def add(code, level, unit=None, text="", hint="", field=""):
        out.append(rt.Finding(code, level, where=(unit or {}).get("uid", story.name),
                              line=(unit or {}).get("line", 0), text=text, hint=hint,
                              field=field))

    if not story["units"]:
        add("struct.no_units", rt.WARN, hint="в файле нет ни scenes, ни steps, ни beats: "
            "это только описание мира, строк сюжета в нём нет")
    if not any(u["text"] for u in story["units"]):
        add("struct.no_text", rt.ERROR, hint="в файле нет текста вообще")

    for unit in story["units"]:
        kind = unit["kind"]
        text = unit["text"]
        if kind not in STEP_TYPES and kind != "option":
            add("struct.unknown_step", rt.ERROR, unit, text=text[:160],
                hint="неизвестный тип шага «%s», движок умеет %s"
                     % (kind, ", ".join(STEP_TYPES)), field="type")
        if kind in ("narration", "dialogue") and not text:
            add("struct.empty_text", rt.ERROR, unit, hint="шаг без текста", field="text")
        if kind == "choice" and not unit.get("choices"):
            add("struct.no_choices", rt.ERROR, unit, text=text[:160],
                hint="шаг типа choice без вариантов", field="choices")
        if kind == "choice":
            choices = unit.get("choices") or []
            if len(choices) < 2:
                add("struct.one_choice", rt.ERROR, unit, text=text[:160],
                    hint="у выбора %d вариант(а), нужен минимум %d" % (len(choices), 2),
                    field="choices")
            if len(choices) > 4:
                add("struct.many_choices", rt.WARN, unit, text=text[:160],
                    hint="%d вариантов выбора, %d-4 читаются легче" % (len(choices), 2),
                    field="choices")
            ids = [str(c.get("id")) for c in choices]
            if len(set(ids)) != len(ids):
                add("struct.dup_choice_id", rt.ERROR, unit, text=text[:160],
                    hint="повторяющиеся id вариантов: %s" % ", ".join(sorted(set(i for i in ids if ids.count(i) > 1))),
                    field="choices")
            for choice in choices:
                if not str(choice.get("text") or "").strip():
                    add("struct.empty_choice", rt.ERROR, unit,
                        hint="вариант %s без текста" % choice.get("id"), field="choices")
        if kind == "option" and not text:
            add("struct.empty_choice", rt.ERROR, unit, hint="вариант выбора без текста")

    _check_repetition(story, add)
    return out


def _check_repetition(story, add):
    seen_text = {}
    seen_kind = {}
    seen_skeleton = {}
    openers = {}
    for unit in story["units"]:
        text = unit["text"].strip()
        if not text:
            continue
        key = " ".join(text.lower().split())
        if key in seen_text:
            # A line repeated between two steps is a copy-paste; a line repeated between a
            # step and a choice option is often a deliberate callback the player recognises.
            add("style.dup_text", rt.WARN if "option" in (unit["kind"], seen_kind.get(key, ""))
                else rt.ERROR, unit, text=text[:160],
                hint="строка дословно повторяет %s" % seen_text[key])
        else:
            seen_text[key] = unit["uid"]
            seen_kind[key] = unit["kind"]
        for sentence in rt.sentences(text):
            skel = rt.skeleton(sentence)
            if len(skel.split()) >= 4:
                if skel in seen_skeleton and seen_skeleton[skel] != unit["uid"]:
                    add("style.dup_sentence", rt.WARN, unit, text=sentence[:160],
                        hint="та же конструкция, что в %s: «%s»"
                             % (seen_skeleton[skel], sentence.strip()[:70]))
                else:
                    seen_skeleton.setdefault(skel, unit["uid"])
        first = (rt.words(text)[:2])
        if len(first) == 2:
            opener = " ".join(w.lower() for w in first)
            openers.setdefault(opener, []).append(unit["uid"])
    for opener, uids in openers.items():
        if len(set(uids)) >= 4:
            add("style.opener_run", rt.INFO, text=opener,
                hint="«%s» начинает %d строк, прозвучит как приём" % (opener, len(set(uids))))
    seen_choice = {}
    for unit in story["units"]:
        for choice in unit.get("choices") or []:
            key = " ".join(str(choice.get("text") or "").lower().split())
            if key and key in seen_choice:
                add("style.dup_choice", rt.WARN, unit, text=str(choice.get("text"))[:160],
                    hint="вариант выбора повторяет %s" % seen_choice[key])
            elif key:
                seen_choice[key] = unit["uid"]
        if unit["kind"] == "option" and unit["text"]:
            key = " ".join(unit["text"].lower().split())
            if key in seen_choice and seen_choice[key] != unit["uid"]:
                add("style.dup_choice", rt.WARN, unit, text=unit["text"][:160],
                    hint="вариант выбора повторяет %s" % seen_choice[key])
            seen_choice.setdefault(key, unit["uid"])


def check_references(story, game_dir=None):
    out = []

    def add(code, level, unit=None, text="", hint="", field=""):
        out.append(rt.Finding(code, level, where=(unit or {}).get("uid", story.name),
                              line=(unit or {}).get("line", 0), text=text, hint=hint,
                              field=field))

    cast = story.get("characters") or {}
    locations = story.get("locations")
    allowed_emotions = emotions()
    blocks = set(story.get("blocks") or [])

    for unit in story["units"]:
        speaker = unit.get("speaker")
        if speaker and cast:
            known = speaker in cast
            if not known and isinstance(speaker, str):
                low = speaker.strip().lower()
                known = any(str(name or "").lower() == low for name in cast.values())
            if not known:
                add("ref.unknown_speaker", rt.ERROR, unit, text=unit["text"][:160],
                    hint="говорящий «%s» не найден в списке персонажей" % speaker, field="speaker")
        if unit.get("emotion") and unit["emotion"] not in allowed_emotions \
                and str(unit["emotion"]).lower() not in [e.lower() for e in allowed_emotions]:
            add("ref.unknown_emotion", rt.WARN, unit, text=unit["text"][:160],
                hint="эмоция «%s» не в списке движка: %s"
                     % (unit["emotion"], ", ".join(allowed_emotions)), field="emotion")
        if unit.get("goto") and blocks and unit["goto"] not in blocks:
            add("ref.unknown_goto", rt.ERROR, unit, text=unit["text"][:160],
                hint="переход «%s» ведёт в несуществующий блок; есть: %s"
                     % (unit["goto"], ", ".join(sorted(blocks)[:12])), field="goto")
        background = unit.get("background")
        if background and locations:
            if isinstance(locations, dict):
                if background not in locations:
                    add("ref.unknown_background", rt.WARN, unit, text=unit["text"][:160],
                        hint="фон «%s» не в locations" % background, field="background")
            elif isinstance(locations, list):
                ids = {str(x.get("id")) for x in locations if isinstance(x, dict)}
                if ids and background not in ids:
                    add("ref.unknown_background", rt.WARN, unit, text=unit["text"][:160],
                        hint="фон «%s» не в списке локаций" % background, field="background")
        for choice in unit.get("choices") or []:
            shape = [k for k in (choice.get("shape") or []) if k not in ("id", "text")]
            if shape:
                continue  # the engine check says exactly which shape is wrong
            if not choice.get("world_flag") and not choice.get("flag") and not choice.get("goto"):
                add("ref.choice_no_flag", rt.WARN, unit, text=str(choice.get("text"))[:120],
                    hint="вариант «%s» не ставит ни флаг, ни переход: выбор не запомнится"
                         % choice.get("id"), field="choices")

    # A choice that sets a flag nobody ever reads is a choice with no consequence. The whole
    # story is searched for the flag name, not just the choices.
    body = " ".join([u["text"] for u in story["units"]]
                    + [v for _, v in (story.get("fields") or [])])
    for unit in story["units"]:
        for choice in unit.get("choices") or []:
            flag = choice.get("world_flag") or choice.get("flag")
            if not flag or choice.get("goto"):
                continue
            if str(flag) not in body:
                add("ref.dead_flag", rt.WARN, unit, text=str(choice.get("text"))[:120],
                    hint="флаг «%s» ставится, но нигде не читается: выбор не влияет ни на что"
                         % flag, field="choices")

    if game_dir and cast:
        for cid, record in cast.items():
            if not isinstance(record, dict):
                continue
            states = (record.get("visual") or {}).get("states") or {}
            for state, rel in states.items():
                if isinstance(rel, str) and rel and not os.path.exists(os.path.join(game_dir, rel)):
                    add("ref.missing_asset", rt.WARN, text=str(rel),
                        hint="картинка %s для «%s» (%s) не найдена в game/" % (rel, cid, state),
                        field="characters.%s.visual.states.%s" % (cid, state))
    return out


def check_contract(story, game_dir=None):
    """Is the file even reachable, and does the engine read the fields it writes?"""
    out = []

    def add(code, level, unit=None, text="", hint="", field=""):
        out.append(rt.Finding(code, level, where=(unit or {}).get("uid", story.name),
                              line=(unit or {}).get("line", 0), text=text, hint=hint,
                              field=field))

    engine = os.path.join(ROOT, "game", "engine.py")
    if os.path.exists(engine):
        with io.open(engine, encoding="utf-8") as fh:
            source = fh.read()
        missing = [name for name in ENGINE_CONTRACT if name not in source]
        if missing:
            add("engine.contract_drift", rt.WARN,
                hint="в game/engine.py больше нет %s: контракт движка изменился, "
                     "обнови ENGINE_CONTRACT в tools/ru_world.py" % ", ".join(missing),
                field="engine.py")

    if not story.get("referenced"):
        add("engine.not_loaded", rt.WARN,
            hint="ни один файл в game/ не ссылается на %s: сюжет лежит, но движок его "
                 "не читает, нужен загрузчик или экспорт в world" % story.name)

    locations = story.get("locations")
    if isinstance(locations, list):
        add("engine.locations_not_map", rt.ERROR,
            hint="locations это список, а engine.py и local_story.py ждут словарь "
                 "{id: {description}}: (world.get('locations') or {}).get(...) сломается",
            field="locations")
    for field in (("title", "genre", "tone", "lore") if story.get("has_world") else ()):
        # A field can be a list, so its entries arrive as `genre[0]`, `genre[1]`.
        values = [v for k, v in story.get("fields") or []
                  if k.split("[")[0].rsplit(".", 1)[-1] == field]
        if not values:
            add("engine.missing_field", rt.INFO, hint="в мире нет поля «%s», WORLD_SCHEMA.md его требует"
                % field, field=field)

    # Flags the engine can read but never reads: a choice with no consequence anywhere.
    body = " ".join([u["text"] for u in story["units"]]
                    + [v for _, v in (story.get("fields") or [])])

    with_music = set()
    for unit in story["units"]:
        if unit.get("music_intent"):
            with_music.add(unit.get("scene"))
    without_music = 0
    for unit in story["units"]:
        keys = unit.get("keys") or []
        if unit["kind"] == "dialogue":
            if not unit.get("character"):
                add("engine.dialogue_no_character", rt.WARN, unit, text=unit["text"][:160],
                    hint="у шага-реплики нет поля character, спрайт не покажется "
                         "(engine._visual_character берёт step['character'])", field="character")
        if unit["kind"] == "choice":
            for choice in unit.get("choices") or []:
                shape = [k for k in (choice.get("shape") or []) if k not in ("id", "text")]
                if shape and not (choice.get("world_flag") or choice.get("flag") or choice.get("goto")):
                    hidden = _hidden_flag(choice, shape)
                    tail = ""
                    if hidden and hidden not in body:
                        tail = " Флаг «%s» больше нигде не встречается: выбор ничего не меняет." % hidden
                    add("engine.choice_flag_shape", rt.ERROR, unit,
                        text=str(choice.get("text"))[:120],
                        hint="движок читает %s, а здесь %s: флаг выбора молча потеряется.%s"
                             % (", ".join(CHOICE_KEYS), ", ".join(shape), tail),
                        field="choices")
                flag = choice.get("world_flag") or choice.get("flag")
                if flag and not choice.get("goto") and str(flag) not in body:
                    add("ref.dead_flag", rt.WARN, unit, text=str(choice.get("text"))[:120],
                        hint="флаг «%s» ставится, но нигде не читается: выбор не влияет ни на что"
                             % flag, field="choices")
        if keys and "type" not in keys and unit["kind"] in ("narration", "dialogue", "choice"):
            add("engine.no_type_field", rt.WARN, unit, text=unit["text"][:160],
                hint="нет поля type: story_pipeline определит его сам, а прямой проигрыватель "
                     "не поймёт, это реплика или рассказ", field="type")
        if unit["kind"] in ("narration", "dialogue") and not unit.get("background") \
                and story.get("locations") and not _scene_step_in(story, unit):
            add("engine.background_missing", rt.INFO, unit, text=unit["text"][:160],
                hint="фон не задан: экран останется с предыдущей сцены", field="background")
        if unit["kind"] in ("narration", "dialogue", "choice") \
                and not unit.get("music_intent") and unit.get("scene") not in with_music:
            without_music += 1
    if without_music:
        add("engine.no_music_intent", rt.INFO,
            hint="у %d строк нет music_intent: музыка для этих сцен не подберётся "
                 "автоматически" % without_music, field="music_intent")
    return out


def _hidden_flag(choice, shape):
    """A flag the author wrote under a key the engine never reads, e.g. `effects.world_flag`."""
    raw = choice.get("raw") or choice
    shape = shape or sorted(raw.keys())
    for key in shape:
        value = raw.get(key)
        if isinstance(value, dict):
            for name in ("world_flag", "flag"):
                if value.get(name):
                    return str(value[name])
        elif isinstance(value, str) and "flag" in key:
            return value
    return ""


def _scene_step_in(story, unit):
    for other in story["units"]:
        if other["kind"] == "scene" and other["line"] <= unit["line"]:
            if unit["line"] - other["line"] < 6:
                return True
    return False
