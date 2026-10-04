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

# --- TTS queue: clips must not be lost, timers must not pile up, failures must be silent ---
import time as _time
played, timers = [], []
renpy.music = types.SimpleNamespace(play=lambda data, **k: played.append(k.get("relative_volume")),
                                    is_playing=lambda channel=None: False)
renpy.create_timer = lambda delay, fn, repeat=False: timers.append(repeat)
engine.AudioData = lambda data, name: data
engine._settings = lambda: {"tts_url": "http://127.0.0.1:9/tts", "voice_volume": 0.5}
_real_pb = ai_client.post_bytes
ai_client.post_bytes = lambda url, payload, timeout=20: b"RIFFwav"
try:
    check("speak_text принимает реплику", engine.speak_text("раз") is True)
    check("вторая реплика не перетирает первую", engine.speak_text("два") is True)
    for _ in range(50):
        if len(engine._PENDING_VOICE["queue"]) == 2 and engine._PENDING_VOICE["inflight"] == 0:
            break
        _time.sleep(0.02)
    check("оба клипа в очереди", len(engine._PENDING_VOICE["queue"]) == 2,
          engine._PENDING_VOICE["queue"])
    engine._drain_voice(); engine._drain_voice()
    check("оба клипа проиграны по очереди", played == [0.5, 0.5], played)
    check("таймеры одноразовые", timers and not any(timers), timers)
    ai_client.post_bytes = lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
    engine.speak_text("сбой")
    for _ in range(50):
        if engine._PENDING_VOICE["inflight"] == 0:
            break
        _time.sleep(0.02)
    check("сбой TTS не оставляет inflight и не ломает игру",
          engine._PENDING_VOICE["inflight"] == 0 and not engine._PENDING_VOICE["queue"])
finally:
    ai_client.post_bytes = _real_pb

# --- ready-made stories (LVN-008): load, validate, play through the buffer, never crash ---
import json as _json, os, tempfile as _tmp
import story_external
for _name in ("pines", "sao"):
    _path = story_external.story_files(str(GAME)).get(_name)
    _story = story_external.load_story(_path) if _path else None
    check("готовая история %s загружается" % _name, bool(_story) and len(_story["steps"]) > 50, _path)
    started = engine.story_start_external(_name)
    check("%s стартует через engine" % _name, started is True)
    seen = choices = 0
    for _ in range(2000):
        step = engine.next_step() if engine._state().get("buffer") or not engine._state()["external"]["done"] else None
        if step is None:
            break
        seen += 1
        if step.get("choices"):
            choices += 1
            engine.apply_choice(step, step["choices"][0]["id"])
    check("%s проигрывается до конца" % _name, engine._state()["external"]["done"] and seen > 50,
          (seen, engine._state()["external"]))
    check("%s: choices на месте" % _name, choices == (6 if _name == "sao" else 0), choices)
check("нет файла: тихий False", engine.story_start_external("/nonexistent/story.json") is False)
with _tmp.TemporaryDirectory() as _d:
    _bad = os.path.join(_d, "story_bad.json")
    open(_bad, "w").write("{not json")
    check("плохой JSON: None, без краха", story_external.load_story(_bad) is None)
    check("плохой JSON: engine False", engine.story_start_external(_bad) is False)
    _mixed = os.path.join(_d, "story_mixed.json")
    _json.dump({"title": "t", "scenes": [{"id": "a", "background": "x", "steps": [
        {"type": "narration", "text": "ok"}, 42, {"type": "dialogue", "text": ""},
        {"type": "choice", "choices": []}, {"type": "bogus", "text": "x"},
        {"text": "без типа", "speaker": "z"}]}]}, open(_mixed, "w"))
    _m = story_external.load_story(_mixed)
    check("невалидные шаги пропущены, годные остались",
          _m and [x["type"] for x in _m["steps"]] == ["scene", "narration", "dialogue"], _m and _m["steps"])
    check("пропуски перечислены", _m and len(_m["issues"]) == 4, _m and _m["issues"])

# --- a background nobody drew: labelled panel, never an empty black screen or a stand-in photo ---
shown = []
renpy.scene = lambda *a, **k: shown.append("scene")
renpy.show = lambda name, **k: shown.append((name, k.get("what")))
engine.Text = lambda text, **k: ("text", text)
engine.Fixed = lambda *a, **k: ("fixed", a)
engine.Solid = lambda c: ("solid", c)
engine._background_dissolve = lambda: None
engine.story_start_external("pines")
engine._show_background({"background": "ext_camp_entrance_day"})
check("нет картинки фона: показана подписанная заглушка",
      any(isinstance(x, tuple) and x[0] == "vn_background" and x[1][0] == "fixed" for x in shown), shown)
check("заглушка помнится как bg_shown", str(engine._state().get("bg_shown")).startswith("placeholder:"))

# --- costume stays put: emotions change the face only (Asuna swimsuit flicker) ---
import story_chapter as _sc
engine._state()["costume_pin"] = {}
_vis = {"poses": ["pose_01_000", "pose_01_003"]}
check("костюм по умолчанию -- первый объявленный", engine._pinned_pose("asuna", None, _vis, None) == "pose_01_000")
check("эмоция не меняет костюм", engine._pinned_pose("asuna", None, _vis, None) == "pose_01_000")
check("неизвестная поза не применяется", engine._pinned_pose("asuna", "pose_99", _vis, None) == "pose_01_000")
check("явная объявленная поза запоминается", engine._pinned_pose("asuna", "pose_01_003", _vis, None) == "pose_01_003"
      and engine._pinned_pose("asuna", None, _vis, None) == "pose_01_003")
check("костюмы разных персонажей не смешиваются", engine._pinned_pose("other", None, {"poses": ["x1"]}, None) == "x1")
check("рукопись не переодевает Асуну", {_sc.P0, _sc.P1, _sc.P2, _sc.P3, _sc.P4, _sc.P5} == {"pose_01_000"})
srv.shutdown()
print("\nИТОГ: провалено %d" % len(FAIL))
sys.exit(1 if FAIL else 0)
