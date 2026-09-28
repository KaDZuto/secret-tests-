"""Reading a model answer, turning it into engine steps, and running it off the main thread.

Three problems, one module.

*The parse.* A local model is not a JSON printer. It wraps the answer in ```json, it adds
"Вот массив:" in front, it answers a bare array, it answers `{"steps": [...]}`, it answers
`{"beats": [...]}` because the old prompt asked for beats, it forgets a bracket, it puts two
arrays in one answer, and once in twenty it answers a paragraph. `parse_steps` tries all of
those shapes in a fixed order, keeps only what the engine can show, and says what it could not
read. The one retry asks the model to write the same story again, with the reason quoted back.

*The shape.* What the model writes is one element -- `background`, `characters`, `text`, `who`
-- and what the engine shows is a beat with a `type`, a `speaker` and a `character`. One
`type` is inferred, the rest is carried through, and an id the catalog does not know is
replaced instead of being drawn as the demo sprite in a scene that matters.

*The freeze.* Nothing here may run on the main thread while a socket is open. `start_job` takes
a finished request and a copy of the world, hands them to a daemon thread, and returns at once;
the result is picked up by `take_result` from a screen's timer, so the game keeps drawing, the
quick menu keeps answering and ESC still opens the menu while the model is thinking.
"""

import copy
import json
import re
import threading
import time

import ai_client
import prompts_story

# Keys a model used instead of a bare array, most likely first. `steps` is what the prompt
# asks for; `beats` is what the old prompt asked for and is still in a small model's memory.
LIST_KEYS = ("steps", "beats", "scenes", "scene", "story", "next", "элементы", "шаги", "items",
             "result", "data", "output", "text")
# Keys a single element can hide behind, when the answer is one object and not an array.
ELEMENT_KEYS = ("step", "element", "beat", "next", "scene", "content", "item")

MAX_STEPS_PER_BUNDLE = 12
MAX_STEP_CHARS = 1200
MAX_CHOICES = 4
MAX_CHOICE_CHARS = 240
MAX_REPAIR_ANSWER = 2600

FENCE = re.compile(r"```(?:json|jsonc|json5)?\s*(.*?)(?:```|$)", re.DOTALL | re.IGNORECASE)
SPEAKER_PREFIX = re.compile(r"^\s*(«)?\s*([А-ЯЁA-Z][^:—\n]{0,40}?)\s*[:—]\s*")
TRAILING_COMMA = re.compile(r",\s*([}\]])")


class StoryError(Exception):
    """A story that could not be produced, in Russian, with the next step in `advice`."""

    def __init__(self, message, advice="", kind="error", detail=""):
        Exception.__init__(self, message)
        self.message = str(message)
        self.advice = str(advice or "")
        self.kind = str(kind or "error")
        self.detail = str(detail or "")


# ------------------------------------------------------------------- extraction

def _clip(text, limit):
    text = str(text or "").replace("\r", " ").strip()
    text = "\n".join(x.rstrip() for x in text.split("\n")).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _loads(chunk):
    """Parsed JSON, or None -- including the one repair a small model always needs.

    A trailing comma before a closing bracket is not valid JSON and is the single most common
    way a local model breaks its own answer, so it is dropped once and the answer is read
    again rather than thrown away.
    """
    try:
        return json.loads(chunk)
    except ValueError:
        pass
    try:
        return json.loads(TRAILING_COMMA.sub(r"\1", chunk))
    except ValueError:
        return None


def _balanced(text, open_char, close_char):
    """The span from the first opening bracket to its matching closing one.

    A model that writes prose around the JSON is normal, and a model that forgets the last
    bracket is also normal: cutting at the last closing bracket is what used to throw the
    whole answer away, and closing the span at the last complete element keeps the steps that
    did arrive.
    """
    start = text.find(open_char)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
            if depth < 0:
                break
    # Nothing closes: keep every element that did finish and close the span after it.
    cut = max(text.rfind("}"), text.rfind("]"))
    if cut > start:
        return text[start:cut + 1] + close_char
    return None


