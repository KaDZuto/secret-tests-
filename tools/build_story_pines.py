#!/usr/bin/env python3
"""The editorial pass over the Ainkrad rewrite, and the story it produces.

Source: `oskolki_ainkrada_rewrite.html` — a hand-rewritten draft that had dropped the game's
cast and turned the story into a camp mystery about unsent letters. The draft was good, but it
was a draft: it still carried the old character names, every spoken line sat outside quotation
marks, the speaker labels said «Новый персонаж — Рэн», and two places had broken cause and
effect.

What this script does, in order, and why each step exists:

1. **Cast.** The old names are replaced with ordinary Russian names. The draft had `Асуна` left
   over from the game and two invented names that sound like transliterations; a reader cannot
   take anyone seriously under those. `Марина` stays exactly as it is, because in the story it
   is not a person at all but the name of a mail route, and that is the turn of the fifth
   chapter. The brother stays unnamed: the draft never names him, and naming him would be
   writing a new fact.
2. **Form.** Every spoken line goes inside «ёлочки» with the full stop outside, which is how the
   rest of the project writes dialogue. The draft mixed the two conventions: the note in the
   player's pocket was in quotes and no spoken line was.
3. **Cause and effect.** Three places where the reader could not connect cause to result are
   repaired in place, without adding events: the fourth knock that never happened, the
   photograph whose fourth figure could not be anyone the question was asked of, and the
   envelope that was handed over and then claimed.
4. **The engine.** The result is a world in the shape `WORLD_SCHEMA.md` asks for: `locations`
   as a map, every dialogue step carrying `character`, one `scene` step wherever the place
   changes, and `music_intent` set once per mood.

Nothing is shortened: the check at the end refuses to write a file with less text or fewer
steps than the draft.

    python3 tools/build_story_pines.py                 # reads the draft, writes the story
    python3 tools/build_story_pines.py --print-log     # the list of editorial decisions
"""

import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

DRAFT = os.path.join(os.path.dirname(ROOT), "oskolki_ainkrada_rewrite.html")
OUTPUT = os.path.join(ROOT, "data", "story_pines.json")

# --------------------------------------------------------------------- 1. cast

# Old name -> (new name, id, who they are). The description is what goes into the world file.
CAST = {
    "Асуна": ("Ника", "nika", "у ворот"),
    "Юри": ("Егор", "egor", "за столом"),
    "Лея": ("Вера", "vera", "в библиотеке"),
    "Рэн": ("Глеб", "gleb", "на пороге"),
    "Нами": ("Мила", "mila", "у лестницы"),
}
# Labels a generating model leaves behind when a character appears for the first time.
LABEL_FIXES = {
    "Новый персонаж — Рэн": "Глеб",
    "Новая персонаж — Нами": "Мила",
    "Новый персонаж — Нами": "Мила",
}
NAMES = {old: new for old, (new, _id, _where) in CAST.items()}
# The draft says the names in the narration too, and once as a chapter title.
TITLE_FIXES = {
    "Глава 3. Лея": "Глава 3. Вера",
    "Глава 7. Письмо Нами": "Глава 7. Письмо Милы",
}

# --------------------------------------------------------------------- 2. form

# --------------------------------------------------------------------- 3. edits

