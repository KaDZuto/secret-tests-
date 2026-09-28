#!/usr/bin/env python3
"""Прогон движка сюжета без Ren'Py: буфер, режимы, ожидание, конец главы.

`renpy` подменяется заглушкой, а локальный сервер на 127.0.0.1 отвечает настоящим JSON в
форме OpenAI. Проверяется то, что не видно в парсере:

  * с моделью, настроенной в настройках, буфер пуст до первого шага и первый шаг приходит
    из настоящего запроса, а не из заглушки;
  * при отказе сервера на экране появляется русская причина с подсказкой, а игра не
    переходит молча на выдуманную сцену;
  * без единого настроенного адреса игра стартует сразу, с рукописной главы и без сети;
  * рукописная глава проходится подряд: реплики, рассказ, выборы, флаги последствий и
    выход на экран конца главы, а не бесконечный повтор;
  * свободная реплика игрока в режиме главы получает ответ;
  * контроль качества (QC) вызывается на каждом блоке, включая блок с выборами в конце;
    низкий балл даёт одну перепись по director_command и повторную оценку, вердикт
    записывается, а сюжет при отказе редактора не падает;
  * music_intent в промпте берётся из словаря тегов game/music.py, а неизвестный тег
    в нормализации отбрасывается;
  * два вызова call_chat уходят с разными payload'ами (разный seed) — без сети,
    через подменённый транспорт.

Запуск: python3 tools/smoke_test_story_flow.py
"""

import json
import sys
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "game"

# --- минимальный Ren'Py: всё, что движок трогает
store = types.ModuleType("renpy.store")
class _Store(types.ModuleType):
    pass
renpy = types.ModuleType("renpy")
renpy.config = types.SimpleNamespace(gamedir=str(GAME), savedir="/tmp/opencode/lvn")
renpy.loadable = lambda name, **k: False
renpy.scene = lambda *a, **k: None
renpy.show = lambda *a, **k: None
renpy.hide_screen = lambda *a, **k: None
renpy.notify = lambda *a, **k: print("   notify:", *a)
renpy.jump = lambda label: print("   jump ->", label)
renpy.pause = lambda *a, **k: None
renpy.say = lambda *a, **k: None
renpy.call_screen = lambda *a, **k: None
renpy.restart_interaction = lambda *a, **k: None
renpy.save_persistent = lambda *a, **k: None
renpy.put_clipboard_text = lambda *a, **k: None
renpy.loadable = lambda name, **k: False
renpy.list_files = lambda: []
renpy.music = types.SimpleNamespace(play=lambda *a, **k: None)
loader = types.ModuleType("renpy.loader"); loader.loadable = renpy.loadable; loader.load = lambda *a, **k: None
renpy.loader = loader
sys.modules["renpy"] = renpy
sys.modules["renpy.config"] = renpy.config
sys.modules["renpy.loader"] = loader
store.config = renpy.config
store.creator_mode = "brief"
store.creator_title = "Летний лагерь"
store.creator_genre = "романтика"
store.creator_tone = "тёплая"
store.creator_description = "тест"
store.creator_character_count = "1"
store.creator_json_path = ""
store.creator_music_paths = ""
store.creator_name = ""
store.creator_title_local = ""
store.game_state = {}
store.persistent = types.SimpleNamespace(vn_settings={}, vn_ai_profiles={}, vn_ai_profile="")
store.creator_export = ""
sys.modules["renpy.store"] = store
renpy.store = store
sys.path.insert(0, str(GAME))

import vn_settings_schema
store.persistent.vn_settings = dict(vn_settings_schema.DEFAULTS)
import engine, story_chapter, story_pipeline
import ai_client
import music
import prompts_story

# --- сервер-заглушка: отвечает настоящим JSON
ANSWER = json.dumps([
 {"background": "ext_camp_entrance_day", "characters": [{"id": "asuna", "position": "center", "emotion": "smile", "pose": "pose_01_000"}], "text": "«Ты приехал».", "who": "asuna"},
 {"text": "Она ждёт.", "who": None, "choices": [{"id": "a", "text": "Пойти."}, {"id": "b", "text": "Остаться."}]},
], ensure_ascii=False)
BROKEN = [False]
SCRIPT = []    # по порядку: что сервер отвечает; пусто — обычный ANSWER
REQUESTS = []  # журнал пришедших payload'ов
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            REQUESTS.append(json.loads(raw.decode("utf-8")))
        except Exception:
            REQUESTS.append({})
        if BROKEN[0]:
            body = b'{"error":"model not loaded"}'
            self.send_response(503); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body); return
        content = SCRIPT.pop(0) if SCRIPT else ANSWER
        body = json.dumps({"choices": [{"message": {"content": "```json\n" + content + "\n```"}}]}, ensure_ascii=False).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = "http://127.0.0.1:%d/v1/chat/completions" % srv.server_port
