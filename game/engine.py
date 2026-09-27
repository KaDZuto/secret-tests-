import json
import os
import random
import traceback

import renpy
import renpy.store as store
from renpy.store import *

from ai_client import generate_bundle, generate_free_response, supervise
from music import analyze_catalog_with_ai, choose_track, save_catalog, scan_music
from world import bootstrap_world, default_world
from cannibalism import assess_absorption, absorb_selected, import_characters_into_world, scan_source, list_absorbed_packs, portable_absorbed_manifest
import live2d_pack
from assets import (
    attach_visual,
    bind_all,
    bind_backgrounds,
    build_catalog,
    catalog_lines,
    clear_cache,
    find_character,
    get_catalog,
    parse_extra_roots,
    resolve_background,
    resolve_state,
    state_chain,
    status_of,
    visual_for_world,
)


def _state():
    return store.game_state


def _settings():
    return dict(store.persistent.vn_settings)


def _clean_settings_for_export():
    data = dict(_settings())
    if not data.get("export_api_key", False):
        data["api_key"] = ""
    data["export_api_key"] = False
    return data


def initialize_game(world):
    world = dict(world)
    world.setdefault("characters", [])
    world.setdefault("locations", {})
    world.setdefault("lore", [])
    world.setdefault("flags", {})
    world.setdefault("history", [])
    world.setdefault("buffer", [])
    world.setdefault("turn", 0)
    world.setdefault("time", "08:30")
    world.setdefault("location", next(iter(world["locations"]), "camp"))
    world.setdefault("memory_summary", "История только начинается.")
    world["supervisor_command"] = ""
    world["last_supervisor"] = {}
    _state().clear()
    _state().update(world)

    paths = [p for p in str(store.creator_music_paths).split(";") if p.strip()]
    catalog = scan_music(paths)
    if catalog and _settings().get("music_ai_analysis", True) and _settings().get("api_url") and _settings().get("model"):
        try:
            catalog = analyze_catalog_with_ai(catalog, _settings())
        except Exception:
            pass
    _state()["music_catalog"] = catalog
    save_catalog(catalog)

    # Scan the real asset folders once per launch, then let every world entry
    # that names a real pack use it. A missing pack never blocks a scene.
    try:
        build_catalog(parse_extra_roots(_settings().get("asset_roots", "")))
    except Exception:
        pass
    bind_assets()

    # Make a small deterministic starting scene so the game works without AI.
    if not _state()["buffer"]:
        _state()["buffer"] = fallback_bundle()


def bind_assets():
    """Attach real character packs and locations to the current world."""
    catalog = get_catalog()
    try:
        bind_all(_state(), catalog)
    except Exception:
        pass
    try:
        bind_backgrounds(_state(), catalog)
    except Exception:
        pass
    try:
        live2d_pack.reset_availability()
    except Exception:
        pass


def asset_catalog():
    """The scanned asset catalog, rebuilt on demand by the inspector."""
    return get_catalog()


def asset_catalog_lines():
    """Inspector rows: one line per discovered character or location."""
    return catalog_lines(get_catalog())


def asset_catalog_summary():
    """One-line summary for the inspector header."""
    catalog = get_catalog()
    characters = catalog.get("characters", [])
    backgrounds = catalog.get("backgrounds", [])
    broken = sum(1 for record in characters if not record.get("states"))
    live2d = sum(1 for record in characters if record.get("visual", {}).get("type") == "live2d")
    return "Персонажей: %d • локаций: %d • Live2D: %d • без спрайтов: %d • корней: %d" % (
        len(characters), len(backgrounds), live2d, broken, len(catalog.get("roots", [])),
    )


def asset_live2d_report():
    """Live2D availability plus per-character pack summaries."""
    catalog = get_catalog()
    lines = ["Поддержка Live2D: %s" % ("да" if live2d_pack.live2d_available() else "нет")]
    for record in catalog.get("characters", []):
        visual = record.get("visual") or {}
        if visual.get("type") != "live2d":
            continue
        lines.append((record.get("display_name") or record.get("id")) + " — " + live2d_pack.describe(live2d_pack.get_pack(visual)))
    if len(lines) == 1:
        lines.append("Live2D-модели не найдены.")
    return lines