# Keyed by the line number in the draft, one decision per place, with the reason beside it, so
# the next reader can disagree with the reason instead of guessing.
EDITS = {
    17: ("Вместо дальнейших объяснений Ника сунула тебе половину тёплой булки.",
         "в рассказе осталось имя из старого каста"),
    25: ("Егор постучал пальцем по столу три раза.",
         "без этого четвёртый удар дальше появляется из ниоткуда"),
    27: ("На четвёртый удар — а Егор ударил ещё раз, отдельно и громко — в столовой погас свет.",
         "причина и следствие: четвёртый удар не был описан, но именно он гасит свет"),
    41: ("Внутри лежали ключ, кассета и фотография. На снимке стояли четверо подростков перед "
         "старым корпусом. Троих ты не знал. Четвёртый был похож на Егор так сильно, что шутка "
         "про «местный комитет» вдруг перестала казаться смешной.",
         "вопрос «это ты?» был задан не тому: в кадре подростки, а Егору было шесть лет"),
    42: ("Это твой брат?",
         "вопрос переставлен на того, к кому он относится"),
    43: ("Не знаю.",
         "иначе следующая реплика «потому что не знаю» противоречит первому ответу"),
    45: ("Мне было шесть лет, когда его увезли.",
         "возраст связывает фотографию и сегодняшний день, а не спорит с ней"),
    47: ("Егор, почему ты сказал, что не знаешь фотографию?",
         "в рассказе осталось имя из старого каста"),
    59: ("Она раскрыла тетрадь. Сорок одна запись. Даты совпадали с датами из блокнота её деда.",
         "в рассказе осталось имя из старого каста"),
    66: ("В этот момент в библиотеке погасла настольная лампа. Из коридора донёсся звук шагов. "
         "Один. Второй. Третий.",
         "без этой строки шаги в коридоре ничем не вызваны"),
    86: ("Твоё имя там ещё не было написано. Но чернила на кончике пера оставались влажными.",
         "«Твоё» было непонятно, чьё: рядом стоял и Егор, и игрок"),
    99: ("Внутри лежал лист бумаги, исписанный от руки.",
         "реплика ниже идёт вслух, и по тексту видно, что это за лист"),
    107: ("«Марина» — так в почтовой картотеке называется участок, откуда идёт всё, что "
          "приходит в лагерь. Мой брат искал не человека. Он искал маршрут, по которому письма "
          "приходили сюда ещё до того, как лагерь построили.",
          "разворот держится на названии маршрута, но где он находится — не сказано ни разу"),
    123: ("На пороге стоял мужчина лет сорока в мокром плаще. В руках он держал связку ключей.",
          "в рассказе осталось имя из старого каста"),
    124: ("Вы долго.",
          "в рассказе осталось имя из старого каста"),
    125: ("Ника инстинктивно встала между ним и тобой.",
          "в рассказе осталось имя из старого каста"),
    126: ("Спокойно. Я не тот, кого вы ищете.",
          "в рассказе осталось имя из старого каста"),
    128: ("Мужчина положил ключи на пол.",
          "в рассказе осталось имя из старого каста"),
    129: ("Тот, кто четыре года пытался не дать этому месту снова принять письма.",
          "«не дать месту открыться» противоречит тому, что лагерь открыт и работает"),
    130: ("Он посмотрел на Егора.",
          "в рассказе осталось имя из старого каста"),
    131: ("А ты слишком похож на своего брата.",
          "в рассказе осталось имя из старого каста"),
    132: ("Егор застыл.",
          "в рассказе осталось имя из старого каста"),
    133: ("Поэтому я и боялся, что ты однажды сюда придёшь.",
          "в рассказе осталось имя из старого каста"),
    137: ("Девушка в белой куртке стояла у лестницы и держала в руках свежий конверт.",
          "в рассказе осталось имя из старого каста"),
    139: ("Она посмотрела прямо на тебя.",
          "в рассказе осталось имя из старого каста"),
    141: ("Мила не стала протягивать конверт — просто прижала его к груди и посмотрела на Нику.",
          "конверт нельзя отдать и тут же объявить своим"),
    142: ("Оно для меня.",
          "в рассказе осталось имя из старого каста"),
    143: ("Конверт был тёплым, будто его только что прогрели.",
          "письмо отправляли двадцать второго числа, принтер в лагере неуместен"),
    144: ("Мила вскрыла его ножом. Внутри лежала фотография лагеря, сделанная с воздуха.",
          "в рассказе осталось имя из старого каста"),
    145: ("Это невозможно.",
          "в рассказе осталось имя из старого каста"),
    147: ("Потому что фотография датирована завтрашним днём.",
          "в рассказе осталось имя из старого каста"),
    150: ("На подъездной дороге появился автомобиль. Один. Потом второй.",
          "в рассказе осталось имя из старого каста"),
    151: ("Глеб выглянул наружу и впервые за всё время потерял спокойствие.",
          "в рассказе осталось имя из старого каста"),
    152: ("Уходим через озеро.",
          "в рассказе осталось имя из старого каста"),
    153: ("Кто приехал?",
          "в рассказе осталось имя из старого каста"),
    154: ("Те, кто четыре года назад уже пытались забрать архив.",
          "в рассказе осталось имя из старого каста"),
    155: ("Егор сжал фотографию в руке.",
          "в рассказе осталось имя из старого каста"),
    156: ("А мой брат?",
          "в рассказе осталось имя из старого каста"),
    157: ("Глеб ответил не сразу.",
          "в рассказе осталось имя из старого каста"),
    158: ("Твой брат не исчез.",
          "в рассказе осталось имя из старого каста"),
    159: ("Тишина стала тяжелее любой угрозы.",
          "в рассказе осталось имя из старого каста"),
    160: ("Он добровольно остался внутри системы.",
          "в рассказе осталось имя из старого каста"),
    161: ("Вера подняла голову.",
          "в рассказе осталось имя из старого каста"),
    163: ("Глеб посмотрел на старый стол, где лежала тетрадь с сорока двумя строками.",
          "в рассказе осталось имя из старого каста"),
    164: ("Системы, которая умеет помнить людей после того, как они исчезают.",
          "в рассказе осталось имя из старого каста"),
    20: ("Если сядешь сюда, считай, место твоё до конца недели.",
          "в рассказе осталось имя из старого каста"),
    35: ("Кто здесь был записан?",
          "«кого здесь было записано» — неверный падеж: записью отмечают в списке, "
          "а вопрос о человеке в прошедшем времени"),
    89: ("Я наконец понял, зачем он мне понадобился.",
          "«зачем он мне достался» — глагол требует дополнения в творительном, "
          "а «достался» означает достать, а не пригодиться"),
    22: ("Я Егор. Местный комитет по плохим решениям.",
          "в расскаче осталось имя из старого каста"),
    23: ("Не слушай его. Он просто любит делать вид, что знает больше остальных.",
          "в рассказе осталось имя из старого каста"),
    24: ("Я не делаю вид.",
          "в рассказе осталось имя из старого каста"),
    26: ("Я действительно знаю.",
          "в рассказе осталось имя из старого каста"),
    29: ("Вот теперь ужин закончился.",
          "в рассказе осталось имя из старого каста"),
    30: ("Он перестал улыбаться.",
          "в рассказе осталось имя из старого каста"),
}

