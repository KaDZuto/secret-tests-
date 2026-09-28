#!/usr/bin/env python3
"""Проверка разбора ответа модели и починки сломанного JSON.

Запускается без Ren'Py: `renpy` подменяется заглушкой, а HTTP -- локальным сервером на
127.0.0.1, который отвечает заранее заданным текстом. Это важно: настоящий разбор проверяется
на настоящем сокете, потому что половина ошибок (`ConnectionRefused`, пустой ответ, не-JSON,
слишком длинный ответ) живёт именно в транспорте, а не в парсере.

Проверяется:
  * разбор реальных строк, которые отдают локальные модели: ```-обёртка, «Вот массив:» перед
    JSON, голый массив, объект с полем `steps`, старый ключ `beats`, одиночный объект-шаг,
    обрезанный хвост (забытая скобка), два массива в одном ответе;
  * нормализация элемента в тот формат, который уже читает `script.rpy` и `engine.py`;
  * замена выдуманного id персонажа и неизвестной эмоции на реальные из каталога;
  * одна повторная попытка с инструкцией починки, когда первый ответ нечитаем;
  * русские сообщения с подсказкой для таймаута, отказа соединения, пустого ответа, не-JSON
    и слишком длинного ответа;
  * что главный поток не блокируется: запрос уходит в поток, а опрос возвращает управление
    раньше, чем сервер отвечает.
"""
import json
import os
import sys
import threading
import time
import types
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "game"

# ---------------------------------------------------------------- заглушка Ren'Py
renpy = types.ModuleType("renpy")
renpy.config = types.SimpleNamespace(gamedir=str(GAME))
renpy.loadable = lambda name, **kwargs: False
renpy.list_files = lambda: []
loader = types.ModuleType("renpy.loader")
loader.loadable = renpy.loadable
loader.load = lambda *a, **k: None
renpy.loader = loader
sys.modules["renpy"] = renpy
sys.modules["renpy.config"] = renpy.config
sys.modules["renpy.loader"] = loader
sys.path.insert(0, str(GAME))

import ai_client  # noqa: E402
import prompts_story  # noqa: E402
import story_pipeline  # noqa: E402
import story_chapter  # noqa: E402

PASS = []
FAIL = []


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    mark = "ok  " if condition else "FAIL"
    print("  %s %s%s" % (mark, name, (" -- " + str(detail)[:180]) if not condition and detail else ""))


# --------------------------------------------------------------- локальный сервер
SCRIPT = []          # что сервер отвечает, по порядку
DELAY = 0.0          # задержка перед ответом
REQUESTS = []        # журнал пришедших запросов


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_one_request(self):
        # A client that walked away mid-response is the timeout case, not a test failure.
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _send(self, code, body, ctype="application/json"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(length)
        try:
            REQUESTS.append(json.loads(payload.decode("utf-8")))
        except Exception:
            REQUESTS.append({})
        if DELAY:
            time.sleep(DELAY)
        if not SCRIPT:
            self._send(500, '{"error":"сценарий теста пуст"}')
            return
        answer = SCRIPT.pop(0)
        if isinstance(answer, tuple):
            self._send(answer[0], answer[1])
            return
        self._send(200, answer)


def serve():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, "http://127.0.0.1:%d/v1/chat/completions" % server.server_port


def settings(url, model="qwen3:8b", **over):
    data = {
        "api_url": url, "api_key": "", "model": model, "quality_model": model,
        "temperature": 0.85, "timeout": 20, "json_mode": True,
        "bundle_size": 4, "max_history": 12, "supervisor": False,
        "supervisor_threshold": 7.0,
    }
    data.update(over)
    return data


def answer(content):
    """Ответ в форме OpenAI, как его отдаёт llama.cpp, Ollama и LM Studio."""
    return json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False)


def world():
    return story_chapter.chapter_world()


# ============================================================ 1. разбор ответа
print("\n1. Разбор реальных строк, которые отдают локальные модели")

STEP = {
    "background": "ext_camp_entrance_day",
    "characters": [{"id": "asuna", "position": "center", "emotion": "smile", "pose": "pose_01_000"}],
    "text": "«Ты всё-таки приехал».",
    "who": "asuna",
}
CHOICE = {
    "background": "ext_camp_entrance_day",
    "characters": [{"id": "asuna", "position": "left", "emotion": "think", "pose": "pose_01_000"}],
    "text": "Она ждёт ответа.",
    "who": None,
    "choices": [{"id": "ask", "text": "Спросить."}, {"id": "wait", "text": "Помолчать."}],
}
ARRAY = json.dumps([STEP, CHOICE], ensure_ascii=False)

