#!/usr/bin/env python3
"""The Russian review of a story file: a machine pass, a judge packet, a merged verdict.

The work is split on purpose. This module answers everything decidable from the text itself
and prints it. What is left -- does the line answer the question, does it follow the previous
line, is this the tone the project asked for -- is handed to the controller agent as numbered
items, because a small model judges a short list with fixed questions far better than it
judges a 38 000-character file.

    python3 tools/ru_qa.py report data/story_sao.json
    python3 tools/ru_qa.py report game/story_chapter.py --json
    python3 tools/ru_qa.py packet data/story_sao.json --tag sao --out agent_bus/qa_lang
    python3 tools/ru_qa.py merge data/story_sao.json --tag sao --dir agent_bus/qa_lang

`packet` also writes a ready template for every packet, so the controller agent fills in blanks
instead of inventing a format, and `merge` refuses to accept a verdict with an unknown id.
"""

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
GAME = os.path.join(os.path.dirname(HERE), "game")

import ru_text as rt  # noqa: E402
import ru_world as rw  # noqa: E402

AXES = ("structure", "reference", "engine", "grammar", "style", "coherence", "form", "judge")
_LEVEL_ORDER = {rt.ERROR: 0, rt.WARN: 1, rt.INFO: 2}
VERDICT_VALUES = ("ok", "bad", "unsure")
# Five questions, always asked in the same wording, so two packets are answered the same way.
QUESTIONS = (
    "meaning: отвечает ли реплика или действие на то, о чём шла речь?",
    "link: следует ли строка из предыдущей и ведёт ли к следующей?",
    "facts: не знает ли персонаж того, чего не мог знать?",
    "voice: соответствует ли интонация объявленной эмоции?",
    "grammar: есть ли то, чего не поймал скрипт: неудачное слово, разнобой, канцелярит?",
)


def axis_of(code):
    return code.split(".", 1)[0] if "." in code else "judge"


def review(path, engine_checks=True):
    """Every machine-decidable finding for one file, plus the per-unit index."""
    story = rw.load(path)
    names = [str(name).lower() for name in (story.get("characters") or {}).values()]
    names += [str(cid).lower() for cid in (story.get("characters") or {}).keys()]
    introduced = set()

    findings = []
    for unit in story["units"]:
        if not unit["text"]:
            continue
        for item in rt.check_text(unit["text"], unit["kind"], where=unit["uid"],
                                 line=unit["line"], mentions=names,
                                 introduced=sorted(introduced)):
            item["axis"] = axis_of(item["code"])
            findings.append(item)
        if unit["kind"] == "dialogue" and unit.get("speaker"):
            introduced.add(str(unit["speaker"]).lower())
    findings += _tag(rw.check_structure(story, GAME))
    findings += _tag(rw.check_references(story, GAME))
    if engine_checks:
        findings += _tag(rw.check_contract(story, GAME))
    for field, value in story.get("fields") or []:
        # A world field is prose for the prompt, not a line of dialogue: the length rule and
        # the "TTS will read it" rules do not apply to it.
        for item in rt.check_text(value, "field", where="%s:%s" % (story.name, field), line=0,
                                 mentions=names, introduced=sorted(introduced)):
            item["axis"] = axis_of(item["code"])
            item["field"] = field
            findings.append(item)
    if not any(rt.CYR_RE.search(u["text"]) for u in story["units"] if u["text"]):
        findings.append(rt.Finding("struct.not_russian", rt.WARN, where=story.name,
                                   axis="structure", hint="в тексте нет кириллицы: это не русский сюжет"))
    findings = _collapse(findings)
    findings.sort(key=lambda f: (_LEVEL_ORDER.get(f["level"], 9), f["code"], f["where"]))
    return story, findings


def _collapse(findings):
    """One line for a rule that fires on every line of a file.

    A rule that hits all 381 steps tells the reader nothing except that the file uses that
    convention, so it is reported once with a count.
    """
    groups = {}
    kept = []
    for item in findings:
        label = item.get("aggregate")
        if not label:
            kept.append(item)
            continue
        groups.setdefault(label, []).append(item)
    for label, items in groups.items():
        first = items[0]
        first["hint"] = "%s: %d мест(а) в файле" % (first["hint"], len(items))
        first["text"] = ""
        kept.append(first)
    return kept


def _tag(items):
    for item in items:
        item["axis"] = axis_of(item["code"])
    return items


def counts(findings):
    out = {}
    for item in findings:
        out[item["level"]] = out.get(item["level"], 0) + 1
    return out


# --------------------------------------------------------------------- report

