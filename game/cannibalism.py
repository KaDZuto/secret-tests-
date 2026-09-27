"""Local game-asset absorption for Living VN.

The importer intentionally works only with files/folders the user can access directly.
It does not decrypt, bypass DRM, unpack proprietary protected archives, or execute source code.
Imported assets are tagged as third-party/unverified and are excluded from portable world export
unless the user explicitly enables it.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime

try:
    import renpy.config as config
except ImportError:
    class _Config:
        gamedir = os.path.dirname(os.path.abspath(__file__))
    config = _Config()

try:
    import rpa_index
except ImportError:  # pragma: no cover - the module always sits next to this one
    rpa_index = None


IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
AUDIO_EXT = (".ogg", ".opus", ".mp3", ".wav", ".flac", ".m4a")
# Cubism 4 is the only flavour Ren'Py 8.x can display, so only these count as
# usable Live2D.
LIVE2D_EXT = (".model3.json", ".moc3", ".physics3.json", ".exp3.json", ".motion3.json")
# Cubism 2 (the older Live2D framework, still shipped by a lot of models) is real
# Live2D, but Ren'Py cannot load it: it wants `.model3.json` + `.moc3`. Catalogued
# separately so the report can say "needs conversion" instead of "not Live2D".
CUBISM2_EXT = (".model.json", ".moc", ".physics.json", ".exp.json", ".mtn")
TEXT_EXT = (".rpy", ".json", ".txt", ".csv", ".tsv", ".yaml", ".yml", ".xml")
RPA_EXT = ".rpa"
# MMD is a genuinely different format and Ren'Py cannot display it at all.
MMD_EXT = (".pmx", ".pmd", ".vmd", ".vpd")
# A model kind that Ren'Py can neither display nor use as a sprite.
NON_USABLE_MODEL_KINDS = ("other_model", "live2d2")
IGNORE_DIRS = {
    ".git", "cache", "caches", "tmp", "temp", "save", "saves", "persistent",
    "__pycache__", ".renpy", "screenshots", "logs"
}

CATEGORY_KEYWORDS = {
    "character": ("char", "character", "portrait", "sprite", "person", "hero", "heroine", "персонаж", "портрет"),
    "background": ("background", "back", "bg", "scene", "location", "фон", "локац"),
    "music": ("music", "bgm", "ost", "song", "soundtrack", "музык", "саундтрек"),
    "voice": ("voice", "voices", "speech", "dialogue", "voiceover", "озвуч", "голос"),
    "live2d": ("live2d", "cubism", "model3", "motion3", "exp3", "physics3", ".moc3"),
    "live2d2": ("live2d", "cubism", "model.json", "moc", "exp", "physics", "animator"),
}


def _slug(text):
    value = re.sub(r"[^0-9A-Za-zА-Яа-я_-]+", "_", str(text)).strip("_")
    return (value[:80] or "source")


def _kind_for(path):
    low = str(path).lower()
    ext = os.path.splitext(low)[1]
    parts = _parts_of(path)
    if low.endswith(LIVE2D_EXT):
        return "live2d"
    if low.endswith(CUBISM2_EXT):
        return "live2d2"
    if low.endswith(MMD_EXT):
        return "other_model"
    if ext in IMAGE_EXT:
        parts = _parts_of(path)
        # `gui/...` and friends are interface art, not characters.
        if any(part in UI_DIRS for part in parts[:-1]):
            return "gui_art"
        # Structure first: a file inside `images/cg/` is cutscene art even when its
        # name contains a word like "scene" that would match a location keyword.
        if any(part in SCENE_ART_DIRS for part in parts[:-1]):
            return "scene_art"
        if any(k in low for k in CATEGORY_KEYWORDS["background"]):
            return "background"
        return "character_art"
    if ext in AUDIO_EXT:
        return "music" if any(k in low for k in CATEGORY_KEYWORDS["music"]) else "audio"
    if ext in TEXT_EXT:
        if any(k in low for k in CATEGORY_KEYWORDS["character"]):
            return "character_data"
        return "text_data"
    return "other"


def _score_candidate(path, kind):
    low = str(path).lower()
    score = 0
    words = CATEGORY_KEYWORDS.get(kind, ())
    for word in words:
        if word in low:
            score += 2
    if "sprite" in low or "portrait" in low:
        score += 2
    if kind == "live2d" and low.endswith(".model3.json"):
        score += 5
    if kind == "live2d2" and low.endswith(".model.json"):
        # The Cubism 2 entry point, so the pack is at least identified.
        score += 5
    if kind == "character_data" and ("character" in low or "char" in low):
        score += 4
    return min(score, 20)


def _file_info(full_path, display_path, source):
    try:
        size = os.path.getsize(full_path)
        mtime = int(os.path.getmtime(full_path))
    except OSError:
        size, mtime = 0, 0
    kind = _kind_for(display_path)
    return {
        "id": hashlib.sha1((source + "|" + display_path).encode("utf-8", "ignore")).hexdigest()[:16],
        "path": display_path,
        "source": source,
        "kind": kind,
        "size": size,
        "mtime": mtime,
        "score": _score_candidate(display_path, kind),
        "selected": False,
    }


def _scan_archive(archive_path, rel_archive, result, max_files, max_file_mb, max_archive_entries=4000):
    """List the usable entries of one standard `.rpa` container.

    A protected or unknown container is refused and reported, never unpacked.
    """
    if rpa_index is None:
        return
    try:
        index = rpa_index.read_index(archive_path)
    except rpa_index.ArchiveRefused as exc:
        result["warnings"].append("archive_refused:%s:%s" % (rel_archive, str(exc)[:80]))
        return
    except Exception as exc:
        result["warnings"].append("archive_unreadable:%s:%s" % (rel_archive, str(exc)[:80]))
        return

    result["archives"].append({
        "path": rel_archive,
        "entries": len(index),
        "bytes": sum(length for _, length, _ in index.values()),
    })
    for name in sorted(index):
        kind = _kind_for(name)
        if kind == "other":
            continue
        if len(result["files"]) >= max_files:
            result["warnings"].append("file_limit_reached")
            return
        length = index[name][1]
        if length > max_file_mb * 1024 * 1024:
            continue
        result["files"].append({
            "id": hashlib.sha1((archive_path + "|" + name).encode("utf-8", "ignore")).hexdigest()[:16],
            "path": name,
            "source": archive_path,
            "archive": rel_archive,
            "kind": kind,
            "size": length,
            "mtime": 0,
            "score": _score_candidate(name, kind),
            "selected": False,
        })


def scan_source(source_path, max_files=5000, max_file_mb=300, include_archives=True):
    """Scan a directly accessible folder or ZIP without executing anything."""
    source_path = os.path.abspath(os.path.expanduser(str(source_path).strip().strip('"')))
    result = {
        "source": source_path,
        "source_type": "folder" if os.path.isdir(source_path) else "zip" if zipfile.is_zipfile(source_path) else "unknown",
        "scanned_at": datetime.utcnow().isoformat() + "Z",
        "files": [],
        "archives": [],
        "warnings": [],
    }
    if os.path.isdir(source_path):
        for root, dirs, files in os.walk(source_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for filename in files:
                full = os.path.join(root, filename)
                rel = os.path.relpath(full, source_path)
                if include_archives and filename.lower().endswith(RPA_EXT):
                    _scan_archive(full, rel, result, max_files, max_file_mb)
                    continue
                if len(result["files"]) >= max_files:
                    result["warnings"].append("file_limit_reached")
                    return result
                try:
                    if os.path.getsize(full) > max_file_mb * 1024 * 1024:
                        continue
                except OSError:
                    continue
                info = _file_info(full, rel, source_path)
                if info["kind"] != "other":
                    result["files"].append(info)
        return result

    if zipfile.is_zipfile(source_path):
        try:
            with zipfile.ZipFile(source_path) as zf:
                for item in zf.infolist():
                    if item.is_dir():
                        continue
                    name = item.filename.replace("\\", "/")
                    if any(part in IGNORE_DIRS for part in name.split("/")[:-1]):
                        continue
                    if len(result["files"]) >= max_files:
                        result["warnings"].append("file_limit_reached")
                        break
                    if item.file_size > max_file_mb * 1024 * 1024:
                        continue
                    kind = _kind_for(name)
                    if kind != "other":
                        result["files"].append({
                            "id": hashlib.sha1((source_path + "|" + name).encode("utf-8", "ignore")).hexdigest()[:16],
                            "path": name,
                            "source": source_path,
                            "kind": kind,
                            "size": item.file_size,
                            "mtime": 0,
                            "score": _score_candidate(name, kind),
                            "selected": False,
                        })
        except (OSError, zipfile.BadZipFile) as exc:
            result["warnings"].append("zip_error: " + str(exc))
        return result

    result["warnings"].append("unsupported_source")
    return result


def _read_text_candidate(source, rel_path, archive_rel=None, limit=3500):
    try:
        if archive_rel and rpa_index is not None:
            data = rpa_index.read_entry(source, rel_path)
            return data[:limit].decode("utf-8", "ignore")
        if os.path.isdir(source):
            full = os.path.join(source, rel_path)
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                return fh.read(limit)
        if zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as zf:
                with zf.open(rel_path) as fh:
                    return fh.read(limit).decode("utf-8", "ignore")
    except Exception:
        return ""
    return ""


def _character_hints(text):
    hints = []
    for match in re.finditer(r"(?:define|default)\s+([A-Za-zА-Яа-я_][\wА-Яа-я_]*)\s*=\s*Character\(\s*[\"']([^\"']+)", text):
        hints.append({"id": match.group(1), "name": match.group(2)})
    return hints[:30]


def build_absorber_packet(scan):
    files = []
    text_samples = []
    character_hints = []
    for item in scan.get("files", []):
        files.append({
            "id": item["id"],
            "path": item["path"],
            "kind": item["kind"],
            "size": item.get("size", 0),
            "score": item.get("score", 0),
            "archive": item.get("archive"),
        })
        if item["kind"] in ("character_data", "text_data") and len(text_samples) < 12:
            sample = _read_text_candidate(item["source"], item["path"], item.get("archive"))
            if sample:
                text_samples.append({"path": item["path"], "text": sample})
                character_hints.extend(_character_hints(sample))
    unique_hints = {}
    for hint in character_hints:
        unique_hints[hint["id"]] = hint
    return {
        "files": files,
        "text_samples": text_samples,
        "character_hints": list(unique_hints.values())[:30],
        "archives": scan.get("archives", []),
    }


def assess_absorption(scan, settings):
    from ai_client import call_chat, _extract_json
    packet = build_absorber_packet(scan)
    if not packet["files"]:
        return {"selected_ids": [], "characters": [], "asset_roles": [], "summary": "Ничего пригодного для поглощения не найдено."}

    system = """
