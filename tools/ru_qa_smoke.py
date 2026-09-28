#!/usr/bin/env python3
"""Self-test for the Russian checker: every rule must fire on a known defect and stay quiet on
clean text.

A rule nobody tests is a rule that rots: the corpus moves, a regex silently stops matching, and
the reviewer trusts an empty report. So the fixtures live here, next to the code, and the
project's own smoke test runs this file.

    python3 tools/ru_qa_smoke.py
"""

import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ru_qa  # noqa: E402
import ru_text as rt  # noqa: E402
import ru_world as rw  # noqa: E402

CLEAN = [
    "Ветер с озера тянет запах хвои и мокрого бетона.",
    "«Ты всё-таки приехал. Я уже решила, что не приедешь».",
    "Асуна достаёт из кармана сложенный вчетверо листок и разглаживает его на коленях.",
    "«Лагерь сначала берёт в долг, а потом требует».",
    "Она улыбается, но улыбка не доходит до глаз: они всё время возвращаются к тропе.",
    "«Кто четвёртый?»",
    "— Идём, — говорит она и не оглядывается.",
]
BROKEN = {
    "typo.latin_in_cyrillic": "Айнkрад остался позади.",
    "typo.double_space": "Ветер  тянет запах хвои.",
    "typo.space_before_punct": "Он ушёл , а она осталась.",
    "typo.repeat_punct": "Он ушёл,, а она осталась.",
    "typo.dots": "И тут всё рухнуло...",
    "typo.straight_quotes": 'Он сказал "уходи".',
    "typo.quote_unclosed": "«Уходи, — говорит она и отворачивается к окну.",
    "typo.dash_pair": "Он ушёл -- а она осталась.",
    "typo.hyphen_dash": "Он ушёл - а она осталась.",
    "typo.nbsp": "Ветер тянет запах\u00a0хвои.",
    "typo.control_char": None,
    "typo.english_word": "Он открыл terminal и закрыл его.",
    "typo.yo_variant": "«Это жестко», — сказала она.",
    "coh.first_person_narration": "Я смотрю на ворота и жду.",
    "coh.double_negative": "Он не хотел не отвечать.",
    "coh.quote_in_narration": "Ворота открылись. «Проходите, — крикнул кто-то. — Скорее».",
    "style.slang": "Это было вообще кринж.",
    "style.placeholder": "Продолжение следует.",
    "style.opener": "Итак, всё пошло не так.",
    "style.brackets": "«Я в лагере (на втором этаже)».",
    "struct.long_text": "Ветер тянет запах хвои. " * 14,
    "struct.short_text": "Эй.",
}
ENGINE_BROKEN = {
    "engine.choice_flag_shape": {"effects": {"world_flag": "x"}},
    "engine.dialogue_no_character": {"type": "dialogue", "text": "«Привет»"},
    "engine.no_type_field": {"text": "Ветер.", "speaker": None},
}


def codes(text, kind="narration", **kw):
    return {f["code"] for f in rt.check_text(text, kind, **kw)}


def failed(checks):
    return [name for name, ok in checks.items() if not ok]


def main():
    checks = {}

    # 1. clean text produces nothing at ERROR or WARN
    for index, text in enumerate(CLEAN):
        for kind in ("narration", "dialogue"):
            bad = [f for f in rt.check_text(text, kind)
                   if f["level"] in (rt.ERROR, rt.WARN)]
            checks["clean[%d/%s]" % (index, kind)] = not bad
            if bad:
                print("  clean line %d/%s: %s" % (index, kind, [f["code"] for f in bad]))

    # 2. each defect fires its own rule
    for code, text in BROKEN.items():
        if text is None:
            continue
        fired = codes(text, "dialogue" if text.startswith("«") else "narration")
        checks[code] = code in fired
        if code not in fired:
            print("  %s did not fire; got %s" % (code, sorted(fired)))

    # 3. the engine contract rules, through a real file
    checks["engine"] = _engine_fixture()
    checks["json_shapes"] = _json_fixture()
    checks["verdict_guard"] = _verdict_fixture()
    checks["packets"] = _packet_fixture()
    checks["patch_guard"] = _patch_fixture()

    bad = failed(checks)
    print("проверок: %d, провалено: %d" % (len(checks), len(bad)))
    if bad:
        for name in bad:
            print(" - %s" % name)
        return 1
    print("RU_QA SMOKE OK")
    return 0


def _engine_fixture():
    story = {
        "title": "Проверка",
        "genre": "драма",
        "tone": "тихо",
        "characters": [{"id": "asuna", "name": "Асуна", "personality": "прямая"},
                       {"id": "kirito", "name": "Кирито", "personality": "молчаливый"}],
        # A list, while the engine reads a dict: the rule must notice.
        "locations": [{"id": "start_plaza", "name": "Площадь", "description": "Пусто."}],
        "scenes": [{
            "id": "scene_1",
            "background": "start_plaza",
            "steps": [
                {"type": "narration", "text": "Площадь пуста."},
                {"type": "dialogue", "speaker": "asuna", "text": "«Я пришла».",
                 "emotion": "happy"},
                {"type": "choice", "text": "Что делать?",
                 "choices": [{"id": "a", "text": "Уйти.", "effects": {"world_flag": "leave"}},
                             {"id": "b", "text": "Остаться."}]},
                {"type": "dialogue", "speaker": "nobody", "text": "«Кто это?»"},
            ],
        }],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "story_probe.json")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(story, ensure_ascii=False))
        loaded = rw.load(path)
        found = {f["code"] for f in rw.check_structure(loaded) + rw.check_references(loaded,
                                                                                  None)
                 + rw.check_contract(loaded, None)}
    want = ("engine.locations_not_map", "engine.choice_flag_shape", "ref.choice_no_flag",
            "ref.unknown_speaker")
    for code in want:
        if code not in found:
            print("  engine fixture: нет %s (найдено %s)" % (code, sorted(found)))
            return False
    return True