def _candidates(raw):
    """Every reading of the answer that could be a list of elements, best first."""
    text = str(raw or "")
    out = []
    fenced = FENCE.search(text)
    if fenced:
        out.append(fenced.group(1))
    out.append(text)

    parsed = []
    for chunk in out:
        value = _loads(chunk)
        if value is not None:
            parsed.append(value)

    # The spans have to be parsed, not just cut: a balanced substring is still a string.
    for value in parsed + [_loads(_balanced(text, "[", "]") or ""),
                           _loads(_balanced(text, "{", "}") or "")]:
        if value is None:
            continue
        if isinstance(value, list):
            out.append(value)
        elif isinstance(value, dict):
            for key in LIST_KEYS:
                inner = value.get(key)
                if isinstance(inner, list):
                    out.append(inner)
                    break
                if isinstance(inner, dict):
                    # `{"scene": {"steps": [...]}}` -- one more wrapper than the prompt asks
                    # for, and a small model adds it more than once.
                    for inner_key in LIST_KEYS:
                        deeper = inner.get(inner_key)
                        if isinstance(deeper, list):
                            out.append(deeper)
                            break
                        if isinstance(deeper, dict):
                            out.append([deeper])
                            break
                    else:
                        out.append([inner])
                    break
            else:
                for key in ELEMENT_KEYS:
                    inner = value.get(key)
                    if isinstance(inner, dict):
                        out.append([inner])
                        break
                else:
                    # A single element written as a bare object, recognized by its own fields.
                    if any(k in value for k in ("text", "who", "speaker", "characters", "background")):
                        out.append([value])
    return out


def _elements(raw):
    """The element list, or None with a reason a player can be told."""
    if raw is None or not str(raw).strip():
        raise StoryError("Модель вернула пустой ответ.",
                         "Повтори запрос или выбери другую модель.", "empty")

    for candidate in _candidates(raw):
        if not isinstance(candidate, list) or not candidate:
            continue
        elements = [x for x in candidate if isinstance(x, dict)]
        if elements:
            return elements[:MAX_STEPS_PER_BUNDLE]

    sample = str(raw).strip().replace("\n", " ")[:200]
    raise StoryError("Ответ модели не похож на список шагов: " + _clip(sample, 200),
                     "Повтори запрос. Если повторяется, уменьши «Сцен в одном запросе» до 3 "
                     "или выключи «Ждать JSON от модели».", "not_json", sample)


def parse_steps(raw):
    """The model's answer as a list of raw elements. Raises `StoryError` when unreadable."""
    return _elements(raw)


def parse_object(raw):
    """A single JSON object out of a model answer. Used for the world and the review."""
    text = str(raw or "")
    for chunk in [FENCE.search(text).group(1) if FENCE.search(text) else None, text]:
        if chunk is None:
            continue
        value = _loads(chunk)
        if isinstance(value, dict):
            return value
    for opener, closer in (("{", "}"), ("[", "]")):
        span = _balanced(text, opener, closer)
        value = _loads(span) if span else None
        if isinstance(value, dict):
            return value
    for candidate in _candidates(text):
        if isinstance(candidate, dict):
            return candidate
    raise StoryError("Ответ модели не разобран как JSON.",
                     "Повтори запрос: модель ответила текстом вместо JSON.", "not_json",
                     _clip(text, 200))


# ------------------------------------------------------------------ normalization

def _known_cast(world):
    """The world's own characters as id -> name, plus the names the model will use instead.

    A model is asked for ids and answers with names about half the time, and a name that does
    not resolve leaves the step without a character at all -- which is a blank screen, not a
    wrong one. So the name is a key here too.
    """
    known = {}
    for character in (world or {}).get("characters") or []:
        if isinstance(character, dict) and character.get("id"):
            cid = str(character["id"])
            known[cid] = str(character.get("name") or cid)
    return known


def _fix_id(value, known, default=None):
    """A catalog id, or None.

    A model that invents `asuna_smile_2` produces a scene with the demo sprite in it, which
    looks like a broken pack rather than a wrong answer, so the invented id is dropped and the
    character is drawn with a known expression instead.
    """
    text = str(value or "").strip().strip("«»\"' ")
    if not text:
        return default
    if text in known:
        return text
    lowered = text.lower()
    for cid, name in known.items():
        if cid.lower() == lowered or name.lower() == lowered:
            return cid
    return default


