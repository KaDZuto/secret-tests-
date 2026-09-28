"""Proof for the settings screen: what the game is using, and what the server said.

A settings screen made only of text fields and sliders is indistinguishable from
decoration. The player types a URL, moves a slider and has no way to learn whether
anything is listening, which is exactly the "настройки не факт что работают" complaint.

So this module answers the three questions the player is really asking, in short Russian
text:

  * what the game uses right now -- the effective endpoint, model and catalog counts;
  * what happened on the last real request to the endpoint -- milliseconds, the model, the
    server's own words or the exact reason it failed, and when;
  * where the values are written on disk, so "saved immediately" is a path, not a promise.

Everything here is total. A settings screen that raises while describing itself is worse
than one that says nothing, so each public function catches everything and returns text
that can be shown as-is.

The provider module reaches for `renpy.fetch`, which is not an attribute of the `renpy`
package: display and fetch helpers live in `renpy.exports` (see layered_sprite.py). The
check below therefore falls back to issuing the identical request from here when
`ai_provider` cannot reach its own transport, so the button always measures the real
endpoint instead of reporting a broken import.
"""

import calendar
import os
import time
from datetime import datetime

import renpy

# Kept on `persistent`, so a check survives a restart: a result the player can see
# tomorrow is proof, and a result held in a store variable would only be a decoration.
TEST_KEY = "vn_last_test"
SCAN_KEY = "vn_last_scan"

# Widths chosen for the panel: the status strip is three fixed lines (the verdict, the
# reason, the advice), the inline test result is one line next to its button, and the
# detail line under the check card is two.
STRIP_LIMIT = 78
INLINE_LIMIT = 64
DETAIL_LIMIT = 200
ERROR_LIMIT = 90

# A check must not freeze the panel for the whole generation timeout, which is two
# minutes on purpose: the request it sends is the same one the generator sends, and for
# an answer that means "not listening" a dead socket is the normal case, not a slow model.
CHECK_TIMEOUT = 30

# What a check can end as is named in the layout module (`VERDICTS`); the advice for a
# failure is keyed by a fragment of the message the server or the socket actually said.
# The server's own words are shown above these, and without a next step they read as a
# dead end, which is how "настройки не факт что работают" starts.
#
# Every line is kept under `STRIP_LIMIT` characters on purpose: the status strip has a
# fixed height, so one wrapped line would push the panel out of its box. The full
# message is one scroll away, in the check card of the provider section.
ADVICE = (
    ("connection refused", "Сервер не слушает этот порт. Запусти модель "
                           "(Ollama, LM Studio, llama.cpp)."),
    ("timed out", "Ответа не было. Повтори проверку или подними таймаут."),
    ("timeout", "Ответа не было. Проверь, что модель загрузилась, или подними таймаут."),
    ("name or service not known", "Адрес не найден. Проверь имя хоста и порт модели."),
    ("404", "Нужен путь до /v1/chat/completions, например "
            "http://127.0.0.1:11434/v1/chat/completions"),
    ("401", "Ключ отвергнут. Локальному серверу ключ не нужен — очисти поле."),
    ("403", "Сервер не пускает с этим ключом. Проверь ключ или права."),
    ("503", "Модель не загружена или сервер перегружен. Подожди и повтори."),
    ("502", "Прокси не получил ответ от модели. Подожди загрузки и повтори."),
    ("connection reset", "Сервер оборвал соединение — это перезапуск модели. Повтори."),
    ("без choices", "Сервер ответил не как OpenAI-совместимый. Включи режим /v1."),
    ("не задан", "Впиши адрес сервера выше и повтори проверку."),
    ("не выбрана", "Выбери или впиши модель выше и повтори проверку."),
)



# ----------------------------------------------------------------------- helpers

def _clip(text, limit):
    """One line, at most `limit` characters, so a long server error cannot break a row."""
    text = str(text or "").replace("\n", " ").replace("\r", " ").strip()
    if len(text) > limit:
        text = text[: max(1, limit - 1)].rstrip() + "…"
    return text


def _settings():
    from vn_settings_schema import view

    return view


def _persistent():
    from renpy.store import persistent

    return persistent


def _plural(number, one, few, many):
    """Russian count forms, so "1 персонаж" does not read as a machine translation."""
    number = int(number)
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def _clock(epoch):
    if not epoch:
        return "неизвестно"
    try:
        return time.strftime("%d.%m %H:%M", time.localtime(float(epoch)))
    except Exception:
        return "неизвестно"