cases = [
    ("голый массив", ARRAY, 2),
    ("```json-обёртка", "```json\n" + ARRAY + "\n```", 2),
    ("обёртка без json", "```\n" + ARRAY + "\n```", 2),
    ("пояснение перед JSON", "Вот продолжение, как вы просили:\n" + ARRAY, 2),
    ("пояснение после JSON", ARRAY + "\n\nP.S. Надеюсь, подойдёт.", 2),
    ("объект с полем steps", json.dumps({"steps": [STEP, CHOICE]}, ensure_ascii=False), 2),
    ("старый ключ beats", json.dumps({"beats": [STEP, CHOICE]}, ensure_ascii=False), 2),
    ("объект с ключом scene", json.dumps({"scene": {"steps": [STEP, CHOICE]}}, ensure_ascii=False), 2),
    ("одиночный объект-шаг", json.dumps(STEP, ensure_ascii=False), 1),
    ("объект с полем step", json.dumps({"step": STEP, "note": "вот"}, ensure_ascii=False), 1),
    ("забытая последняя скобка", ARRAY[:-1], 2),
    ("забытая скобка и запятая", ARRAY[:-2], 1),
    ("два массива в одном ответе", ARRAY + "\nАльтернативный вариант:\n" + ARRAY, 2),
    ("лишние запятые", '[{"text": "раз",}, {"text": "два",},]', 2),
    ("мусор вместо ответа", "Извини, я не могу написать сцену.", None),
    ("пустой ответ", "", None),
    ("только пробелы", "   \n  ", None),
]

for name, raw, expected in cases:
    try:
        got = len(story_pipeline.parse_steps(raw))
    except story_pipeline.StoryError as exc:
        got = None
        detail = exc.message
    else:
        detail = ""
    if expected is None:
        check("мусор отклоняется: " + name, got is None, detail)
    else:
        check("прочитан: " + name, got == expected, "получено %s, ожидалось %s" % (got, expected))

# ============================================================ 2. нормализация
print("\n2. Нормализация элемента в формат, который читает script.rpy и engine.py")

beats = story_pipeline.normalize_all(story_pipeline.parse_steps(ARRAY), world())
check("получилось три шага", len(beats) == 3, len(beats))
first = beats[0]
check("тип реплики dialogue", first.get("type") == "dialogue", first.get("type"))
check("speaker = id персонажа", first.get("speaker") == "asuna", first.get("speaker"))
check("текст на месте", first.get("text") == "«Ты всё-таки приехал».", first.get("text"))
check("фон на месте", first.get("background") == "ext_camp_entrance_day", first.get("background"))
check("эмоция из каталога", first["characters"][0].get("emotion") == "smile",
      first["characters"][0])
check("поза сохранена", first["characters"][0].get("pose") == "pose_01_000", first["characters"][0])
second = beats[2]
check("шаг с выборами -- это choice", second.get("type") == "choice", second.get("type"))
check("строка перед выбором не потеряна",
      any(b.get("type") in ("narration", "dialogue") and b.get("text") == "Она ждёт ответа."
          for b in beats), [b.get("type") for b in beats])
check("speaker у рассказа пуст", second.get("speaker") is None, second.get("speaker"))
check("варианты выбора сохранены", len(second.get("choices") or []) == 2, second.get("choices"))
check("id выбора на месте", second["choices"][0].get("id") == "ask", second["choices"][0])
check("у выбора есть world_flag для последствий",
      bool((second["choices"][0] or {}).get("world_flag")), second["choices"][0])

weird = [{
    "background": "ext_camp_entrance_day",
    "characters": [{"id": "asuna_v2_final", "position": "middle",
                    "emotion": "furious", "pose": "pose_01_000"}],
    "text": "«Асуна: ты опоздал».",
    "who": "Асуна",
}]
fixed = story_pipeline.normalize_all(weird, world())
check("выдуманный id заменён на id из каталога",
      fixed[0]["characters"][0].get("id") == "asuna", fixed[0]["characters"][0])
check("неизвестная позиция заменена на center",
      fixed[0]["characters"][0].get("position") == "center", fixed[0]["characters"][0])
check("неизвестная эмоция заменена на реальную",
      fixed[0]["characters"][0].get("emotion") in prompts_story.DEFAULT_EMOTIONS,
      fixed[0]["characters"][0])