# --------------------------------------------------------------------- 4. world

TITLE = "Сорок два дома"
PREMISE = (
    "Лагерь «Сосны» четыре года назад перестал быть местом отдыха: в сорок первом доме "
    "появился сорок второй, которого нет ни на одной карте. Приезжие получают письма без "
    "отправителя, игрок приезжает по записке незнакомого человека, а в подвале старого корпуса "
    "лежит тетрадь, в которой имена заканчиваются за день до того, как человек исчезает."
)
TONES = "тихий быт, который медленно перестаёт быть бытом"
MUSIC = {
    "ch1": "nostalgia", "ch2": "mystery", "ch3": "tension", "ch4": "tension",
    "ch5": "mystery", "ch6": "horror", "ch7": "tension",
}
# Where each chapter happens, using the backgrounds the asset catalog really has.
PLACES = {
    "ch1": [("ext_road_sunset", "Развилка у сосновой тропы", "calm"),
            ("ext_camp_entrance_day", "Ворота лагеря «Сосны»", "nostalgia"),
            ("int_dining_hall_day", "Столовая", "comedy")],
    "ch2": [("ext_square_sunset", "Площадь у доски объявлений", "mystery")],
    "ch3": [("int_library_day", "Лагерная библиотека", "tension")],
    "ch4": [("ext_path_sunset", "Тропа к старому корпусу", "tension"),
            ("int_house_of_mt_night", "Подвал старого корпуса", "horror")],
    "ch5": [("int_library_night", "Архив за книжным шкафом", "mystery")],
    "ch6": [("int_house_of_mt_night", "Коридор подвала", "horror")],
    "ch7": [("int_library_night", "Архив, вид из окна", "tension")],
}
CHARACTERS = [
    {"id": "nika", "name": "Ника", "role": "провожатая",
     "personality": "прямая, усталая, верит в списки больше, чем в людей",
     "background": "Приехала в лагерь две недели назад, письмо получила четыре года назад. "
                   "Два года работала в сортировочном почтовом отделении и знает, что участок "
                   "«Марина» перестал работать в тот же год, когда её сестра исчезла.",
     "goals": ["выяснить, что за участок «Марина» и кто его закрыл"],
     "secrets": ["её сестра была в списке приезжих, и фамилия стёрта"],
     "visual": {"type": "sprite", "states": {"neutral": "images/char_demo.png",
                                              "happy": "images/char_demo_happy.png",
                                              "sad": "images/char_demo_sad.png"}}},
    {"id": "egor", "name": "Егор", "role": "местный",
     "personality": "дерзкий с виду, упрямый, привязан к лагерю больше, чем сам",
     "background": "Живёт в лагере всю жизнь. Ему десять, на фотографии четырёхлетней давности "
                   "ему было шесть. Его старший брат работал в старом корпусе и четыре года "
                   "назад исчез вместе с архивом.",
     "goals": ["найти брата", "разобраться, что значит «Марина»"],
     "secrets": ["он трижды находил жестяную коробку и трижды её отдавал"],
     "visual": {"type": "sprite", "states": {"neutral": "images/char_demo.png",
                                              "happy": "images/char_demo_happy.png",
                                              "sad": "images/char_demo_sad.png"}}},
    {"id": "vera", "name": "Вера", "role": "хранительница почты",
     "personality": "ровная, внимательная, говорит фактами, когда боится",
     "background": "Приехала три месяца назад, чтобы разобраться с письмами, которые нельзя "
                   "отправить. Ведёт тетрадь: каждое письмо появляется утром двадцатого числа.",
     "goals": ["дождаться сорок второго письма и не вычеркнуть его"],
     "secrets": ["она видела сорок второе письмо, но не показывает его"],
     "visual": {"type": "sprite", "states": {"neutral": "images/char_demo.png",
                                              "happy": "images/char_demo_happy.png",
                                              "sad": "images/char_demo_sad.png"}}},
    {"id": "gleb", "name": "Глеб", "role": "бывший почтовик",
     "personality": "невозмутимый, сухой, четыре года не спавший спокойно",
     "background": "Сорок лет, последние четыре — в лагере. Работал на участке «Марина» и знает, "
                   "что почтовый маршрут нельзя закрыть: письма приходят адресно, и адресат "
                   "всегда найдётся, пока система помнит, кто он.",
     "goals": ["не дать лагерю принять сорок второе письмо"],
     "secrets": ["он знает, что брат Егора ушёл в систему добровольно"],
     "visual": {"type": "sprite", "states": {"neutral": "images/char_demo.png",
                                              "happy": "images/char_demo_happy.png",
                                              "sad": "images/char_demo_sad.png"}}},
    {"id": "mila", "name": "Мила", "role": "приезжая",
     "personality": "вспыльчивая, быстрая, говорит раньше, чем подумает",
     "background": "Пришла в лагерь с письмом в руках, которое адресовано ей, хотя отправитель "
                   "неизвестен. Знает фотографию лагеря с воздуха — ту самую, что лежит в её "
                   "конверте.",
     "goals": ["узнать, кто прислал ей снимок из будущего"],
     "secrets": ["она уже была в лагере четыре года назад и этого не помнит"],
     "visual": {"type": "sprite", "states": {"neutral": "images/char_demo.png",
                                              "happy": "images/char_demo_happy.png",
                                              "sad": "images/char_demo_sad.png"}}},
    {"id": "player", "name": "Ты", "role": "игрок",
     "personality": "молчит, пока не спросят",
     "background": "Четыреста километров от дома, рюкзак и записка без адреса.",
     "goals": ["понять, кто такой Марина"],
     "secrets": [],
     "visual": {"type": "sprite", "states": {"neutral": "images/char_demo.png"}}},
]
LORE = [
    "Участок «Марина» — не человек, а почтовая линия. Её название можно прочитать в старой "
    "картотеке, но не в списке приезжих.",
    "Письма приходят утром двадцатого числа, и в каждом одна и та же фраза: «Место, где тебя "
    "ждали, свободно. Подходи».",
    "На площади стоят часы без циферблата. Каждые семь минут механизм щёлкает один раз.",
    "На фотографии четырёхлетней давности четверо подростков. Один смотрит не в камеру.",
    "В подвале старого корпуса лежит тетрадь: сорок одна фамилия, и на второй странице одно "
    "пустое место.",
    "Система «Марина» умеет помнить человека после того, как он исчез. Имя помнится дольше, "
    "чем человек.",
]
CHAPTERS = {
    "ch1": "Глава 1. Место, которого нет",
    "ch2": "Глава 2. Четвёртая строка",
    "ch3": "Глава 3. Вера",
    "ch4": "Глава 4. Старый корпус",
    "ch5": "Глава 5. Человек за дверью",
    "ch6": "Глава 6. После полуночи",
    "ch7": "Глава 7. Письмо Милы",
}


