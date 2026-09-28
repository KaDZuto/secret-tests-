"""The settings the project declares, how they survive an old save, and what they mean.

`persistent` is stored in a save file, so a key added in a later version is simply
absent from a save written by an earlier version. Ren'Py's `default` statement does
not help here: it only applies while the variable is undefined, and
`persistent.vn_settings` is always defined once it has been saved. A settings screen
that asks for such a key raises `The 'x' field does not exist` and stops the game.

So this module is the single source of truth: the `default` statement copies
`DEFAULTS`, and `merge_into_persistent` fills in whatever an existing save is missing
without touching values the player has already changed.

Ren'Py reads a screen `input` through `FieldInputValue`, and its `_get_field` walks the
name with `getattr` only. Handing it a dict therefore fails for every key, not only for
missing ones, because a dict exposes no attributes. `view` below is an attribute window
onto the same dict, so the screen can bind inputs normally while the dict stays the one
source of truth that is saved and merged.

`FIELDS` is the same idea for the other half of the screen: the human label, the hint,
the slider bounds and the unit live here next to the value they describe, so the screen
never carries a number of its own and can never show something the engine does not get.
A stored value that is not the declared kind -- a hand-edited persistent, a slider that
wrote a float into an integer key -- is coerced on the way in and clamped on the way
out, so a bar, a label and the engine all see the same number.
"""

DEFAULTS = {
    # The DeepSeek proxy from ForgetMeAI is OpenAI-compatible, needs no key and is the
    # default because it is already running locally on this machine.
    "api_url": "http://127.0.0.1:9655/v1/chat/completions",
    "api_key": "",
    "model": "deepseek-chat",
    "quality_model": "deepseek-reasoner",
    "absorber_model": "",
    "temperature": 0.85,
    "timeout": 120,
    "bundle_size": 8,
    "max_history": 18,
    "free_input": True,
    "supervisor": True,
    "supervisor_threshold": 7.0,
    "tts_enabled": True,
    "tts_url": "http://127.0.0.1:8009/tts",
    "tts_speaker": "baya",
    "tts_sample_rate": 48000,
    "music_enabled": True,
    "music_volume": 0.70,
    "voice_volume": 0.95,
    "low_spec": False,
    "live2d_enabled": True,
    "save_ai_transcript": True,
    "export_api_key": False,
    "auto_music_scan": True,
    "music_ai_analysis": True,
    "json_mode": True,
    "asset_roots": "",
}


def _text_field(key, label, hint, length=240):
    return {"kind": "text", "label": label, "hint": hint, "length": length}


def _number_field(key, label, hint, low, high, step, unit="", integer=False):
    return {
        "kind": "number",
        "label": label,
        "hint": hint,
        "min": float(low),
        "max": float(high),
        "step": float(step),
        "unit": unit,
        "integer": integer,
    }


def _flag_field(key, label, hint):
    return {"kind": "flag", "label": label, "hint": hint}


