import json
import os
import random
import threading
import traceback

import renpy
import renpy.store as store
from renpy.store import *
## The store defines `dict` and `list` as their revertable subclasses, and the star import
## above pulled them into this module's namespace. Every `isinstance(x, dict)` here would then
## reject the plain dicts that come out of JSON: the model writes a world, the answer is taken
## off the waiting screen, and the game discards it as unreadable -- which looks exactly like
## "the model answered but nothing happened". The subclasses accept the builtins, so putting the
## builtins back is safe in both directions and is done once instead of at every check.
import builtins as _builtins
dict = _builtins.dict
list = _builtins.list

import story_pipeline
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
    world.setdefault("player_choices", [])
    world.setdefault("turn", 0)
    world.setdefault("time", "08:30")
    world.setdefault("location", next(iter(world["locations"]), "camp"))
    world.setdefault("memory_summary", "История только начинается.")
    ## Nothing is on screen yet: the first background must be shown without a dissolve.
    world["bg_shown"] = ""
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

    # Where the story comes from. With a model configured the buffer starts empty on purpose:
    # the first `next_step` sends a real request and the player watches a real wait, instead of
    # reading a two-line stub that pretends to be a scene. Without a model the hand-written
    # chapter starts immediately, so the game is playable the moment it is launched.
    _state()["ai_error"] = ""
    _state()["ai_failed_at"] = -1
    _state()["buffer"] = []
    if ai_configured():
        _state()["story_mode"] = str(_state().get("story_mode") or "ai")
    else:
        _state()["story_mode"] = "chapter"
        import story_chapter

        _state()["chapter"] = story_chapter.new_cursor()
        _extend_chapter(_state(), 2)


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


def ai_configured():
    """True when there is an endpoint and a model to talk to. Read from the live settings."""
    settings = _settings()
    return bool(str(settings.get("api_url", "") or "").strip()
                and str(settings.get("model", "") or "").strip())


## Посылки для «Полного рандома». Собираются локально, без единого запроса: модель получает
## готовый краткий бриф и разворачивает из него мир ровно так же, как в режиме краткого
## описания. Пулы лежат в коде, а не в мире, потому что посылка должна быть разной при каждом
## запуске, а не одинаковой, как один записанный JSON.
_RANDOM_TITLES = (
    "Двадцатое число", "Станция после полуночи", "Письмо без адреса", "Лагерь на третьей смене",
    "Тот, кто ждёт у ворот", "Комната с окном на север", "Гудок в час перерыва",
    "Дорога, которой нет на карте", "Соседи сверху не спят", "Последний автобус в Медный",
    "Ключ от чердака", "Кто-то пишет на полях", "Тише, чем нужно", "Всё, что осталось на поляне",
)

_RANDOM_GENRES = (
    "тайна", "романтика", "драма", "мистика", "повседневность", "триллер",
    "фантастика", "комедия", "историческая драма", "детектив",
)

_RANDOM_TONES = (
    "тёплая повседневность с постепенным напряжением",
    "тихо и сосредоточенно, звук важнее слова",
    "светлая грусть с юмором на заднем плане",
    "нарастающее беспокойство под ровным ритмом дня",
    "ирония и нежность, без пафоса",
    "холодная сосредоточенность, детали важнее эмоций",
    "ностальгия, которая постепенно становится тревогой",
    "игриво, но у каждой шутки есть дно",
)

_RANDOM_PLACES = (
    "маленький приморский город",
    "заброшенная станция в двадцати километрах от районного центра",
    "общежитие старого университета",
    "сельская школа, где учатся три класса",
    "ночная смена на хлебозаводе",
    "дачный посёлок, где все друг другу родственники",
    "картографическая станция на северном берегу",
    "рынок, который закрывается в четыре утра",
    "пансионат, открытый только для своих",
    "библиотека в здании старой почты",
)

_RANDOM_TIMES = (
    "на рассвете", "в жаркое утро", "в день, когда неожиданно пошёл дождь",
    "на золотом закате", "в глубокий вечер", "после полуночи",
    "в последний день лета", "в первый день после каникул",
)