def _seconds(epoch):
    try:
        return max(0, int(time.time() - float(epoch)))
    except Exception:
        return 0


def _ago(epoch):
    """How long ago, in the words a person would use."""
    if not epoch:
        return ""
    seconds = _seconds(epoch)
    if seconds < 90:
        return "только что"
    if seconds < 3600:
        return "%d %s назад" % (seconds // 60, _plural(seconds // 60, "минуту", "минуты", "минут"))
    if seconds < 86400:
        return "%d %s назад" % (seconds // 3600, _plural(seconds // 3600, "час", "часа", "часов"))
    return _clock(epoch)


def _scan_clock(stamp):
    """The catalog stores UTC, so it is converted to the player's local time here."""
    try:
        text = str(stamp or "")[:19]
        if not text:
            return ""
        parts = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
        return _clock(calendar.timegm(parts.timetuple()))
    except Exception:
        return ""


# ------------------------------------------------------------------ the check

def last_test():
    """The stored result of the last real check, or an empty dict."""
    try:
        record = getattr(_persistent(), TEST_KEY, None)
    except Exception:
        return {}
    return record if isinstance(record, dict) else {}


def has_test():
    return bool(last_test().get("at"))


def _reply_words(message, ok):
    """The first words of the reply, or the failure reason, without the provider's prefix."""
    text = str(message or "").strip()
    for prefix in ("Ответ: ", "Ошибка: ", "ответ: ", "ошибка: "):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    if not text:
        return "(сервер вернул пустой ответ)" if ok else "(без пояснения)"
    return text


def _headers():
    result = {"Content-Type": "application/json"}
    key = str(_settings().get("api_key", "") or "").strip()
    if key:
        result["Authorization"] = "Bearer " + key
    return result


def _direct_test(url, model, timeout=None):
    """The provider's own request, issued from a module that can reach the transport."""
    from renpy.exports.fetchexports import fetch

    if not url:
        return False, "Адрес не задан"
    if not model:
        return False, "Модель не выбрана"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Ответь одним словом: работает?"}],
        "max_tokens": 24,
        "temperature": 0.0,
    }
    if timeout is None:
        timeout = CHECK_TIMEOUT
    try:
        result = fetch(
            url,
            method="POST",
            json=payload,
            headers=_headers(),
            timeout=int(timeout),
            result="json",
        )
    except Exception as exc:
        return False, "Ошибка запроса: " + _clip(exc, ERROR_LIMIT)
    choices = (result or {}).get("choices") if isinstance(result, dict) else None
    if not choices:
        return False, "Ответ без choices (сервер не OpenAI-совместимый?)"
    message = choices[0].get("message") or {}
    text = str(message.get("content") or message.get("reasoning_content") or "").strip()
    return True, text or "(пусто)"


# How a failure ended. A timeout is its own verdict: it is the one failure that is
# usually not a mistake in the address, and the advice differs from the other errors.
_TIMEOUT_WORDS = ("timed out", "timeout", "таймаут", "превышено время")


def classify(message, ok):
    """"ok", "timeout" or "error", from what the server or the socket actually said."""
    if ok:
        return "ok"
    lowered = str(message or "").lower()
    for word in _TIMEOUT_WORDS:
        if word in lowered:
            return "timeout"
    return "error"


def _remember(ok, text, elapsed_ms, model, url, kind=None):
    record = {
        "ok": bool(ok),
        "kind": kind or classify(text, ok),
        "text": text,
        "elapsed_ms": int(elapsed_ms),
        "model": model,
        "url": url,
        "at": time.time(),
    }
    try:
        setattr(_persistent(), TEST_KEY, record)
        from renpy.exports.persistentexports import save_persistent

        save_persistent()
    except Exception:
        pass
    # The screen variable the old button used is kept in step, so nothing reading it
    # shows a stale verdict after a new check.
    try:
        renpy.store.provider_test = ("Ответ: " if ok else "Ошибка: ") + text
    except Exception:
        pass
    return record


def test_now():
    """Send one real request and remember what came back. Returns (ok, text, elapsed_ms).

    The request is issued from here rather than from `ai_provider`, for two reasons that
    used to live in a try/except: `ai_provider` reaches for `renpy.fetch`, which is not an
    attribute of the `renpy` package, so that path always fell through; and the check
    needs a shorter ceiling than the two-minute generation timeout, because a settings
    panel that hangs for two minutes is indistinguishable from a crashed game. The
    request itself is the same one the generator makes, to the same address, with the
    same key and the same model.
    """
    settings = _settings()
    model = str(settings.get("model", "") or "")
    url = str(settings.get("api_url", "") or "")

    started = time.time()
    try:
        ok, message = _direct_test(url, model, timeout=CHECK_TIMEOUT)
    except Exception as exc:
        ok, message = False, "Ошибка проверки: " + _clip(exc, ERROR_LIMIT)
    elapsed_ms = int((time.time() - started) * 1000)

    words = _clip(_reply_words(message, ok), ERROR_LIMIT)
    _remember(ok, words, elapsed_ms, model or "не выбрана", url or "не задан",
              kind=classify(message, ok))
    return (bool(ok), words, elapsed_ms)


def test_kind():
    """"none", "ok", "timeout" or "error" -- what the panel colours and names."""
    record = last_test()
    if not record.get("at"):
        return "none"
    if record.get("ok"):
        return "ok"
    # A record written before the verdict existed still classifies from its own text.
    return str(record.get("kind") or classify(record.get("text", ""), False))


def test_label():
    """The button says what is known, so the screen never guesses on the player's behalf."""
    kind = test_kind()
    if kind == "none":
        return "Проверить соединение"
    if kind == "timeout":
        return "Проверено: таймаут"
    return "Проверено: работает" if kind == "ok" else "Проверено: не работает"


def test_tone():
    kind = test_kind()
    if kind == "none":
        return "warn"
    if kind == "ok":
        return "good"
    if kind == "timeout":
        return "warn"
    return "bad"


def test_when_text():
    """One line for the always-visible strip: when it was checked and how fast it answered."""
    record = last_test()
    if not record.get("at"):
        return "Ещё не проверялось"
    return "Проверено %s • ответ за %d мс" % (
        _clock(record.get("at")), int(record.get("elapsed_ms", 0) or 0),
    )


def fix_hint():
    """What to do next, in Russian, for the failure the server reported.

    A message with no next step is a dead end, and "настройки не факт что работают" is
    exactly what a player concludes when the only information on screen is an exception.
    """
    record = last_test()
    if not record.get("at") or record.get("ok"):
        return ""
    text = str(record.get("text", "") or "").lower()
    for needle, advice in ADVICE:
        if needle in text and advice:
            return _clip(advice, STRIP_LIMIT)
    return "Проверь адрес и что сервер запущен."


def test_result_text():
    """The inline verdict: what came back, how long it took, which model answered."""
    record = last_test()
    if not record.get("at"):
        return "Кнопка делает настоящий запрос и показывает ответ сервера."
    marks = {"ok": "Ответ", "timeout": "Таймаут", "error": "Ошибка"}
    mark = marks.get(test_kind(), "Ошибка")
    return _clip(
        "%s: %s • %d мс • %s" % (mark, record.get("text", ""), int(record.get("elapsed_ms", 0) or 0), record.get("model", "?")),
        INLINE_LIMIT,
    )


def test_detail_text():
    """The full verdict underneath: when it happened, against which address, in full."""
    record = last_test()
    if not record.get("at"):
        return "Ещё ни одной проверки: нажмите кнопку выше — игра отправит один короткий запрос и покажет ответ."
    return _clip(
        "Проверено %s (%s) • адрес %s • %s"
        % (
            _clock(record.get("at")),
            _ago(record.get("at")) or "только что",
            record.get("url", "не задан"),
            record.get("text", ""),
        ),
        DETAIL_LIMIT,
    )


# ------------------------------------------------------------------- the profiles

def apply_builtin_profile():
    """Put the built-in profile back and leave the outcome on the line under the buttons.

    The button used to say "профиль применён" whether or not anything happened, because
    the message was written into the screen before the profile was applied. The return
    value of `apply_profile` is the truth, so it is what the player is shown.
    """
    import ai_provider

    try:
        message = ai_provider.apply_profile(ai_provider.DEFAULT_PROFILE)
    except Exception as exc:
        message = "Не удалось применить профиль: " + _clip(exc, ERROR_LIMIT)
    try:
        renpy.store.provider_test = str(message or "")
    except Exception:
        pass
    return message


# ------------------------------------------------------------------- the models

def _direct_models(url):
    import ai_provider

    from renpy.exports.fetchexports import fetch

    root = ai_provider.base_url(url)
    fallback = list(getattr(ai_provider, "_FALLBACK_MODELS", []) or [])
    if not root:
        return fallback, "Не задан адрес сервера"
    problems = []
    for target in (root + "/models", root + "/v1/models"):
        try:
            result = fetch(target, method="GET", headers=_headers(), timeout=8, result="json")
        except Exception as exc:
            problems.append(_clip(exc, 60))
            continue
        data = result.get("data") if isinstance(result, dict) else None
        if not data and isinstance(result, dict):
            data = result.get("models")
        ids = []
        for item in data or []:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict):
                name = item.get("id") or item.get("name")
                if name:
                    ids.append(str(name))
        if ids:
            return ids, "Модели загружены: %d" % len(ids)
        problems.append("пустой список")
    return fallback, "Список моделей недоступен (" + "; ".join(problems[:2]) + ")"


