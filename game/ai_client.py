"""The transport to any OpenAI-compatible server, and the two non-story calls.

`renpy.fetch` is not an attribute of the `renpy` package in this project -- display and
fetch helpers live in `renpy.exports` -- so a call written as `renpy.fetch(...)` raised
`AttributeError` every time and every failure looked like "the model is broken" while the
real cause was a line of code. Nothing here uses it any more: HTTP goes through
`urllib.request`, which is always present, and every failure is an `AIError` that carries a
Russian sentence and the next step to take.

The module is deliberately import-free of Ren'Py, so the smoke tests and the parser test
can exercise it, and the real request can be issued from a worker thread. A socket call on
the main thread is what freezes a visual novel: the interpreter cannot redraw, cannot answer
ESC and cannot open the menu until the server answers or the timeout expires. So the story
callers live in `story_pipeline`, and only the transport sits here.

Two calls stay in this module because they are not the story: `generate_world` builds the
world at the start, and `supervise` is the second opinion about a bundle. Both are wrappers
around the same transport and are used from a worker thread as well.
"""

import json
import random
import socket
import urllib.error
import urllib.request

# A local model asked for a whole chapter can answer with a lot of text, but not with an
# unbounded amount: reading it all into the game's memory is how a slow machine stalls, and
# anything past this limit is unusable anyway because the repair request quotes it back.
MAX_TTS_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 400_000

# What to tell the player, in the words the failure actually used, plus the next step. A
# message with no next step is a dead end, and "the model is broken" is exactly what a player
# concludes when the only thing on screen is an exception.
ADVICE = (
    ("connection refused", "Сервер не слушает этот порт. Запусти модель: Ollama, LM Studio или llama.cpp."),
    ("timed out", "Ответа не было. Подними «Таймаут запроса» или уменьши «Сцен в одном запросе»."),
    ("timeout", "Ответа не было. Проверь, что модель загрузилась, или подними таймаут."),
    ("name or service not known", "Адрес не найден. Проверь имя хоста и порт модели."),
    ("no route to host", "Сеть недоступна. Проверь адрес или VPN."),
    ("404", "Нужен полный путь: http://127.0.0.1:11434/v1/chat/completions (Ollama) "
            "или http://127.0.0.1:1234/v1/chat/completions (LM Studio)."),
    ("401", "Ключ отвергнут. Локальному серверу ключ не нужен — очисти поле «Ключ доступа»."),
    ("403", "Сервер не пускает с этим ключом. Проверь ключ или права доступа."),
    ("502", "Прокси не дождался модели. Дождись загрузки модели и повтори запрос."),
    ("503", "Модель не загружена или сервер перегружен. Подожди и повтори запрос."),
    ("500", "Сервер упал на этом запросе. Проверь журнал сервера модели и повтори."),
)


class AIError(Exception):
    """A failed request, as text a player can act on.

    `kind` is "timeout", "connection", "http", "empty", "too_long" or "error", and is what
    the waiting screen colours; `advice` is the sentence with the next step.
    """

    def __init__(self, message, kind="error", advice=""):
        Exception.__init__(self, message)
        self.message = str(message)
        self.kind = str(kind or "error")
        self.advice = str(advice or "")


def _clip(text, limit=200):
    """One line, at most `limit` characters, so a long server error cannot break a row."""
    text = str(text or "").replace("\n", " ").replace("\r", " ").strip()
    if len(text) > limit:
        return text[: max(1, limit - 1)].rstrip() + "…"
    return text


def _advice_for(text):
    """The advice whose trigger the server or the socket actually used."""
    lowered = str(text or "").lower()
    for needle, advice in ADVICE:
        if needle in lowered:
            return advice
    return ""


def headers_for(settings):
    result = {"Content-Type": "application/json", "Accept": "application/json"}
    key = str((settings or {}).get("api_key", "") or "").strip()
    if key:
        result["Authorization"] = "Bearer " + key
    return result


def _timeout(settings, default=60):
    try:
        value = float((settings or {}).get("timeout", default))
    except (TypeError, ValueError):
        return float(default)
    # A local model on a CPU thinks for minutes on the first token; a ceiling below 15
    # seconds only produces a false "the server is down".
    return max(5.0, min(900.0, value))


def _decode(raw):
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return str(raw or "")