store.persistent.vn_settings["api_url"] = url
store.persistent.vn_settings["model"] = "qwen3:8b"
store.persistent.vn_settings["tts_enabled"] = False
store.persistent.vn_settings["music_enabled"] = False
store.persistent.vn_settings["supervisor"] = False
store.persistent.vn_settings["auto_music_scan"] = False

FAIL = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "  -- %s" % (detail,)))
    if not cond: FAIL.append(name)

print("\nA. Модель настроена: буфер пуст, первый шаг идёт через реальный запрос")
engine.initialize_game(story_chapter.chapter_world())
engine._state()["story_mode"] = "ai"
check("буфер пуст до первого шага", engine._state()["buffer"] == [], engine._state()["buffer"])
# экран ожидания: настоящий call_screen -> ждём ответ в потоке
def fake_screen(name):
    seen = []
    for _ in range(600):
        engine.story_wait_tick()
        seen.append(engine.store.story_phase)
        if engine.store.story_phase == "done":
            return engine.story_wait_take()
        if engine.store.story_phase == "error":
            engine.story_wait_take()
            return "error"
        time.sleep(0.02)
    print("   экран опросили %d раз, фазы: %s" % (len(seen), sorted(set(seen))))
    return "done"
renpy.call_screen = fake_screen
step = engine.next_step()
check("первый шаг -- реплика", step.get("type") == "dialogue" and step.get("speaker") == "asuna", step)
check("текст из ответа модели", "приехал" in (step.get("text") or ""), step.get("text"))
check("ошибки нет", not engine._state().get("ai_error"), engine._state().get("ai_error"))
n = 0
for _ in range(4):
    n += 1
    engine.next_step()
check("буфер пополняется и игра идёт дальше", n == 4 and engine._state()["buffer"], (n, len(engine._state()["buffer"])))

BROKEN[0] = True
print("\nB. Модель упала: русская ошибка на экране, выбор из трёх действий")
engine._state()["buffer"] = []
engine._state()["story_mode"] = "ai"
# сервер молчит: экран показывает русскую ошибку, игрок жмёт «читать написанную главу»
def failing_screen(name):
    for _ in range(400):
        engine.story_wait_tick()
        if engine.store.story_phase == "error":
            break
        time.sleep(0.02)
    print("   ошибка на экране: %s" % engine.store.story_error)
    print("   подсказка:        %s" % engine.store.story_advice)
    return "offline"
renpy.call_screen = failing_screen
step = engine.next_step()
check("после отказа буфер наполнен главой", len(engine._state()["buffer"]) >= 1, step)
check("режим переключился на главу", engine._state()["story_mode"] == "chapter", engine._state()["story_mode"])
check("ошибка записана в мир", bool(engine._state().get("ai_error")), engine._state().get("ai_error"))

print("\nC. Ничего не настроено: игра стартует сразу, без сети")
store.persistent.vn_settings["api_url"] = ""
engine.initialize_game(story_chapter.chapter_world())
check("режим -- глава", engine._state()["story_mode"] == "chapter")
check("буфер уже наполнен", len(engine._state()["buffer"]) >= 2, engine._state()["buffer"])
check("ai_configured() честно говорит НЕТ", engine.ai_configured() is False)

print("\nD. Рукописная глава играется целиком: 20 сцен подряд, выборы и последствия")
engine._state()["buffer"] = []
renpy.call_screen = lambda name: (_ for _ in ()).throw(AssertionError("сеть не должна требоваться"))
seen_types = {}
flags = set()
steps = 0
jumped = []
renpy.jump = lambda label: jumped.append(label)
for _ in range(1500):
    st = engine.next_step()
    seen_types[st.get("type")] = seen_types.get(st.get("type"), 0) + 1
    steps += 1
    if st.get("type") in ("dialogue", "narration"):
        engine.consume_dialogue(st)
    elif st.get("type") == "choice":
        pick = (st.get("choices") or [{}])[-1]
        engine.apply_choice(st, pick.get("id"))
        flags.add(pick.get("world_flag"))
    if jumped:
        break
check("глава отдала много шагов", steps > 150, steps)
check("и были реплики, рассказ и выборы", set(seen_types) >= {"dialogue", "narration", "choice"}, seen_types)
check("выборы ставили флаги", len(flags) >= 4, flags)
check("в конце игра ушла на экран конца главы", jumped == ["story_chapter_finished"], jumped)
check("ошибок ИИ не было", not engine._state().get("ai_error"), engine._state().get("ai_error"))