def _emotion_of(value, allowed):
    text = str(value or "").strip()
    if not text:
        return "neutral"
    if text in allowed:
        return text
    synonyms = {
        "smile": "smile", "smiling": "smile", "happy": "happy", "joy": "happy",
        "laugh": "laugh", "laughing": "laugh", "sad": "sad", "sorrow": "sad",
        "surprised": "surprised", "shock": "surprised", "shy": "shy",
        "embarrassed": "shy", "think": "think", "thinking": "think", "closed": "closed",
        "neutral": "neutral", "calm": "neutral", "serious": "neutral",
    }
    return synonyms.get(text.lower(), "neutral")


def _characters_of(item, known, expressions):
    out = []
    for spec in item.get("characters") or []:
        if not isinstance(spec, dict):
            continue
        if isinstance(spec, str):
            spec = {"id": spec}
        cid = _fix_id(spec.get("id") or spec.get("character"), known)
        if not cid:
            continue
        allowed = expressions.get(cid) or list(prompts_story.DEFAULT_EMOTIONS)
        position = str(spec.get("position") or "center").strip()
        if position not in prompts_story.KNOWN_POSITIONS:
            position = "center"
        out.append({
            "id": cid,
            "position": position,
            "emotion": _emotion_of(spec.get("emotion"), allowed),
            "motion": str(spec.get("motion") or "idle").strip() or "idle",
            "pose": str(spec.get("pose") or "").strip() or None,
        })
    # A single-element answer names the character flat, as the old schema did.
    if not out:
        cid = _fix_id(item.get("id") or item.get("character") or item.get("who") or item.get("speaker"),
                      known)
        if cid:
            allowed = expressions.get(cid) or list(prompts_story.DEFAULT_EMOTIONS)
            position = str(item.get("position") or "center").strip()
            out.append({
                "id": cid,
                "position": position if position in prompts_story.KNOWN_POSITIONS else "center",
                "emotion": _emotion_of(item.get("emotion"), allowed),
                "motion": str(item.get("motion") or "idle").strip() or "idle",
                "pose": str(item.get("pose") or "").strip() or None,
            })
    # Deduplicate by character: two entries for one id would draw the same tag twice.
    unique = []
    for spec in out:
        if not any(x["id"] == spec["id"] for x in unique):
            unique.append(spec)
    return unique[:2]


def _choices_of(item):
    choices = []
    for index, choice in enumerate(item.get("choices") or []):
        if isinstance(choice, str):
            choice = {"text": choice}
        if not isinstance(choice, dict):
            continue
        text = _clip(choice.get("text") or choice.get("caption") or choice.get("label"), MAX_CHOICE_CHARS)
        if not text:
            continue
        cid = str(choice.get("id") or "").strip() or "opt%d" % (index + 1)
        choices.append({
            "id": cid,
            "text": text,
            "flag": str(choice.get("flag") or "").strip() or None,
            "world_flag": str(choice.get("world_flag") or "").strip() or None,
        })
    if len(choices) < 2:
        return []
    return choices[:MAX_CHOICES]


# The model's wording for a mood, mapped onto the tags `music.choose_track` really matches.
# An intent the dictionary does not know would make `choose_track` fall back to the whole
# catalog and play an arbitrary track, so an unknown value is dropped instead of guessed at.
MUSIC_SYNONYMS = {
    "calming": "calm", "peaceful": "calm", "quiet": "calm", "ambient": "calm",
    "romantic": "romance", "love": "romance",
    "tense": "tension", "urgent": "tension", "danger": "tension",
    "scary": "horror", "fear": "horror", "creepy": "horror",
    "melancholy": "sad", "sorrow": "sad", "lonely": "sad",
    "funny": "comedy", "fun": "comedy", "everyday": "comedy",
    "victory": "triumph", "finale": "triumph",
    "no": "none", "off": "none", "silence": "none",
}


def _music_of(value):
    """A real music tag, "none", or None when the step should not touch the music."""
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    text = MUSIC_SYNONYMS.get(text, text)
    if text == "none" or text in prompts_story.music_tags():
        return text
    return None


def _type_of(item, has_text, has_speaker, has_choices, has_background, has_characters, music):
    declared = str(item.get("type") or "").strip().lower()
    known = ("scene", "dialogue", "narration", "choice", "wait", "music")
    if declared in known:
        if declared == "dialogue" and not has_speaker:
            return "narration"
        if declared == "choice" and not has_choices:
            return "narration"
        return declared
    if has_choices:
        return "choice"
    if has_text:
        return "dialogue" if has_speaker else "narration"
    if has_background and not has_characters:
        return "scene"
    if music:
        return "music"
    return "wait"


