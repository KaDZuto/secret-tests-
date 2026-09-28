import json
import os

import renpy
import renpy.config as config

AUDIO_EXT = (".ogg", ".opus", ".mp3", ".wav")

## Папки внутри игры, которые считаются музыкой. `renpy.list_files()` отдаёт весь игровой
## каталог, так что фильтр -- это префикс: раньше здесь были только `music/` и `absorbed/`,
## и два трека из `audio/` не попадали в каталог никогда.
PACKAGED_DIRS = ("music/", "audio/", "sound/", "absorbed/")

## Треки, которые лежат в репозитории. Теги у них проставлены руками, а не выводятся из
## имени файла: каталог должен что-то значить ещё до того, как игрок указал свои папки, а
## `choose_track` ищет именно по тегам. Порядок -- порядок включения по умолчанию.
BUNDLED_TRACKS = (
    ("audio/daylight.wav", ["calm"]),
    ("music/nostalgia_daylight.wav", ["nostalgia", "calm"]),
    ("audio/tension.wav", ["tension"]),
    ("music/mystery_tension.wav", ["mystery", "tension"]),
)

## Запасной тег для файлов, имя которых ничего не говорит: тише молчания.
DEFAULT_TAGS = ["calm"]

KEYWORDS = {
    "calm": ("calm", "quiet", "ambient", "peace", "morning", "night", "спокой", "утро", "ночь"),
    "romance": ("love", "romance", "date", "heart", "sweet", "любов", "романтик", "свидан"),
    "nostalgia": ("nostalgia", "summer", "memory", "old", "retro", "лето", "ностальг", "памят", "винтаж"),
    "tension": ("tension", "danger", "chase", "urgent", "battle", "fight", "опас", "погон", "напряж"),
    "mystery": ("mystery", "myster", "secret", "clue", "strange", "investigation", "тайн", "загад", "расслед"),
    "sad": ("sad", "sorrow", "tear", "lonely", "melancholy", "goodbye", "печал", "слез", "одино", "прощан"),
    "comedy": ("fun", "funny", "comedy", "comic", "school", "daily", "комед", "школ", "повседнев"),
    "horror": ("horror", "dark", "fear", "creepy", "nightmare", "ужас", "страх", "мрач", "кошмар"),
    "triumph": ("victory", "triumph", "finale", "win", "hero", "побед", "финал", "герой"),
}


def _tags(text):
    low = text.lower()
    result = []
    for tag, words in KEYWORDS.items():
        if any(word in low for word in words):
            result.append(tag)
    return result or ["calm"]


def _exists(path):
    """True when the game can actually load this file (archive or loose file)."""
    try:
        if renpy.loadable(path):
            return True
    except Exception:
        pass
    gamedir = getattr(config, "gamedir", "") or ""
    return bool(gamedir) and os.path.isfile(os.path.join(gamedir, str(path)))


def bundled_entries():
    """The shipped tracks, hand-tagged, without asking the runtime for anything."""
    entries = []
    for path, tags in BUNDLED_TRACKS:
        entries.append({
            "path": path,
            "name": os.path.basename(path),
            "source": "bundled",
            "tags": list(tags),
        })
    return entries


def scan_music(paths=None):
    paths = paths or []
    entries = []
    seen = set()

    def add(entry):
        path = entry.get("path")
        if not path or path in seen:
            return
        seen.add(path)
        entries.append(entry)

    # 1. Shipped tracks first: a later discovery of the same file must not overwrite the
    #    hand-written tags with whatever the file name happens to contain.
    for entry in bundled_entries():
        if _exists(entry["path"]):
            add(entry)

    # 2. Everything else that ships with the game, whether it is loose or in an archive.
    try:
        for filename in renpy.list_files():
            lower = filename.lower()
            if not lower.endswith(AUDIO_EXT) or not lower.startswith(PACKAGED_DIRS):
                continue
            add({
                "path": filename,
                "name": os.path.basename(filename),
                "source": "absorbed" if lower.startswith("absorbed/") else "packaged",
                "tags": _tags(filename),
            })
    except Exception:
        pass

    # 3. Folders the player pointed at in the creator screen.
    for root in paths:
        root = root.strip().strip('"')
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for filename in files:
                if filename.lower().endswith(AUDIO_EXT):
                    full = os.path.join(dirpath, filename)
                    try:
                        stat = os.stat(full)
                        size = stat.st_size
                        mtime = int(stat.st_mtime)
                    except OSError:
                        size = 0
                        mtime = 0
                    add({
                        "path": full,
                        "name": filename,
                        "source": "external",
                        "tags": _tags(full),
                        "size": size,
                        "mtime": mtime,
                    })

    return entries