_RANDOM_PREMISES = (
    "Кто-то оставляет записки, которые появляются раньше, чем событие, о котором они "
    "предупреждают. {place} {time}.",
    "Герой находит вещь, которая доказывает: здесь уже кто-то жил этой же жизнью, только "
    "лучше. {place} {time}.",
    "Раз в неделю одно и то же происходит чуть иначе, и замечает это только новенький. "
    "{place} {time}.",
    "Между двумя людьми есть то, о чём не принято говорить вслух, и место, где это можно "
    "сказать. {place} {time}.",
    "Кто-то исчез, но его продолжают звать по имени, будто он просто вышел за угол. "
    "{place} {time}.",
    "У обещания, данного давно, наконец наступает срок, и никто не готов его держать. "
    "{place} {time}.",
    "Список того, что нельзя делать в этом месте, растёт быстрее, чем кто-то успевает его "
    "читать. {place} {time}.",
    "Нужно продержаться до конца смены, не сказав того, что уже почти сказано. {place} {time}.",
)


def random_brief():
    """A random premise for the «Полный рандом» mode, built without a single request.

    The same dict shape `story_world_request` already takes for the brief mode, so both
    modes run through one chain and the model sees one kind of input.
    """
    title = random.choice(_RANDOM_TITLES)
    genres = random.sample(_RANDOM_GENRES, k=random.randint(2, 3))
    tone = random.choice(_RANDOM_TONES)
    place = random.choice(_RANDOM_PLACES)
    when = random.choice(_RANDOM_TIMES)
    premise = random.choice(_RANDOM_PREMISES).format(place=place, time=when)
    return {
        "title": title,
        "genre": ", ".join(genres),
        "tone": tone,
        "description": premise,
        "place": place,
        "time": when,
    }


def _adopt_brief(world, brief):
    """Put the generated premise on the fallback world, so it is never the old template."""
    if not isinstance(world, dict) or not isinstance(brief, dict):
        return world
    for key in ("title", "genre", "tone"):
        value = str(brief.get(key) or "").strip()
        if value:
            world[key] = value
    if str(brief.get("description") or "").strip():
        world["premise"] = str(brief["description"]).strip()
    world["random_premise"] = True
    return world


def create_game_from_creator():
    creator = {
        "title": store.creator_title,
        "genre": store.creator_genre,
        "tone": store.creator_tone,
        "description": store.creator_description,
        "character_count": int(store.creator_character_count or 3),
        "json_path": store.creator_json_path,
    }
    mode = store.creator_mode
    world = None
    ## The brief mode asks the model for the world itself. That request is two minutes long on a
    ## local model, so it goes through the same worker and the same waiting screen as the story:
    ## a creator screen that freezes for two minutes with no way to leave is a hang, not a wait.
    ## «Полный рандом» идёт той же дорогой: посылка собирается здесь, локально, а мир по ней
    ## пишет модель. Рукописный мир остаётся только запасным вариантом -- когда модели нет или
    ## когда запрос не прошёл.
    brief = None
    if mode in ("brief", "random") and ai_configured():
        if mode == "random":
            brief = random_brief()
        else:
            brief = {
                "title": creator["title"] or "Living VN",
                "genre": creator["genre"] or "драма",
                "tone": creator["tone"] or "естественно и атмосферно",
                "description": creator["description"] or "",
            }
        if story_world_request(brief, creator["character_count"]) == "done":
            payload = getattr(store, "story_payload", None) or []
            if payload and isinstance(payload[0], dict) and payload[0].get("characters"):
                world = payload[0]
    if world is None:
        try:
            world = bootstrap_world(mode, creator, _settings())
        except Exception as exc:
            renpy.notify("Не удалось создать мир: " + str(exc)[:120])
            world = default_world()
        # The random mode fell back: the world must still carry the premise that was rolled,
        # not one of the four templates the model was supposed to replace.
        if brief is not None and mode == "random":
            _adopt_brief(world, brief)
    try:
        initialize_game(world)
    except Exception as exc:
        renpy.notify("Мир не загрузился: " + str(exc)[:120])
        initialize_game(default_world())
    renpy.hide_screen("creator")
    renpy.jump("play")


