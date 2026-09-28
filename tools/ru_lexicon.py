#!/usr/bin/env python3
"""The data half of the Russian text checker.

Every list here is a decision about the house style, not a fact about Russian, so the words
live in one file instead of being buried in regexes. The style the project asks for is
`prompts_story.STYLE_NOTE`: quiet everyday prose, short lines, detail over pathos, no slang
and no internet jokes. A checker that does not know that cannot tell a placeholder from a
line of dialogue.

Three groups:

- words that are allowed even though they are not Russian (`ALLOWED_TERMS`, `ALLOWED_PHRASES`),
- words that are forbidden in this house style (`BAN_SLANG`, `CLICHE`, `PLACEHOLDER`),
- spellings a Russian editor checks with a ruler: `YO_FORMS` (a word written with `е` where
  the text already uses `ё`) and `GENDER_*` for agreement checks.

A false positive is worse than a missing finding: the reader has to check every hit, and one
wrong hit teaches them to ignore the tool. Anything that can be a normal Russian word is not
listed here.

No third-party dependency: the project runs on stdlib, and the checker runs next to the game.
"""

# Latin runs that are legitimate inside a Russian sentence: franchise names, platform words,
# asset ids, and the emotion words the engine already prints.
ALLOWED_TERMS = (
    "sword art online", "aincrad", "sao", "alfheim", "yggdrasil", "kirito", "asuna", "asunas",
    "leafa", "sugou", "klay", "kazuto", "yuuki", "kino", "mito", "silica", "nori",
    "vr", "ar", "mr", "npc", "mmo", "mmorpg", "rpg", "fps", "ai", "api", "id", "uid", "ui",
    "ux", "tts", "pc", "ps4", "ps5", "xbox", "steam", "discord", "telegram", "wiki", "dvd",
    "dlc", "hd", "usb", "url", "json", "png", "rpy", "ms", "gb", "tb", "mb", "kb", "гб", "мб",
    "happy", "sad", "neutral", "think", "surprised", "shy", "smile", "laugh", "closed", "pose",
)

# Multi-word Latin runs that must be matched as a whole before the single-word list applies.
ALLOWED_PHRASES = (
    "sword art online",
    "ready player one",
    "virtual reality",
    "player unknown",
)

# Internet slang, chat-speak and meme vocabulary. A VN that says this out loud through TTS
# breaks the illusion instantly, so these are errors, not suggestions.
BAN_SLANG = (
    "кринж", "вайб", "жиза", "рофл", "скуф", "имба", "имбовый", "топовый", "челленджер",
    "спидран", "флекс", "гооо", "кек", "лол", "ржу", "ору", "ахаха", "хаха", "кеке",
    "словил", "залип", "залипла", "бабки", "чувак", "чуваки", "грин", "буст", "аккаунт",
    "краш", "мейк", "лорд", "поц", "пиу", "скуфу", "вайбы", "жизненно",
    "погнали", "да ладно", "надо же", "круто что",
    "свинг", "сворд", "билд", "спейм", "фарм", "гринд", "дроп", "лут", "инвентарь",
    "аккаунтик", "плейер", "контент-мейкер", "мемчик", "имбовая", "рофля",
)

# Russian clichés and pathos. Not errors: a line may be fine once. Reported as style, so the
# editor decides instead of the script.
CLICHE = (
    "глаза цвета", "сердце забилось", "сердце замерло", "время остановилось",
    "кто бы мог подумать", "силы небесные", "пробирает до мурашек",
    "бросился в атаку", "всей душой", "не покидая", "как и обещала", "как и обещал",
    "из ниоткуда", "ниоткуда", "вдруг пронёс", "леденящий", "леденящая",
    "разбитое сердце", "холодный пот", "кулаки сжались", "стиснул зубы",
)