def refresh_models():
    """Ask the endpoint for its model list, with the same transport fallback as the check.

    Whether the list came from the server or from the built-in fallback is recorded, so
    the panel can say where a chosen model name came from instead of showing a chip list
    that looks authoritative and is only a guess.
    """
    import ai_provider

    url = str(_settings().get("api_url", "") or "")
    from_server = False
    try:
        models, note = ai_provider.model_ids()
    except AttributeError:
        # The provider module cannot reach renpy.fetch, so the same GET is issued here.
        models, note = _direct_models(url)
    except Exception as exc:
        models, note = [], "Список моделей недоступен: " + _clip(exc, ERROR_LIMIT)
    note = str(note or "")
    from_server = note.startswith("Модели загружены")
    try:
        renpy.store.provider_models = list(models or [])
        renpy.store.provider_models_note = note
        renpy.store.provider_models_from_server = bool(from_server)
    except Exception:
        pass
    return note


def models_note():
    """The last note about the model list, in the player's words."""
    try:
        return str(getattr(renpy.store, "provider_models_note", "") or "")
    except Exception:
        return ""


def models_from_server():
    """True only when the list on screen really came from the server."""
    try:
        if bool(getattr(renpy.store, "provider_models_from_server", False)):
            return True
    except Exception:
        pass
    return str(models_note()).startswith("Модели загружены")