def asset_bind_report():
    """Which world characters were bound to a real pack, and why not."""
    catalog = get_catalog()
    world = _state()
    lines = []
    for entry in world.get("characters", []):
        cid = entry.get("id")
        record = find_character(catalog, cid)
        if record:
            lines.append("%s → %s (%s)" % (
                entry.get("name") or cid,
                record.get("display_name") or record.get("pack_dir") or record.get("id"),
                status_of(record) or "ready",
            ))
        else:
            lines.append("%s → ассет не найден, используется демо" % (entry.get("name") or cid))
    if not lines:
        lines.append("Персонажей в мире нет.")
    return lines


def clear_asset_cache_action():
    """Drop the cached catalog so the next scan starts from disk."""
    clear_cache()


def asset_rescan():
    """Rescan every asset root and rebind the current world."""
    clear_cache()
    build_catalog(parse_extra_roots(_settings().get("asset_roots", "")))
    live2d_pack.reset_availability()
    bind_assets()
    renpy.notify("Ассеты пересканированы: " + asset_catalog_summary())




def cannibalism_scan():
    path = str(store.cannibalism_source_path or "").strip().strip('"')
    if not path:
        renpy.notify("Укажи путь к папке или ZIP игры.")
        return
    store.cannibalism_scan_result = scan_source(path)
    store.cannibalism_assessment = {}
    renpy.notify("Поглотитель: найдено ресурсов %d" % len(store.cannibalism_scan_result.get("files", [])))


def cannibalism_assess():
    scan = store.cannibalism_scan_result or {}
    if not scan.get("files"):
        renpy.notify("Сначала просканируй источник.")
        return
    try:
        result = assess_absorption(scan, _settings())
        ids = set(result.get("selected_ids", []))
        for item in scan.get("files", []):
            item["selected"] = item.get("id") in ids
        store.cannibalism_assessment = result
        renpy.notify("AI-поглотитель выбрал %d ресурсов" % len(ids))
    except Exception as exc:
        store.cannibalism_assessment = {"error": str(exc)}
        renpy.notify("Поглотитель недоступен: %s" % exc)


def cannibalism_absorb():
    scan = store.cannibalism_scan_result or {}
    assessment = dict(store.cannibalism_assessment or {})
    if not scan.get("files") or not assessment.get("selected_ids"):
        renpy.notify("Сначала запусти AI-оценку.")
        return
    try:
        manifest = absorb_selected(scan, assessment, store.cannibalism_source_name or None)
        added = []
        if store.cannibalism_import_characters:
            added = import_characters_into_world(_state(), manifest, assessment.get("selected_ids"))
        _state()["absorbed_packs"] = portable_absorbed_manifest()
        renpy.notify("Поглощено: %d ресурсов, персонажей добавлено: %d" % (len(manifest.get("assets", [])), len(added)))
    except Exception as exc:
        renpy.notify("Ошибка поглощения: %s" % exc)


def cannibalism_select_all(value=True):
    scan = store.cannibalism_scan_result or {}
    for item in scan.get("files", []):
        item["selected"] = bool(value)
    assessment = dict(store.cannibalism_assessment or {})
    assessment["selected_ids"] = [x["id"] for x in scan.get("files", []) if x.get("selected")]
    store.cannibalism_assessment = assessment


def cannibalism_toggle(item_id):
    scan = store.cannibalism_scan_result or {}
    for item in scan.get("files", []):
        if item.get("id") == item_id:
            item["selected"] = not item.get("selected", False)
            break
    store.cannibalism_assessment = dict(store.cannibalism_assessment or {})
    store.cannibalism_assessment["selected_ids"] = [x["id"] for x in scan.get("files", []) if x.get("selected")]


