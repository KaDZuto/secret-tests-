"""How the settings are arranged for the player: sections, rows and what each one means.

`vn_settings_schema` knows what every key is; this module knows the order the player
meets them in. One flat list of twenty-odd fields is why the panel felt unusable: the
connection check, the model, the story parameters, the volumes and the export policy
were all one column, so nothing had a place and nothing had a name.

So the panel is a contents list on the left and one section on the right. A section
carries a title, one line saying what it is for, two or four real values in the "итог"
strip, and its rows. `Field` describes one row, and its `value_text()` is the same value
the engine will read, rendered in Russian — the screen shows no key name and no number
that is not in the schema.

Every method here is total. A settings screen that raises while describing itself is
worse than one that says nothing, so each of them catches and returns something
showable instead.
"""

import renpy

import vn_settings_schema as schema

# A section id, as stored in `settings_tab`. The ids of the tabs the panel already had
# are kept, so an old value of that variable still opens a real section; `story` is the
# one addition, carved out of the old "ИИ" tab where the connection check was drowning
# in generation parameters.
ORDER = ("ai", "story", "assets", "sound", "ui", "data", "cannibalism")

# What a check can end as. The tone is what the panel colours, this is what it names.
VERDICTS = {
    "none": "не проверено",
    "ok": "работает",
    "timeout": "таймаут",
    "error": "ошибка",
}


def _store(name, fallback=None):
    """A store variable read at call time, so the panel never caches a stale value."""
    try:
        value = getattr(renpy.store, name, fallback)
    except Exception:
        return fallback
    return fallback if value is None else value


def _dictionary(name):
    value = _store(name, {})
    return value if isinstance(value, dict) else {}


def _plural(number, one, few, many):
    """Russian count forms, so "1 персонаж" does not read as a machine translation."""
    number = int(number)
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def _pair(label, value, limit=64):
    """One "name: value" row. A long path or a server message is clipped, never wrapped."""
    text = str(value or "").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return (str(label), text or "—")


def _verdict():
    """How the last real connection check ended, in one word."""
    try:
        import settings_status

        return VERDICTS.get(settings_status.test_kind(), VERDICTS["none"])
    except Exception:
        return VERDICTS["none"]


def _window_mode():
    """The Ren'Py window mode, read from the engine's own preference mirror."""
    try:
        fullscreen = bool(getattr(renpy, "fullscreen", False))
    except Exception:
        return ""
    return "полный экран" if fullscreen else "окно"


def _display(key):
    try:
        return schema.display(key)
    except Exception:
        return "?"


def _text(key):
    try:
        return schema.text(key) or "—"
    except Exception:
        return "—"


def _endpoint():
    """The server root of the stored address, or a dash when it cannot be read."""
    try:
        return schema.endpoint_root() or "не задан"
    except Exception:
        return "не задан"


class Field(object):
    """One row of a section: a label, what it means, and the control that changes it.

    An object, not a dict, for the same reason the settings view is not a dict: Ren'Py
    screen language reads a row with `getattr`, so `row.key` has to be a real attribute.
    """

    def __init__(self, key, label=None, hint=None):
        declared = schema.spec(key)
        self.key = key
        self.kind = declared.get("kind", "text")
        self.label = label or declared.get("label", key)
        self.hint = hint or declared.get("hint", "")
        self.length = int(declared.get("length") or 240)
        self.low = declared.get("min")
        self.high = declared.get("max")
        self.step = declared.get("step")
        self.unit = declared.get("unit", "")
        self.integer = bool(declared.get("integer"))

    def value_text(self):
        try:
            return schema.display(self.key)
        except Exception:
            return "?"


class Section(object):
    """A titled group of rows with the values that decide what it currently does."""

    def __init__(self, sid, title, help_text, fields=(), summary=None, status=None):
        self.id = sid
        self.title = title
        self.help = help_text
        self.fields = [Field(key, label, hint) for key, label, hint in fields]
        self._summary = summary
        self._status = status

    def summary_pairs(self):
        """The "итог" strip: what this section currently does, from the real values."""
        try:
            rows = list(self._summary() or [])
        except Exception:
            rows = []
        return [row for row in rows if row and len(row) == 2]

    def status(self):
        """The one line the contents list shows next to the title."""
        try:
            text = str(self._status() or "").replace("\n", " ").strip()
        except Exception:
            text = ""
        return text or "не настроено"


def _summary_ai():
    return [
        _pair("Модель", _text("model")),
        _pair("Сервер", _endpoint()),
        _pair("Проверка", _verdict()),
    ]


def _status_ai():
    verdict = _verdict()
    if verdict == "не проверено":
        return "ИИ ещё не проверен"
    return "ИИ: " + verdict


def _summary_story():
    return [
        _pair("Температура", _display("temperature")),
        _pair("Таймаут", _display("timeout")),
        _pair("Сцен в запросе", _display("bundle_size")),
        _pair("Надсмотрщик", _display("supervisor")),
    ]


def _status_story():
    return "%s, %s, %s сцен" % (
        _display("temperature"), _display("timeout"), _display("bundle_size"),
    )


def _summary_assets():
    import settings_status

    characters, backgrounds, scanned = settings_status.catalog_info()
    return [
        _pair("Персонажей", "%d %s" % (characters, _plural(characters, "персонаж", "персонажа", "персонажей"))),
        _pair("Фонов", "%d %s" % (backgrounds, _plural(backgrounds, "фон", "фона", "фонов"))),
        _pair("Просканировано", scanned or "ещё нет", limit=40),
    ]


def _status_assets():
    ## Short on purpose: the contents list is one line wide, and a wrapped line doubles
    ## the height of every entry, which is what makes a contents list stop being one.
    import settings_status

    characters, backgrounds, _scanned = settings_status.catalog_info()
    return "%d %s / %d %s" % (characters, _plural(characters), backgrounds, _plural(backgrounds))