print("\nE. Ответ не теряется, если его спросили дважды")
## Таймер экрана ожидания может сработать ещё раз, пока Ren'Py ещё не убрал экран. Второе
## обращение не должно выглядеть как «модель не ответила»: это ровно тот случай, из-за которого
## сцена пропадала, хотя модель её написала.
class _Done:
    state = "done"
    result = [{"type": "dialogue", "text": "проверка"}]
    review = {}
    def cancel(self):
        pass
    def snapshot(self):
        return {"state": "done", "result": list(self.result), "error": "", "advice": "",
                "kind": "", "review": {}, "attempt": 1, "elapsed": 0.1}

story_pipeline._register(_Done())
_first = story_pipeline.take_result()
_second = story_pipeline.take_result()
check("первое обращение отдало ответ", _first[0] == "done" and _first[1], _first[0])
check("второе обращение отдало тот же ответ", _second[0] == "done" and _second[1] == _first[1],
      (_second[0], _second[1]))
check("фаза экрана не сбрасывается при выдаче ответа",
      engine.story_wait_take() == "done" and store.story_phase != "idle",
      (engine.story_wait_take(), store.story_phase))
story_pipeline._register(_Done())
_third = story_pipeline.take_result()
check("новый запрос забывает прошлый ответ", _third[0] == "done" and _third[1], _third[0])
engine.story_job_reset("проверка")

print("\nE. Свободная реплика в режиме главы")
engine.initialize_game(story_chapter.chapter_world())
engine._state()["buffer"] = []
out = engine.free_response("привет, Асун")
check("ответ на свободную реплику есть", len(engine._state()["buffer"]) >= 1, out)
check("в ответе есть её реплика",
      any(x.get("speaker") == "asuna" for x in engine._state()["buffer"]), engine._state()["buffer"])

## --- контроль качества на каждом блоке --------------------------------------------
BROKEN[0] = False
store.persistent.vn_settings["api_url"] = url
cfg = dict(store.persistent.vn_settings)
cfg["supervisor"] = True
cfg["supervisor_threshold"] = 7.0