def cannibalism_info():
    packs = list_absorbed_packs()
    return len(packs)


def create_game_from_creator():
    try:
        mode = store.creator_mode
        creator = {
            "title": store.creator_title,
            "genre": store.creator_genre,
            "tone": store.creator_tone,
            "description": store.creator_description,
            "character_count": int(store.creator_character_count or 3),
            "json_path": store.creator_json_path,
        }
        world = bootstrap_world(mode, creator, _settings())
        initialize_game(world)
        renpy.hide_screen("creator")
        renpy.jump("play")
    except Exception as exc:
        renpy.notify("Не удалось создать мир: " + str(exc))
        initialize_game(default_world())
        renpy.hide_screen("creator")
        renpy.jump("play")


def _repair_bundle(bundle, feedback):
    world = _state()
    old = world.get("supervisor_command", "")
    world["supervisor_command"] = str(feedback.get("director_command", ""))[:2500]
    try:
        repaired = generate_bundle(world, _settings())
        return repaired
    except Exception:
        world["supervisor_command"] = old
        return bundle
    finally:
        world["supervisor_command"] = old


def ensure_buffer(min_items=2):
    world = _state()
    turn = int(world.get("turn", 0))
    if len(world.get("buffer", [])) >= min_items:
        return

    try:
        bundle = generate_bundle(world, _settings())
        if _settings().get("supervisor", True):
            try:
                review = supervise(world, bundle, _settings())
                world["last_supervisor"] = review
                world["memory_summary"] = review.get("summary", world.get("memory_summary", ""))
                threshold = float(_settings().get("supervisor_threshold", 7.0))
                if review.get("repair") or not review.get("approved", True) or float(review.get("score", 10)) < threshold:
                    bundle = _repair_bundle(bundle, review)
            except Exception as exc:
                world["last_supervisor"] = {"score": 0, "approved": True, "summary": "Supervisor unavailable", "error": str(exc)}

        beats = bundle.get("beats", []) if isinstance(bundle, dict) else []
        if beats:
            world["buffer"].extend(beats)
            return
    except Exception as exc:
        # Kept, not swallowed: an endpoint that is off has to be visible, or a silent
        # fallback looks like the game refusing to write a story.
        world["ai_error"] = str(exc)[:200]
        world["ai_failed_at"] = turn
        return _extend_local(world, min_items)

    world["ai_error"] = ""
    _extend_local(world, min_items)


def next_step():
    ensure_buffer(2)
    world = _state()
    if not world.get("buffer"):
        world["buffer"] = fallback_bundle()
    return world["buffer"].pop(0)


def _character_by_id(cid):
    for ch in _state().get("characters", []):
        if ch.get("id") == cid:
            return ch
    return None


def _asset_path(path):
    """A loadable sprite path, or the demo fallback, or None.

    Paths outside the game directory are refused unless Ren'Py can load them
    itself, because an imported third-party pack is inspect-only.
    """
    if not path:
        return None
    path = str(path)
    if renpy.loadable(path):
        return path
    gamedir = getattr(store.config, "gamedir", None) if hasattr(store, "config") else None
    if os.path.isabs(path) and os.path.isfile(path):
        if gamedir and not os.path.abspath(path).startswith(os.path.abspath(gamedir) + os.sep):
            return None
        return path
    fallback = "images/char_demo.png"
    return fallback if renpy.loadable(fallback) else None


def _transform_for(position):
    mapping = {
        "left": "vn_left",
        "center": "vn_center",
        "right": "vn_right",
        "far_left": "vn_far_left",
        "far_right": "vn_far_right",
    }
    name = mapping.get(position or "center", "vn_center")
    return getattr(store, name, None)