def report_text(story, findings, verdicts=None, limit=40):
    verdicts = verdicts or []
    lines = []
    add = lines.append
    tally = counts(findings)
    add("# Проверка текста: %s" % story.name)
    add("")
    add("Источник: `%s`" % story["path"])
    add("Строк сюжета: %d, полей мира: %d, персонажей: %d"
        % (len(story["units"]), len(story.get("fields") or []), len(story.get("characters") or {})))
    add("Находок: ошибок %d, предупреждений %d, замечаний %d"
        % (tally.get(rt.ERROR, 0), tally.get(rt.WARN, 0), tally.get(rt.INFO, 0)))
    if verdicts:
        bad = sum(1 for v in verdicts if v.get("verdict") == "bad")
        add("Вердиктов агента: %d, из них «плохо»: %d" % (len(verdicts), bad))
    add("")

    by_code = {}
    for item in findings:
        by_code.setdefault(item["code"], []).append(item)
    add("## Сводка по правилам")
    add("")
    add("| код | уровень | сколько | что это |")
    add("|---|---|---|---|")
    for code in sorted(by_code, key=lambda c: (_LEVEL_ORDER.get(by_code[c][0]["level"], 9), c)):
        items = by_code[code]
        add("| `%s` | %s | %d | %s |"
            % (code, items[0]["level"], len(items), items[0].get("hint", "")))
    add("")

    add("## Список по строкам")
    add("")
    add("_Не больше 5 примеров на правило: полный список — в report.json._")
    add("")
    shown = 0
    per_code = {}
    for item in findings:
        if shown >= limit:
            break
        seen = per_code.get(item["code"], 0)
        if seen >= 5:
            continue
        per_code[item["code"]] = seen + 1
        add("- **%s** `%s` %s" % (item["level"], item.get("where") or "-",
                                 ("строка %d" % item["line"]) if item.get("line") else ""))
        if item.get("text"):
            add("  - текст: %s" % rt.visible(item["text"])[:200])
        if item.get("hint"):
            add("  - %s" % item["hint"])
        shown += 1
    add("")

    if verdicts:
        add("## Вердикты агента-контролёра")
        add("")
        bad = [v for v in verdicts if v.get("verdict") != "ok"]
        add("Проверено строк: %d, замечаний: %d, из них плохих: %d"
            % (len(verdicts), len(bad), sum(1 for v in bad if v["verdict"] == "bad")))
        add("")
        if bad:
            add("| строка | смысл | связность | факты | интонация | грамотность | что делать |")
            add("|---|---|---|---|---|---|---|")
            for item in bad:
                add("| `%s` | %s | %s | %s | %s | %s | %s |" % (
                    item.get("id"), item.get("meaning"), item.get("link"), item.get("facts"),
                    item.get("voice"), item.get("grammar"),
                    (item.get("note") or item.get("fix") or "—").replace("|", "/")))
        else:
            add("Замечаний нет.")
        add("")
    add("## Что делать")
    add("")
    order = [i for i in findings if i["level"] == rt.ERROR]
    order += [i for i in findings if i["level"] == rt.WARN]
    if not order:
        add("Механических ошибок нет. Остаётся только суждение агента по пакетам.")
    seen = set()
    unique = []
    for item in order:
        key = (item.get("where"), item["code"], item.get("hint"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    for index, item in enumerate(unique[:12], 1):
        add("%d. `%s` — %s" % (index, item.get("where") or story.name, item.get("hint") or item["code"]))
    if len(unique) > 12:
        add("_…ещё %d, порядок тот же: сначала ошибки, потом предупреждения._" % (len(unique) - 12))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------- packets

def build_packets(story, findings, size=8):
    """Numbered judge items: the line, its neighbours, and what the script already found."""
    by_unit = {}
    for item in findings:
        by_unit.setdefault(item.get("where"), []).append(item)
    index = {u["uid"]: i for i, u in enumerate(story["units"])}
    units = [u for u in story["units"] if u["text"].strip()]
    packets = []
    for start in range(0, len(units), size):
        chunk = units[start:start + size]
        items = []
        for unit in chunk:
            position = index[unit["uid"]]
            previous = story["units"][position - 1] if position else None
            following = story["units"][position + 1] if position + 1 < len(story["units"]) else None
            items.append({
                "id": unit["uid"],
                "kind": unit["kind"],
                "speaker": unit.get("speaker") or "",
                "emotion": unit.get("emotion") or "",
                "scene": unit.get("scene") or "",
                "before": (previous["text"][:200] if previous else ""),
                "text": unit["text"][:400],
                "after": (following["text"][:200] if following else ""),
                "choices": [str(c.get("text") or "")[:200] for c in (unit.get("choices") or [])],
                "script": ["%s: %s" % (f["code"], f.get("hint") or "")
                           for f in by_unit.get(unit["uid"], [])],
            })
        packets.append({"id": None, "items": items})
    return packets


def world_brief(story):
    """Who is who and what the story is, so the judge can answer the `facts` question at all."""
    fields = dict(story.get("fields") or [])
    lines = []
    title = fields.get("title") or story.name
    lines.append("- название: %s" % title)
    for key in ("description", "premise", "tone", "genre"):
        if fields.get(key):
            lines.append("- %s: %s" % (key, fields[key]))
    cast = story.get("characters") or {}
    if cast:
        lines.append("- герои:")
        for cid, record in cast.items():
            if isinstance(record, dict):
                who = record.get("name") or cid
                lines.append("  * %s (%s): %s" % (who, cid, record.get("personality") or "—"))
            else:
                lines.append("  * %s (%s)" % (record, cid))
    # The parts of a story, in order of appearance. A hand-written chapter is a dict of blocks
    # that cannot be literal_eval'ed, so this reads what the loader actually saw.
    seen, blocks = set(), []
    for unit in story["units"]:
        scene = str(unit.get("scene") or "")
        if scene and scene not in seen and scene not in ("say", "root"):
            seen.add(scene)
            blocks.append(scene)
    if blocks:
        lines.append("- части сюжета: %s" % ", ".join(blocks[:24]))
    if not lines:
        lines.append("- сюжет без описания мира: суди только по самим строкам")
    return lines


def packet_text(packets, story):
    lines = []
    add = lines.append
    add("# Пакеты для агента-контролёра: %s" % story.name)
    add("")
    add("Источник: `%s`" % story["path"])
    add("")
    add("## Кто есть кто в этом сюжете")
    add("")
    for row in world_brief(story):
        add(row)
    add("")
    add("## Вопросы к каждой строке")
    add("")
    for question in QUESTIONS:
        add("- %s" % question)
    add("")
    add("Поля ответа: meaning, link, facts, voice, grammar — только ok, bad или unsure.")
    add("Ставь ok везде, где сомнения нет: незаполненным строкам score не нужен.")
    add("")
    for number, packet in enumerate(packets, 1):
        add("## Пакет %d (id: %s)" % (number, packet["id"]))
        add("")
        for item in packet["items"]:
            add("### %s [%s]" % (item["id"], item["kind"]))
            add("- сцена: %s, говорит: %s, эмоция: %s"
                % (item["scene"] or "-", item["speaker"] or "рассказчик", item["emotion"] or "-"))
            if item["before"]:
                add("- предыдущая строка: %s" % rt.visible(item["before"]))
            add("- **эта строка**: %s" % rt.visible(item["text"]))
            if item["choices"]:
                add("- варианты выбора: %s" % " | ".join(rt.visible(c) for c in item["choices"]))
            if item["after"]:
                add("- следующая строка: %s" % rt.visible(item["after"]))
            if item["script"]:
                add("- уже найдено скриптом: %s" % "; ".join(item["script"]))
            add("")
    return "\n".join(lines) + "\n"


TEMPLATE = {
    "id": "",
    "items": [],
}
ITEM_TEMPLATE = {
    "id": "",
    "meaning": "ok",
    "link": "ok",
    "facts": "ok",
    "voice": "ok",
    "grammar": "ok",
    "note": "",
    "fix": "",
}


def item_template(item):
    out = dict(ITEM_TEMPLATE)
    out["id"] = item["id"]
    return out


VERDICT_FIELDS = ("meaning", "link", "facts", "voice", "grammar")


def is_untouched(document):
    """A sheet with no answers in it is not a review, and must never enter a report."""
    items = (document or {}).get("items") or []
    if not items:
        return True
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("note") or "").strip():
            return False
        if str(item.get("fix") or "").strip():
            return False
        for key in VERDICT_FIELDS:
            if str(item.get(key) or "ok").strip().lower() not in ("", "ok"):
                return False
    return True


def verdict_document(packet):
    return {"id": packet["id"],
            "items": [item_template(item) for item in packet["items"]]}


# --------------------------------------------------------------------- merge

def normalize_verdict(doc, packet, strict=True):
    """Turn whatever the model wrote into our shape, refusing unknown ids when strict."""
    allowed = {item["id"] for item in packet["items"]}
    items = doc.get("items")
    if not isinstance(items, list):
        raise ValueError("нет поля items со списком строк")
    by_id = {}
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("элемент items не объект: %r" % (raw,))
        uid = str(raw.get("id") or "").strip()
        if not uid:
            raise ValueError("элемент без id")
        if uid not in allowed:
            raise ValueError("в пакете нет строки «%s»" % uid)
        row = {"id": uid}
        for key in ("meaning", "link", "facts", "voice", "grammar"):
            value = str(raw.get(key) or "ok").strip().lower()
            if value not in VERDICT_VALUES:
                value = "unsure" if strict is False else value
            if value not in VERDICT_VALUES:
                raise ValueError("в строке %s поле %s: «%s» — допустимо только ok, bad, unsure"
                                 % (uid, key, value))
            row[key] = value
        row["note"] = str(raw.get("note") or "")[:400]
        fix = raw.get("fix")
        row["fix"] = str(fix)[:600] if isinstance(fix, str) else ""
        by_id[uid] = row
    missing = sorted(allowed - set(by_id))
    if missing:
        raise ValueError("нет ответа по строкам: %s" % ", ".join(missing[:8]))
    out = []
    for item in packet["items"]:
        row = by_id[item["id"]]
        row["verdict"] = "bad" if "bad" in (row["meaning"], row["link"], row["facts"],
                                            row["voice"], row["grammar"]) else (
            "unsure" if "unsure" in (row["meaning"], row["link"], row["facts"],
                                     row["voice"], row["grammar"]) else "ok")
        row["text"] = item["text"]
        out.append(row)
    return out


# --------------------------------------------------------------------- cli

def main(argv=None):
    parser = argparse.ArgumentParser(description="Проверка русского текста сюжета")
    parser.add_argument("command", choices=["report", "packet", "merge", "list"])
    parser.add_argument("path")
    parser.add_argument("--tag", default=None, help="короткое имя для пакетов и папки вердиктов")
    parser.add_argument("--out", default=os.path.join(os.path.dirname(HERE), "agent_bus", "qa_lang"))
    parser.add_argument("--size", type=int, default=8, help="строк в пакете")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-engine", action="store_true")
    parser.add_argument("--write", action="store_true", help="сохранить отчёт в папку bus")
    args = parser.parse_args(argv)

    if args.command == "list":
        for path in args.path.split(","):
            path = path.strip()
            if not path:
                continue
            story, _ = review(path, engine_checks=not args.no_engine)
            print("%s: %d строк, %d персонажей, %d полей мира, подключён: %s"
                  % (story["path"], len(story["units"]), len(story.get("characters") or {}),
                     len(story.get("fields") or []), "да" if story.get("referenced") else "нет"))
        return 0

    story, findings = review(args.path, engine_checks=not args.no_engine)
    tag = args.tag or os.path.splitext(story.name)[0]

    if args.command == "report":
        if args.json:
            print(json.dumps({"story": story["path"], "findings": list(findings)},
                             ensure_ascii=False, indent=1))
        else:
            print(report_text(story, findings, limit=args.limit), end="")
        if args.write:
            _write(os.path.join(args.out, "report.md"), report_text(story, findings, limit=10 ** 6))
            _write(os.path.join(args.out, "report.json"),
                   json.dumps({"story": story["path"], "findings": list(findings)},
                              ensure_ascii=False, indent=1))
        return 0

    if args.command == "packet":
        packets = build_packets(story, findings, size=args.size)
        folder = os.path.join(args.out, "packets", tag)
        os.makedirs(folder, exist_ok=True)
        for number, packet in enumerate(packets, 1):
            packet["id"] = "%s-%02d" % (tag, number)
            _write(os.path.join(folder, packet["id"] + ".json"),
                   json.dumps(verdict_document(packet), ensure_ascii=False, indent=1))
            _write(os.path.join(folder, packet["id"] + ".txt"), packet_text([packet], story))
        _write(os.path.join(args.out, "packets", tag + ".index.json"),
               json.dumps({"story": story["path"], "tag": tag,
                           "packets": [p["id"] for p in packets],
                           "questions": list(QUESTIONS)}, ensure_ascii=False, indent=1))
        print("пакетов: %d, папка: %s" % (len(packets), folder))
        return 0

    if args.command == "merge":
        packets = build_packets(story, findings, size=args.size)
        for number, packet in enumerate(packets, 1):
            packet["id"] = "%s-%02d" % (tag, number)
        rows, problems = [], []
        for packet in packets:
            path = os.path.join(args.out, "verdicts", packet["id"] + ".json")
            if not os.path.exists(path):
                problems.append("нет файла %s" % path)
                continue
            try:
                with io.open(path, encoding="utf-8") as fh:
                    doc = json.load(fh)
            except Exception as exc:
                problems.append("%s: не читается (%s)" % (path, exc))
                continue
            try:
                rows += normalize_verdict(doc, packet)
            except ValueError as exc:
                problems.append("%s: %s" % (packet["id"], exc))
        text = report_text(story, findings, verdicts=rows, limit=args.limit)
        print(text, end="")
        for problem in problems:
            print("!! %s" % problem)
        if args.write:
            _write(os.path.join(args.out, "report.md"), text)
            _write(os.path.join(args.out, "report.json"), json.dumps(
                {"story": story["path"], "findings": list(findings), "verdicts": rows,
                 "problems": problems}, ensure_ascii=False, indent=1))
        return 1 if problems else 0
    return 0


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


if __name__ == "__main__":
    raise SystemExit(main())
