"""The prompt for a story bundle: what the model is told, and how much of it there is.

Two things went wrong before this module existed. The whole world was dumped into the
request, buffer and history included, so a local 8B model spent most of its context on the
past and lost the instruction; and the schema was a block of raw JSON with no explanation,
so the model answered with a wrapper, a bare array, or an object under a key nobody asked
for, and the parser gave up silently.

So the prompt is built here in three separate parts: a short system rule, an explicit
element schema with a worked example, and a context section that is measured in characters
rather than in "whatever the world happens to contain". The cast and the background ids come
from the asset catalog, never from imagination: a model that invents `asuna_smile_v2` gets
the demo sprite, which reads as a bug to the player.

Nothing here touches the network or the store, so the same builder serves the main thread
(preparing the request) and the worker thread (using it).
"""

import json
import random

# The vocabulary `music_intent` may use: the keys of `music.KEYWORDS`, which are the tags
# `music.choose_track` matches a track against. `game/music.py` is read, never edited --
# the dictionary is its own source of truth, and the fallback keeps the prompt working
# where the music module cannot be imported (a build step, a bare test).
MUSIC_FALLBACK_TAGS = ("calm", "romance", "nostalgia", "tension", "mystery", "sad",
                       "comedy", "horror", "triumph")
_MUSIC_TAGS = {"value": None}


def music_tags():
    """The intent values the engine really resolves, as a tuple of strings."""
    if _MUSIC_TAGS["value"]:
        return _MUSIC_TAGS["value"]
    tags = MUSIC_FALLBACK_TAGS
    try:
        import music
        found = tuple(str(x) for x in (getattr(music, "KEYWORDS", None) or {}))
        if found:
            tags = found
    except Exception:
        pass
    _MUSIC_TAGS["value"] = tags
    return tags


MUSIC_INTENT_RULE = (
    '- "music_intent": настроение шага для музыки, ровно одно значение из: %s. '
    'Если музыка не нужна — "none". Ставь только на шаг, где настроение действительно '
    'меняется (обычно один раз на сцену), не выдумывай своих значений.'
) % ", ".join(music_tags())

# The element vocabulary, written as a sentence per field. A table in a prompt is read as
# noise by a small model; one line per field with what to write is read as an instruction.
ELEMENT_RULES = """Один шаг — это один объект с такими полями:
- "background": id фона из списка ФОНЫ. Либо null, если фон не меняется.
- "characters": список тех, кто сейчас на экране. [{"id": "...", "position": "center", "emotion": "neutral", "pose": "pose_01_000", "outfit": "school"}]. Больше одного человека на экране не нужно.
- "text": одна строка. Обычно 80-200 символов. Это либо рассказ от автора, либо реплика.
- "who": id персонажа, если реплику говорит он. null, если это рассказ от автора.
- "choices": только у последнего шага, если игрок должен выбрать. [{"id": "a", "text": "..."}]. Два или три варианта.
- {music_intent}

Пример одного шага:
{"background": "ext_camp_entrance_day", "characters": [{"id": "asuna", "position": "center", "emotion": "neutral", "pose": "pose_01_000"}], "text": "У ворот лагеря стоит Асуна и смотрит на дорогу.", "who": null}

Пример реплики:
{"background": "ext_camp_entrance_day", "characters": [{"id": "asuna", "position": "center", "emotion": "happy", "pose": "pose_01_000"}], "text": "«Ты всё-таки приехал. Я уже решила, что не приедешь».", "who": "asuna"}

Пример выбора:
{"background": "ext_camp_entrance_day", "characters": [{"id": "asuna", "position": "center", "emotion": "think", "pose": "pose_01_000"}], "text": "Она ждёт, что ты скажешь первым.", "who": null, "choices": [{"id": "ask", "text": "Спросить, что она здесь делает."}, {"id": "silent", "text": "Помолчать и смотреть на ворота."}]}""".replace(
    "{music_intent}", MUSIC_INTENT_RULE)