def _summary_sound():
    state = _store("game_state", {})
    if not isinstance(state, dict):
        state = {}
    tracks = len(state.get("music_catalog", []) or [])
    return [
        _pair("Музыка", "%s, %d %s" % (
            _display("music_enabled"), tracks, _plural(tracks, "трек", "трека", "треков"),
        )),
        _pair("Озвучка", _display("tts_enabled")),
        _pair("Голос", _text("tts_speaker"), limit=24),
        _pair("Громкость", "%s / %s" % (_display("music_volume"), _display("voice_volume"))),
    ]


def _status_sound():
    music = "музыка вкл" if schema.flag("music_enabled") else "музыка выкл"
    voice = "озвучка вкл" if schema.flag("tts_enabled") else "озвучка выкл"
    return "%s • %s" % (music, voice)


def _summary_ui():
    return [
        _pair("Окно", _window_mode() or "по умолчанию"),
        _pair("Слабая машина", _display("low_spec")),
        _pair("Live2D", _display("live2d_enabled")),
    ]


def _status_ui():
    return "слабая %s • Live2D %s" % (_display("low_spec"), _display("live2d_enabled"))


def _summary_data():
    import settings_status

    return [
        _pair("Ключ в экспорте", _display("export_api_key")),
        _pair("Сохранения", settings_status.save_dir(), limit=52),
    ]


def _status_data():
    return "ключ " + ("в экспорте" if schema.flag("export_api_key") else "не экспортируется")


def _summary_cannibalism():
    scan = _dictionary("cannibalism_scan_result")
    picked = _dictionary("cannibalism_assessment")
    return [
        _pair("Найдено файлов", str(len(scan.get("files", []) or []))),
        _pair("Выбрано", str(len(picked.get("selected_ids", []) or []))),
        _pair("Оценка ИИ", picked.get("summary") or picked.get("error") or "не запускалась", limit=52),
    ]


def _status_cannibalism():
    scan = _dictionary("cannibalism_scan_result")
    return "найдено файлов: %d" % len(scan.get("files", []) or [])


# The section list. Field tuples are (key, label, hint); a `None` label or hint takes
# the wording declared in the schema, so the screen and the schema cannot drift apart.
SECTIONS = (
    Section(
        "ai",
        "Провайдер и модель",
        "Куда игра обращается за сценами, какая модель отвечает и работает ли она "
        "прямо сейчас.",
        (
            ("api_url", None, None),
            ("api_key", None, None),
            ("model", None, None),
            ("quality_model", None, None),
            ("absorber_model", None, None),
        ),
        summary=_summary_ai,
        status=_status_ai,
    ),
    Section(
        "story",
        "Генерация сюжета",
        "Как модель пишет: насколько свободно, сколько ждать ответа, сколько сцен "
        "брать за раз и проверяет ли надсмотрщик результат.",
        (
            ("temperature", None, None),
            ("timeout", None, None),
            ("bundle_size", None, None),
            ("max_history", None, None),
            ("supervisor", None, None),
            ("supervisor_threshold", None, None),
            ("json_mode", None, None),
            ("free_input", None, None),
        ),
        summary=_summary_story,
        status=_status_story,
    ),
    Section(
        "assets",
        "Персонажи и ассеты",
        "Спрайты и фоны, которые игра берёт из папок, и привязка их к персонажам мира.",
        (("asset_roots", None, None),),
        summary=_summary_assets,
        status=_status_assets,
    ),
    Section(
        "sound",
        "Звук и озвучка",
        "Музыка, громкости каналов и локальная озвучка реплик через TTS-сервер. "
        "Сцена сама выбирает трек по намерению и тегам, вручную выбирать не нужно.",
        (
            ("music_enabled", None, None),
            ("music_volume", None, None),
            ("auto_music_scan", None, None),
            ("music_ai_analysis", None, None),
            ("tts_enabled", None, None),
            ("tts_url", None, None),
            ("tts_speaker", None, None),
            ("voice_volume", None, None),
        ),
        summary=_summary_sound,
        status=_status_sound,
    ),
    Section(
        "ui",
        "Интерфейс",
        "Стандартные настройки Ren'Py, Live2D и режим слабой машины.",
        (
            ("low_spec", None, None),
            ("live2d_enabled", None, None),
            ("save_ai_transcript", None, None),
        ),
        summary=_summary_ui,
        status=_status_ui,
    ),
    Section(
        "data",
        "Данные и экспорт",
        "Экспорт мира в JSON, которым можно поделиться, и то, где всё это лежит на диске.",
        (("export_api_key", None, None),),
        summary=_summary_data,
        status=_status_data,
    ),
    Section(
        "cannibalism",
        "Поглощение",
        "Разбор чужой игры и перенос её ресурсов сюда, с оценкой ИИ.",
        (),
        summary=_summary_cannibalism,
        status=_status_cannibalism,
    ),
)

BY_ID = dict((item.id, item) for item in SECTIONS)
DEFAULT_ID = ORDER[0]


def sections():
    """The contents list, in the order the player reads it."""
    return SECTIONS


def section(sid=None):
    """The section for a tab id, or the first one, so an unknown id cannot blank it."""
    try:
        found = BY_ID.get(str(sid))
    except Exception:
        found = None
    return found or BY_ID[DEFAULT_ID]


def current():
    return section(_store("settings_tab", DEFAULT_ID))


def select(sid):
    """Open a section. An id this build does not know falls back to the first one."""
    target = section(sid).id
    try:
        renpy.store.settings_tab = target
    except Exception:
        pass
    return target


def help_of(sid):
    try:
        return section(sid).help
    except Exception:
        return ""
