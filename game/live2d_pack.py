"""Live2D pack loader for Living VN.

Ren'Py 8.3.7 builds the available motion and expression names from the
`.model3.json` file of a Cubism model: a name is the lower-cased base name of a
`*.motion3.json` / `*.exp3.json` file with the model name prefix removed. This
module reproduces exactly that naming rule, so a `character.json` manifest can
map story-facing names (emotions, motions, outfits) onto Cubism names, and a
pack is only offered to the engine when its files are actually loadable.

The loader never constructs a Live2D displayable by itself: `build_displayable`
returns None whenever the platform, the settings, or the model make Live2D
unusable, and the caller falls back to sprites.
"""

import json
import os
import re

try:
    import renpy
except Exception:  # pragma: no cover - the offline smoke tests run without renpy
    renpy = None

try:
    import renpy.loader as loader
except Exception:  # pragma: no cover
    loader = None

try:
    import renpy.config as config
except Exception:  # pragma: no cover
    class _Config(object):
        gamedir = os.path.dirname(os.path.abspath(__file__))

    config = _Config()

MOTION_SUFFIX = "motion3.json"
EXPRESSION_SUFFIX = "exp3.json"
RESERVED_NAMES = ("still", "null")
IDLE_NAMES = ("idle", "still", "stand", "breath", "loop")

_AVAILABILITY = None
_PACK_CACHE = {}


# ------------------------------------------------------------------ platform


def live2d_available():
    """True when this Ren'Py build can initialize Cubism at all."""
    global _AVAILABILITY
    if _AVAILABILITY is None:
        if renpy is None or not hasattr(renpy, "has_live2d"):
            _AVAILABILITY = False
        else:
            try:
                _AVAILABILITY = bool(renpy.has_live2d())
            except Exception:
                _AVAILABILITY = False
    return _AVAILABILITY


def reset_availability():
    global _AVAILABILITY
    _AVAILABILITY = None
    _PACK_CACHE.clear()


def _gamedir():
    return getattr(config, "gamedir", os.path.dirname(os.path.abspath(__file__)))


def _loadable(path):
    if not path:
        return False
    if renpy is not None:
        try:
            if renpy.loadable(path):
                return True
        except Exception:
            pass
    return os.path.isfile(os.path.join(_gamedir(), str(path)))


def _read_json(path):
    """Read JSON from the game directory or from the game archive."""
    if renpy is not None and loader is not None:
        try:
            with loader.load(path, directory="images") as fh:
                return json.loads(fh.read().decode("utf-8", "ignore"))
        except Exception:
            pass
    try:
        with open(os.path.join(_gamedir(), str(path)), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# --------------------------------------------------------------- model naming


def model_name_of(model_path):
    """The name Ren'Py uses to strip a redundant file name prefix."""
    base = str(model_path).replace("\\", "/").rstrip("/")
    return base.rpartition("/")[2].partition(".")[0].lower()


def cubism_name(file_name, model_name):
    """Reimplementation of Ren'Py's motion/expression naming rule."""
    name = str(file_name).replace("\\", "/").lower().rpartition("/")[2].partition(".")[0]
    prefix, _, suffix = name.partition("_")
    if prefix == model_name and suffix:
        name = suffix
    return name


def _walk_file_refs(node, found):
    if isinstance(node, list):
        for item in node:
            _walk_file_refs(item, found)
        return
    if not isinstance(node, dict):
        return
    if isinstance(node.get("File"), str):
        found.append(node)
        return
    for value in node.values():
        _walk_file_refs(value, found)


def _base_of(model_path):
    base = str(model_path).replace("\\", "/").rstrip("/").rpartition("/")[0]
    return (base + "/") if base else ""


def read_model(model_path):
    """Return the parsed `.model3.json`, or None when it is unusable."""
    if not model_path or not str(model_path).lower().endswith(".model3.json"):
        return None
    if not _loadable(model_path):
        return None
    data = _read_json(model_path)
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("FileReferences"), dict):
        return None
    return data