def normalize(item, world, expressions):
    """One model element as an engine beat.

    The engine reads `type`, `speaker`, `text`, `background`, `characters`, `choices`,
    `music_intent` and `state_patch`. Everything else the model wrote is kept, because
    `apply_choice` reads `flag` and `world_flag` off a choice and a director may want to add a
    state patch of its own.
    """
    if not isinstance(item, dict):
        return None
    known = _known_cast(world)
    text = _clip(item.get("text") or item.get("what") or item.get("line") or item.get("say"),
                 MAX_STEP_CHARS)
    speaker_raw = item.get("who")
    if speaker_raw is None:
        speaker_raw = item.get("speaker")
    # `Асуна: «...»` written into the text: the engine would otherwise narrate a line that is
    # plainly spoken, and the name plate would be empty. The name is cut off the text whether it
    # also sits in `who` or not -- a model that writes it in both places is normal.
    if text:
        match = SPEAKER_PREFIX.match(text)
        if match and _fix_id(match.group(2), known):
            speaker_raw = speaker_raw or match.group(2)
            text = text[match.end():].strip()
            # `«Асуна: привет».` is one line, and the guillemets belonged to the whole thing.
            if match.group(1):
                text = re.sub(r"\s*»\s*([.!?…]*)", r"\1", text).strip()
    speaker = _fix_id(speaker_raw, known) if speaker_raw else None
    characters = _characters_of(item, known, expressions)
    if speaker and not any(x["id"] == speaker for x in characters):
        allowed = expressions.get(speaker) or list(prompts_story.DEFAULT_EMOTIONS)
        characters.insert(0, {"id": speaker, "position": "center", "emotion": "neutral",
                              "motion": "idle", "pose": None})
    background = str(item.get("background") or "").strip() or None
    choices = _choices_of(item)
    music = _music_of(item.get("music_intent"))

    if not (text or choices or background or music):
        return None

    beat = dict(item)
    beat.pop("who", None)
    beat.pop("what", None)
    beat.pop("line", None)
    beat.pop("say", None)
    beat.pop("outfit", None)
    beat.pop("pose", None)
    beat["type"] = _type_of(item, bool(text), bool(speaker), bool(choices),
                            bool(background), bool(characters), bool(music))
    beat["text"] = text
    beat["speaker"] = speaker
    beat["who"] = speaker
    beat["background"] = background
    beat["characters"] = characters
    beat["music_intent"] = music
    if choices:
        beat["choices"] = choices
    if not text and beat["type"] in ("dialogue", "narration"):
        return None
    if beat["type"] == "narration":
        beat["speaker"] = None
        beat["who"] = None
    return beat


def normalize_all(elements, world):
    """A whole answer as engine beats, with the catalog's real expressions substituted in.

    A choice that carries text becomes two beats -- the line and then the question -- because
    `script.rpy` plays a `choice` step by opening the choice screen and never says its text.
    A line the model wrote and then lost is a line the player never reads.
    """
    import assets

    catalog = assets.get_catalog()
    expressions = {}
    for cid in _known_cast(world):
        expressions[cid] = prompts_story._emotions_of(assets.find_character(catalog, cid) or {})
    beats = []
    turn = int((world or {}).get("turn", 0))
    for item in elements:
        beat = normalize(item, world, expressions)
        if not beat:
            continue
        if beat.get("type") == "choice" and beat.get("text"):
            line = dict(beat)
            for key in ("choices", "checkpoint"):
                line.pop(key, None)
            line["type"] = "dialogue" if line.get("speaker") else "narration"
            beats.append(line)
            question = dict(beat)
            question["text"] = ""
            question.pop("who", None)
            beats.append(question)
        else:
            beats.append(beat)
    # Every answer carries a flag on each option, so a choice made in a generated scene is
    # recorded in the world exactly like a choice in the written chapter.
    for beat in beats:
        for choice in beat.get("choices") or []:
            if not choice.get("world_flag"):
                choice["world_flag"] = "ai_t%d_%s" % (turn, choice.get("id") or "opt")
    return beats[:MAX_STEPS_PER_BUNDLE]


# --------------------------------------------------------------------- the worker