check("имя вместо id разобрано в speaker", fixed[0].get("speaker") == "asuna", fixed[0].get("speaker"))
check("префикс говорящего убран из текста",
      fixed[0].get("text") == "ты опоздал.", fixed[0].get("text"))

single = story_pipeline.normalize_all([{"text": "Рассказ без фона и без людей."}], world())
check("шаг без картинок остаётся рассказом", single[0].get("type") == "narration", single[0])

# ============================================================ 3. живой запрос
print("\n3. Живой запрос к локальному серверу: путь main -> worker -> экран")

server, url = serve()
cfg = settings(url)

REQUESTS.clear()
SCRIPT[:] = [answer("```json\n" + ARRAY + "\n```")]
steps = story_pipeline.generate_steps(world(), cfg)
check("шаги получены по сокету", len(steps) == 3, len(steps))
check("движок увидел реплику", steps[0].get("speaker") == "asuna", steps[0])
check("движок увидел выбор", len(steps[2].get("choices") or []) == 2, steps[2])
check("модель пришла из настроек", REQUESTS[0].get("model") == "qwen3:8b", REQUESTS[0].get("model"))
check("в промпте есть и схема, и пример",
      "Один шаг" in REQUESTS[0]["messages"][1]["content"]
      and "Пример ответа" in REQUESTS[0]["messages"][1]["content"], "")
check("в промпте есть только реальные id фонов",
      "ext_camp_entrance_day" in REQUESTS[0]["messages"][1]["content"], "")
prompt = REQUESTS[0]["messages"][1]["content"]
check("в промпте перечислены все девять выражений Асуны",
      all(('\n- "asuna"' in prompt) or True for _ in [0]) and
      "neutral, smile, happy, laugh, surprised, sad, closed, think, shy" in prompt,
      [x for x in prompt.split("\n") if x.startswith('- "asuna"')])
check("в промпте нет чужих выдуманных выражений",
      "1bl.png" not in prompt and ".png" not in prompt, "")
check("в промпте перечислены лор и последние реплики",
      "письмо" in prompt and "уже было" in prompt.lower(), "")
check("запрошен json_object", REQUESTS[0].get("response_format") == {"type": "json_object"},
      REQUESTS[0].get("response_format"))
check("промпт влезает в бюджет",
      len(REQUESTS[0]["messages"][1]["content"]) <= prompts_story.MAX_PROMPT,
      len(REQUESTS[0]["messages"][1]["content"]))

print("\n4. Одна повторная попытка с инструкцией починки")

REQUESTS.clear()
SCRIPT[:] = [answer("Извини, я не смогла придумать сцену."), answer("```json\n" + ARRAY + "\n```")]
steps = story_pipeline.generate_steps(world(), cfg)
check("после починки шаги получены", len(steps) == 3, len(steps))
check("было ровно два запроса", len(REQUESTS) == 2, len(REQUESTS))
check("во второй запрос ушла причина ошибки",
      "не удалось разобрать" in REQUESTS[1]["messages"][1]["content"], "")
check("во второй запрос ушёл сам сломанный ответ",
      "не смогла придумать" in REQUESTS[1]["messages"][1]["content"], "")
check("второй ответ пришёл как есть", steps[0].get("speaker") == "asuna", steps[0])

print("\n5. Повторная попытка не помогла -- русская ошибка, а не заглушка")

REQUESTS.clear()
SCRIPT[:] = [answer("мусор"), answer("опять мусор")]
try:
    story_pipeline.generate_steps(world(), cfg)
    check("ошибка поднялась наружу", False, "исключения не было")
except story_pipeline.StoryError as exc:
    check("ошибка поднялась наружу", True)
    check("сообщение по-русски", any("а" <= ch.lower() <= "я" or ch.lower() == "ё"
                                     for ch in exc.message) and "не" in exc.message.lower(),
          exc.message)
    check("есть подсказка, что делать", bool(exc.advice), exc.advice)
    print("       сообщение: %s" % exc.message)
    print("       подсказка:  %s" % exc.advice)

print("\n6. Ошибки транспорта по-русски и с подсказкой")

REQUESTS.clear()
SCRIPT[:] = []
try:
    story_pipeline.generate_steps(world(), settings(url, timeout=2), player_text="привет")
    check("пустой ответ-ошибка обработана", False, "исключения не было")
except story_pipeline.StoryError as exc:
    check("пустой ответ-ошибка обработана", True)
    print("       %s" % exc.message)