SYSTEM = """Ты пишешь сюжет для русскоязычной визуальной новеллы.

Правила ответа:
1. Ответ -- это ТОЛЬКО один массив JSON с шагами. Ни слова вне массива.
2. Никаких тройных кавычек, пояснений, заголовков и нумерации перед JSON.
3. Пиши по-русски, литературно, без разговорного сленга и без интернет-шуток.
4. Текст читают как книжную новеллу: короткие абзацы, деталь, живая речь, без канцелярита.
5. Не пересказывай то, что игрок уже видел. Начинай с того места, где сцена остановилась.
6. Не торопи события: сначала место и люди, потом реплика, потом выбор.
7. Персонаж не знает того, чего не слышал и не видел.
8. Бери только те id фонов, персонажей, эмоций и поз, что перечислены ниже. Ничего не выдумывай.
9. Выбор нужен только когда сюжетно оправдан: развилка, решение игрока, важный момент. Не заставляй персонажа каждые несколько реплик задавать вопрос. Не делай выбор в конце каждого пакета."""

REPAIR_SYSTEM = """Ты исправляешь ответ другой модели.

Правила:
1. Ответ -- это ТОЛЬКО один массив JSON с шагами. Ни слова вне массива.
2. Никаких тройных кавычек, пояснений и заголовков.
3. Сохрани смысл и текст шагов, исправь только форму: лишние запятые, кавычки, обрезанные скобки, текст вокруг JSON.
4. Если шагов меньше трёх, добавь ещё шагов в том же стиле, с тем же id фона и персонажа."""

STYLE_NOTE = ("Стиль: тихая летняя повседневность, короткие реплики, деталь важнее пафоса. "
              "Романтика и тайна, без жести и без современного сленга.")

# One line of variation per request. A model behind a deterministic proxy can answer two
# identical requests word for word; the random seed in every payload (ai_client.call_chat)
# is the main defence, and this line changes the ask itself so even a fixed sampler has
# something slightly different to answer. The directives only move emphasis -- they never
# override the schema, the cast or the history.
MIX_DIRECTIVES = (
    "Подача: начинай с реплики, без описания обстановки.",
    "Подача: больше деталей места, реплики короче.",
    "Подача: один короткий внутренний монолог игрока, без новых фактов о мире.",
    "Подача: веди диалог короткими репликами, без длинных абзацев.",
    "Подача: внимание жестам и взгляду, без новых событий.",
    "Подача: одну зацепку за шаг, напряжение нарастай медленно.",
    "Подача: небольшая деталь быта в начале сцены — звук, погода, предмет.",
)

# Caps. A local 8B model on a laptop has a few thousand tokens to spend, and every character
# of context is a character the scene does not get.
MAX_PROMPT = 7000
MAX_LORE_ITEMS = 6
MAX_LORE_CHARS = 220
MAX_HISTORY_ITEMS = 10
MAX_HISTORY_CHARS = 240
MAX_CHOICE_ITEMS = 5
MAX_CHOICE_CHARS = 160
MAX_CAST = 4
MAX_BACKGROUNDS = 40
MAX_MEMORY_CHARS = 700

KNOWN_POSITIONS = ("far_left", "left", "center", "right", "far_right")
DEFAULT_EMOTIONS = ("neutral", "smile", "happy", "laugh", "surprised", "sad", "closed",
                     "think", "shy")
# `assets.EMOTION_WORDS` guesses an expression from a file name and does not know "closed",
# which is one of the nine the layered pack really has. A name that is filtered out here is a
# name the model is never offered, so a scene would ask for a face the pack cannot show.
EXTRA_EMOTIONS = ("closed", "laugh", "smile", "shy", "surprised", "think", "neutral")
# Backgrounds whose id says the picture is a filter or a joke rather than a place. They are
# real files, so the engine can show them, but a scene written by a director does not mean
# "the screen fills with glitch" and the catalogue should not offer it as a backdrop.
_SKIP_BG = ("noise", "glitch", "vignette", "bsod", "veinmask", "warning", "splash",
            "end-", "eyes", "notebook", "poem", "eyes", "seed")