class Job(object):
    """One request in flight. The screen reads `state`, the worker writes `result`.

    A plain object with a lock rather than a store variable, because a thread must not touch
    the store, and the screen must not read a half-written answer.
    """

    def __init__(self, request, world, player_text=None, use_supervisor=False, settings=None,
                 supervise=None):
        self.request = request
        self.world = world
        self.player_text = player_text
        self.use_supervisor = bool(use_supervisor)
        self.settings = settings or {}
        # Injected rather than imported: the engine owns the decision to run the supervisor,
        # and importing it here would make the module that owns the thread depend on the
        # module that owns the store.
        self._supervise = supervise or ai_client.supervise
        self.state = "running"
        self.result = []
        self.review = {}
        self.error = ""
        self.advice = ""
        self.kind = ""
        self.detail = ""
        self.attempt = 0
        self.started = time.time()
        self.finished = 0.0
        self.cancelled = False
        self.lock = threading.Lock()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run, name="living-vn-story")
        # A daemon thread dies with the process: a model that is still thinking must never
        # keep the game from closing.
        self.thread.daemon = True
        self.thread.start()
        return self

    def cancel(self):
        with self.lock:
            self.cancelled = True
        return self

    def snapshot(self):
        with self.lock:
            return {
                "state": self.state,
                "result": list(self.result),
                "error": self.error,
                "advice": self.advice,
                "kind": self.kind,
                "review": dict(self.review or {}),
                "attempt": self.attempt,
                "elapsed": (self.finished or time.time()) - self.started,
            }

    def _finish_ok(self, beats):
        with self.lock:
            self.cancelled = False
            self.result = beats
            self.state = "done"
            self.finished = time.time()

    def _finish_error(self, error):
        with self.lock:
            self.error = getattr(error, "message", str(error))
            self.advice = getattr(error, "advice", "")
            self.kind = getattr(error, "kind", "error")
            self.detail = getattr(error, "detail", "")
            self.state = "error"
            self.finished = time.time()

    def _note(self, attempt):
        with self.lock:
            self.attempt = int(attempt)

    def _run(self):
        try:
            self._note(1)
            system, user = self.request
            raw = ai_client.call_chat(user, system, self.settings, max_tokens=self._tokens())
            try:
                beats = normalize_all(parse_steps(raw), self.world)
            except StoryError as first:
                # The one retry. Same story, same schema, and the reason quoted back, because
                # a model that was cut off does not know it was cut off.
                self._note(2)
                repair_system, repair_user = prompts_story.repair_request(raw, first.message)
                raw = ai_client.call_chat(repair_user, repair_system, self.settings,
                                          max_tokens=self._tokens())
                beats = normalize_all(parse_steps(raw), self.world)
            if not beats:
                raise StoryError("Модель ответила, но показать нечего: ни одного шага.",
                                 "Повтори запрос: в ответе не было ни текста, ни фона, ни выбора.",
                                 "empty")
            if self.use_supervisor:
                # Every block, and that includes a block that ends with choices: a scene
                # with a choice used to skip the review entirely, and a broken scene that
                # asks the player to decide is exactly where a bad bundle strands them.
                # Anything at all going wrong inside the review keeps the original beats:
                # a refusal of the reviewer is never a refusal of the story.
                replacement = None
                try:
                    replacement = self._review(beats)
                except Exception:
                    replacement = None
                if replacement:
                    beats = replacement
            self._finish_ok(beats)
        except StoryError as exc:
            self._finish_error(exc)
        except ai_client.AIError as exc:
            self._finish_error(exc)
        except Exception as exc:  # a bug in here is a failure the player must still see
            self._finish_error(StoryError("Внутренняя ошибка разбора: %s" % exc,
                                          "Это ошибка игры, не модели. Вернись в меню и сообщи.",
                                          "error"))

    def _tokens(self):
        steps = max(2, min(8, int(self.settings.get("bundle_size", 5) or 5)))
        return 700 + 420 * steps

    def _review(self, beats):
        """The second opinion about every block. A refusal of the reviewer is never a
        refusal of the story: every failure on this path returns None and the original
        beats reach the player.

        The bundle is reviewed whether or not it ends with choices. Below
        `supervisor_threshold`, or on an explicit `repair` / `approved=false`, the
        editor's own `director_command` buys exactly one rewrite and one re-review.
        After that the better of the two variants is kept, and the verdict of the kept
        variant is written into `self.review`, from which the engine stores it as
        `world["last_supervisor"]`.
        """
        first = self._ask(beats)
        if first is None:
            return None
        verdict, score = first
        if not self._must_rewrite(verdict, score):
            self._store(verdict, score, replaced=False)
            return None
        command = self._command(verdict)
        rewritten = self._rewrite(command) if command else None
        if rewritten is None:
            # No concrete command, or the rewrite could not be read: the original stays
            # and the verdict still leaves through self.review.
            self._store(verdict, score, replaced=False)
            return None
        second = self._ask(rewritten)
        if second is None:
            # The rewrite ran but the second look did not: the rewritten block answers
            # the editor's own command, so it is the better of the two known variants.
            self._store(verdict, score, replaced=True)
            return rewritten
        verdict2, score2 = second
        if score2 >= score:
            self._store(verdict2, score2, replaced=True)
            return rewritten
        self._store(verdict, score, replaced=False)
        return beats

    def _ask(self, beats):
        """The reviewer's verdict with its score, or None when it could not be obtained."""
        try:
            review = self._supervise(self.world, {"steps": beats}, self.settings)
        except Exception:
            return None
        if not isinstance(review, dict) or not review:
            return None
        try:
            score = float(review.get("score", 10))
        except (TypeError, ValueError):
            score = 10.0
        if score != score:  # NaN reads as a number and would be written into the world
            score = 10.0
        return review, score

    def _must_rewrite(self, verdict, score):
        try:
            threshold = float(self.settings.get("supervisor_threshold", 7.0))
        except (TypeError, ValueError):
            threshold = 7.0
        return bool(verdict.get("repair")) or not verdict.get("approved", True) \
            or score < threshold

    def _issues_of(self, verdict):
        """The verdict's issues as a list of strings, whatever shape the model gave them."""
        issues = verdict.get("issues") or []
        if isinstance(issues, str):
            issues = [issues]
        elif not isinstance(issues, (list, tuple)):
            issues = [issues]
        return [str(x).strip() for x in issues if str(x).strip()]

    def _command(self, verdict):
        """What the director is told, even when the verdict forgot to say it."""
        command = str(verdict.get("director_command") or "").strip()
        if command:
            return command
        named = self._issues_of(verdict)
        if named:
            return "Исправь в следующей версии: " + "; ".join(named[:4])
        summary = str(verdict.get("summary") or "").strip()
        if summary:
            return "Перепиши сцену с учётом замечания редактора: " + summary
        # Nothing concrete to pass on: a blind rewrite of a scene nobody criticised would
        # only trade one unknown bundle for another.
        return ""

    def _rewrite(self, command):
        """The one rewrite through the editor's command, or None when it did not happen."""
        self._note(self.attempt + 1)
        try:
            system, user = prompts_story.story_request(self.world, self.settings,
                                                       director_command=command)
            raw = ai_client.call_chat(user, system, self.settings, max_tokens=self._tokens())
            beats = normalize_all(parse_steps(raw), self.world)
        except Exception:
            return None
        return beats or None

    def _store(self, verdict, score, replaced):
        """The verdict, under the lock, so the screen cannot read a half-written one."""
        with self.lock:
            self.review = {
                "score": float(score),
                "approved": bool(verdict.get("approved", True)),
                "summary": str(verdict.get("summary") or ""),
                "issues": self._issues_of(verdict)[:6],
                "director_command": str(verdict.get("director_command") or "").strip(),
                "repair": bool(verdict.get("repair")),
                "repaired": bool(replaced),
            }