# What every declared key means, in the words of the screen and in the bounds the
# engine accepts. `min`/`max`/`step` are the real slider range, taken from what the
# generation code can work with, not from round numbers chosen for the interface.
FIELDS = {
    "api_url": _text_field(
        "api_url",
        "Адрес сервера",
        "Полный путь до chat/completions. Локальный сервер: "
        "http://127.0.0.1:11434/v1/chat/completions (Ollama) или "
        "http://127.0.0.1:1234/v1/chat/completions (LM Studio).",
        500,
    ),
    "api_key": _text_field(
        "api_key",
        "Ключ доступа",
        "Локальному серверу (Ollama, LM Studio, llama.cpp) ключ не нужен — "
        "оставь поле пустым. Нужен только для облачного API.",
        500,
    ),
    "model": _text_field(
        "model",
        "Модель для сцен",
        "Имя модели один в один, как его называет сервер: qwen3:8b, deepseek-chat. "
        "Можно выбрать из списка сервера или вписать вручную.",
        300,
    ),
    "quality_model": _text_field(
        "quality_model",
        "Модель надсмотрщика",
        "Переписывает слабую сцену. Пусто = работает та же модель, что и для сцен.",
        300,
    ),
    "absorber_model": _text_field(
        "absorber_model",
        "Модель ИИ-поглотителя",
        "Разбирает чужие ресурсы при поглощении. Пусто = основная модель.",
        300,
    ),
    "temperature": _number_field(
        "temperature",
        "Температура",
        "Насколько свободно модель пишет. Ниже = ближе к тексту промпта и быстрее, "
        "выше = живее и непредсказуемее. Для Qwen3 локально обычно хватает 0.7–1.0.",
        0.1, 1.3, 0.05,
    ),
    "timeout": _number_field(
        "timeout",
        "Таймаут запроса",
        "Сколько секунд игра ждёт ответ. Локальная модель на процессоре может думать "
        "долго: на первом запуске это 60–180 секунд.",
        15, 300, 5, unit=" с", integer=True,
    ),
    "bundle_size": _number_field(
        "bundle_size",
        "Сцен в одном запросе",
        "Сколько сцен модель пишет за один вызов. Больше = дольше ответ и выше шанс, "
        "что модель забудет начало. Для локальной модели держи 3–6.",
        3, 14, 1, unit="", integer=True,
    ),
    "max_history": _number_field(
        "max_history",
        "Событий в памяти",
        "Сколько последних событий игра пересказывает модели как контекст. "
        "Больше = модель лучше помнит, но запрос длиннее.",
        6, 40, 1, unit="", integer=True,
    ),
    "supervisor": _flag_field(
        "supervisor",
        "Надсмотрщик сцен",
        "После генерации модель оценивает сцену и переписывает её, если качество "
        "ниже порога. Стоит лишнего запроса, но заметно поднимает качество.",
    ),
    "supervisor_threshold": _number_field(
        "supervisor_threshold",
        "Порог качества",
        "Оценка сцены по 10. Ниже порога — надсмотрщик переписывает сцену. "
        "Выше порога — игра доверяет первому ответу и тратит меньше времени.",
        5.0, 9.5, 0.1,
    ),
    "json_mode": _flag_field(
        "json_mode",
        "Ждать JSON от модели",
        "Просить модель отвечать строго JSON. Нужно для разбора ответа, но некоторые "
        "локальные модели отвечают неохотно: если сцены ломаются — выключи.",
    ),
    "free_input": _flag_field(
        "free_input",
        "Свободный ввод игрока",
        "Показывать выбор «Сказать самому» в сценах с вариантами.",
    ),
    "asset_roots": _text_field(
        "asset_roots",
        "Дополнительные папки с ассетами",
        "Через «;» — свои папки с персонажами и фонами. Игра только осматривает их; "
        "нужно нажать «Пересканировать», чтобы подхватить.",
        500,
    ),
    "tts_url": _text_field(
        "tts_url",
        "Адрес TTS-сервера",
        "Локальная озвучка реплик (Silero). Если сервера нет — оставь пустым, "
        "игра будет молчать, а не падать.",
        500,
    ),
    "tts_speaker": _text_field(
        "tts_speaker",
        "Голос",
        "Имя голоса, как его знает сервер (например baya).",
        120,
    ),
    "tts_sample_rate": _number_field(
        "tts_sample_rate",
        "Частота озвучки",
        "Частота, с которой сервер вернул аудио. Меняй, только если звук пищит.",
        8000, 48000, 1000, unit=" Гц", integer=True,
    ),
    "tts_enabled": _flag_field(
        "tts_enabled",
        "Озвучка реплик",
        "Проговаривать текст локальным TTS. Требует запущенного сервера выше.",
    ),
    "music_enabled": _flag_field(
        "music_enabled",
        "Музыка",
        "Играть фоновую музыку из папки music/.",
    ),
    "music_volume": _number_field(
        "music_volume",
        "Громкость музыки",
        "Погромче — фон, потише — чтобы было слышно реплики.",
        0.0, 1.0, 0.05,
    ),
    "voice_volume": _number_field(
        "voice_volume",
        "Громкость голоса",
        "Громкость озвучки и звуков поверх музыки.",
        0.0, 1.0, 0.05,
    ),
    "auto_music_scan": _flag_field(
        "auto_music_scan",
        "Пересканировать music/ при старте",
        "Игра сама ищет новые треки при запуске, чтобы не искать их вручную.",
    ),
    "music_ai_analysis": _flag_field(
        "music_ai_analysis",
        "ИИ-разбор названий треков",
        "Модель определяет настроение трека по названию, чтобы подбирать музыку "
        "к сцене точнее. Это ещё один запрос при старте.",
    ),
    "low_spec": _flag_field(
        "low_spec",
        "Режим слабой машины",
        "Меньше эффектов и анимации в интерфейсе. Помогает на слабом железе, "
        "но сцена выглядит проще.",
    ),
    "live2d_enabled": _flag_field(
        "live2d_enabled",
        "Live2D",
        "Показывать Live2D-модели, если они нашлись в паках. На слабой машине "
        "лучше выключить.",
    ),
    "save_ai_transcript": _flag_field(
        "save_ai_transcript",
        "Сохранять текст ИИ в игру",
        "Писать сгенерированные реплики в файл игры рядом с сохранениями. "
        "Пригодится, чтобы прочитать, что именно придумала модель.",
    ),
    "export_api_key": _flag_field(
        "export_api_key",
        "Экспортировать ключ в мир",
        "Если включено, экспорт мира JSON унесёт и ключ доступа. "
        "Отправляя такой файл другому игроку, ты отдаёшь ему свой ключ.",
    ),
}


# ----------------------------------------------------------------------- storage

def merge_into_persistent():
    """Add any declared key the stored settings lack. Returns the added key names."""
    from renpy.store import persistent

    stored = getattr(persistent, "vn_settings", None)
    if not isinstance(stored, dict):
        # Corrupt or hand-edited persistent: fall back to the declared values.
        persistent.vn_settings = dict(DEFAULTS)
        return sorted(DEFAULTS)
    added = []
    for key, value in DEFAULTS.items():
        if key not in stored:
            stored[key] = value
            added.append(key)
    return added