def _show_background(step):
    bg = step.get("background")
    if not bg:
        return
    renpy.scene()
    world = _state()
    if bg in world.get("locations", {}):
        world["location"] = bg
    # A bound location already carries a real path; otherwise look it up in the
    # scanned catalog so a location works without a manifest entry in the world.
    path = None
    if bg in world.get("locations", {}):
        candidate = world["locations"][bg]
        if isinstance(candidate, str):
            path = candidate
    if not path:
        resolved = resolve_background(get_catalog(), bg)
        path = resolved[0] if isinstance(resolved, tuple) else None
    if not path and renpy.loadable(str(bg)):
        path = str(bg)
    path = _asset_path(path) if path else None
    if not path:
        path = "images/bg_demo.png"
        path = path if renpy.loadable(path) else None
    if path:
        renpy.show("vn_background", what=Image(path), at_list=[])


def _draw_layered(tag, record, transform, emotion, pose=None):
    """Draw a layered pack if it is one. Returns False so the caller falls through."""
    import layered_sprite

    return layered_sprite.draw_layered(tag, record, transform, emotion=emotion, pose=pose)


def _visual_character(spec):
    cid = spec.get("id") or spec.get("character")
    if not cid:
        return
    ch = _character_by_id(cid)
    record = find_character(get_catalog(), cid)
    if ch is None and record is None:
        return
    # The world's entry wins, but a character that only exists in the catalog still has
    # to be drawable: imported packs are the whole point of the asset browser.
    visual = (ch or {}).get("visual") or (record or {}).get("visual") or {}
    emotion = spec.get("emotion") or "neutral"
    motion = spec.get("motion") or "idle"
    position = spec.get("position") or "center"
    outfit = spec.get("outfit") or visual.get("outfit")
    tag = "vn_char_" + cid
    transform = _transform_for(position)

    # Live2D is optional. The pack loader returns None whenever Cubism is
    # unavailable, the setting is off, or the model cannot be built, and the
    # sprite path below then runs instead.
    if _settings().get("live2d_enabled", True):
        displayable = live2d_pack.build_displayable(visual, emotion=emotion, motion=motion, outfit=outfit)
        if displayable is not None:
            renpy.show(tag, what=displayable, at_list=[transform] if transform else [])
            return

    record = find_character(get_catalog(), cid)

    path = None
    if record:
        resolved = resolve_state(record, emotion)
        path = resolved[0] if isinstance(resolved, tuple) else None
    if not path:
        states = visual.get("states") or {}
        path = states.get(emotion) or states.get("neutral")
    if not path and record:
        for candidate in state_chain(record, emotion):
            if _asset_path(candidate):
                path = candidate
                break

    # A character that used to be drawn layered leaves its face overlays behind.
    import layered_sprite

    # A finished sprite is the normal case: the importer bakes every expression into a
    # full-height image, which needs nothing but a position and a scale. The runtime overlay
    # is the fallback for a pack that still ships separate face files, and it only runs when
    # there is no finished file for this emotion.
    if not _asset_path(path) and record:
        if _draw_layered(tag, record, transform, emotion, spec.get("pose")):
            return

    layered_sprite.clear_face(tag)

    path = _asset_path(path)
    if path:
        import sprite_fit

        at_list = ([transform] if transform else []) + [Transform(zoom=sprite_fit.fit_zoom(path))]
        renpy.show(tag, what=Image(path), at_list=at_list)


def apply_visuals(step):
    _show_background(step)
    specs = step.get("characters") or []
    if not specs and step.get("character"):
        specs = [{
            "id": step.get("character"),
            "emotion": step.get("emotion", "neutral"),
            "motion": step.get("motion", "idle"),
            "position": step.get("position", "center"),
        }]
    for spec in specs:
        _visual_character(spec)

    intent = step.get("music_intent")
    if intent and _settings().get("music_enabled", True):
        track = choose_track(_state().get("music_catalog", []), intent)
        if track:
            try:
                renpy.music.play(track, channel="music", loop=True, fadeout=1.0, fadein=1.0, if_changed=True)
            except Exception:
                pass