class WorldJob(Job):
    """The same worker, one other job: the world the creator screen asks for.

    It shares `Job` so the screen, the polling and the result hand-off are the same code -- a
    second class with a second screen would be a second place where a freeze could hide.
    """

    def __init__(self, brief, character_count, settings):
        Job.__init__(self, ("", ""), {}, settings=dict(settings or {}), use_supervisor=False)
        self.brief = dict(brief or {})
        self.character_count = int(character_count or 3)

    def _run(self):
        try:
            self._note(1)
            world = ai_client.generate_world(self.brief, self.character_count, self.settings)
            if not isinstance(world, dict) or not isinstance(world.get("characters"), list) \
                    or not world["characters"]:
                raise StoryError("Модель вернула мир без персонажей.",
                                 "Повтори запрос или опиши мир подробнее.", "empty")
            self._finish_ok([world])
        except StoryError as exc:
            self._finish_error(exc)
        except ai_client.AIError as exc:
            self._finish_error(exc)
        except Exception as exc:
            self._finish_error(StoryError("Мир не создан: %s" % exc,
                                          "Повтори запрос из окна создания мира.", "error"))


# The single job in flight, and where its result is left for the screen.
_LOCK = threading.Lock()
_JOB = {"job": None}
## What was already handed to the screen. Kept so a second ask returns the same answer.
_TAKEN = {"state": None, "beats": [], "job": None}