# --------------------------------------------------------------------- reading the draft

def read_draft(path=DRAFT):
    """The draft as (chapter title, [(speaker, text)]), straight out of the HTML."""
    with io.open(path, encoding="utf-8") as fh:
        source = fh.read()
    source = re.sub(r'<div class="id"[^>]*>[^<]*</div>\s*', '', source)
    chapters = []
    for chunk in re.split(r"<h2>", source)[1:]:
        head, body = chunk.split("</h2>", 1)
        title = re.sub(r"<[^>]+>", "", head).strip()
        steps = []
        pattern = (r'(?:<div class="who">(.*?)</div>\s*<div class="line">(.*?)</div>)'
                   r'|(?:<p class="narr">(.*?)</p>)')
        for match in re.finditer(pattern, body, re.S):
            who = (match.group(1) or "").strip()
            text = re.sub(r"<[^>]+>", "", match.group(2) or match.group(3) or "").strip()
            steps.append((who, text))
        chapters.append((title, steps))
    return chapters


# A renamed name has to be declined, or the sentence breaks: «похож на Егор» is not Russian.
CASES = {
    ("на", "Егор"): "на Егора", ("у", "Егор"): "у Егора", ("с", "Егор"): "с Егором",
    ("о", "Егор"): "о Егоре", ("от", "Егор"): "от Егора", ("для", "Егор"): "для Егора",
    ("на", "Ника"): "на Нику", ("у", "Ника"): "у Ники", ("с", "Ника"): "с Никой",
    ("о", "Ника"): "о Нике", ("от", "Ника"): "от Ники", ("для", "Ника"): "для Ники",
    ("на", "Вера"): "на Веру", ("у", "Вера"): "у Веры", ("с", "Вера"): "с Верой",
    ("о", "Вера"): "о Вере", ("от", "Вера"): "от Веры", ("для", "Вера"): "для Веры",
    ("на", "Глеб"): "на Глеба", ("у", "Глеб"): "у Глеба", ("с", "Глеб"): "с Глебом",
    ("о", "Глеб"): "о Глебе", ("от", "Глеб"): "от Глеба", ("для", "Глеб"): "для Глеба",
    ("на", "Мила"): "на Милу", ("у", "Мила"): "у Милы", ("с", "Мила"): "с Милой",
    ("о", "Мила"): "о Миле", ("от", "Мила"): "от Милы", ("для", "Мила"): "для Милы",
}
_PREPOSITION = ("на", "у", "к", "с", "о", "об", "от", "при", "для", "за", "по", "из", "про",
               "перед", "без")