# ------------------------------------------------------------- the story request

# What the waiting screen shows. These are flat store variables rather than a dict because a
# screen condition is safer than a subscript, and because the screen must never be able to read
# a half-written object while the worker is still going.
def story_job_reset(title="Модель пишет сюжет"):
    store.story_phase = "running"
    store.story_title = str(title or "")
    store.story_error = ""
    store.story_advice = ""
    store.story_detail = ""
    store.story_kind = ""
    store.story_elapsed = 0.0
    store.story_attempt = 1
    store.story_progress = 0.0
    try:
        store.story_timeout = max(5, int(float(_settings().get("timeout", 120) or 120)))
    except (TypeError, ValueError):
        store.story_timeout = 120
    store.story_timeout_text = "%d с" % store.story_timeout
    store.story_elapsed_text = "0 с"
    store.story_payload = []


def story_job_cancel():
    """Drop the answer of a request the player stopped waiting for."""
    story_pipeline.cancel_job()
    store.story_phase = "idle"


def story_wait_tick():
    """Called by the screen's timer. Copies the job's state onto the screen, then returns.

    Nothing here blocks: the socket is in a worker thread, so this runs a few times a second
    while the model is thinking, and the game keeps drawing and keeps answering ESC.
    """
    job = story_pipeline.current_job()
    if job is None:
        return True
    info = job.snapshot()
    store.story_phase = info["state"]
    store.story_elapsed = round(float(info["elapsed"]), 1)
    store.story_elapsed_text = "%d с" % int(store.story_elapsed)
    store.story_attempt = int(info["attempt"] or 1)
    store.story_progress = min(1.0, store.story_elapsed / max(1.0, float(store.story_timeout)))
    if info["state"] == "error":
        store.story_error = info["error"]
        store.story_advice = info["advice"]
        store.story_kind = info["kind"]
        # Recorded on the world at once, not when the player presses a button: a save made from
        # the failure screen has to say why the scene is missing.
        world = _state()
        world["ai_error"] = str(info["error"] or "")[:200]
        world["ai_failed_at"] = int(world.get("turn", 0))
    return True


def story_wait_take():
    """Called by the screen when the job left the running state. Returns the outcome.

    The answer itself leaves through `store.story_payload`, because a screen action can carry a
    value but the caller of `call_screen` is three frames deeper and needs the steps, not a flag.
    """
    state, payload, job = story_pipeline.take_result()
    ## The phase is deliberately left alone here. It is reset by `story_job_reset` when the
    ## next request starts, and clearing it here meant the screen's timer could fire once more
    ## before Ren'Py had taken the screen down, see "idle" and show "the request ended without
    ## an answer" about a request the model had already answered.
    if state == "done":
        store.story_payload = payload
        if job is not None:
            _keep_review(job.review)
        _state()["ai_error"] = ""
        return "done"
    if state == "error":
        store.story_payload = []
        if job is not None:
            info = job.snapshot()
            store.story_error = info["error"]
            store.story_advice = info["advice"]
            store.story_kind = info["kind"]
        _state()["ai_error"] = str(store.story_error or "")[:200]
        _state()["ai_failed_at"] = int(_state().get("turn", 0))
        return "error"
    return "cancel"


def _call_story_screen(title):
    """Show the waiting screen and return what the player decided there."""
    try:
        outcome = renpy.call_screen("story_generating")
    except Exception as exc:
        story_pipeline.cancel_job()
        store.story_error = "Экран ожидания закрылся: " + str(exc)[:120]
        store.story_advice = "Повтори запрос из главного меню."
        store.story_phase = "idle"
        return "error"
    if outcome in ("retry", "offline", "done", "error"):
        return outcome
    if outcome == "cancel":
        ## The screen asked for the answer and the slot was already empty: the model had
        ## replied, but the reply could not be handed over. Reporting this as "wait" would put
        ## the screen back up over an answer that no longer exists, so it is an error a player
        ## can see and retry.
        store.story_error = "Ответ модели был получен, но не доехал до игры."
        store.story_advice = "Повтори запрос — обычно это решается сразу."
        store.story_kind = "empty"
        return "error"
    # ESC opens the save menu over this screen; coming back means the player chose to wait.
    return "wait"


