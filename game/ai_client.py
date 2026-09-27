import json
import re

import renpy


def _headers(settings):
    headers = {"Content-Type": "application/json"}
    key = str(settings.get("api_key", "")).strip()
    if key:
        headers["Authorization"] = "Bearer " + key
    return headers


def _extract_json(text):
    if not text:
        raise ValueError("LLM returned an empty response")
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))
    starts = [p for p in (text.find("{"), text.find("[")) if p >= 0]
    first = min(starts) if starts else -1
    if first >= 0:
        last = max(text.rfind("}"), text.rfind("]"))
        if last > first:
            return json.loads(text[first:last + 1])
    raise ValueError("Could not extract JSON from LLM response")


def call_chat(prompt, system_prompt, settings, model_override=None, max_tokens=2200):
    url = str(settings.get("api_url", "")).strip()
    model = str(model_override or settings.get("model", "")).strip()
    if not url or not model:
        raise RuntimeError("AI endpoint or model is not configured")

    payload = {
        "model": model,
        "temperature": float(settings.get("temperature", 0.85)),
        "max_tokens": int(max_tokens),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    if settings.get("json_mode", False):
        payload["response_format"] = {"type": "json_object"}

    result = renpy.fetch(
        url,
        method="POST",
        json=payload,
        headers=_headers(settings),
        timeout=int(settings.get("timeout", 35)),
        result="json",
    )

    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError("No choices in LLM response")
    message = choices[0].get("message", {})
    content = message.get("content")
    if content is None:
        content = message.get("reasoning_content", "")
    return str(content)


def generate_world(brief, character_count, settings):
    system = """
Ты — сценарный архитектор движка Living VN.
Создай игровой мир для визуальной новеллы, а не ответ в виде чата.
Верни только JSON.
Сохраняй внутреннюю логику, небольшое число ключевых персонажей и понятные конфликты.
Не используй существующих персонажей или защищённые миры напрямую.
"""
    prompt = f"""
Параметры:
Название: {brief.get('title')}
Жанр: {brief.get('genre')}
Тон: {brief.get('tone')}
Описание: {brief.get('description')}
Количество персонажей: {character_count}

JSON schema:
{{
  "title": "...",
  "genre": ["..."],
  "tone": "...",
  "premise": "...",
  "characters": [{{
    "id": "...", "name": "...", "role": "...", "personality": "...",
    "goals": ["..."], "secrets": ["..."], "relationships": {{}}
  }}],
  "locations": {{"id": {{"description": "...", "lore": ["..."]}}}},
  "lore": ["..."],
  "opening": "..."
}}
"""
    return _extract_json(call_chat(prompt, system, settings, max_tokens=3400))


def generate_bundle(world, settings):
    bundle_size = max(4, min(12, int(settings.get("bundle_size", 8))))
    system = """
Ты — AI Director визуальной новеллы Living VN.
Игрок не общается с тобой напрямую: ты генерируешь игровой материал, который будет показан движком.
Не пиши пояснения вне JSON. Не говори от лица разработчика.
Каждый bundle должен быть самодостаточным микросценарием и заканчиваться естественным checkpoint.
Не телепортируй персонажей без scene.move. Не давай персонажам знания, которых они не получали.
Диалог должен соответствовать характеру.
"""
    prompt = _director_prompt(world, bundle_size)
    return _extract_json(call_chat(prompt, system, settings, max_tokens=4800))


def generate_free_response(world, player_text, settings):
    system = """
Ты — character/world director визуальной новеллы.
Ответ игрока уже является частью сцены. Продолжи игру как 2-5 игровых beat'ов.
Никаких пояснений, только JSON.
"""
    prompt = _director_prompt(world, 5)
    prompt += "\nСвободная реплика игрока:\n" + player_text
    return _extract_json(call_chat(prompt, system, settings, max_tokens=2800))


def supervise(world, bundle, settings):
    quality_model = str(settings.get("quality_model", "")).strip() or str(settings.get("model", "")).strip()
    system = """
Ты — беспристрастный редактор и надсмотрщик качества сюжета для Living VN.
Проверяй то, что уже произошло, и то, что собирается произойти дальше.
Отслеживай: противоречия, знания персонажей, повторяемость, темп, скуку, искусственные диалоги,
слишком резкие повороты, потерю агентности игрока, плохую мотивацию и слабое использование лора.
Верни только JSON.
"""
    prompt = f"""
WORLD:
{json.dumps(world, ensure_ascii=False, indent=2)}

CANDIDATE FUTURE BUNDLE:
{json.dumps(bundle, ensure_ascii=False, indent=2)}

Schema:
{{
  "score": 0.0,
  "approved": true,
  "summary": "...",
  "issues": ["..."],
  "director_command": "...",
  "repair": false
}}
"""
    return _extract_json(call_chat(prompt, system, settings, model_override=quality_model, max_tokens=2200))


def _director_prompt(world, bundle_size):
    supervisor = world.get("supervisor_command", "")
    return f"""
Сгенерируй до {bundle_size} последовательных beat'ов.
Требуемый JSON:
{{
  "beats": [
    {{
      "type": "scene|dialogue|narration|choice|wait|music",
      "speaker": "character_id|narrator|null",
      "text": "...",
      "character": "character_id|null",
      "emotion": "neutral|happy|sad|angry|embarrassed|surprised|thinking|...",
      "motion": "idle|wave|nod|look_away|...|null",
      "position": "left|center|right|far_left|far_right|null",
      "background": "path-or-location-id|null",
      "characters": [{{"id":"...","emotion":"...","motion":"...","position":"left|center|right"}}],
      "music_intent": "calm|romance|nostalgia|tension|mystery|sad|comedy|horror|triumph|none|null",
      "choices": [{{"id": "a", "text": "..."}}, {{"id": "b", "text": "..."}}],
      "checkpoint": true,
      "state_patch": {{"...": "..."}}
    }}
  ]
}}

Правила:
- Обычно 5-9 beats до следующего checkpoint.
- Не добавляй choice в каждый beat.
- `scene` меняет фон/перемещение, `dialogue` — реплику, `narration` — рассказ, `music` — смену музыки.
- Используй только существующие character_id и location_id.
- state_patch должен быть маленьким и очевидным.
- Один checkpoint обычно ставь перед choice, reveal, сменой локации или эмоциональным поворотом.
- Игрок должен влиять на события, но свободный ввод не обязан присутствовать в каждом разговоре.

WORLD STATE:
{json.dumps(world, ensure_ascii=False, indent=2)}

SUPERVISOR COMMAND:
{supervisor}
"""