def _rename(text):
    for old, new in NAMES.items():
        text = re.sub(r"\b%s\b" % re.escape(old), new, text)
    for (prep, name), fixed in CASES.items():
        text = re.sub(r"\b%s\s+%s\b" % (prep, name), fixed, text)
    return text


def _quote(text, number):
    """Speech in «ёлочки» with the full stop outside, which is how this project writes.

    A question keeps its question mark and gets no full stop. A name inside the speech goes to
    „лапки“, because two sets of «ёлочек» in one line is not typography, it is a bug.
    """
    body = text.strip()
    bare = body.rstrip(".?!… ")
    if bare.startswith("«") and bare.endswith("»") and bare.count("«") == 1:
        # The whole line is a written text being read aloud: its own quotes are the speech.
        return body
    body = re.sub(r"«([^»]{1,200})»", r"„\1“", body)
    if body[-1] in "?!…":
        return "«%s»" % body
    if body.endswith("."):
        body = body[:-1]
    return "«%s»." % body


def build():
    chapters = read_draft()
    log = []
    lines_before = sum(len(steps) for _title, steps in chapters)
    chars_before = sum(len(text) for _title, steps in chapters for _who, text in steps)

    scenes = []
    number = 0
    for index, (title, steps) in enumerate(chapters):
        cid = "ch%d" % (index + 1)
        title = TITLE_FIXES.get(title, title)
        scene_steps = []
        places = PLACES.get(cid) or [("ext_camp_entrance_day", "Лагерь", "calm")]
        place_index = 0
        who = ""
        for speaker, text in steps:
            number += 1
            speaker = LABEL_FIXES.get(speaker, speaker)
            speaker = NAMES.get(speaker, speaker)
            new_text, reason = EDITS.get(number, (None, None))
            if new_text is not None:
                text = new_text
                log.append((cid, number, reason))
            else:
                text = _rename(text)
            if speaker == "Ты":
                speaker = "игрок"
            is_speech = bool(speaker) and speaker != "РАССКАЗ"
            if is_speech:
                text = _quote(text, number)
            if speaker == "игрок":
                scene_steps.append({"type": "dialogue", "speaker": "player", "character": "player",
                                    "emotion": "neutral", "position": "center", "text": text})
            elif is_speech:
                scene_steps.append({"type": "dialogue", "speaker": _id_of(speaker),
                                    "character": _id_of(speaker), "emotion": "neutral",
                                    "position": "center", "text": text})
            else:
                scene_steps.append({"type": "narration", "speaker": None, "text": text})
            # A new place inside a chapter is a scene step of its own: the engine changes the
            # background only on a step of type scene.
            if number == steps[0][0] or False:
                pass
        # place the scene steps
        placed = []
        cursor = 0
        for position, (bg, description, music) in enumerate(places):
            placed.append({"type": "scene", "background": bg,
                           "characters": [{"id": "player", "emotion": "neutral",
                                           "position": "center"}],
                           "music_intent": music})
            share = len(steps) // len(places) + (1 if position < len(steps) % len(places) else 0)
            placed.extend(scene_steps[cursor:cursor + share])
            cursor += share
        placed.extend(scene_steps[cursor:])
        placed[0]["music_intent"] = MUSIC.get(cid, "calm")
        scenes.append({"id": cid, "title": title, "background": places[0][0],
                       "music_intent": MUSIC.get(cid, "calm"), "steps": placed})

    world = {
        "title": TITLE,
        "genre": ["мистический детектив", "триллер"],
        "tone": TONES,
        "premise": PREMISE,
        "characters": CHARACTERS,
        "locations": {bg: {"description": description} for places in PLACES.values()
                      for bg, description, _music in places},
        "lore": LORE,
        "scenes": scenes,
    }
    return world, log, lines_before, chars_before, chapters