def _wait_for_story_screen(title):
    """The waiting screen, shown again after a round trip through the save menu.

    "wait" is what the screen returns when it came back from ESC without an answer, and it is
    the one outcome the callers below would otherwise turn into a false failure about a request
    that is still in flight. The bound exists for the other case -- a screen that closes with no
    value at all, where nobody is there to click anything: an unbounded loop here would hang the
    game where a visible failure would at least be actionable.
    """
    outcome = _call_story_screen(title)
    for _ in range(8):
        if outcome != "wait":
            break
        outcome = _call_story_screen(title)
    return outcome


def story_world_request(brief, character_count):
    """Ask the model for a world, off the main thread, and wait for it on the waiting screen."""
    settings = _settings()
    story_job_reset("Модель создаёт мир…")
    story_pipeline.start_world_job(brief, int(character_count or 3), settings)
    outcome = _wait_for_story_screen("Модель создаёт мир…")
    if outcome == "done":
        return "done"
    if outcome == "retry":
        story_job_reset("Модель создаёт мир…")
        story_pipeline.start_world_job(brief, int(character_count or 3), settings)
        outcome = _wait_for_story_screen("Модель создаёт мир…")
    if outcome == "offline":
        _state()["story_mode"] = "chapter"
        return "error"
    if outcome == "done":
        return "done"
    return "error"


def _story_request(player_text=None, title="Модель пишет продолжение…", min_items=2):
    """One real request, with the screen, and the player's decision about a failure.

    Returns the outcome. On "done" the steps are already in the buffer.
    """
    world = _state()
    for _attempt in range(2):
        story_job_reset(title)
        story_pipeline.start_job(world, _settings(), player_text=player_text,
                                 supervise=supervise_bundle)
        # The player can leave through the save menu and come back; the request is still the
        # one in flight, so the screen is simply shown again over it.
        outcome = _wait_for_story_screen(title)
        if outcome == "done":
            steps = [x for x in (getattr(store, "story_payload", None) or []) if isinstance(x, dict)]
            if steps:
                world["buffer"].extend(steps)
                return "done"
            continue
        if outcome == "retry":
            continue
        if outcome == "offline":
            world["story_mode"] = "chapter"
            return "offline"
        return "error"
    return "error"


def supervise_bundle(world, bundle, settings):
    """The plot supervisor: one second opinion about a bundle.

    The request itself is issued from the worker thread, because it is a socket call like any
    other. What lives here is the decision -- which bundle, which model, and what happens to
    the verdict -- so that the engine stays the place where "does the supervisor run" is
    answered, and `story_pipeline` stays the place where the thread is.
    """
    import ai_client

    if not _settings().get("supervisor", True):
        return {}
    return ai_client.supervise(world, bundle, settings)


def _keep_review(review):
    """The verdict on the world, and a shorter memory line when the editor gave one."""
    if not isinstance(review, dict) or not review:
        return
    world = _state()
    world["last_supervisor"] = review
    summary = str(review.get("summary") or "").strip()
    if summary:
        world["memory_summary"] = summary[:4000]


def story_start_chapter():
    """Put the hand-written chapter into the world and make it the source of the story.

    It is a real `initialize_game`: the same catalog scan, the same asset binding, the same
    buffer. Nothing about the chapter is drawn by a second code path.
    """
    import story_chapter

    world = story_chapter.chapter_world()
    initialize_game(world)
    # `initialize_game` decides the mode from the settings, and a player who deliberately asked
    # for the written chapter must not be pushed onto the model by that decision.
    _state()["story_mode"] = "chapter"
    _state()["chapter"] = story_chapter.new_cursor()
    _state()["chapter_locked"] = True
    _extend_chapter(_state(), 3)
    return _state()