def _apply_patch(patch):
    if not isinstance(patch, dict):
        return
    world = _state()
    flags = patch.get("flags")
    if isinstance(flags, dict):
        world.setdefault("flags", {}).update({str(k): bool(v) for k, v in flags.items()})
    if isinstance(patch.get("location"), str):
        world["location"] = patch["location"]
    if isinstance(patch.get("time"), str):
        world["time"] = patch["time"]
    if isinstance(patch.get("memory_summary"), str):
        world["memory_summary"] = patch["memory_summary"][:4000]
    if isinstance(patch.get("lore_add"), str) and patch["lore_add"].strip():
        world.setdefault("lore", []).append(patch["lore_add"].strip())
    rel = patch.get("relationship")
    if isinstance(rel, dict):
        cid = rel.get("character")
        delta = rel.get("delta", 0)
        ch = _character_by_id(cid)
        if ch and isinstance(delta, (int, float)):
            rels = ch.setdefault("relationships", {})
            current = float(rels.get("player", 0))
            rels["player"] = max(-100, min(100, current + delta))


def consume_dialogue(step):
    world = _state()
    world["turn"] = int(world.get("turn", 0)) + 1
    _apply_patch(step.get("state_patch", {}))
    text = step.get("text", "")
    speaker = step.get("speaker")
    world.setdefault("history", []).append({"speaker": speaker or "narrator", "text": text, "turn": world["turn"]})
    max_history = int(_settings().get("max_history", 18))
    world["history"] = world["history"][-max_history:]

    if speaker and _settings().get("tts_enabled", True):
        speak_text(text)


def apply_choice(step, choice_id):
    world = _state()
    _apply_patch(step.get("state_patch", {}))
    import local_story

    for choice in step.get("choices", []):
        if choice.get("id") == choice_id:
            world.setdefault("history", []).append({"speaker": "player", "text": choice.get("text", ""), "turn": world.get("turn", 0)})
            # A local scene can only react to an answer if the answer reaches it.
            local_story.note_choice(world, choice.get("text", ""), choice.get("flag"))
            if choice.get("world_flag"):
                world.setdefault("flags", {})[choice["world_flag"]] = True
            break
    world["memory_summary"] = "\n".join(x.get("text", "") for x in world.get("history", [])[-6:])


def free_response(text):
    text = str(text or "").strip()
    if not text:
        return
    world = _state()
    world.setdefault("history", []).append({"speaker": "player", "text": text, "turn": world.get("turn", 0)})
    try:
        bundle = generate_free_response(world, text, _settings())
        beats = bundle.get("beats", []) if isinstance(bundle, dict) else []
        if beats:
            world["buffer"] = beats + world.get("buffer", [])
            return
    except Exception:
        pass
    world["buffer"] = fallback_bundle() + world.get("buffer", [])


def speak_text(text):
    url = str(_settings().get("tts_url", "")).strip()
    if not url or not text:
        return False
    payload = {
        "text": text,
        "speaker": _settings().get("tts_speaker", "baya"),
        "sample_rate": 48000,
        "put_accent": True,
        "put_yo": True,
    }
    try:
        data = renpy.fetch(url, method="POST", json=payload, timeout=20, result="bytes")
        if data:
            audio = AudioData(data, "living_vn_tts.wav")
            renpy.music.play(audio, channel="voice", loop=False, relative_volume=float(_settings().get("voice_volume", 0.95)))
            return True
    except Exception:
        return False
    return False


def _extend_local(world, min_items):
    """Fill the buffer from the local story, which advances without a model."""
    import local_story

    while len(world.get("buffer", [])) < min_items:
        world["buffer"].extend(local_story.build_scene(world))
    return world["buffer"]


