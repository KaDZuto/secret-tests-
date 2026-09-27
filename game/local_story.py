"""A story that keeps moving when no AI is available.

`ensure_buffer` falls back to a local bundle when the endpoint is missing or fails, and a
dead end there is worse than a plain one: the player reaches a choice, answers it, and the
same two lines come back forever. This module builds a small scene that actually advances.

It is not a language model and does not pretend to be one. It rotates narration, character
lines and situations by turn, uses the world's own characters, locations and lore so the
text belongs to the world that was created, and records the player's answer as a flag that
the next scene reacts to. `ai_status` carries why the model was not used, and the player is
told once, in the interface, instead of wondering.
"""

import random

LOCAL_NOTICE = "ИИ недоступен — сюжет ведёт локальный режим."

NARRATION = [
    "Ветер с озера приносит запах хвои и мокрого бетона.",
    "Тропинка выводит к костру, вокруг которого кто-то расставил кружки.",
    "Свет фонарей ложится на доски и ровно на звук дальнего удара.",
    "На доске объявлений сменилась половина бумаг: половина — новых.",
    "В кухне кто-то напевает, и мелкой посуды слышно поверх разговора.",
    "Над озером держится дымка, и видно, что ветер скоро сменится.",
    "С подоконника видно, как по дороге идут последние за сегодня.",
    "В палатке снята лампа, и на тумбочке лежит сложенная карта.",
    "На площадке слышно, как заканчивают уборку после репетиции.",
    "Дверь в столовую открыта, и оттуда тянет чем-то печёным.",
]

CHARACTER_LINES = [
    "«Ты всё-таки доехал. Я не была уверена, что приедешь».",
    "«Иди сюда, тут теплее. Только садись на край, он уже того».",
    "«Не смотри так, будто это чужое место. Через неделю оно будет твоим».",
    "«Если что-то пойдёт не так, ты скажи сразу. Молчать не надо».",
    "«Я тут состою в совете. Звучит смешно, но это правда».",
    "«Держи. Тебе понадобится позже, когда пойдём дальше».",
    "«Не спрашивай, откуда я знаю. Просто верь, что я знаю».",
    "«Тебе понравится здесь. Почти всё равно понравится».",
    "«Я останусь, если понадоблюсь. Меня сложно найти».",
    "«Лучше не смотри на ту сторону, пока не объясню, что там».",
]

CHOICE_LINES = [
    ("Пойти дальше.", ["«Только вместе».", "«Сначала передохни»."]),
    ("Задать вопрос.", ["«Кто это вообще такой?»", "«Зачем нас сюда позвали?»."]),
    ("Помочь.", ["«Понесу это».", "«Куда сначала?»."]),
    ("Понаблюдать.", ["«Покажу позже».", "«Узнай сам»."]),
]

LORE_PREFIX = "Из того, что ты уже знаешь: "


def _characters(world):
    found = [c for c in world.get("characters", []) if isinstance(c, dict) and c.get("id")]
    return found or [{"id": "guide", "name": "Проводник", "personality": "спокойный"}]


def _locations(world):
    return [k for k in (world.get("locations") or {}) if k] or ["camp"]


def _flags(world):
    return world.setdefault("flags", {})


def ai_status(world):
    """Why the model is not answering, or an empty string when it is."""
    return str(world.get("ai_error") or "")


def _dialogue(speaker, character_id, emotion, text, position):
    return {
        "type": "dialogue",
        "speaker": speaker,
        "character": character_id,
        "emotion": emotion,
        "position": position,
        "text": text,
    }


def build_scene(world):
    """The next local scene: a location, a character, a situation and a choice."""
    turn = int(world.get("turn", 0))
    characters = _characters(world)
    locations = _locations(world)
    flags = _flags(world)

    who = characters[turn % len(characters)]
    speaker = str(who.get("name") or who.get("id"))
    where = locations[turn % len(locations)]

    steps = [{"type": "scene", "background": where,
              "characters": [{"id": who["id"], "emotion": "neutral", "position": "center"}]}]

    # React to what the player chose last time, when there was a choice to react to.
    last = world.get("last_choice")
    if last:
        steps.append({"type": "narration", "speaker": None,
                      "text": "Ты выбрал: %s. Именно это и отличает один день от другого." % last})
        world["last_choice"] = None

    steps.append({"type": "narration", "speaker": None,
                  "text": "%s. %s" % (random.choice(NARRATION), _place_clause(world, where))})

    lore = [str(x) for x in world.get("lore", []) if x]
    if lore:
        steps.append({"type": "narration", "speaker": None,
                      "text": LORE_PREFIX + random.choice(lore) + "."})

    steps.append(_dialogue(speaker, who["id"], random.choice(["neutral", "happy", "think"]),
                           random.choice(CHARACTER_LINES), "center"))

    situation, options = CHOICE_LINES[turn % len(CHOICE_LINES)]
    choices = []
    for index, text in enumerate(options):
        choices.append({"id": "opt%d" % index, "text": text, "flag": "chose%d" % index,
                        "world_flag": "opt%d_turn%d" % (index, turn)})
    steps.append({"type": "choice", "speaker": None, "text": situation,
                  "choices": choices, "checkpoint": True})
    return steps


def _place_clause(world, where):
    place = (world.get("locations") or {}).get(where) or {}
    text = str(place.get("description") or "").strip()
    return text[:140] if text else "Здесь пока тихо."


def note_choice(world, choice_id, flag):
    """Remember the answer so the next local scene can refer to it."""
    world["last_choice"] = choice_id
    if flag:
        _flags(world)[flag] = True