def save_catalog(catalog):
    path = os.path.join(config.gamedir, "data", "music_catalog.json")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(catalog, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return path


def load_catalog():
    path = os.path.join(config.gamedir, "data", "music_catalog.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def choose_track(catalog, intent):
    """The track for a scene's `music_intent`.

    `none` -- это просьба сцены оставить канал в покое. Всё остальное, включая пустой
    намеренный и пустой каталог, заканчивается звуком, а не тишиной: сначала ищется тег
    из намерения, потом спокойный фон, и только потом первый попавшийся трек. Пустой
    каталог дополняется треками, которые лежат в игре.
    """
    intent = str(intent or "").strip().lower()
    if intent == "none":
        return None
    tracks = [x for x in (catalog or []) if isinstance(x, dict) and x.get("path")]
    if not tracks:
        tracks = bundled_entries()
    if not tracks:
        return None
    if intent:
        for item in tracks:
            if intent in [str(t).lower() for t in item.get("tags") or []]:
                return item["path"]
    for item in tracks:
        if "calm" in [str(t).lower() for t in item.get("tags") or []]:
            return item["path"]
    return tracks[0]["path"]


def analyze_catalog_with_ai(catalog, settings):
    """Lightweight metadata-first analysis. Audio is not uploaded in the MVP.

    The model only receives track names/paths and existing heuristic tags. This is
    intentional: it keeps the game cheap and compatible with small/old devices.
    """
    if not catalog:
        return []

    from ai_client import call_chat, _extract_json

    compact = []
    for item in catalog[:160]:
        compact.append({
            "path": item.get("path", ""),
            "name": item.get("name", ""),
            "heuristic_tags": item.get("tags", []),
        })

    system = """
Ты — музыкальный редактор визуальной новеллы.
По названию и пути аудиофайлов оцени предполагаемое назначение треков.
Не придумывай фактических свойств аудио: делай вывод только из доступных названий/путей.
Верни только JSON.
"""
    prompt = f"""
Для каждого трека верни один объект с path и tags из набора:
calm, romance, nostalgia, tension, mystery, sad, comedy, horror, triumph.
Добавь energy от 0 до 1 и краткий use_case.
Не удаляй path.

TRACKS:
{json.dumps(compact, ensure_ascii=False)}

SCHEMA:
{{"tracks":[{{"path":"...","tags":["calm"],"energy":0.5,"use_case":"..."}}]}}
"""
    result = _extract_json(call_chat(prompt, system, settings, max_tokens=min(6000, 500 + len(compact) * 45)))
    analyzed = result.get("tracks", []) if isinstance(result, dict) else []

    by_path = {x.get("path"): x for x in analyzed if isinstance(x, dict)}
    merged = []
    for item in catalog:
        copy = dict(item)
        ai = by_path.get(item.get("path"))
        if ai:
            if isinstance(ai.get("tags"), list) and ai["tags"]:
                copy["tags"] = [str(x) for x in ai["tags"]]
            if isinstance(ai.get("energy"), (int, float)):
                copy["energy"] = max(0.0, min(1.0, float(ai["energy"])))
            if isinstance(ai.get("use_case"), str):
                copy["use_case"] = ai["use_case"][:300]
            copy["analysis"] = "ai_metadata"
        merged.append(copy)
    return merged