# Leftovers from generation. A line like this reaches the player as text, so it is an error.
PLACEHOLDER = (
    "todo", "tbd", "fixme", "lorem ipsum", "ipsum dolor", "заглушка", "placeholder",
    "placeholder text", "текст здесь", "вставьте сюда", "описание здесь", "текст реплики",
    "имя персонажа", "здесь текст", "asdf", "qwerty", "тест тест", "продолжение следует",
)

# A word written with `е` where the text already uses `ё`. Pairs are (written, correct).
# Only words where the `е` spelling is never correct in this position are listed: `все`/`всё`
# and `её`/`ее` are ambiguous, so they are handled by a look-ahead in `ru_text`, not here.
YO_FORMS = (
    ("придет", "придёт"), ("уйдет", "уйдёт"), ("зашел", "зашёл"), ("нашел", "нашёл"),
    ("пришел", "пришёл"), ("далекий", "далёкий"), ("далекие", "далёкие"), ("мертв", "мёртв"),
    ("съел", "сёл"), ("жесткий", "жёсткий"), ("жестко", "жёстко"), ("жестче", "жёстче"),
    ("жест", "жёст"), ("счет", "счёт"), ("счета", "счёта"), ("еще", "ещё"),
    ("обо всем", "обо всём"), ("перед всем", "перед всём"), ("все время", "всё время"),
    ("все равно", "всё равно"), ("все таки", "всё-таки"), ("все же", "всё же"),
    ("все это", "всё это"), ("все тут", "всё тут"), ("все вместе", "всё вместе"),
    ("все говорят", "всё говорят"), ("все молчат", "всё молчат"), ("все знают", "всё знают"),
    ("все наконец", "всё наконец"), ("все поняли", "всё поняли"),
    ("все смеялись", "всё смеялись"), ("все получили", "всё получили"), ("все устали", "всё устали"),
    ("все дома", "всё дома"), ("все вместе", "всё вместе"),
)

# Gender hints for agreement checks. Used only to compare a name with a pronoun inside one
# sentence, so a wrong guess produces a WARN and never an error.
GENDER_FEMALE = (
    "асуна", "лина", "сора", "марина", "девушка", "гостья", "тётя", "тётка", "тётей",
    "сестра", "дочь", "мать", "подруга", "она", "кёко", "коко", "лизбет", "сачи", "юи",
    "аня", "катя", "наташа", "елена", "ольга", "ирина", "светлана", "вера", "даша", "юля",
    "лена", "ника", "кира", "зина", "милана", "полина", "алиса", "диана", "ксюша",
)
GENDER_MALE = (
    "кирито", "кадзуто", "кай", "пох", "хироши", "кибао", "кляйн", "мамору", "беррони",
    "виктор", "муж", "отец", "брат", "сын", "друг", "парень", "дед", "дядя", "мальчик",
    "мужчина", "директор", "мастер", "он", "хеппи", "агил", "эгиль", "сёрдж", "сердж",
)

# Chat-speak openings and unfinished-draft openings in a narration sentence.
BAD_OPENERS = ("короче", "в общем,", "в принципе,", "получается, что", "это самое", "итак,")

# Line length. The engine clips long steps, and `prompts_story.ELEMENT_RULES` asks for
# 80-200 characters, so anything past 260 is a real readability problem.
TEXT_MIN = 8
TEXT_MAX = 260
# A world description (`background`, `description`, `lore`) is read by the prompt, not by the
# screen, so it is allowed to be longer than one line of dialogue.
FIELD_MAX = 600
NARRATION_MAX = 240
CHOICE_MIN = 2
CHOICE_MAX = 4


def is_latin_allowed(word):
    """True when a Latin run is a known term, id or acronym rather than a typo."""
    low = word.lower()
    for phrase in ALLOWED_PHRASES:
        if phrase in low:
            return True
    if low in ALLOWED_TERMS:
        return True
    # An id from the asset catalog (`asuna_smile_v2`, `ext_camp_entrance_day`) is data, not
    # prose, so underscores and digits make it acceptable.
    if "_" in word or any(ch.isdigit() for ch in word):
        return True
    return False
