import json
import os
import random
import string

import renpy

from ai_client import generate_world


def default_world():
    return {
        "title": "Шаг в неизвестность",
        "genre": ["романтика", "тайна", "драма"],
        "tone": "тёплая повседневность с постепенным напряжением",
        "premise": "Новая компания друзей проводит лето в маленьком приморском городе, где каждый что-то скрывает.",
        "characters": [
            {
                "id": "asuna",
                "name": "Асуна",
                "role": "главная героиня",
                "personality": "добрая, собранная, внимательная, временами скрывает тревогу",
                "goals": ["сохранить дружбу", "разобраться с тайной старого дома"],
                "secrets": ["она уже видела странный символ раньше"],
                "relationships": {"player": 25},
                "visual": {
                    "type": "sprite",
                    "states": {
                        "neutral": "images/char_demo.png",
                        "happy": "images/char_demo.png",
                        "sad": "images/char_demo.png"
                    }
                }
            },
            {
                "id": "ren",
                "name": "Рэн",
                "role": "друг",
                "personality": "шутник, любопытный, быстро замечает детали",
                "goals": ["не дать компании развалиться"],
                "secrets": [],
                "relationships": {"player": 18},
                "visual": {"type": "sprite", "states": {"neutral": "images/char_demo.png"}}
            },
            {
                "id": "mio",
                "name": "Мио",
                "role": "наблюдатель",
                "personality": "тихая, рациональная, осторожная",
                "goals": ["понять, кто оставляет письма"],
                "secrets": ["она хранит одно из писем"],
                "relationships": {"player": 12},
                "visual": {"type": "sprite", "states": {"neutral": "images/char_demo.png"}}
            }
        ],
        "locations": {
            "camp": {"description": "Небольшой летний лагерь у моря.", "lore": ["У западной тропы стоит заброшенный дом."]},
            "house": {"description": "Старый дом на краю леса.", "lore": ["На двери вырезан незнакомый символ."]},
            "lake": {"description": "Тихое озеро за лагерем.", "lore": ["Вечером над водой почти всегда стоит туман."]}
        },
        "lore": [
            "Несколько лет назад в лагере исчезла коробка с письмами.",
            "Никто не любит говорить о старом доме у леса."
        ],
        "flags": {},
        "time": "08:30",
        "location": "camp",
        "memory_summary": "История только начинается.",
        "history": [],
        "buffer": [],
        "turn": 0,
        "music_catalog": []
    }


def random_world(character_count=3):
    rng = random.Random()
    worlds = [
        ("Пионерское лето", ["романтика", "тайна"], "ностальгическая история о лагере и странных письмах"),
        ("Школа после дождя", ["школа", "драма", "мистика"], "обычные школьные дни начинают повторяться с небольшими изменениями"),
        ("Станция Ноль", ["научная фантастика", "тайна"], "несколько человек просыпаются на станции, которую никто не помнит"),
        ("Дом напротив моря", ["романтика", "готика", "драма"], "летний дом хранит семейную тайну, которая постепенно меняет отношения героев"),
    ]
    title, genres, premise = rng.choice(worlds)
    base = default_world()
    base["title"] = title
    base["genre"] = genres
    base["premise"] = premise
    base["tone"] = "спокойно в начале, затем всё более личная и напряжённая история"
    base["characters"] = base["characters"][:max(1, min(int(character_count), 8))]
    for ch in base["characters"]:
        ch["relationships"]["player"] = rng.randint(5, 35)
    base["lore"] = rng.sample(base["lore"], k=len(base["lore"]))
    return base


def bootstrap_world(mode, creator, settings):
    if mode == "import":
        path = creator.get("json_path", "").strip()
        if path and os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        raise RuntimeError("Файл world/story JSON не найден")

    if mode == "brief":
        brief = {
            "title": creator.get("title") or "Living VN",
            "genre": creator.get("genre") or "драма",
            "tone": creator.get("tone") or "естественно и атмосферно",
            "description": creator.get("description") or "",
        }
        try:
            return generate_world(brief, int(creator.get("character_count", 3)), settings)
        except Exception:
            return random_world(creator.get("character_count", 3))

    return random_world(creator.get("character_count", 3))


def safe_id(prefix="event"):
    suffix = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return prefix + "_" + suffix