def _clip(text, limit):
    text = str(text or "").replace("\r", " ").strip()
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _number(value, default, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if number != number:
        number = float(default)
    return max(float(low), min(float(high), number))


def bundle_size(settings):
    """How many steps to ask for. A local model forgets the beginning of a long answer."""
    return int(_number((settings or {}).get("bundle_size", 5), 5, 2, 8))


def _clean_emotions(record):
    """The expression names a pack really has, taken from its own state keys.

    An empty answer means the pack's keys are file names, not expressions -- offering the
    default list for such a pack would put a face on screen that the pack does not have.
    """
    states = ((record or {}).get("visual") or {}).get("states") or {}
    found = []
    for key in states:
        key = str(key)
        if key.startswith("pose_") or key in found:
            continue
        found.append(key)
    if not found:
        return []
    import assets

    words = set(assets.EMOTION_WORDS) | set(EXTRA_EMOTIONS)
    clean = [x for x in found if x in words]
    if not clean:
        return []
    ordered = [x for x in DEFAULT_EMOTIONS if x in clean]
    ordered += [x for x in clean if x not in ordered]
    return ordered[:10]


def _emotions_of(record):
    """The same list, never empty: used when a world names a character without a pack."""
    return _clean_emotions(record) or list(DEFAULT_EMOTIONS)


def _poses_of(record):
    poses = list(((record or {}).get("visual") or {}).get("poses") or {})
    return [p for p in poses if str(p).startswith("pose_")][:8]


def _outfits_of(record):
    outfits = list(((record or {}).get("visual") or {}).get("outfits") or {})
    return [o for o in outfits if str(o).strip()][:6]


def cast_block(world):
    """The drawable cast with the exact ids, expressions and poses it really has."""
    import assets

    catalog = assets.get_catalog()
    entries = []
    seen = set()
    for character in list(world.get("characters") or []):
        if not isinstance(character, dict) or not character.get("id"):
            continue
        cid = str(character["id"])
        record = assets.find_character(catalog, cid) or {}
        entries.append((cid, str(character.get("name") or record.get("display_name") or cid),
                        str(character.get("personality") or ""), record, "world"))
        seen.add(cid)
    # A pack that exists in the catalog but not in the world is still drawable, and the
    # importer is the whole point of the asset panel -- so it may be used, but only after the
    # world's own cast, and never invented names.
    for record in catalog.get("characters", []):
        cid = str(record.get("id") or "")
        if not cid or cid in seen:
            continue
        if record.get("status") == "broken" or record.get("root_kind") == "external":
            continue
        if not assets.state_chain(record, "neutral"):
            continue
        # A pack whose state keys are file names has no expression a scene can ask for, so it
        # is left out: naming it would only produce a scene with the demo sprite in it.
        if not _clean_emotions(record):
            continue
        entries.append((cid, str(record.get("display_name") or cid), "", record, "pack"))
    lines = []
    for cid, name, personality, record, source in entries[:MAX_CAST]:
        clean = _clean_emotions(record)
        if clean:
            emotions = ", ".join(clean)
        else:
            emotions = "только neutral, других выражений у пака нет"
        poses = _poses_of(record)
        if poses:
            pose_note = "позы: " + ", ".join(poses)
        else:
            pose_note = "поз нет, поле pose можно не указывать"
        outfits = _outfits_of(record)
        if outfits:
            outfit_note = "костюмы: " + ", ".join(outfits)
        else:
            outfit_note = "костюмов нет"
        lines.append('- "%s" — %s%s. Выражения: %s. %s. %s' % (
            cid, name,
            (": " + _clip(personality, 120)) if personality else "",
            emotions, pose_note, outfit_note,
        ))
    if not lines:
        # A world with no drawable character still has to be playable: the engine falls back
        # to the demo sprite, so one name is named here and the model is told to use it.
        lines.append('- "asuna" — Асуна, единственный персонаж с готовыми спрайтами. '
                     'Выражения: %s.' % ", ".join(DEFAULT_EMOTIONS))
    return "ПЕРСОНАЖИ (id, имя, выражения, позы):\n" + "\n".join(lines)


def backgrounds_block(world):
    """Background ids from the scanned catalog, the world's own locations first."""
    import assets

    catalog = assets.get_catalog()
    known = set(str(x.get("id") or "") for x in catalog.get("backgrounds", []))
    entries = []
    seen = set()
    for name in (world.get("locations") or {}):
        name = str(name)
        # A location is named logically ("gate", "cellar") while the catalog knows it by file
        # name ("ext_camp_entrance_day"). The model is given the name the engine resolves, so a
        # background written into a step actually finds a file.
        shown = name if name in known else None
        if shown is None:
            path, reason = assets.resolve_background(catalog, name)
            if path and reason in ("ok", "fuzzy"):
                for item in catalog.get("backgrounds", []):
                    if item.get("path") == path:
                        shown = str(item.get("id") or "")
                        break
        if shown and shown not in seen:
            entries.append(shown)
            seen.add(shown)
    vn, other = [], []
    for item in catalog.get("backgrounds", []):
        cid = str(item.get("id") or "")
        if not cid or cid in seen:
            continue
        lowered = cid.lower()
        if any(word in lowered for word in _SKIP_BG):
            continue
        # Backdrops named `ext_*` / `int_*` are the ones a scene is written against; the rest
        # are other games' files and go last, so the 40-id list is not spent on them.
        (vn if lowered.startswith(("ext_", "int_")) else other).append(cid)
    for cid in vn + other:
        if len(entries) >= MAX_BACKGROUNDS:
            break
        entries.append(cid)
        seen.add(cid)
    if not entries:
        entries = ["ext_camp_entrance_day", "ext_lake_day", "int_wooden_house_day"]
    return "ФОНЫ (id):\n" + ", ".join(entries[:MAX_BACKGROUNDS])


def history_block(world, settings):
    """The last few things that happened, newest last, each one clipped."""
    limit = int(_number((settings or {}).get("max_history", 10), 10, 2, 20))
    limit = min(limit, MAX_HISTORY_ITEMS)
    rows = []
    for item in (world.get("history") or [])[-limit:]:
        if not isinstance(item, dict):
            continue
        text = _clip(item.get("text", ""), MAX_HISTORY_CHARS)
        if not text:
            continue
        speaker = str(item.get("speaker") or "автор")
        rows.append("- %s: %s" % ("игрок" if speaker == "player" else speaker, text))
    if not rows:
        return "ЧТО УЖЕ БЫЛО:\n- история начинается, до этого ничего не было."
    return "ЧТО УЖЕ БЫЛО (не повторяй это):\n" + "\n".join(rows)


def choices_block(world):
    """What the player decided, so the next bundle answers that choice instead of ignoring it."""
    rows = []
    for item in (world.get("history") or []):
        if not isinstance(item, dict) or item.get("speaker") != "player":
            continue
        rows.append("- игрок выбрал: %s" % _clip(item.get("text", ""), MAX_CHOICE_CHARS))
    for item in (world.get("player_choices") or [])[-MAX_CHOICE_ITEMS:]:
        if isinstance(item, dict) and item.get("text"):
            rows.append("- игрок ответил сам: %s" % _clip(item["text"], MAX_CHOICE_CHARS))
    if not rows:
        return "ЧТО ВЫБРАЛ ИГРОК:\n- пока ничего, игрок ещё не выбирал."
    return "ЧТО ВЫБРАЛ ИГРОК (это уже произошло, не отменяй):\n" + "\n".join(rows[-MAX_CHOICE_ITEMS:])


def lore_block(world):
    items = [_clip(x, MAX_LORE_CHARS) for x in (world.get("lore") or []) if str(x or "").strip()]
    if not items:
        return "ЛОР МИРА:\n- пока ничего особенного."
    return "ЛОР МИРА (соблюдай, не переписывай):\n" + "\n".join("- " + x for x in items[-MAX_LORE_ITEMS:])


def state_block(world):
    return "СОСТОЯНИЕ: сцена %s, время %s, ход %s, память: %s" % (
        world.get("location") or "неизвестно",
        world.get("time") or "неизвестно",
        world.get("turn", 0),
        _clip(world.get("memory_summary") or "история только начинается", MAX_MEMORY_CHARS),
    )


def _world_line(world):
    parts = []
    if world.get("title"):
        parts.append("название: " + str(world["title"]))
    if world.get("genre"):
        genre = world["genre"]
        parts.append("жанр: " + (", ".join(genre) if isinstance(genre, (list, tuple)) else str(genre)))
    if world.get("tone"):
        parts.append("тон: " + str(world["tone"]))
    if world.get("premise"):
        parts.append("завязка: " + _clip(world["premise"], 300))
    return "МИР: " + ("; ".join(parts) if parts else "летний лагерь у моря, тихая история с тайной.")


def _fit(text):
    """Keep the prompt inside the budget by cutting the middle, not the ends.

    The head carries the world and the cast, the tail carries the schema and the example, and
    the middle is history and lore -- the only part that may be shortened without breaking the
    instruction. Cutting the ends instead would drop the very lines the model needs most.
    """
    text = str(text or "")
    if len(text) <= MAX_PROMPT:
        return text
    lines = text.split("\n")
    if len(lines) <= 6:
        return text[:MAX_PROMPT]
    head = lines[:22]
    tail = lines[-46:]
    middle = lines[22:len(lines) - 46]
    trimmed = list(head)
    budget = MAX_PROMPT - sum(len(x) + 1 for x in head + tail) - 200
    for line in middle:
        if budget - len(line) - 1 < 0:
            trimmed.append("- (часть истории обрезана, чтобы запрос поместился)")
            break
        trimmed.append(line)
        budget -= len(line) + 1
    text = "\n".join(trimmed + tail)
    if len(text) > MAX_PROMPT:
        text = text[:MAX_PROMPT]
    return text


def story_request(world, settings, player_text=None, director_command=""):
    """The (system, user) pair for one bundle. Built on the main thread, before the worker."""
    world = world or {}
    settings = settings or {}
    count = bundle_size(settings)
    blocks = [
        _world_line(world),
        state_block(world),
        lore_block(world),
        cast_block(world),
        backgrounds_block(world),
        history_block(world, settings),
        choices_block(world),
    ]
    if str(world.get("story_source")) == "chapter":
        blocks.append("ВАЖНО: игрок идёт по первой главе, написанной вручную. "
                      "Продолжай её тон и героиню, не ломай уже показанное.")
    if player_text:
        blocks.append("ИГРОК СКАЗАЛ СВОИМИ СЛОВАМИ (это реплика, попавшая в сцену): %s"
                      % _clip(player_text, 400))
    if director_command:
        blocks.append("ЗАМЕЧАНИЕ РЕДАКТОРА (исполни его в этот раз): %s" % _clip(director_command, 600))

    question = (
        "Напиши продолжение сцены: массив JSON ровно из %d %s. %s\n"
        "%s\n"
        "Выбери темп и тон сам. Если в конце пакета есть сюжетная развилка — добавь выбор. "
        "Если нет — просто закончи сцену естественно."
    ) % (count, _plural(count, "шага", "шагов", "шагов"), ELEMENT_RULES,
         random.choice(MIX_DIRECTIVES))

    user = _fit("%s\n\n%s\n\nЗАДАЧА:\n%s\n\nПример ответа (только форма, не сюжет):\n%s" % (
        "\n\n".join(blocks),
        STYLE_NOTE,
        question,
        EXAMPLE,
    ))
    return SYSTEM, user


def _plural(number, one, few, many):
    number = int(number)
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


EXAMPLE = """[
  {"background": "ext_camp_entrance_day", "characters": [{"id": "asuna", "position": "center", "emotion": "neutral", "pose": "pose_01_000"}], "text": "Дорога кончается у ворот лагеря, и дальше — только тропа и сосны.", "who": null},
  {"background": "ext_camp_entrance_day", "characters": [{"id": "asuna", "position": "center", "emotion": "smile", "pose": "pose_01_000"}], "text": "«Ты всё-таки доехал. Я уже почти поверила, что не дождёшься».", "who": "asuna"},
  {"background": "ext_camp_entrance_day", "characters": [{"id": "asuna", "position": "left", "emotion": "think", "pose": "pose_01_000"}], "text": "Она смотрит на твою сумку и на дорогу за спиной, будто ждёт кого-то ещё.", "who": null, "choices": [{"id": "ask", "text": "Спросить, кого она ждёт."}, {"id": "help", "text": "Предложить помочь с сумкой."}]}
]"""


def repair_request(raw_text, error):
    """The single retry: the broken answer plus the schema, asking for the same steps again."""
    user = (
        "Предыдущий ответ не удалось разобрать: %s\n\n"
        "Вот он целиком:\n%s\n\n"
        "Верни тот же сюжет заново, ТОЛЬКО как массив JSON с шагами. Без пояснений.\n\n%s"
    ) % (
        _clip(str(error or ""), 200),
        _clip(raw_text, 2600),
        ELEMENT_RULES,
    )
    return REPAIR_SYSTEM, _fit(user)