def storage():
    """The live settings dict, replacing a corrupt one instead of failing."""
    from renpy.store import persistent

    stored = getattr(persistent, "vn_settings", None)
    if not isinstance(stored, dict):
        stored = dict(DEFAULTS)
        persistent.vn_settings = stored
    return stored


# ---------------------------------------------------------------------- coercion

def spec(key):
    """The declared description of one key, or an empty dict for an unknown one."""
    try:
        return FIELDS.get(str(key), {}) or {}
    except Exception:
        return {}


def number(key, fallback=None):
    """The stored number, coerced and clamped to the declared range.

    A hand-edited persistent holding "abc", `None` or `True` in a slider key must not
    take the settings screen down, and must not reach the generator either.
    """
    declared = spec(key)
    low, high = declared.get("min"), declared.get("max")
    if fallback is None:
        fallback = DEFAULTS.get(key, 0.0)
    try:
        value = float(storage()[key])
    except (KeyError, TypeError, ValueError):
        value = float(fallback or 0.0)
    if value != value:  # NaN compares false against everything, so test it directly
        value = float(fallback or 0.0)
    if low is not None and value < low:
        value = float(low)
    if high is not None and value > high:
        value = float(high)
    return value


def text(key, fallback=""):
    """The stored string. `None` becomes empty instead of printing «None» in a field."""
    try:
        value = storage()[key]
    except (KeyError, TypeError):
        value = fallback
    if value is None:
        return ""
    if isinstance(value, (str, bytes)):
        return value.decode("utf-8", "replace") if isinstance(value, bytes) else value
    return str(value)


def flag(key, fallback=False):
    try:
        return bool(storage()[key])
    except (KeyError, TypeError):
        return bool(fallback)


def coerce(key, value):
    """The value as it may be stored: declared kind, declared range, nothing else."""
    declared = spec(key)
    kind = declared.get("kind")
    if kind == "flag":
        return bool(value)
    if kind == "number":
        stored = value
        try:
            stored = float(value)
        except (TypeError, ValueError):
            stored = DEFAULTS.get(key, 0.0)
        low, high = declared.get("min"), declared.get("max")
        if low is not None and stored < low:
            stored = float(low)
        if high is not None and stored > high:
            stored = float(high)
        if declared.get("integer"):
            return int(round(stored))
        return round(stored, 4)
    if kind == "text":
        return "" if value is None else str(value)
    return value


def sanitize():
    """Write back the coerced value of every declared key. Returns the repaired keys.

    Called once at init, next to `merge_into_persistent`, so a settings screen that
    asks for a number gets a number even when the save it came from was edited by hand.
    """
    stored = storage()
    repaired = []
    for key in FIELDS:
        if key not in stored:
            stored[key] = DEFAULTS.get(key)
            repaired.append(key)
            continue
        wanted = coerce(key, stored[key])
        if wanted != stored[key] or type(wanted) is not type(stored[key]):
            stored[key] = wanted
            repaired.append(key)
    return repaired


# ----------------------------------------------------------------------- display

def display(key):
    """The value the way the player reads it: from the stored value, in Russian."""
    declared = spec(key)
    kind = declared.get("kind")
    if kind == "flag":
        return "вкл" if flag(key) else "выкл"
    if kind == "number":
        unit = declared.get("unit", "")
        if declared.get("integer"):
            return ("%d%s" % (int(round(number(key))), unit)).strip()
        return ("%.2f%s" % (number(key), unit)).strip()
    value = text(key)
    return value if value else "(пусто)"


def endpoint_root():
    """The server root of the stored address, e.g. http://127.0.0.1:9655/v1.

    Taken from the real address, so the player can see which server is meant without
    reading the whole path. `ai_provider` owns the rule, so it is used when it loads.
    """
    url = text("api_url").strip()
    if not url:
        return ""
    try:
        import ai_provider

        return str(ai_provider.base_url(url) or "").strip()
    except Exception:
        for suffix in ("/chat/completions", "/completions", "/responses"):
            if url.endswith(suffix):
                return url[: -len(suffix)]
        return url


# ------------------------------------------------------------------ the view

class SettingsView:
    """Attribute view over the settings dict, resolved on every access.

    The dict is looked up each time instead of cached, so the view keeps working
    after the persistent file is reloaded or replaced. Reads fall back to the declared
    default for a key an older save is missing, and writes are coerced to the declared
    kind, so nothing the screen displays can disagree with what the engine reads.
    """

    def __getattr__(self, name):
        try:
            return coerce(name, storage()[name])
        except KeyError:
            if name in DEFAULTS:
                return coerce(name, DEFAULTS[name])
            raise AttributeError(name)

    def __setattr__(self, name, value):
        storage()[name] = coerce(name, value)

    def __contains__(self, name):
        return name in storage()

    def get(self, name, fallback=None):
        return storage().get(name, fallback)


view = SettingsView()