def _collect(data, model_name, base):
    """Loadable motion and expression names, mirroring Ren'Py's own scan."""
    motions = {}
    expressions = {}
    refs = data.get("FileReferences", {})

    entries = []
    _walk_file_refs(refs.get("Motions", {}), entries)
    for item in entries:
        name = cubism_name(item["File"], model_name)
        path = base + item["File"]
        if name in motions or name in RESERVED_NAMES:
            continue
        if _loadable(path):
            motions[name] = path

    entries = []
    _walk_file_refs(refs.get("Expressions", []), entries)
    for item in entries:
        name = cubism_name(item["File"], model_name)
        path = base + item["File"]
        if name in expressions or name in RESERVED_NAMES or name in motions:
            continue
        if _loadable(path):
            expressions[name] = path
    return motions, expressions


def load_pack(visual):
    """Resolve a `character.visual` block into a usable Live2D pack description.

    Returns a dict with `ok`, `model`, `motions`, `expressions`, `aliases`,
    `nonexclusive` and `issues`. Nothing here raises.
    """
    visual = visual if isinstance(visual, dict) else {}
    model_path = visual.get("model")
    pack = {
        "ok": False,
        "model": None,
        "model_name": "",
        "motions": {},
        "expressions": {},
        "aliases": {},
        "outfit_expressions": [],
        "nonexclusive": [],
        "issues": [],
    }
    if not model_path:
        pack["issues"].append("no_model")
        return pack

    data = read_model(model_path)
    if data is None:
        pack["issues"].append("model_unreadable")
        return pack

    model_name = model_name_of(model_path)
    base = _base_of(model_path)
    motions, expressions = _collect(data, model_name, base)
    pack["model"] = model_path
    pack["model_name"] = model_name
    pack["motions"] = motions
    pack["expressions"] = expressions
    if not motions and not expressions:
        pack["issues"].append("no_motions_or_expressions")

    def resolve(value):
        """Map a manifest value onto a Cubism name, or onto an alias."""
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip().replace("\\", "/")
        name = text.rpartition("/")[2]
        name = os.path.splitext(name)[0] if name.lower().endswith((".exp3.json", ".motion3.json")) else name
        name = name.lower()
        for table in (motions, expressions):
            if name in table:
                return table[name]
        hints = (visual.get("files") or {})
        for hint in hints.values():
            if isinstance(hint, str) and hint.replace("\\", "/").endswith(text):
                stem = os.path.splitext(text.rpartition("/")[2])[0].lower()
                for table in (motions, expressions):
                    if stem in table:
                        return table[stem]
        return None

    def add_alias(alias, target):
        if not alias or not target or alias in RESERVED_NAMES:
            return False
        if alias in motions or alias in expressions or alias in pack["aliases"]:
            return False
        if alias != target:
            pack["aliases"][alias] = target
        return True

    # Story-facing expressions.
    for alias, value in (visual.get("expressions") or {}).items():
        target = resolve(value)
        if target is None:
            pack["issues"].append("expression_unresolved:" + str(alias))
            continue
        add_alias(str(alias), target)

    # Story-facing motions.
    for alias, value in (visual.get("motions") or {}).items():
        target = resolve(value)
        if target is None:
            pack["issues"].append("motion_unresolved:" + str(alias))
            continue
        add_alias(str(alias), target)

    # Outfits are part-visibility toggles. Cubism authors them as expression
    # files, and Ren'Py only blends several of those at once when they are
    # declared non-exclusive, so every declared outfit is registered as one.
    for alias, value in (visual.get("outfits") or {}).items():
        if isinstance(value, dict):
            # Parameter-driven outfit: the model needs an update function, which
            # the engine does not build. Keep it visible in the catalog and let
            # the character use its sprites.
            pack["issues"].append("outfit_parameters_unsupported:" + str(alias))
            continue
        target = resolve(value)
        if target is None:
            pack["issues"].append("outfit_unresolved:" + str(alias))
            continue
        alias = str(alias)
        if add_alias(alias, target) and alias not in pack["outfit_expressions"]:
            pack["outfit_expressions"].append(alias)

    for name in (visual.get("aliases") or {}):
        alias = str(name)
        if alias in pack["aliases"] or alias in motions or alias in expressions:
            continue
        if alias in RESERVED_NAMES:
            continue
        pack["issues"].append("alias_shadowed:" + alias)

    pack["nonexclusive"] = list(pack["outfit_expressions"])
    for name in (visual.get("nonexclusive") or []):
        alias = str(name)
        if alias in pack["nonexclusive"]:
            continue
        target = pack["aliases"].get(alias) or (expressions.get(alias) and alias)
        if target:
            pack["nonexclusive"].append(alias)

    pack["ok"] = True
    return pack