def _extend_chapter(world, min_items):
    """Fill the buffer from the hand-written chapter, which needs no model at all."""
    import story_chapter

    cursor = world.setdefault("chapter", None) or story_chapter.new_cursor()
    world["chapter"] = cursor
    guard = 0
    while len(world.get("buffer", [])) < min_items and guard < 40:
        steps = story_chapter.next_steps(world, max(1, min_items - len(world["buffer"])))
        if not steps:
            break
        world["buffer"].extend(steps)
        guard += 1
        # A choice is a question to the player: the scene behind it is not queued until the
        # answer is known, so topping the buffer up past a question would pick the branch for
        # the player.
        if steps[-1].get("choices") or story_chapter.waiting_for_answer(world):
            break
    return world["buffer"]


def _chapter_is_over(world):
    """True when the written chapter has no blocks left. The ending screen uses it."""
    import story_chapter

    return story_chapter.chapter_finished(world)


def ensure_buffer(min_items=2):
    """Make sure the buffer has something to show, and say out loud when it could not."""
    world = _state()
    if len(world.get("buffer", [])) >= min_items:
        return

    mode = str(world.get("story_mode") or ("ai" if ai_configured() else "chapter"))
    if mode == "chapter" or world.get("chapter_locked"):
        _extend_chapter(world, min_items)
        return
    if mode == "offline":
        _extend_local(world, min_items)
        return
    if not ai_configured():
        # No endpoint is not a story: the chapter is the honest answer, and the notice at the
        # start of `play` says why the model was not used.
        world["story_mode"] = "chapter"
        _extend_chapter(world, min_items)
        return

    outcome = _story_request(min_items=min_items)
    if outcome == "done":
        return
    if outcome == "offline":
        _extend_chapter(world, min_items)
        return
    # A failure is never turned into a stub behind the player's back: the buffer keeps whatever
    # it already had, and `next_step` shows the reason on screen instead of inventing a scene.
    world.setdefault("ai_error", "")


def next_step():
    ensure_buffer(2)
    world = _state()
    buffer = world.get("buffer") or []
    if buffer:
        return buffer.pop(0)
    mode = str(world.get("story_mode")) == "chapter" or world.get("chapter_locked")
    if mode:
        import story_chapter

        if story_chapter.waiting_for_answer(world):
            # The chapter is on a question and the answer has not come yet. `script.rpy` shows
            # the question and applies it in the same interaction, so this is only reachable
            # from a caller that asks for a step between those two halves; a two-tenths pause
            # keeps that caller alive without inventing anything.
            return {"type": "wait", "seconds": 0.2}
        # The written text ran out. That is an ending, not a hang, and it gets an ending screen
        # instead of an empty scene repeated forever.
        renpy.jump("story_chapter_finished")
    # Nothing came back and the player did not agree to anything else: say so on screen rather
    # than showing a scene nobody wrote.
    return {
        "type": "narration",
        "speaker": None,
        "text": "Сцена не пришла. %s Открой настройки ИИ и проверь соединение." % (
            str(world.get("ai_error") or "Модель не ответила."),
        ),
    }


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


def _background_dissolve():
    """Queue a short dissolve for a real change of scenery.

    `renpy.transition` applies to the next interaction, and `apply_visuals` runs right before
    the line is said, so the fade covers exactly the frame where the place changes. The
    transition honours the player's «переходы» preference and is skipped while the game is
    being skipped through, which is what a transition is supposed to do.
    """
    try:
        from renpy.display.transition import Dissolve

        renpy.transition(Dissolve(0.35))
    except Exception:
        pass


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
        # `bg_shown` lives in the world, not in a module global, so a save, a rollback and a
        # restart all still know what is on screen. The first background of a game is not a
        # change and is shown without a transition.
        previous = str(world.get("bg_shown") or "")
        changed = bool(previous) and previous != path
        renpy.show("vn_background", what=Image(path), at_list=[])
        world["bg_shown"] = path
        if changed:
            _background_dissolve()


def _draw_layered(tag, record, transform, emotion, pose=None):
    """Draw a layered pack if it is one. Returns False so the caller falls through."""
    import layered_sprite

    return layered_sprite.draw_layered(tag, record, transform, emotion=emotion, pose=pose)


