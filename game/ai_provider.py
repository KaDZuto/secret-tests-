"""The AI provider: named profiles, model discovery and a connection test.

The game talks to any OpenAI-compatible endpoint. A "profile" is a saved set of those
settings, so switching between a local proxy, a hosted API and a second local model is
one click instead of retyping a URL. Model ids are read from the live server through
`/v1/models` when the server exposes it, and fall back to what the player typed.

Nothing here is required for the game to run: a provider is optional, and a failure in
this module is reported in the settings screen instead of raising into the dialogue.

The requests go through `ai_client`, which uses `urllib` rather than `renpy.fetch`. That
function is not an attribute of the `renpy` package in this project -- display and fetch
helpers live in `renpy.exports` -- so a call written as `renpy.fetch(...)` raised
`AttributeError` and every check here reported a broken module instead of a working server.
Both calls below still block the thread they are made on, which is why the settings screen's
check has a short ceiling and the story's request runs on a worker.
"""

from vn_settings_schema import DEFAULTS, view
import ai_client

PROVIDER_KEYS = (
    "api_url",
    "api_key",
    "model",
    "quality_model",
    "absorber_model",
    "temperature",
    "timeout",
    "json_mode",
    "bundle_size",
    "max_history",
    "supervisor",
    "supervisor_threshold",
)

DEFAULT_PROFILE = "DeepSeek (локальный прокси)"
DEEPSEARCH_BASE = "http://127.0.0.1:9655"

# Last known working defaults, so a fresh install has something to talk to.
BUILTIN_PROFILES = {
    DEFAULT_PROFILE: {
        "api_url": DEEPSEARCH_BASE + "/v1/chat/completions",
        "api_key": "",
        "model": "deepseek-chat",
        "quality_model": "deepseek-reasoner",
        "absorber_model": "",
        "temperature": 0.85,
        "timeout": 120,
        "json_mode": True,
        "bundle_size": 8,
        "max_history": 18,
        "supervisor": True,
        "supervisor_threshold": 7.0,
    },
}

_FALLBACK_MODELS = [
    "deepseek-chat",
    "deepseek-default",
    "deepseek-v3",
    "deepseek-reasoner",
    "deepseek-r1",
    "deepseek-chat-search",
    "deepseek-v4-pro",
]


def base_url(url):
    """The server root of an endpoint, e.g. .../v1/chat/completions -> server root."""
    text = str(url or "").strip()
    for suffix in ("/chat/completions", "/completions", "/responses"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def headers():
    key = str(view.get("api_key", "") or "").strip()
    result = {"Content-Type": "application/json"}
    if key:
        result["Authorization"] = "Bearer " + key
    return result


def model_ids(url=None):
    """Model ids from the live server, or the built-in list when it does not answer."""
    settings = {k: view.get(k) for k in ("api_key",)}
    root = base_url(url or view.get("api_url"))
    if not root:
        return list(_FALLBACK_MODELS), "Не задан адрес сервера"

    # A base URL may or may not already include the /v1 prefix, so both are tried.
    problems = []
    for target in (root + "/models", root + "/v1/models"):
        try:
            result = ai_client.get_json(target, settings, timeout=8)
        except Exception as exc:
            problems.append(str(exc)[:60])
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

    return list(_FALLBACK_MODELS), "Список моделей недоступен (" + "; ".join(problems[:2]) + ")"


def apply_profile(name):
    """Copy a stored profile into the live settings."""
    from renpy.store import persistent

    profile = (persistent.vn_ai_profiles or {}).get(name)
    if not profile:
        return "Профиль не найден: " + str(name)
    for key in PROVIDER_KEYS:
        if key in profile:
            view.__setattr__(key, profile[key])
    return "Профиль применён: " + str(name)


def store_profile(name):
    """Save the current provider settings under a profile name."""
    from renpy.store import persistent

    name = str(name or "").strip()
    if not name:
        return "Имя профиля пустое"
    profiles = dict(persistent.vn_ai_profiles or {})
    if name in (persistent.vn_ai_profiles or {}) and name not in BUILTIN_PROFILES:
        profiles[name] = dict(profiles.get(name) or {})
    else:
        profiles[name] = dict(BUILTIN_PROFILES.get(name) or {})
    for key in PROVIDER_KEYS:
        profiles[name][key] = view.get(key, DEFAULTS.get(key))
    persistent.vn_ai_profiles = profiles
    return "Профиль сохранён: " + name


def delete_profile(name):
    from renpy.store import persistent

    if name in BUILTIN_PROFILES:
        return "Встроенный профиль не удаляется"
    profiles = dict(persistent.vn_ai_profiles or {})
    if name not in profiles:
        return "Профиль не найден: " + str(name)
    profiles.pop(name)
    persistent.vn_ai_profiles = profiles
    if getattr(persistent, "vn_ai_profile", "") == name:
        persistent.vn_ai_profile = DEFAULT_PROFILE
    return "Профиль удалён: " + name


def set_active_profile(name):
    from renpy.store import persistent

    persistent.vn_ai_profile = str(name or DEFAULT_PROFILE)
    return apply_profile(name)


def reset_to_builtin(name):
    from renpy.store import persistent

    if name not in BUILTIN_PROFILES:
        return "Это не встроенный профиль"
    persistent.vn_ai_profiles = dict(BUILTIN_PROFILES)
    return "Встроенные профили восстановлены"


def test_connection(url=None, model=None):
    """One short request, so the settings screen can prove the endpoint works."""
    endpoint = str(url or view.get("api_url") or "").strip()
    chosen = str(model or view.get("model") or "").strip()
    if not endpoint:
        return False, "Адрес не задан"
    if not chosen:
        return False, "Модель не выбрана"
    payload = {
        "model": chosen,
        "messages": [{"role": "user", "content": "Ответь одним словом: работает?"}],
        "max_tokens": 24,
        "temperature": 0.0,
    }
    try:
        result = ai_client.post_json(
            endpoint,
            payload,
            {"api_key": view.get("api_key")},
            timeout=int(view.get("timeout", 60) or 60),
        )
    except Exception as exc:
        message = getattr(exc, "message", str(exc))
        advice = getattr(exc, "advice", "")
        return False, ("Ошибка запроса: " + str(message)[:120]) + ((" — " + advice) if advice else "")
    text = ai_client.message_text(result)
    if text is None:
        return False, "Ответ без choices"
    return True, "Ответ: " + (text[:80] if text else "(пусто)")