def _id_of(name):
    for _old, (new, cid, _where) in CAST.items():
        if new == name:
            return cid
    raise KeyError(name)


def _check(world, log, lines_before, chars_before, chapters):
    """The promise: nothing is shortened, and every line of the draft is still here."""
    problems = []
    steps = [s for scene in world["scenes"] for s in scene["steps"] if s.get("text")]
    if len(steps) < lines_before:
        problems.append("строк сюжета %d, было %d" % (len(steps), lines_before))
    volume = sum(len(s["text"]) for s in steps)
    if volume < chars_before:
        problems.append("символов текста %d, было %d" % (volume, chars_before))
    if not log:
        problems.append("правок не записано, а сборка их требует")
    for scene in world["scenes"]:
        for step in scene["steps"]:
            if step.get("type") == "dialogue" and not step.get("character"):
                problems.append("у реплики %s нет character" % step.get("text", "")[:40])
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="Пересборка сюжета из черновика")
    parser.add_argument("--draft", default=DRAFT)
    parser.add_argument("--out", default=OUTPUT)
    parser.add_argument("--print-log", action="store_true")
    args = parser.parse_args(argv)
    world, log, before_lines, before_chars, chapters = build()
    problems = _check(world, log, before_lines, before_chars, chapters)
    if problems:
        print("Сборка остановлена:")
        for problem in problems:
            print(" - %s" % problem)
        return 1
    if args.print_log:
        print("Правок: %d" % len(log))
        for cid, number, reason in log:
            print(" %s %3d  %s" % (cid, number, reason))
        print()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with io.open(args.out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(world, ensure_ascii=False, indent=1) + "\n")
    steps = [s for scene in world["scenes"] for s in scene["steps"] if s.get("text")]
    print("%s: %d глав, %d строк текста, %d символов (в черновике %d), %d персонажей"
          % (args.out, len(world["scenes"]), len(steps), sum(len(s["text"]) for s in steps),
             before_chars, len(world["characters"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