def models_source_title():
    """What the list of names on screen really is, so a fallback is not passed off as fact."""
    try:
        if models_from_server():
            return "Список с сервера — нажми на модель, чтобы выбрать её"
    except Exception:
        pass
    return ("Сервер свой список не отдал: это встроенный набор имён. Если нужной модели "
            "среди них нет — впиши её вручную.")


def model_source_text():
    """Where the current model name came from, in one line.

    A local server that does not publish a list leaves the player typing an id by hand,
    and then a stale chip list from another server looks like a promise. This says which
    of the two it is, from the stored value and the last list, not from an assumption.
    """
    model = str(_settings().get("model", "") or "").strip()
    if not model:
        return "Модель не выбрана: выберите из списка или впишите имя вручную."
    models = []
    try:
        models = [str(item) for item in (getattr(renpy.store, "provider_models", []) or [])]
    except Exception:
        models = []
    if model in models:
        if models_from_server():
            return "Модель «%s» выбрана из списка, который отдал сервер." % model
        return ("Модель «%s» выбрана из встроенного списка: сервер свой список не отдал, "
                "проверь имя по «Загрузить модели с сервера»." % model)
    return ("Модель «%s» вписана вручную: сервер её не подтвердил. Если сцены не "
            "генерируются, сверь имя со списком моделей сервера." % model)


# ------------------------------------------------------------------- the catalog

def catalog_info():
    """(characters, backgrounds, when the catalog was last scanned) from the live catalog."""
    catalog = {}
    try:
        import engine

        found = engine.asset_catalog()
        if isinstance(found, dict):
            catalog = found
    except Exception:
        catalog = {}
    characters = len(catalog.get("characters") or [])
    backgrounds = len(catalog.get("backgrounds") or [])
    scanned = _scan_clock(catalog.get("generated_at"))
    if not scanned:
        scanned = _clock(getattr(_persistent(), SCAN_KEY, None))
    return characters, backgrounds, scanned


def rescan_assets():
    """The existing rescan, with the time of the scan recorded so the status line is true."""
    import engine

    result = engine.asset_rescan()
    try:
        setattr(_persistent(), SCAN_KEY, time.time())
        from renpy.exports.persistentexports import save_persistent

        save_persistent()
    except Exception:
        pass
    return result


