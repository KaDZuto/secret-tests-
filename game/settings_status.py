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

# Widths chosen for the panel: the status line is one line, the inline test result is one
# line next to its button, and the detail line below them is two.
INLINE_LIMIT = 64
DETAIL_LIMIT = 200
ERROR_LIMIT = 90

SECTION_HELP = {
    "ai": "ИИ — адрес сервера, модель и параметры генерации; здесь же настоящая проверка соединения.",
    "assets": "Ассеты — персонажи и фоны, которые игра берёт из папок и паков, и привязка их к миру.",
    "sound": "Звук — музыка, громкости каналов и локальная озвучка через Silero/TTS.",
    "ui": "Интерфейс — стандартные настройки Ren'Py, Live2D и режим слабой машины.",
    "data": "Данные — экспорт и импорт мира в JSON, которым можно поделиться с другим игроком.",
    "cannibalism": "Поглощение — разбор чужой игры и перенос её ресурсов сюда, с оценкой ИИ.",
}


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


def _characters(count):
    return "%d %s" % (count, _plural(count, "персонаж", "персонажа", "персонажей"))


def _backgrounds(count):
    return "%d %s" % (count, _plural(count, "фон", "фона", "фонов"))


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


def _direct_test(url, model):
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
    try:
        result = fetch(
            url,
            method="POST",
            json=payload,
            headers=_headers(),
            timeout=int(_settings().get("timeout", 60) or 60),
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


def _remember(ok, text, elapsed_ms, model, url):
    record = {
        "ok": bool(ok),
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
    """Send one real request and remember what came back. Returns (ok, text, elapsed_ms)."""
    import ai_provider

    settings = _settings()
    model = str(settings.get("model", "") or "")
    url = str(settings.get("api_url", "") or "")

    started = time.time()
    try:
        ok, message = ai_provider.test_connection()
    except AttributeError:
        # The provider module cannot reach renpy.fetch. Measure the same endpoint here
        # rather than reporting our own plumbing as a broken server.
        ok, message = _direct_test(url, model)
    except Exception as exc:
        ok, message = False, "Ошибка проверки: " + _clip(exc, ERROR_LIMIT)
    elapsed_ms = int((time.time() - started) * 1000)

    words = _clip(_reply_words(message, ok), ERROR_LIMIT)
    _remember(ok, words, elapsed_ms, model or "не выбрана", url or "не задан")
    return (bool(ok), words, elapsed_ms)


def test_label():
    """The button says what is known, so the screen never guesses on the player's behalf."""
    record = last_test()
    if not record.get("at"):
        return "Проверить соединение"
    return "Проверено: работает" if record.get("ok") else "Проверено: не работает"


def test_tone():
    record = last_test()
    if not record.get("at"):
        return "warn"
    return "good" if record.get("ok") else "bad"


def test_result_text():
    """The inline verdict: what came back, how long it took, which model answered."""
    record = last_test()
    if not record.get("at"):
        return "Кнопка делает настоящий запрос и показывает ответ сервера."
    mark = "Ответ" if record.get("ok") else "Ошибка"
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
    """Ask the endpoint for its model list, with the same transport fallback as the check."""
    import ai_provider

    url = str(_settings().get("api_url", "") or "")
    try:
        models, note = ai_provider.model_ids()
    except AttributeError:
        models, note = _direct_models(url)
    except Exception as exc:
        models, note = [], "Список моделей недоступен: " + _clip(exc, ERROR_LIMIT)
    try:
        renpy.store.provider_models = list(models or [])
        renpy.store.provider_models_note = str(note or "")
    except Exception:
        pass
    return note


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
    """The values the game will actually use, re-read on every screen update."""
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
        timeout = int(settings.get("timeout", 0) or 0)
    except Exception:
        timeout = 0
    try:
        temperature = float(settings.get("temperature", 0.0) or 0.0)
    except Exception:
        temperature = 0.0
    return [
        "Модель: %s  •  надсмотрщик: %s  •  поглотитель: %s" % (model, quality, absorber),
        "Адрес: %s" % _clip(url, 96),
        "Таймаут: %d с  •  температура: %.2f  •  JSON-режим: %s  •  профиль: %s"
        % (timeout, temperature, "ВКЛ" if settings.get("json_mode") else "ВЫКЛ", profile),
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


# ------------------------------------------------------------------ the panel

def headline():
    """The single line summary, for anything that wants one string instead of a list."""
    for _tone, line in status_lines():
        return line
    return ""


def status_lines():
    """(tone, text) rows for the always-visible status block at the top of the panel."""
    record = last_test()
    try:
        settings = _settings()
        model = str(settings.get("model", "") or "не выбрана")
        url = str(settings.get("api_url", "") or "не задан")
    except Exception:
        model, url = "неизвестно", "неизвестно"

    if record.get("at"):
        when = "%s (%s)" % (_clock(record.get("at")), _ago(record.get("at")) or "только что")
        if record.get("ok"):
            tone = "good"
            head = "ИИ: работает • проверено %s" % when
        else:
            tone = "bad"
            head = "ИИ: не работает • проверено %s" % when
    else:
        tone = "warn"
        head = "ИИ: ещё не проверялось — нажмите «Проверить соединение»"

    if local_mode():
        tone = "bad" if tone == "good" else tone
    lines = [(tone, "%s  •  Режим: %s" % (head, mode_text()))]

    if record.get("at") and not record.get("ok"):
        lines.append(("bad", "Причина: %s" % _clip(record.get("text", ""), DETAIL_LIMIT)))

    lines.append(("none", "Адрес: %s  •  модель: %s" % (_clip(url, 78), _clip(model, 40))))

    characters, backgrounds, scanned = catalog_info()
    lines.append(("none", "Каталог: %s / %s%s" % (
        _characters(characters),
        _backgrounds(backgrounds),
        " • просканирован %s" % scanned if scanned else " • ещё не сканировался",
    )))
    return lines


def section_help():
    """The one line that says what the visible section is for."""
    try:
        tab = str(getattr(renpy.store, "settings_tab", "") or "")
    except Exception:
        tab = ""
    return SECTION_HELP.get(tab, "Раздел не найден.")