def wait_job(job, seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        info = job.snapshot()
        if info["state"] in ("done", "error"):
            return info
        time.sleep(0.02)
    return job.snapshot()

print("\nF. QC вызывается на блоке, который ЗАКАНЧИВАЕТСЯ выборами")
SCRIPT[:] = []
REQUESTS[:] = []
qc_calls = []
def qc_ok(w, bundle, settings):
    qc_calls.append(bundle)
    return {"score": 9.5, "approved": True, "summary": "сцена в порядке",
            "issues": [], "director_command": "", "repair": False}

job = story_pipeline.start_job(story_chapter.chapter_world(), cfg,
                               use_supervisor=True, supervise=qc_ok)
info = wait_job(job)
check("блок сюжета дошёл до конца", info["state"] == "done", info.get("error"))
last = info["result"][-1] if info["result"] else {}
check("в конце блока есть choices", bool(last.get("choices")), last)
check("QC вызван, хотя в конце choices", len(qc_calls) == 1 and "steps" in qc_calls[0],
      len(qc_calls))
check("вердикт QC записан в job.review", job.review.get("score") == 9.5, job.review)
check("переписи не было: оценка выше порога", job.review.get("repaired") is False, job.review)

print("\nG. Низкий балл: одна перепись по director_command и повторная оценка")
REWRITE = json.dumps([
 {"background": "ext_camp_entrance_day", "characters": [{"id": "asuna", "position": "center", "emotion": "smile", "pose": "pose_01_000"}], "text": "«Переписанный вариант».", "who": "asuna"},
 {"text": "Переписанный блок ждёт решения.", "who": None, "choices": [{"id": "a", "text": "Идти."}, {"id": "b", "text": "Ждать."}]},
], ensure_ascii=False)
REQUESTS[:] = []
SCRIPT[:] = [ANSWER, REWRITE]
qc_calls = []
def qc_low(w, bundle, settings):
    qc_calls.append(bundle)
    if len(qc_calls) == 1:
        return {"score": 3.0, "approved": False, "summary": "сцена сырья",
                "issues": ["штампы в каждой строке", "голоса персонажей одинаковые"],
                "director_command": "Убери штампы и разведи голоса персонажей",
                "repair": True}
    return {"score": 4.5, "approved": False, "summary": "лучше, но ещё слабо",
            "issues": ["канцелярит в последнем шаге"],
            "director_command": "Убери канцелярит из последнего шага", "repair": True}

job = story_pipeline.start_job(story_chapter.chapter_world(), cfg,
                               use_supervisor=True, supervise=qc_low)
info = wait_job(job)
check("сюжет не упал при отказе редактора", info["state"] == "done" and info["result"],
      info.get("error"))
check("были оценка, перепись и повторная оценка", len(qc_calls) == 2, len(qc_calls))
check("в перепись ушло замечание редактора",
      len(REQUESTS) >= 2 and "Убери штампы" in REQUESTS[1]["messages"][1]["content"],
      [r.get("messages", [{}])[1].get("content", "")[-160:] for r in REQUESTS[:2]])
check("вердикт записан: балл, issues и director_command",
      job.review.get("score") in (3.0, 4.5) and bool(job.review.get("issues"))
      and bool(job.review.get("director_command")), job.review)
check("остался лучший вариант (4.5 > 3.0)",
      "Переписанный" in (info["result"][0].get("text") or ""), info["result"][0])
check("вердикт оставленного варианта — 4.5", job.review.get("score") == 4.5, job.review)

print("\nG2. Повторная оценка хуже: остаётся исходный блок и первый вердикт")
REQUESTS[:] = []
SCRIPT[:] = [ANSWER, REWRITE]
qc_calls = []
def qc_worse(w, bundle, settings):
    qc_calls.append(bundle)
    if len(qc_calls) == 1:
        return {"score": 3.0, "approved": False, "summary": "слабо",
                "issues": ["штампы"], "director_command": "Убери штампы", "repair": True}
    return {"score": 1.5, "approved": False, "summary": "стало хуже",
            "issues": ["потеряна связь с историей"],
            "director_command": "Верни связь с историей", "repair": True}

job = story_pipeline.start_job(story_chapter.chapter_world(), cfg,
                               use_supervisor=True, supervise=qc_worse)
info = wait_job(job)
check("блок не упал", info["state"] == "done" and info["result"], info.get("error"))
text0 = info["result"][0].get("text") or ""
check("остался исходный блок, а не ставший хуже", "приехал" in text0, text0)
check("вердикт — первый (3.0), перепись не сочтена ставшей",
      job.review.get("score") == 3.0 and job.review.get("repaired") is False, job.review)
SCRIPT[:] = []
REQUESTS[:] = []

print("\nH. music_intent: теги из game/music.py, неизвестный тег отбрасывается")
_, user_msg = prompts_story.story_request(story_chapter.chapter_world(), dict(cfg))
intent_lines = [x for x in user_msg.split("\n") if "music_intent" in x]
check("промпт требует music_intent", bool(intent_lines), "")
if intent_lines:
    check("предложены все теги music.KEYWORDS",
          all(tag in intent_lines[0] for tag in music.KEYWORDS), intent_lines[0])
    check('разрешено "none", когда музыка не нужна', '"none"' in intent_lines[0],
          intent_lines[0])
mood_steps = story_pipeline.normalize_all(story_pipeline.parse_steps(json.dumps([
    {"text": "Тишина под соснами.", "music_intent": "calming"},
    {"text": "Поленья трещат в очаге.", "music_intent": "нет такого тега"},
], ensure_ascii=False)), story_chapter.chapter_world())
check("калька с английского переводится в реальный тег",
      mood_steps[0].get("music_intent") == "calm", mood_steps[0])
check("неизвестный тег отброшен, а не играет случайный трек",
      mood_steps[1].get("music_intent") in (None, ""), mood_steps[1])

print("\nI. Два вызова call_chat дают разные payload'ы (seed), без сети")
payloads = []
def fake_post(url_, payload, settings=None, timeout=None):
    payloads.append(payload)
    return {"choices": [{"message": {"content": "[]"}}]}
real_post = ai_client.post_json
ai_client.post_json = fake_post
try:
    ai_client.call_chat("один и тот же вопрос", "система", dict(cfg))
    ai_client.call_chat("один и тот же вопрос", "система", dict(cfg))
finally:
    ai_client.post_json = real_post
check("оба запроса перехвачено транспортом", len(payloads) == 2, len(payloads))
check("payload'ы различаются по seed",
      len(payloads) == 2 and payloads[0].get("seed") != payloads[1].get("seed"),
      [p.get("seed") for p in payloads])
check("seed — целое число", isinstance(payloads[0].get("seed"), int),
      payloads[0].get("seed"))
check("temperature дошла до payload", payloads[0].get("temperature") == 0.85,
      payloads[0].get("temperature"))
check("в payload есть messages и max_tokens",
      payloads[0].get("messages") and payloads[0].get("max_tokens", 0) > 0, payloads[0].keys())
srv.shutdown()
print("\nИТОГ: провалено %d" % len(FAIL))
sys.exit(1 if FAIL else 0)