def post_json(url, payload, settings=None, timeout=None):
    """POST JSON and return the parsed answer, or raise `AIError` with a Russian reason."""
    target = str(url or "").strip()
    if not target:
        raise AIError("Адрес сервера не задан.", "config",
                      "Впиши адрес в настройках ИИ: http://127.0.0.1:11434/v1/chat/completions")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(target, data=body, method="POST")
    for key, value in headers_for(settings).items():
        request.add_header(key, value)

    limit = _timeout(settings) if timeout is None else float(timeout)
    try:
        with urllib.request.urlopen(request, timeout=limit) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        try:
            detail = _clip(_decode(exc.read()), 220)
        except Exception:
            detail = ""
        reason = _clip(detail or exc.reason or "ответа нет", 220)
        raise AIError("Сервер ответил ошибкой %s: %s" % (exc.code, reason), "http",
                      _advice_for("%s %s" % (exc.code, reason)))
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise AIError("Модель не ответила за %d с" % int(limit), "timeout", _advice_for("timed out"))
        text = _clip(reason, 200)
        raise AIError("Не удалось соединиться с сервером: %s" % text, "connection",
                      _advice_for(text))
    except (socket.timeout, TimeoutError):
        raise AIError("Модель не ответила за %d с" % int(limit), "timeout", _advice_for("timed out"))
    except OSError as exc:
        text = _clip(exc, 200)
        raise AIError("Соединение оборвалось: %s" % text, "connection", _advice_for(text))

    if len(raw) > MAX_RESPONSE_BYTES:
        raise AIError(
            "Ответ модели слишком длинный (больше %d КБ)." % (MAX_RESPONSE_BYTES // 1024),
            "too_long",
            "Уменьши «Сцен в одном запросе» — например, до 4. Модель не успевает уложиться в лимит.",
        )

    text = _decode(raw).strip()
    if not text:
        raise AIError("Сервер вернул пустой ответ.", "empty",
                      "Проверь, что модель загрузилась, и повтори запрос.")
    try:
        return json.loads(text)
    except ValueError:
        raise AIError("Сервер вернул не JSON: " + _clip(text, 200), "not_json",
                      "Адрес должен указывать на /v1/chat/completions. Если адрес верный, "
                      "повтори запрос: модель ответила текстом вместо JSON.")


def post_bytes(url, payload, settings=None, timeout=20):
    """POST JSON and return the raw body.

    The speech endpoint answers with a WAV, not with JSON, so this is the one call that
    cannot go through `post_json`. The refusals are the same ones, in the same Russian wording,
    because a TTS server that is not running should say so as plainly as a model server.
    """
    target = str(url or "").strip()
    if not target:
        raise AIError("Адрес сервера озвучки не задан.", "config",
                      "Впиши адрес в настройках звука, например http://127.0.0.1:9880")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(target, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in headers_for(settings).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=float(timeout)) as response:
            return response.read(MAX_TTS_BYTES)
    except urllib.error.HTTPError as exc:
        raise AIError("Сервер озвучки ответил ошибкой %s" % exc.code, "http",
                      _advice_for(str(exc.code)))
    except urllib.error.URLError as exc:
        text = _clip(exc.reason, 200)
        raise AIError("Не удалось соединиться с сервером озвучки: %s" % text, "connection",
                      _advice_for(text))
    except (socket.timeout, TimeoutError):
        raise AIError("Сервер озвучки не ответил за %d с" % int(timeout), "timeout",
                      _advice_for("timed out"))
    except OSError as exc:
        text = _clip(exc, 200)
        raise AIError("Соединение с сервером озвучки оборвалось: %s" % text, "connection",
                      _advice_for(text))


def get_json(url, settings=None, timeout=10):
    """GET JSON, or raise `AIError`. Used by the model list, which has no other path."""
    target = str(url or "").strip()
    if not target:
        raise AIError("Адрес сервера не задан.", "config", "Впиши адрес в настройках ИИ.")
    request = urllib.request.Request(target, method="GET")
    for key, value in headers_for(settings).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=float(timeout)) as response:
            raw = response.read(MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        raise AIError("Сервер ответил ошибкой %s" % exc.code, "http", _advice_for(str(exc.code)))
    except urllib.error.URLError as exc:
        text = _clip(exc.reason, 200)
        raise AIError("Не удалось соединиться с сервером: %s" % text, "connection", _advice_for(text))
    except (socket.timeout, TimeoutError):
        raise AIError("Сервер не ответил за %d с" % int(timeout), "timeout", _advice_for("timed out"))
    except OSError as exc:
        text = _clip(exc, 200)
        raise AIError("Соединение оборвалось: %s" % text, "connection", _advice_for(text))
    try:
        return json.loads(_decode(raw) or "{}")
    except ValueError:
        raise AIError("Список моделей пришёл не в JSON.", "not_json", "Проверь адрес сервера.")


def message_text(result):
    """The assistant's text out of an OpenAI-shaped answer, or None when there is none.

    A reasoning model can put its thinking in `reasoning_content` and answer in `content`;
    some builds answer only in `reasoning_content`. Both are read, and an answer that is
    only whitespace counts as no answer at all.
    """
    choices = result.get("choices") if isinstance(result, dict) else None
    if not choices:
        return None
    message = choices[0].get("message") or {}
    for key in ("content", "reasoning_content"):
        text = str(message.get(key) or "").strip()
        if text:
            return text
    return None


# The seed of the request that went out last. Two consecutive requests must differ, and a
# one-in-two-billion coincidence is still a duplicate story in a test, so the re-roll loop
# makes "the payloads differ by seed" a guarantee rather than a probability.
_LAST_SEED = {"value": 0}


def _fresh_seed():
    """A random integer seed no previous request in this process used."""
    while True:
        value = random.randrange(1, 1 << 31)
        if value != _LAST_SEED["value"]:
            _LAST_SEED["value"] = value
            return value


def call_chat(prompt, system_prompt, settings, model_override=None, max_tokens=2200):
    """One chat completion, as text. Raises `AIError` on every failure.

    Two identical requests must not become one identical answer: a model or a proxy in front
    of it can answer deterministically even at temperature 0.85, and a player who gets the
    same story word for word reads it as a bug. So every payload carries its own random
    `seed` (an integer, understood by DeepSeek and ignored by servers that do not know it),
    and no answer is ever cached -- each call opens the socket again.
    """
    url = str((settings or {}).get("api_url", "") or "").strip()
    model = str(model_override or (settings or {}).get("model", "") or "").strip()
    if not url:
        raise AIError("Адрес сервера не задан.", "config",
                      "Впиши адрес в настройках ИИ: http://127.0.0.1:11434/v1/chat/completions")
    if not model:
        raise AIError("Модель не выбрана.", "config", "Выбери модель в списке или впиши её имя руками.")

    try:
        temperature = float((settings or {}).get("temperature", 0.85))
    except (TypeError, ValueError):
        temperature = 0.85
    payload = {
        "model": model,
        "temperature": temperature,
        "seed": _fresh_seed(),
        "max_tokens": int(max_tokens),
        "messages": [
            {"role": "system", "content": str(system_prompt or "")},
            {"role": "user", "content": str(prompt or "")},
        ],
    }
    if (settings or {}).get("json_mode", False):
        # A local model that does not support the knob ignores it, and one that does support
        # it stops wrapping the answer in prose -- which is the whole point of asking.
        payload["response_format"] = {"type": "json_object"}
    result = post_json(url, payload, settings)
    text = message_text(result)
    if not text:
        raise AIError("Модель вернула пустой ответ.", "empty",
                      "Проверь, что модель загрузилась, и повтори запрос.")
    return text


# ------------------------------------------------------------------ world build

def generate_world(brief, character_count, settings):
    system = """
Ты — сценарный архитектор движка Living VN.
Создай игровой мир для визуальной новеллы, а не ответ в виде чата.
Верни только JSON: без пояснений, без обрамления в тройные кавычки.
Несколько ключевых персонажей, понятные конфликты, связи между персонажами.
"""
    prompt = """
Параметры:
Название: {title}
Жанр: {genre}
Тон: {tone}
Описание: {description}
Количество персонажей: {count}

Верни JSON такого вида:
{{
  "title": "...",
  "genre": ["..."],
  "tone": "...",
  "premise": "...",
  "characters": [{{
    "id": "ascii_id", "name": "Имя", "role": "роль", "personality": "...",
    "goals": ["..."], "secrets": ["..."], "relationships": {{"player": 0}}
  }}],
  "locations": {{"id": {{"description": "...", "lore": ["..."]}}}},
  "lore": ["..."],
  "opening": "..."
}}
""".format(
        title=brief.get("title"),
        genre=brief.get("genre"),
        tone=brief.get("tone"),
        description=brief.get("description"),
        count=int(character_count),
    )
    import story_pipeline

    return story_pipeline.parse_object(call_chat(prompt, system, settings, max_tokens=3400))


# --------------------------------------------------------------------- the check

def supervise(world, bundle, settings):
    """The second opinion about a bundle: a score, a verdict and, if needed, a command."""
    quality_model = str((settings or {}).get("quality_model", "") or "").strip() \
        or str((settings or {}).get("model", "") or "").strip()
    system = """
Ты — беспристрастный редактор визуальной новеллы. Твоя работа — найти, что именно не так
с готовящейся сценой, и дать режиссёру одну конкретную правку. Проверяй по критериям:

1. Слова. Естественная живая русская речь. Лови переводную кривизну, канцелярит, штампы
   («не мог не отметить», «в мире, где», «обрывок тишины» в каждом шаге) и AI-шлак:
   шаблонные обороты и повторяющиеся конструкции от шага к шагу.
2. Голоса. У каждого персонажа свой голос: свой словарь, свой ритм, своя длина реплик.
   Если все говорят одинаково — это ошибка.
3. Память и логика. Сцена опирается на предыдущие шаги из состояния мира: кто что знает,
   где находится, сколько времени прошло. Персонаж не помнит того, чего не слышал;
   события не откатываются и не противоречат уже показанному.
4. Посторонние детали. Случайная смена костюма, обстановки, времени суток или отношений
   без основания в предыдущих шагах — деталь вывалилась из ниоткуда, это ошибка.
5. Темп и цель. Не пересказ увиденного и не спешка: каждый шаг двигает сцену, а выбор
   вытекает из ситуации.

Состояние мира содержит историю шагов и память — сверяй сцену именно с ней.
Верни ТОЛЬКО JSON: без пояснений и без обрамления в тройные кавычки.
{
  "score": 0.0,
  "approved": true,
  "summary": "...",
  "issues": ["..."],
  "director_command": "что исправить в следующем запросе",
  "repair": false
}
Правила вердикта: score — от 0 до 10, 10 — показывать как есть. issues — конкретные
замечания списком, каждое с примером из сцены, а не общие слова. director_command — ОДНА
точная правка для следующей переписи (что убрать, что развести, что связать). Если
approved=false или repair=true, director_command обязателен и обязан называть правку.
"""
    prompt = """
СОСТОЯНИЕ МИРА (история шагов и память — часть его):
{world}

СЦЕНА, КОТОРАЯ ГОТОВИТСЯ:
{bundle}

Оцени сцену по критериям из системной инструкции и верни JSON такого вида:
{{
  "score": 0.0,
  "approved": true,
  "summary": "...",
  "issues": ["конкретное замечание", "ещё замечание"],
  "director_command": "одна точная правка для переписи",
  "repair": false
}}
""".format(world=json.dumps(_digest(world), ensure_ascii=False, indent=2),
           bundle=json.dumps(bundle, ensure_ascii=False, indent=2)[:6000])
    import story_pipeline

    return story_pipeline.parse_object(
        call_chat(prompt, system, settings, model_override=quality_model, max_tokens=1200))


def _digest(world):
    """The world's own fields, without the buffers and the caches, for a prompt."""
    world = world or {}
    return {k: v for k, v in world.items()
            if k not in ("buffer", "music_catalog", "absorbed_packs", "chapter", "visual")}


# ------------------------------------------- compatibility with the old entry points

def _extract_json(text):
    """The old JSON out of a model answer. `music` and `cannibalism` still import this.

    The tolerant reader lives in `story_pipeline` now; this name stays so the two modules
    that were not part of the story rewrite keep working unchanged.
    """
    import story_pipeline

    return story_pipeline.parse_object(text)


def generate_bundle(world, settings):
    """Kept so `from ai_client import generate_bundle` still resolves. See `story_pipeline`."""
    import story_pipeline

    return {"steps": story_pipeline.generate_steps(world, settings)}


def generate_free_response(world, player_text, settings):
    import story_pipeline

    return {"steps": story_pipeline.generate_steps(world, settings, player_text=player_text)}