def get_pack(visual):
    """Cached `load_pack`, keyed by the model path and mapping sizes."""
    if not isinstance(visual, dict):
        return load_pack(visual)
    key = (
        visual.get("model"),
        len(visual.get("expressions") or {}),
        len(visual.get("motions") or {}),
        len(visual.get("outfits") or {}),
        len(visual.get("nonexclusive") or []),
    )
    if key in _PACK_CACHE:
        return _PACK_CACHE[key]
    pack = load_pack(visual)
    _PACK_CACHE[key] = pack
    return pack


def expression_for(pack, emotion, outfit=None):
    """The expression name to show for an emotion, or None to keep the model."""
    if not pack or not pack.get("ok"):
        return None
    for candidate in (emotion, "neutral", "normal"):
        if not candidate:
            continue
        if candidate in pack["expressions"]:
            return candidate
        if pack["aliases"].get(candidate) in pack["expressions"]:
            return candidate
    if outfit:
        return None
    return None


def motion_for(pack, motion):
    """The motion name to play, or None. `loop` reflects whether it is idle."""
    if not pack or not pack.get("ok") or not motion:
        return None, False
    for candidate in (str(motion), "idle"):
        if candidate in pack["motions"]:
            return candidate, candidate in IDLE_NAMES
        alias = pack["aliases"].get(candidate)
        if alias in pack["motions"]:
            return alias, alias in IDLE_NAMES
        if candidate in pack["expressions"]:
            return None, False
    return None, False


def build_displayable(visual, emotion=None, motion=None, outfit=None):
    """Build a Live2D displayable, or return None so the caller uses sprites.

    Returns None when Live2D is unavailable, disabled, or when the model cannot
    be constructed. It never raises.
    """
    if not isinstance(visual, dict):
        return None
    if str(visual.get("type") or "").strip().lower() != "live2d":
        return None
    if renpy is None or not live2d_available():
        return None

    pack = get_pack(visual)
    if not pack.get("ok") or not pack.get("model"):
        return None

    if not _loadable(pack["model"]):
        return None

    displayable_class = getattr(store_module(), "Live2D", None)
    if displayable_class is None:
        return None

    kwargs = {
        "base": _number(visual.get("base"), 1.0),
        "height": _number(visual.get("height"), 0.0),
        "loop": True,
        "seamless": visual.get("seamless") if isinstance(visual.get("seamless"), (bool, list, set, tuple)) else None,
    }
    if visual.get("zoom") is not None:
        kwargs["zoom"] = _number(visual.get("zoom"), 1.0)
    if visual.get("top") is not None:
        kwargs["top"] = _number(visual.get("top"), 0.0)
    if kwargs["height"] <= 0:
        kwargs.pop("height")
    if pack["aliases"]:
        kwargs["aliases"] = dict(pack["aliases"])
    if pack["nonexclusive"]:
        kwargs["nonexclusive"] = list(pack["nonexclusive"])

    motion_name, is_idle = motion_for(pack, motion)
    if motion_name:
        kwargs["motions"] = [motion_name]
    kwargs["loop"] = True if is_idle or not motion_name else False

    expression = expression_for(pack, emotion)
    if expression:
        kwargs["expression"] = expression

    try:
        return displayable_class(pack["model"], **kwargs)
    except Exception:
        return None


def _number(value, default):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result:  # NaN
        return default
    return result


def store_module():
    """The Ren'Py store, where `Live2D` lives. None outside Ren'Py."""
    if renpy is None:
        return None
    try:
        import renpy.store as store
        return store
    except Exception:
        return None


def describe(pack):
    """A short human-readable summary for the asset inspector."""
    if not pack or not pack.get("ok"):
        return "live2d недоступен: " + ", ".join((pack or {}).get("issues", []) or ["нет модели"])
    return "модель %s • движений %d • выражений %d • алиасов %d • гардероб %s" % (
        pack.get("model_name") or pack.get("model"),
        len(pack.get("motions") or {}),
        len(pack.get("expressions") or {}),
        len(pack.get("aliases") or {}),
        ", ".join(pack.get("outfit_expressions") or []) or "—",
    )