def _json_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "steps.json")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"scenes": [{"id": "s", "steps": [
                {"type": "narration", "text": "Дверь закрылась."},
                {"type": "narration", "text": "Дверь закрылась."},
                {"type": "choice", "text": "?", "choices": [{"id": "a", "text": "Да"}]},
            ]}]}, ensure_ascii=False))
        story = rw.load(path)
        found = {f["code"] for f in rw.check_structure(story)}
    for code in ("style.dup_text", "struct.one_choice"):
        if code not in found:
            print("  json fixture: нет %s" % code)
            return False
    return True


def _verdict_fixture():
    packet = {"id": "t-01", "items": [{"id": "a/1", "text": "«Привет»"},
                                       {"id": "a/2", "text": "Пока."}]}
    good = {"id": "t-01", "items": [
        {"id": "a/1", "meaning": "ok", "link": "bad", "note": "не отвечает"},
        {"id": "a/2"},
    ]}
    try:
        rows = ru_qa.normalize_verdict(good, packet)
    except ValueError as exc:
        print("  verdict: %s" % exc)
        return False
    if rows[0]["verdict"] != "bad" or rows[1]["verdict"] != "ok":
        print("  verdict: неверный подсчёт %s" % [r["verdict"] for r in rows])
        return False
    for broken, why in (({"items": [{"id": "zzz"}]}, "чужой id"),
                        ({"items": [{"id": "a/1", "meaning": "maybe"}]}, "значение не из списка"),
                        ({"items": [{"id": "a/1"}]}, "нет ответа по строке"),
                        ({"nope": []}, "нет items")):
        try:
            ru_qa.normalize_verdict(broken, packet)
        except ValueError:
            continue
        print("  verdict: принято плохое (%s)" % why)
        return False
    return True


def _packet_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "p.json")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"scenes": [{"id": "s", "steps": [
                {"type": "narration", "text": "Дверь закрылась."},
                {"type": "dialogue", "speaker": "asuna", "text": "«Я пришла»."},
                {"type": "choice", "text": "Что делать?",
                 "choices": [{"id": "a", "text": "Уйти."}, {"id": "b", "text": "Остаться."}]},
            ]}]}, ensure_ascii=False))
        story, findings = ru_qa.review(path, engine_checks=False)
        packets = ru_qa.build_packets(story, findings, size=8)
        if len(packets) != 1 or len(packets[0]["items"]) != 3:
            print("  packet: %d пакетов, %d строк" % (len(packets), len(packets[0]["items"])))
            return False
        item = packets[0]["items"][1]
        if item["before"] != "Дверь закрылась." or item["after"] != "Что делать?":
            print("  packet: соседи не подставлены: %r" % item)
            return False
        if "Рулетка" in ru_qa.packet_text(packets, story):
            return False
    return True


def _patch_fixture():
    """The guard must refuse every shape a small model actually produces."""
    import json as _json
    import ru_patch as rp

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "story_sao.json")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(_json.dumps({"scenes": [{"id": "scene_1", "steps": [
                {"type": "narration", "text": "Прошло два года с того дня, как всё это кончилось."},
                {"type": "dialogue", "speaker": "asuna", "text": "«О»."},
            ]}]}, ensure_ascii=False))
        first, second = "story_sao.json/scene_1/0", "story_sao.json/scene_1/1"

        def refused(patch):
            try:
                rp.parse_patch(patch, rw.load(path))
            except rp.Refused:
                return True
            return False

        good_first = "Прошло два года с того дня, как Sword Art Online перестала быть ловушкой."
        cases = {
            "unknown id": ([{"id": "scene_1@1", "new": good_first}], True),
            "new and split": ([{"id": first, "new": good_first, "split": ["а", "б"]}], True),
            "same line twice": ([{"id": first, "new": good_first},
                                {"id": first, "new": good_first}], True),
            "json fragment as text": ([{"id": first, "new": '"emotion": "worried"'}], True),
            "shortened": ([{"id": first, "new": "Да."}], True),
            "unbalanced quotes": ([{"id": first, "new": "«О, -- говорит она."}], True),
            "not a list": ({"nope": 1}, True),
            "valid replace": ([{"id": first, "new": good_first}], False),
            "valid split": ([{"id": second, "split": ["«О».", "Она поднимает голову."]}], False),
            "skip is allowed": ([{"id": first, "skip": "строка хорошая"}], False),
        }
        bad = []
        for name, (patch, want_refused) in cases.items():
            got = refused(patch)
            if got != want_refused:
                bad.append("%s: %s" % (name, "принято" if got else "отклонено"))
                print("  patch %s: %s" % (name, "принято, а надо было отклонить" if got
                                          else "отклонено, а надо было принять"))
        return not bad


if __name__ == "__main__":
    raise SystemExit(main())