def _register(job):
    with _LOCK:
        previous = _JOB.get("job")
        _JOB["job"] = job
        # A new request forgets the previous answer, so a stale one cannot be handed out
        # as this request's result.
        _TAKEN.update({"state": None, "beats": [], "job": None})
    if previous is not None:
        previous.cancel()
    return job


def start_job(world, settings, player_text=None, use_supervisor=None, supervise=None):
    """Prepare the request on the calling thread and hand the socket to a worker.

    The prompt is built here, on the main thread, because it reads the asset catalog and the
    world; the worker only opens the socket and reads JSON, so it can never touch the store.
    """
    system, user = prompts_story.story_request(world, settings, player_text=player_text)
    snapshot = copy.deepcopy(dict(world or {}))
    supervisor = (settings.get("supervisor", True) if use_supervisor is None else use_supervisor)
    job = Job((system, user), snapshot, player_text=player_text,
              use_supervisor=bool(supervisor), settings=dict(settings or {}),
              supervise=supervise)
    _register(job)
    job.start()
    return job


def start_world_job(brief, character_count, settings):
    """The creator screen's request, on the same worker and behind the same screen."""
    job = WorldJob(brief, character_count, settings)
    _register(job)
    job.start()
    return job


def current_job():
    with _LOCK:
        return _JOB.get("job")


def take_result():
    """The finished answer and the job. Returns (state, beats, job) for the screen.

    Asking twice returns the same answer, and that is the point. A one-shot slot turns a
    finished request into "the request ended without an answer" as soon as anything looks at
    it twice: the screen's timer can fire again before Ren'Py has actually taken the screen
    down, and the second ask found the job already gone. The answer was written by the model
    and thrown away by the game, which is the worst possible way to lose it.
    """
    with _LOCK:
        job = _JOB.get("job")
        if job is not None and job.state == "running":
            return "running", [], job
        if job is None:
            if _TAKEN["state"] is not None:
                return _TAKEN["state"], list(_TAKEN["beats"]), _TAKEN["job"]
            return "empty", [], None
        _JOB["job"] = None
        _TAKEN.update({"state": job.state, "beats": list(job.result), "job": job})
        return job.state, list(job.result), job


def cancel_job():
    job = current_job()
    if job is not None:
        job.cancel()
    with _LOCK:
        _JOB["job"] = None


# ------------------------------------------------------------- the blocking call

def generate_steps(world, settings, player_text=None, use_supervisor=None, supervise=None):
    """The whole request in one call: used off the main thread only.

    `ensure_buffer` does not call this -- it starts a job and shows a screen -- but the
    compatibility entry points in `ai_client` and the tests do, and they run where no screen
    exists.
    """
    job = start_job(world, settings, player_text=player_text, use_supervisor=use_supervisor,
                    supervise=supervise)
    while True:
        state, beats, finished = take_result()
        if state == "done":
            return beats
        if state == "error":
            raise StoryError(finished.error, finished.advice, finished.kind, finished.detail)
        if state == "empty":
            raise StoryError("Запрос не был запущен.", "Повтори запрос.", "error")
        time.sleep(0.1)


def wait_for_steps():
    """Block the calling thread on the job that is already in flight, then take its answer.

    This is the waiting screen's other half: `ensure_buffer` starts the job, `wait_for_steps`
    is called from the screen's timer once the screen is on top, and the answer leaves the
    worker through here.
    """
    job = current_job()
    if job is None:
        return "empty", []
    if job.state == "running":
        return "running", []
    state, beats, finished = take_result()
    if state == "done":
        return "done", beats
    if state == "error":
        return "error", finished
    return "empty", []