def fallback_bundle():
    world = _state()
    chars = world.get("characters", [])
    first = chars[0] if chars else {"id": "guide", "name": "Проводник", "personality": "спокойный"}
    cid = first.get("id", "guide")
    name = first.get("name", "Проводник")
    turn = int(world.get("turn", 0))
    if turn == 0:
        return [
            {"type": "scene", "background": "camp", "characters": [{"id": cid, "emotion": "neutral", "motion": "idle", "position": "center"}], "music_intent": "nostalgia"},
            {"type": "dialogue", "speaker": cid, "character": cid, "emotion": "neutral", "position": "center", "text": f"{name} посмотрела на тебя и улыбнулась.", "music_intent": "nostalgia"},
            {"type": "dialogue", "speaker": cid, "character": cid, "emotion": "happy", "position": "left", "text": "Кажется, сегодня будет интересный день."},
            {"type": "narration", "speaker": None, "text": "Где-то за деревьями раздался короткий звонкий звук."},
            {"type": "choice", "speaker": None, "text": "Что ты сделаешь?", "choices": [
                {"id": "follow", "text": "Пойти к лесу."},
                {"id": "stay", "text": "Остаться здесь и расспросить её."}
            ], "checkpoint": True}
        ]
    return [
        {"type": "dialogue", "speaker": cid, "character": cid, "emotion": random.choice(["happy", "thinking", "neutral"]), "position": random.choice(["left", "center", "right"]), "text": f"{name} ждёт твоего решения. Давай посмотрим, куда оно приведёт."},
        {"type": "choice", "text": "Продолжить?", "choices": [{"id": "yes", "text": "Да."}, {"id": "later", "text": "Посмотреть вокруг."}], "checkpoint": True}
    ]


def create_story_from_text():
    # Compatibility helper for future agents; creator UI calls create_game_from_creator directly.
    creator = {
        "title": store.creator_title,
        "genre": store.creator_genre,
        "tone": store.creator_tone,
        "description": store.creator_description,
        "character_count": int(store.creator_character_count or 3),
        "json_path": store.creator_json_path,
    }
    world = bootstrap_world(store.creator_mode, creator, _settings())
    initialize_game(world)


def toggle_setting(key):
    current = bool(store.persistent.vn_settings.get(key, False))
    store.persistent.vn_settings[key] = not current
    renpy.save_persistent()


def set_export_key(value):
    store.persistent.vn_settings["export_api_key"] = bool(value)
    renpy.save_persistent()


def get_export_folder():
    path = os.path.join(renpy.config.savedir, "exports")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def export_current_world():
    try:
        folder = get_export_folder()
        filename = os.path.basename(store.export_name.strip() or "my_world") + ".json"
        path = os.path.join(folder, filename)
        story = {k: v for k, v in _state().items() if k not in ("buffer",)}
        story["absorbed_packs"] = portable_absorbed_manifest()
        data = {
            "format": "living-vn-world",
            "version": 2,
            "story": story,
            "settings": _clean_settings_for_export(),
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        renpy.put_clipboard_text(path)
        renpy.notify("Мир экспортирован. Путь скопирован в буфер обмена.")
    except Exception as exc:
        renpy.notify("Ошибка экспорта: " + str(exc))


def import_world_from_path():
    path = str(store.import_world_path or "").strip().strip('"')
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        imported = data.get("story", data)
        if not isinstance(imported, dict):
            raise ValueError("Неверный world JSON")
        initialize_game(imported)
        renpy.hide_screen("settings")
        renpy.jump("play")
    except Exception as exc:
        renpy.notify("Ошибка импорта: " + str(exc))


def load_story_from_clipboard():
    try:
        text = renpy.get_clipboard_text()
        obj = json.loads(text)
        folder = os.path.join(config.gamedir, "data")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "clipboard_story.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
        store.creator_json_path = path
        renpy.notify("JSON из буфера загружен")
    except Exception as exc:
        renpy.notify("В буфере нет корректного JSON: " + str(exc))


def add_lore_from_input():
    text = str(store.lore_edit_text or "").strip()
    if not text:
        return
    _state().setdefault("lore", []).append(text)
    store.lore_edit_text = ""
    renpy.save_persistent()
    renpy.restart_interaction()


# Export names used by screens.rpy.
create_game_from_creator.__name__ = "create_game_from_creator"