def _declared_costumes(*visuals):
    """Every pose/outfit name the character's packs really declare.

    The world's own `visual` and the catalog record are both read: `visual_for_world` copies
    a subset of keys, so a pack's poses can be present in one of the two and absent in the
    other. Nothing outside this set may change how a character looks.
    """
    names = set()
    for visual in visuals:
        if not isinstance(visual, dict):
            continue
        for key in ("poses", "outfits"):
            value = visual.get(key)
            if isinstance(value, dict):
                names.update(str(x) for x in value)
        poses = visual.get("poses")
        if isinstance(poses, dict):
            # A layered pack nests its costumes inside a pose: `{"pose_1": {"costumes": ...}}`.
            for info in poses.values():
                if isinstance(info, dict):
                    for name in (info.get("costumes") or {}):
                        names.add(str(name))
    return names


def _costume_for(spec, visual, record_visual, trusted):
    """`(outfit, pose)` for one character in one step.

    Два правила, которые движок держит сам:

    * имя, которого у персонажа нет, не применяется никогда. Выдуманное моделью значение иначе
      молча уводит отрисовку на первый спрайт, который разрешился, то есть меняет вид персонажа
      посторонней командой;
    * «поза» у слоёного пака -- это костюм, а не ракурс: у SAO-пака тринадцать «поз», и это
      доспехи, купальник, платье и школьная форма (сверено по спрайтам). Модель получает список
      этих имён в промпте и выбирает наугад, поэтому для её шагов поза не применяется вообще.
      Костюм меняется только по рукописному шагу или по явному объявленному `outfit`.
    """
    declared = _declared_costumes(visual, record_visual)
    wanted_outfit = str(spec.get("outfit") or visual.get("outfit") or "").strip()
    outfit = wanted_outfit if wanted_outfit in declared else None
    wanted_pose = str(spec.get("pose") or "").strip()
    pose = wanted_pose if trusted and wanted_pose in declared else None
    return outfit, pose


def _visual_character(spec, trusted=True):
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
    outfit, pose = _costume_for(spec, visual, (record or {}).get("visual"), trusted)
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
        # A pose is asked for by name, and the importer writes one state per pose and emotion
        # (`pose_01_100_happy`). Without this the pose was ignored and every emotion resolved
        # to the first pose that had it, so a character could never stand the way a scene
        # wanted her to. `pose` comes out of `_costume_for`, so a step that has no right to
        # change the costume arrives here as `None` and falls through to the default look.
        wanted_pose = pose
        if wanted_pose:
            states = (record.get("visual") or {}).get("states") or {}
            for key in ("%s_%s" % (wanted_pose, emotion), wanted_pose):
                if states.get(key) and _asset_path(states[key]):
                    path = states[key]
                    break
    if not path and record:
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
        if _draw_layered(tag, record, transform, emotion, pose):
            return

    layered_sprite.clear_face(tag)

    path = _asset_path(path)
    if path:
        import sprite_fit

        at_list = ([transform] if transform else []) + [Transform(zoom=sprite_fit.fit_zoom(path))]
        renpy.show(tag, what=Image(path), at_list=at_list)


def _sync_music(step):
    """The track for the scene that is about to be shown. Never raises, never blocks.

    Музыка включается и по намерению сцены, и без него: если сцена ничего не сказала, а на
    канале пусто, играет спокойный фон из каталога. Молчание остаётся только там, где про
    него явно попросили (`music_intent: "none"`) или где выключена настройка.
    """
    if not _settings().get("music_enabled", True):
        return
    intent = str(step.get("music_intent") or "").strip().lower()
    if intent == "none":
        return
    if not intent:
        try:
            if renpy.music.is_playing(channel="music"):
                return
        except Exception:
            pass
    try:
        track = choose_track(_state().get("music_catalog") or [], intent)
    except Exception:
        track = None
    if not track:
        return
    try:
        renpy.music.play(track, channel="music", loop=True, fadeout=1.0, fadein=1.0, if_changed=True)
    except Exception:
        pass