# ------------------------------------------------------------------ what is used

def effective_lines():
    """The values the game will actually use, re-read on every screen update.

    Everything here is formatted by the schema, the same code the sliders and the row
    labels use, so the proof strip cannot show a number the engine does not have.
    """
    import vn_settings_schema

    settings = _settings()
    url = str(settings.get("api_url", "") or "не задан")
    model = str(settings.get("model", "") or "не выбрана")
    quality = str(settings.get("quality_model", "") or "") or "та же"
    absorber = str(settings.get("absorber_model", "") or "") or "основная"
    try:
        profile = str(getattr(_persistent(), "vn_ai_profile", "") or "не выбран")
    except Exception:
        profile = "не выбран"
    try:
        timeout = vn_settings_schema.display("timeout")
        temperature = vn_settings_schema.display("temperature")
        json_mode = vn_settings_schema.display("json_mode")
    except Exception:
        timeout, temperature, json_mode = "?", "?", "?"
    return [
        "Модель: %s  •  надсмотрщик: %s  •  поглотитель: %s" % (model, quality, absorber),
        "Адрес: %s" % _clip(url, 96),
        "Таймаут: %s  •  температура: %s  •  JSON-режим: %s  •  профиль: %s"
        % (timeout, temperature, json_mode, profile),
    ]


def ai_reason():
    """Why the game is running its own story instead of asking the model."""
    try:
        state = getattr(renpy.store, "game_state", None) or {}
        if not isinstance(state, dict):
            return ""
        return str(state.get("ai_error", "") or "").strip()
    except Exception:
        return ""


def local_mode():
    return bool(ai_reason())


def mode_text():
    reason = ai_reason()
    if reason:
        return "локальный сюжет — " + _clip(reason, 70)
    return "ИИ"


def save_dir():
    """Where the settings and the saves live, so "saved immediately" is a path."""
    try:
        folder = str(renpy.config.savedir)
    except Exception:
        return "(неизвестно)"
    if not os.path.isabs(folder):
        folder = os.path.abspath(folder)
    return folder


def save_dir_short(limit=78):
    """The same path on one line, for a footer that has a fixed height."""
    return _clip(save_dir(), limit)


# ------------------------------------------------------------------ the panel

def headline():
    """The single line summary, for anything that wants one string instead of a list."""
    for _tone, line in status_lines():
        return line
    return ""


def status_lines():
    """(tone, text) rows for the always-visible status block at the top of the panel.

    Three lines at most, because this block has a fixed height and must not push the
    rest of the panel out of its box: the verdict, the mode if the game fell back to its
    own story, and the reason with the advice on one line. The address, the model and the
    catalog counts are not repeated here -- every section shows its own real values in its
    "итог" strip, and the check card of the provider section carries the whole message.
    """
    record = last_test()
    kind = test_kind()
    if kind == "none":
        tone = "warn"
        head = "ИИ: ещё не проверялось — нажмите «Проверить соединение»"
    else:
        when = "%s (%s)" % (_clock(record.get("at")), _ago(record.get("at")) or "только что")
        if kind == "ok":
            tone = "good"
            head = "ИИ: работает • проверено %s" % when
        elif kind == "timeout":
            tone = "warn"
            head = "ИИ: ответ не пришёл за %d с • проверено %s" % (
                int(record.get("elapsed_ms", 0) or 0) // 1000 + 1, when,
            )
        else:
            tone = "bad"
            head = "ИИ: не работает • проверено %s" % when

    lines = [(tone, head)]

    if local_mode():
        # The mode is the reason "the model works but nothing changes": the game stopped
        # asking it and writes its own story instead, so it is a failure worth a line.
        lines.append(("bad", "Режим: %s" % _clip(mode_text(), STRIP_LIMIT)))
        tone = "bad" if tone == "good" else tone
        lines[0] = (tone, lines[0][1])

    if kind in ("error", "timeout"):
        reason = record.get("text", "")
        lines.append(("bad", _clip("Причина: %s. Что делать: %s" % (reason, fix_hint()), STRIP_LIMIT)))
    return lines


def section_help():
    """The one line that says what the visible section is for.

    The wording lives with the section itself, in the layout module, so the contents
    list, the section header and this helper can never describe different things.
    """
    try:
        import vn_settings_layout

        tab = str(getattr(renpy.store, "settings_tab", "") or "")
        return vn_settings_layout.help_of(tab)
    except Exception:
        return "Раздел не найден."