Ты — AI-поглотитель и оценщик ресурсов для Living VN.
Ты анализируешь файлы уже доступной локальной игры, но не переносишь её сюжет.
Твоя задача — выбрать полезные визуальные/аудио/данные ресурсы и отдельно вывести кандидатов-персонажей.
Не утверждай неизвестные факты: характер персонажа выводи только из доступного текста/имени/структуры.
Не выбирай исполняемый код, сохранения, DRM-обход или системные файлы.
Верни только JSON.
"""
    prompt = f"""
Источник: {scan.get('source')}
Файлы:
{json.dumps(packet['files'][:1200], ensure_ascii=False)}

Небольшие текстовые образцы:
{json.dumps(packet['text_samples'], ensure_ascii=False)}

Явно найденные в исходнике имена персонажей:
{json.dumps(packet.get('character_hints', []), ensure_ascii=False)}

Верни:
{{
  "selected_ids": ["..."],
  "asset_roles": [{{"id":"...","role":"character_art|background|music|voice|live2d|character_data|other","reason":"..."}}],
  "characters": [{{"id":"source_character_1","name":"...","personality":"...","goals":["..."],"visual_asset_ids":["..."]}}],
  "summary":"..."
}}
"""
    result = _extract_json(call_chat(prompt, system, settings, model_override=str(settings.get("absorber_model", "")).strip() or None, max_tokens=4200))
    if not isinstance(result, dict):
        raise ValueError("Absorber returned invalid JSON")
    result.setdefault("selected_ids", [])
    result.setdefault("characters", [])
    result.setdefault("asset_roles", [])
    result.setdefault("summary", "")
    return result


def _source_reader(source):
    if os.path.isdir(source):
        return "folder"
    if zipfile.is_zipfile(source):
        return "zip"
    return "unknown"


def _copy_member(source, rel_path, destination, item=None):
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    item = item or {}
    archive_rel = item.get("archive")
    if archive_rel:
        # The entry lives inside a standard .rpa container, read-only.
        archive_path = os.path.join(source, archive_rel)
        data = rpa_index.read_entry(archive_path, rel_path)
        with open(destination, "wb") as fh:
            fh.write(data)
        return
    if os.path.isdir(source):
        shutil.copy2(os.path.join(source, rel_path), destination)
        return
    with zipfile.ZipFile(source) as zf:
        with zf.open(rel_path) as src, open(destination, "wb") as dst:
            shutil.copyfileobj(src, dst)


# Interface and engine folders. Their images are real files, but they are not
# characters: a "scrollbar pack" would be noise in the catalogue. Ren'Py itself
# keeps its own chrome in `gui/`, and every game follows some subset of these.
UI_DIRS = {
    "gui", "renpy", "common", "menu", "overlay", "namebox", "textbox", "window",
    "notify", "button", "bar", "scrollbar", "slider", "mouse", "frame", "skip",
    "nvl", "placeholder", "phone", "credits", "end", "filter", "filters",
    "outline", "roundrect", "save_load", "settings", "title_menu", "o_rly", "game",
}
# Scene and event art: cutscenes, spritesheets, gallery images. Worth keeping as
# art, but not a character, so they never become a pack. Container names such as
# `images` or `art` are not here: they only say "files live under me".
SCENE_ART_DIRS = {
    "cg", "misc", "anim", "gallery", "cards", "cards_contest", "maps", "day",
    "night", "sunset", "op", "prologue",
}
# Folders that only say "characters live here", so the real character name has to
# come from the file name instead of the parent directory.
GENERIC_ART_DIRS = {
    "sprites", "sprite", "char", "chars", "character", "characters",
    "portrait", "portraits", "character_art", "images", "img", "art", "assets",
    "image", "resource", "resources", "data", "files",
}
# A character is a folder of states, not a single picture. Below this a folder is
# treated as ordinary art, which keeps a lone `logo.png` from becoming a character.
MIN_CHARACTER_STATES = 4


def _parts_of(path):
    return [p.lower() for p in str(path).replace("\\", "/").split("/") if p]


def _is_blocked_art_path(path):
    """True when the file lives in interface or cutscene art, so never a character."""
    parts = _parts_of(path)
    return any(p in UI_DIRS or p in SCENE_ART_DIRS for p in parts[:-1])


def _display_character_name(slug):
    """`dv` -> `Dv`, `yuki_happy` -> `Yuki Happy`; best effort, cosmetic only."""
    words = [w for w in re.split(r"[^0-9A-Za-zА-Яа-я]+", str(slug)) if w]
    return " ".join(w[:1].upper() + w[1:] for w in words) or str(slug)


def _slug_of_stem(path):
    """`hero_happy_2.png` -> `hero`: the name part before the first number."""
    stem = os.path.splitext(os.path.basename(path))[0]
    prefix = re.split(r"[_\-\s\d]+", stem)[0]
    return _slug(prefix or stem or "")


def _character_candidates(item):
    """Ordered character names for one file, innermost folder first.

    `images/sprites/normal/dv/dv_3_pioneer.png` gives `["dv", "normal"]` and
    `images/yuri/stab/1.png` gives `["stab", "yuri"]`. An empty list means the file
    sits in a generic folder and the name has to come from the file itself.
    """
    path = str(item["path"]).replace("\\", "/")
    parts = _parts_of(path)
    if _is_blocked_art_path(path):
        return []
    candidates = []
    for candidate in reversed(parts[:-1]):
        if candidate in UI_DIRS or candidate in SCENE_ART_DIRS:
            continue
        if candidate in GENERIC_ART_DIRS:
            continue
        slug = _slug(candidate)
        if slug and slug not in candidates:
            candidates.append(slug)
    return candidates


def _unplanned_group(item):
    """The character this file belongs to, judged from its own path alone."""
    candidates = _character_candidates(item)
    if candidates:
        return candidates[0]
    return _slug_of_stem(item["path"])


def _own_group(item):
    """The group that owns this file directly: its own folder, or its name prefix.

    A folder that holds nothing but sub-folders is a container, not a character, so
    `images/sprites/normal/` must not become a character called `normal` just because
    `dv`, `us` and the rest live below it.
    """
    parts = _parts_of(item["path"])
    parent = parts[-2] if len(parts) > 1 else ""
    if (not parent or parent in UI_DIRS or parent in SCENE_ART_DIRS
            or parent in GENERIC_ART_DIRS):
        return _slug_of_stem(item["path"])
    return _slug(parent)


def _plan_characters(files):
    """Character groups that hold enough of their own states, mapped to state count.

    Only the files directly inside a folder count, so a character is a folder of
    states and a container is not a character.
    """
    counts = {}
    for item in files:
        if item.get("kind") != "character_art":
            continue
        if _is_blocked_art_path(item["path"]):
            continue
        group = _own_group(item)
        if group:
            counts[group] = counts.get(group, 0) + 1
    return {group: count for group, count in counts.items() if count >= MIN_CHARACTER_STATES}


def _character_group(item, planned=None):
    """Which character a piece of art belongs to, or "" when it is not one.

    Ren'Py games usually put a character's sprites in their own folder
    (`images/sprites/<code>/<code>_<pose>_<expression>.png`), and the folder is the
    name. When the files sit directly in a generic folder, the prefix of the file
    name is used instead, so `hero_happy.png` still belongs to `hero`.

    With `planned` the outermost real character wins, so `images/yuri/stab/1.png`
    counts towards `yuri` instead of inventing a `stab` character.
    """
    if _is_blocked_art_path(item["path"]):
        return ""
    if planned:
        # Outermost real character first, so a scene folder inside a character
        # folder hands the file back to the character instead of inventing one.
        for candidate in reversed(_character_candidates(item)):
            if candidate in planned:
                return candidate
    return _unplanned_group(item)


def _pose_of(item):
    """The scale/pose folder above the character, e.g. `normal` or `far`."""
    path = str(item["path"]).replace("\\", "/")
    parts = [p for p in path.split("/")[:-1] if p]
    for candidate in reversed(parts[:-1]):
        if candidate.lower() not in GENERIC_ART_DIRS and re.search(r"[a-zа-я]", candidate, re.I):
            return candidate
    return ""


def _destination_for(item, root, planned=None):
    """`game-relative destination` inside the pack, and the character group."""
    kind = item["kind"]
    ext = os.path.splitext(item["path"])[1].lower()
    stem = os.path.splitext(os.path.basename(item["path"]))[0]
    if kind == "character_art" and not item.get("_force_flat"):
        group = _character_group(item, planned)
        if group:
            # One folder per character, exactly like a hand-made Ren'Py pack, so the
            # states of two characters can never be merged by name.
            return os.path.join(kind, group, _slug(stem) + ext), group
    # Slug the stem only, otherwise "hero.png" becomes "hero_png.png".
    safe_name = _slug(stem) or "asset"
    if ext:
        safe_name += ext
    return os.path.join(kind, safe_name), ""


def _unique_dest(root, dest_rel):
    """Never overwrite: archives hold many entries with the same base name."""
    dest = os.path.join(root, dest_rel)
    if not os.path.exists(dest):
        return dest, dest_rel
    stem, suffix = os.path.splitext(dest)
    attempt = 1
    while os.path.exists("%s_%d%s" % (stem, attempt, suffix)):
        attempt += 1
    dest = "%s_%d%s" % (stem, attempt, suffix)
    return dest, os.path.relpath(dest, root).replace("\\", "/")


def _write_character_manifests(root, groups, src_name, source):
    """One `character.json` per absorbed character, so the sprites are usable.

    Without this the absorbed art is a pile of files: the asset manager needs to be
    told who a character is and which file is which state, otherwise a scene would
    have to guess from file names alone.
    """
    written = []
    for group, info in sorted(groups.items()):
        folder = os.path.join(root, "character_art", group)
        if not os.path.isdir(folder):
            continue
        states = {}
        for file_name in sorted(info["states"]):
            if os.path.isfile(os.path.join(folder, file_name)):
                # State values are pack-relative, like every other pack: the
                # asset manager resolves them against this folder, and the pack
                # keeps working if it is moved.
                states[file_name] = file_name
        if not states:
            continue
        manifest = {
            "id": group,
            "name": _display_character_name(info.get("name") or group),
            "source": source,
            "pack": src_name,
            "third_party": True,
            "redistributable": False,
            "visual": {
                "type": "sprite",
                "states": states,
            },
        }
        if info.get("poses"):
            manifest["poses"] = sorted(info["poses"])
        path = os.path.join(folder, "character.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        written.append(os.path.relpath(path, config.gamedir).replace("\\", "/"))
    return written


def absorb_selected(scan, assessment, source_name=None):
    source = scan.get("source", "")
    src_name = _slug(source_name or os.path.basename(source) or "absorbed_game")
    root = os.path.join(config.gamedir, "absorbed", src_name)
    os.makedirs(root, exist_ok=True)

    by_id = {x["id"]: x for x in scan.get("files", [])}
    planned = _plan_characters(scan.get("files", []))
    selected = []
    groups = {}
    for item_id in assessment.get("selected_ids", []):
        item = by_id.get(item_id)
        if not item:
            continue
        if item.get("kind") in NON_USABLE_MODEL_KINDS:
            # MMD (`.pmx`/`.pmd`) and Cubism 2 (`.moc` + `.model.json`) are both
            # real models, but Ren'Py 8.x can display neither: it needs Cubism 4
            # (`.moc3` + `.model3.json`) for Live2D and a sprite for everything
            # else. So they are never copied into the game.
            continue
        if item.get("kind") == "gui_art":
            # Interface art is catalogued, never pulled in as a character.
            continue
        dest_rel, group = _destination_for(item, root, planned)
        if group and group not in planned:
            group = ""
            dest_rel, _ = _destination_for(dict(item, _force_flat=True), root, planned)
        dest, dest_rel = _unique_dest(root, dest_rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        try:
            _copy_member(source, item["path"], dest, item)
            imported = dict(item)
            imported["copied_path"] = os.path.relpath(dest, config.gamedir).replace("\\", "/")
            imported["stored_as"] = dest_rel
            if group:
                imported["character"] = group
                entry = groups.setdefault(group, {"states": {}, "poses": set()})
                entry["states"][os.path.basename(dest)] = imported["copied_path"]
                pose = _pose_of(item)
                if pose:
                    entry["poses"].add(pose)
                # A character name from the absorber wins over the folder guess.
                for character in assessment.get("characters", []):
                    ids = character.get("visual_asset_ids") or []
                    if character.get("id") == group or item_id in ids:
                        if character.get("name"):
                            entry["name"] = character["name"]
                        break
            selected.append(imported)
        except Exception as exc:
            item = dict(item)
            item["error"] = str(exc)
            selected.append(item)

    character_manifests = _write_character_manifests(root, groups, src_name, source)

    manifest = {
        "pack_id": hashlib.sha1((source + "|" + src_name).encode("utf-8", "ignore")).hexdigest()[:16],
        "name": src_name,
        "source": source,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "third_party": True,
        "redistributable": False,
        "archives": scan.get("archives", []),
        "assets": selected,
        "characters": assessment.get("characters", []),
        "character_packs": sorted(groups),
        "character_manifests": character_manifests,
        "summary": assessment.get("summary", ""),
    }
    manifest_path = os.path.join(root, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return manifest


def import_characters_into_world(world, manifest, selected_ids=None):
    selected_ids = set(selected_ids or [])
    added = []
    existing = {c.get("id") for c in world.get("characters", [])}
    asset_map = {x.get("id"): x.get("copied_path") for x in manifest.get("assets", []) if x.get("copied_path")}
    for character in manifest.get("characters", []):
        cid = _slug(character.get("id") or character.get("name") or "absorbed_character")
        if not cid or cid in existing:
            cid = cid + "_absorbed"
        profile = {
            "id": cid,
            "name": character.get("name", cid),
            "role": "imported character",
            "personality": character.get("personality", "").strip(),
            "goals": character.get("goals", []) if isinstance(character.get("goals"), list) else [],
            "secrets": [],
            "relationships": {},
            "imported_from": manifest.get("pack_id"),
            "visual_assets": [asset_map[x] for x in character.get("visual_asset_ids", []) if x in asset_map and (not selected_ids or x in selected_ids)],
        }
        world.setdefault("characters", []).append(profile)
        existing.add(cid)
        added.append(cid)
    world.setdefault("flags", {})["absorbed_content_present"] = True
    world.setdefault("absorbed_packs", []).append({
        "pack_id": manifest.get("pack_id"),
        "name": manifest.get("name"),
        "characters_added": added,
        "redistributable": False,
    })
    return added


def list_absorbed_packs():
    root = os.path.join(config.gamedir, "absorbed")
    result = []
    if not os.path.isdir(root):
        return result
    for name in sorted(os.listdir(root)):
        manifest_path = os.path.join(root, name, "manifest.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                result.append(json.load(fh))
        except Exception:
            continue
    return result


def portable_absorbed_manifest():
    """Return metadata safe for ordinary world export: no third-party binary assets."""
    packs = []
    for pack in list_absorbed_packs():
        packs.append({
            "pack_id": pack.get("pack_id"),
            "name": pack.get("name"),
            "characters": pack.get("characters", []),
            "redistributable": False,
        })
    return packs