def apply_visuals(step):
    ## Шаг от модели помечен в `_story_request`: его `pose` не значит ничего, потому что
    ## модель выбирает костюм из списка, которого она не видит. Рукописные шаги, локальная
    ## история и демо идут как `trusted` и право на смену костюма сохраняют.
    trusted = not step.get("ai_generated")
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
        _visual_character(spec, trusted=trusted)

    _sync_music(step)


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
            text = choice.get("text", "")
            world.setdefault("history", []).append({"speaker": "player", "text": text, "turn": world.get("turn", 0)})
            # A local scene can only react to an answer if the answer reaches it.
            local_story.note_choice(world, text, choice.get("flag"))
            if choice.get("world_flag"):
                world.setdefault("flags", {})[choice["world_flag"]] = True
            # What the player decided is the one thing the next request must not forget: the
            # prompt quotes it, and the hand-written chapter walks its branches by it.
            world.setdefault("player_choices", []).append({
                "id": str(choice_id),
                "text": text,
                "turn": int(world.get("turn", 0)),
                "world_flag": choice.get("world_flag"),
                "flag": choice.get("flag"),
                "goto": choice.get("goto"),
            })
            break
    world["memory_summary"] = "\n".join(x.get("text", "") for x in world.get("history", [])[-6:])


def free_response(text):
    """A line the player typed. It becomes part of the scene, not a separate chat."""
    text = str(text or "").strip()
    if not text:
        return
    world = _state()
    world.setdefault("history", []).append({"speaker": "player", "text": text, "turn": world.get("turn", 0)})
    world.setdefault("player_choices", []).append({"id": "__free__", "text": text,
                                                   "turn": int(world.get("turn", 0))})
    mode = str(world.get("story_mode") or "ai")
    if mode == "chapter":
        import story_chapter

        world["buffer"] = story_chapter.react(world, text) + (world.get("buffer") or [])
        return
    if mode == "offline" or not ai_configured():
        # The answer is owed even when the buffer is not empty yet.
        _extend_local(world, len(world.get("buffer") or []) + 2)
        return
    outcome = _story_request(player_text=text, title="Модель отвечает на твою реплику…")
    if outcome == "done":
        return
    # The line is already in the history, so the chapter can answer it in its own words and the
    # player is not left talking to a screen that never replies.
    import story_chapter

    world["buffer"] = story_chapter.react(world, text) + (world.get("buffer") or [])


## Pending speech: the server answers in its own time, and a line must not wait for it.
_PENDING_VOICE = {"data": None, "volume": 1.0}


def _drain_voice():
    """Play speech that has arrived. Ren'Py's player belongs to the main thread, so the
    request is made in a worker and the audio is picked up from here, on a timer."""
    data = _PENDING_VOICE.get("data")
    if not data:
        return
    _PENDING_VOICE["data"] = None
    try:
        renpy.music.play(AudioData(data, "living_vn_tts.wav"), channel="voice", loop=False,
                         relative_volume=float(_PENDING_VOICE.get("volume", 0.95)))
    except Exception:
        pass


def speak_text(text):
    url = str(_settings().get("tts_url", "")).strip()
    if not url or not text:
        return False
    if _PENDING_VOICE.get("data"):
        return False
    payload = {
        "text": text,
        "speaker": _settings().get("tts_speaker", "baya"),
        "sample_rate": 48000,
        "put_accent": True,
        "put_yo": True,
    }
    volume = float(_settings().get("voice_volume", 0.95))

    def work():
        # A worker thread, because the request takes as long as the server needs and the game
        # has to stay responsive: the line is already on screen while the voice is fetched.
        import ai_client

        try:
            data = ai_client.post_bytes(url, payload, timeout=20)
        except Exception:
            return
        if data:
            _PENDING_VOICE["data"] = data
            _PENDING_VOICE["volume"] = volume
            try:
                renpy.restart_interaction()
            except Exception:
                pass

    try:
        threading.Thread(target=work, daemon=True).start()
        renpy.create_timer(0.15, _drain_voice, repeat=True)
    except Exception:
        return False
    return True


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