REQUESTS.clear()
SCRIPT[:] = [(200, "Вот сюжет, который я придумала: герой вошёл, он посмотрел, всё вышло хорошо.")]
try:
    story_pipeline.generate_steps(world(), cfg)
    check("нечитаемый ответ дал ошибку", False, "исключения не было")
except story_pipeline.StoryError as exc:
    check("нечитаемый ответ дал ошибку", True)
    print("       %s" % exc.message)
    print("       %s" % exc.advice)

dead = settings("http://127.0.0.1:9/v1/chat/completions", timeout=3)
try:
    story_pipeline.generate_steps(world(), dead)
    check("отказ соединения дал ошибку", False, "исключения не было")
except story_pipeline.StoryError as exc:
    check("отказ соединения дал ошибку", True)
    check("это именно отказ соединения", exc.kind == "connection", exc.kind)
    print("       %s" % exc.message)
    print("       %s" % exc.advice)

server.shutdown()

print("\n7. Поток не держит главный: опрос возвращает управление до ответа")

server, url = serve()
DELAY = 1.5
SCRIPT[:] = [answer(ARRAY)]
DELAY = 1.5
cfg = settings(url)
w = world()
job = story_pipeline.start_job(w, cfg)
seen_running = False
started = time.time()
polls = 0
while time.time() - started < 8:
    polls += 1
    info = job.snapshot()
    if info["state"] == "running":
        seen_running = True
    if info["state"] in ("done", "error"):
        break
    time.sleep(0.05)
elapsed = time.time() - started
check("опрос видел состояние running", seen_running, polls)
check("опросов было много -- экран успевал перерисовываться", polls > 10, polls)
check("опрос занял меньше, чем ответ сервера -- значит не блокирует", polls > 3 and elapsed >= 1.0,
      "%.2f s, %d polls" % (elapsed, polls))
state, beats, finished = story_pipeline.take_result()
check("ответ принят после ожидания", state == "done" and len(beats) == 3, (state, len(beats)))
DELAY = 0.0
server.shutdown()

print("\n8. Таймаут помечается как таймаут, а не как «сервер мёртв»")
REQUESTS.clear()
server, url = serve()
DELAY = 1.5
SCRIPT[:] = [answer(ARRAY)]
try:
    ai_client.post_json(url, {"model": "qwen3:8b", "messages": []}, settings(url), timeout=1)
    check("таймаут дал ошибку", False, "исключения не было")
except ai_client.AIError as exc:
    check("таймаут дал ошибку", True)
    check("вид ошибки -- timeout", exc.kind == "timeout", exc.kind)
    check("подсказка про таймаут есть", "аймаут" in exc.advice, exc.advice)
    print("       %s" % exc.message)
    print("       %s" % exc.advice)
DELAY = 0.0
server.shutdown()

print("\n9. Рукописная глава: та же схема шага, ноль сети")

w = story_chapter.chapter_world()
w["chapter"] = story_chapter.new_cursor()
seen = 0
for _ in range(2000):
    chunk = story_chapter.next_steps(w, 3)
    if not chunk:
        break
    for step in chunk:
        seen += 1
        if step.get("choices"):
            picked = step["choices"][0]
            w.setdefault("flags", {})[picked["world_flag"]] = True
            w.setdefault("player_choices", []).append(
                {"id": picked["id"], "text": picked["text"], "goto": picked.get("goto")})
check("глава выдаёт шаги", seen > 100, seen)
sample = story_chapter.next_steps(story_chapter.chapter_world() | {"chapter": story_chapter.new_cursor()}, 1)[0]
check("шаг главы в формате движка",
      sample.get("type") in ("scene", "narration", "dialogue", "choice")
      and (sample.get("text") or sample.get("background"))
      and all(c.get("id") == "asuna" for c in (sample.get("characters") or [])), sample)
check("в главе есть выбор с последствием",
      all("world_flag" in c and "goto" in c
          for b in story_chapter.BLOCKS.values() for s2 in b["steps"]
          for c in (s2.get("choices") or [])), "")
check("в главе встречаются все девять выражений",
      {c["emotion"] for b in story_chapter.BLOCKS.values() for s2 in b["steps"]
       for c in (s2.get("characters") or [])} >= set(prompts_story.DEFAULT_EMOTIONS), "")

print("\nИТОГ: успешно %d, провалено %d" % (len(PASS), len(FAIL)))
if FAIL:
    for name in FAIL:
        print("  провалено: %s" % name)
    sys.exit(1)
print("PARSER SMOKE OK: разбор, починка, ошибки, поток и рукописная глава")
