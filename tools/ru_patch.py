#!/usr/bin/env python3
"""The sheet a controller fills in, and the guard that refuses a broken edit.

A small model editing a 38 000-character story file in place is a bad bet: one lost quote and
the JSON stops parsing, one renamed `ASUNA` and every scene that referenced it breaks. So the
model never writes the story. It writes a list of replacements addressed by the same line ids
the report uses, and this tool applies them:

    python3 tools/ru_patch.py template data/story_sao.json --out /tmp/fix.json
    python3 tools/ru_patch.py check   data/story_sao.json /tmp/fix.json
    python3 tools/ru_patch.py apply   data/story_sao.json /tmp/fix.json --out data/story_fixed.json

Every command re-reads the story after writing and compares it with the original on the things
that must not move: the set of speakers, backgrounds, emotions, choice ids, gotos and flags, the
number of steps, the total length of the text, and whether the file still parses. If any of
those changed, the write is refused and the reason is printed. That is the whole point: the
model is allowed to change the words and nothing else, and the tool proves it.

Patch item, one per fixed line:

    {"id": "...", "why": "кратко", "new": "новый текст"}
    {"id": "...", "why": "кратко", "split": ["первая строка", "вторая строка"]}
    {"id": "...", "skip": "почему оставляем"}
"""

import argparse
import ast
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
GAME = os.path.join(ROOT, "game")

import ru_qa  # noqa: E402
import ru_world as rw  # noqa: E402

# Fields of a call that must survive an edit untouched.
KEEP_KEYS = ("who", "bg", "background", "emotion", "music", "music_intent", "goto", "flag",
             "world_flag", "character", "position", "state_patch", "checkpoint", "type")


class Refused(Exception):
    pass


# --------------------------------------------------------------------- signature

def signature(story):
    """Everything an edit is forbidden to change, as a comparable structure."""
    speakers, backgrounds, emotions, gotos, flags, choice_ids, types = set(), set(), set(), set(), set(), set(), set()
    for unit in story["units"]:
        for key, bucket in (("speaker", speakers), ("background", backgrounds),
                            ("emotion", emotions), ("goto", gotos)):
            value = unit.get(key)
            if value:
                bucket.add("%s=%s" % (key, value))
        if unit.get("kind"):
            types.add(unit["kind"])
        for choice in unit.get("choices") or []:
            if choice.get("id"):
                choice_ids.add("id=%s" % choice["id"])
            for key in ("world_flag", "flag", "goto"):
                if choice.get(key):
                    flags.add("%s=%s" % (key, choice[key]))
    return {
        "speakers": speakers, "backgrounds": backgrounds, "emotions": emotions,
        "gotos": gotos, "flags": flags, "choice_ids": choice_ids, "types": types,
    }


def text_volume(story):
    return sum(len(u["text"]) for u in story["units"])


def units_by_id(story):
    return {u["uid"]: u for u in story["units"]}


# --------------------------------------------------------------------- template

def build_template(path, size=None, limit=None):
    """A sheet with the machine findings already filled in and nothing else to invent."""
    story, findings = ru_qa.review(path)
    packets = ru_qa.build_packets(story, findings, size=size or 8)
    order = {}
    for packet in packets:
        for item in packet["items"]:
            order.setdefault(item["id"], {"id": item["id"], "kind": item["kind"],
                                         "speaker": item["speaker"], "emotion": item["emotion"],
                                         "scene": item["scene"], "old": item["text"],
                                         "script": item["script"], "new": "", "split": [],
                                         "skip": "", "why": ""})
    for item in findings:
        row = order.get(item.get("where"))
        if row is None:
            continue
        row["script"].append("%s: %s" % (item["code"], item.get("hint") or ""))
        if not row["why"]:
            row["why"] = item.get("hint") or item["code"]
    # The form-of-a-line rule from the house style comes first: it changes how the rest reads.
    for key in ("form.tag_after_quote", "form.quote_with_tag", "typo.quote_unclosed",
                "coh.reported_in_dialogue", "coh.quote_in_narration",
                "style.stage_in_dialogue"):
        for item in findings:
            row = order.get(item.get("where"))
            if row is not None and item["code"] == key and not row["why"]:
                row["why"] = item.get("hint") or item["code"]
    # A missing `character` field is not a sentence, and a model asked to fix it will either
    # ignore it or invent text. Engine and reference findings stay in the report for the
    # developer; the sheet holds only what a language editor can decide.
    text_codes = ("form.", "typo.", "style.", "coh.", "struct.")
    rows, foreign = [], []
    for row in order.values():
        mine = [x for x in row["script"] if x.startswith(text_codes)]
        theirs = [x for x in row["script"] if not x.startswith(text_codes)]
        if mine:
            rows.append(dict(row, script=mine))
        if theirs:
            foreign.append({"id": row["id"], "not_yours": theirs})
    held = 0
    if limit and len(rows) > limit:
        held = len(rows) - limit
        rows = rows[:limit]
    return {
        "story": story["path"],
        "note": ("Заполни поля new или split. Если правка не нужна — skip. "
                 "Правь только те строки, что перечислены в items."),
        "held_back": held,
        "held_back_note": ("Строк с находками ещё %d: они попадут в следующий бланк, "
                           "когда этот будет применён." % held) if held else "",
        "questions": list(ru_qa.QUESTIONS),
        "style": ("Тихая летняя повседневность, короткие реплики, деталь важнее пафоса. "
                  "Внутри «…» только голос персонажа, ремарка и действие — отдельной строкой."),
        "items": rows,
        "not_yours": foreign,
        "not_yours_note": ("Это ошибки формата и движка, а не языка. Текст здесь не трогай, "
                           "их чинит разработчик: они остаются в agent_bus/qa_lang/report.md."),
    }


# --------------------------------------------------------------------- patch parsing

def parse_patch(document, story):
    """Validate the model's answer and return the operations it asks for.

    Every problem is reported, not just the first one: a model that gets nine errors in one
    answer fixes nine things, a model that gets one at a time needs nine rounds.
    """
    if isinstance(document, dict):
        items = document.get("items")
        if items is None:
            items = document.get("patch")
    else:
        items = document
    errors = []
    if not isinstance(items, list):
        raise Refused("ожидался массив правок или объект с полем items")
    known = units_by_id(story)
    seen = set()
    operations = []
    for number, raw in enumerate(items, 1):
        if not isinstance(raw, dict):
            errors.append("правка №%d: элемент не объект" % number)
            continue
        uid = str(raw.get("id") or "").strip()
        why = str(raw.get("why") or "").strip()
        skip = str(raw.get("skip") or "").strip()
        new = raw.get("new")
        split = raw.get("split")
        if not uid:
            errors.append("правка №%d: нет id" % number)
            continue
        if uid not in known:
            near = _nearest(known, uid)
            errors.append("правка №%d: строки «%s» нет%s" % (number, uid, ("; похоже: " + near)
                                                                if near else ""))
            continue
        if uid in seen:
            errors.append("правка №%d: строка «%s» уже правилась выше" % (number, uid))
            continue
        seen.add(uid)
        unit = known[uid]
        if skip and (new or split):
            errors.append("правка №%d: skip и new/split вместе нельзя" % number)
            continue
        if new is not None and split:
            errors.append("правка №%d: укажи что-то одно — new или split" % number)
            continue
        if skip:
            operations.append({"id": uid, "kind": "skip", "why": why or skip})
            continue
        if new is not None:
            problems = _text_problems(str(new), unit, "new")
            if problems:
                errors.append("правка №%d (%s): %s" % (number, uid, "; ".join(problems)))
                continue
            operations.append({"id": uid, "kind": "replace", "text": str(new), "why": why})
            continue
        if split is not None:
            if not isinstance(split, list) or len(split) < 2:
                errors.append("правка №%d: split должен быть списком из двух и более строк" % number)
                continue
            split = [str(x) for x in split]
            problems = []
            for index, part in enumerate(split):
                problems += ["часть %d: %s" % (index + 1, p) for p in
                             _text_problems(part, unit if index == 0 else None, "split")]
            was = len(unit["text"])
            if was and sum(len(x) for x in split) < was * 0.7:
                problems.append("split короче исходника на %d символов: сокращать нельзя, "
                                "допиши вторую часть, а не выбрасывай текст"
                                % (was - sum(len(x) for x in split)))
            if problems:
                errors.append("правка №%d (%s): %s" % (number, uid, "; ".join(problems)))
                continue
            operations.append({"id": uid, "kind": "split", "parts": split, "why": why})
            continue
        operations.append({"id": uid, "kind": "skip", "why": why or "правки не предложено"})
    if errors:
        raise Refused("%d проблем в правках\n  - %s" % (len(errors), "\n  - ".join(errors)))
    return operations


def _nearest(known, uid):
    """The line the model probably meant, so a wrong address is fixable in one round."""
    import difflib
    close = difflib.get_close_matches(uid, list(known), n=1, cutoff=0.5)
    return close[0] if close else ""


def _text_problems(text, unit, field):
    """What a replacement must satisfy before the guard will even look at the file."""
    problems = []
    body = text.strip()
    if not body:
        return ["%s пустой" % field]
    if body.startswith('"') and '":' in body:
        problems.append("%s похож на кусок JSON, а нужен только текст строки" % field)
    if body.count("«") != body.count("»"):
        problems.append("%s: кавычки «…» не сходятся" % field)
    if unit is not None and field == "new":
        was = len(unit["text"])
        if was and len(body) < was * 0.7:
            problems.append("new короче исходника на %d символов: сокращать нельзя, "
                            "допиши, а не выбрасывай" % (was - len(body)))
    return problems


# --------------------------------------------------------------------- applying

def _json_apply(story_path, operations):
    with io.open(story_path, encoding="utf-8") as fh:
        data = json.load(fh)
    index = {}
    for scene in data.get("scenes") or []:
        for position, step in enumerate(scene.get("steps") or []):
            index["%s/%s/%d" % (os.path.basename(story_path), scene.get("id"), position)] = (scene, position)
    for op in operations:
        if op["kind"] == "skip":
            continue
        scene, position = index[op["id"]]
        step = scene["steps"][position]
        if op["kind"] == "replace":
            step["text"] = op["text"]
            continue
        # split: the first part keeps the step, the rest follow it
        head = dict(step)
        head["text"] = op["parts"][0]
        tail = []
        for extra in op["parts"][1:]:
            follow = dict(step)
            follow["text"] = extra
            follow.pop("choices", None)
            follow.pop("checkpoint", None)
            if step.get("type") == "dialogue":
                follow["type"] = "narration"
                follow.pop("speaker", None)
                follow.pop("who", None)
                follow.pop("emotion", None)
            tail.append(follow)
        scene["steps"][position:position + 1] = [head] + tail
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n", data


def _python_apply(story_path, operations):
    """Rewrite the text inside `s(...)` and `opt(...)` calls, in place, by source span.

    Everything here works in bytes, because `ast` reports `col_offset` in UTF-8 bytes. Splicing
    a Cyrillic line with character offsets silently eats the rest of the call, so the source is
    split as bytes and decoded once at the end.
    """
    with io.open(story_path, encoding="utf-8") as fh:
        source = fh.read()
    raw = source.encode("utf-8")
    tree = ast.parse(source, filename=story_path)
    calls = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        if name in ("s", "opt") and node.args:
            calls.setdefault(node.lineno, []).append((name, node))
    offsets = [0]
    for line in raw.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    edits = []
    for op in operations:
        if op["kind"] == "skip":
            continue
        line_no = int(op["id"].split("@")[-1])
        found = calls.get(line_no)
        if not found:
            raise Refused("строка %s: вызова s()/opt() в исходнике нет" % op["id"])
        name, node = found[0]
        literal = node.args[0]
        # Only a plain string literal is rewritten. A call that builds its text from a variable
        # or a concatenation is left for a human rather than mangled.
        if not (isinstance(literal, ast.Constant) and isinstance(literal.value, str)):
            continue
        start = offsets[literal.lineno - 1] + literal.col_offset
        end = offsets[literal.end_lineno - 1] + literal.end_col_offset
        if op["kind"] == "replace":
            edits.append((start, end, json.dumps(op["text"], ensure_ascii=False).encode("utf-8")))
            continue
        edits.append((start, end, json.dumps(op["parts"][0], ensure_ascii=False).encode("utf-8")))
        # The extra lines go right after the call, at the same indent, with the same background.
        indent = b" " * node.col_offset
        background = _bg_of(node, source) or b"None"
        extra = b"".join(indent + b"s(" + json.dumps(x, ensure_ascii=False).encode("utf-8")
                         + b", bg=" + background + b"),\n" for x in op["parts"][1:])
        # The call is often followed by a comma (`s(...),` inside a list literal), so the new
        # lines go after the whole line, not between the bracket and the comma.
        tail_at = offsets[node.end_lineno - 1] + node.end_col_offset
        newline = raw.find(b"\n", tail_at)
        tail_at = len(raw) if newline < 0 else newline
        edits.append((tail_at, tail_at, b"\n" + extra.rstrip(b"\n")))
    if not edits:
        return source
    out = raw
    for start, end, text in sorted(edits, key=lambda e: -e[0]):
        out = out[:start] + text + out[end:]
    return out.decode("utf-8")


def _bg_of(node, source):
    """The background the call already uses, as source text, so a split line keeps its place."""
    for keyword in node.keywords:
        if keyword.arg in ("bg", "background"):
            segment = ast.get_source_segment(source, keyword.value)
            if segment:
                return segment.encode("utf-8")
    return b""


def apply_text(path, operations):
    """The rewritten file, as text. Which path this takes depends only on the extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return _json_apply(path, operations)[0]
    if ext == ".py":
        return _python_apply(path, operations)
    raise Refused("правка через отчёт поддерживается для .json и .py, не для %s" % ext)


# --------------------------------------------------------------------- guard

def guard(before_path, after_path):
    """The promise the tool makes: the words changed, nothing else did."""
    before = rw.load(before_path)
    after = rw.load(after_path)
    problems = []
    sb, sa = signature(before), signature(after)
    for key in sb:
        if sb[key] != sa[key]:
            lost = sorted(sb[key] - sa[key])[:6]
            added = sorted(sa[key] - sb[key])[:6]
            problems.append("изменилось «%s»: пропало %s, появилось %s"
                            % (key, ", ".join(map(str, lost)) or "—",
                               ", ".join(map(str, added)) or "—"))
    if len(after["units"]) < len(before["units"]):
        problems.append("строк стало меньше: %d → %d, сокращать нельзя"
                        % (len(before["units"]), len(after["units"])))
    volume_before, volume_after = text_volume(before), text_volume(after)
    if volume_after < volume_before:
        problems.append("текста стало меньше: %d → %d символов, сокращать нельзя"
                        % (volume_before, volume_after))
    try:
        ast.parse(io.open(after_path, encoding="utf-8").read(), filename=after_path)
    except SyntaxError as exc:
        problems.append("после правки файл не разбирается: %s" % exc)
    return problems, before, after


def main(argv=None):
    parser = argparse.ArgumentParser(description="Правка сюжета по списку замен")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("template", help="собрать бланк правок по находкам отчёта")
    p.add_argument("path")
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=30,
                   help="сколько строк класть в один бланк (остальные — в следующий проход)")

    p = sub.add_parser("check", help="проверить правки, не записывая файл")
    p.add_argument("path")
    p.add_argument("patch")
    p.add_argument("--out", default=None, help="куда записать результат проверки")

    p = sub.add_parser("apply", help="применить правки и проверить результат")
    p.add_argument("path")
    p.add_argument("patch")
    p.add_argument("--out", default=None)

    args = parser.parse_args(argv)

    if args.command == "template":
        document = build_template(args.path, limit=args.limit)
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with io.open(args.out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(document, ensure_ascii=False, indent=1))
        print("Строк в бланке: %d -> %s" % (len(document["items"]), args.out))
        print("Заполняй поля new или split, или skip с причиной.")
        return 0

    story = rw.load(args.path)
    document = None
    if os.path.exists(args.patch):
        with io.open(args.patch, encoding="utf-8") as fh:
            raw = fh.read()
        try:
            document = json.loads(raw)
        except ValueError as exc:
            # A model that writes `«текст»` without quotes, or a trailing comma, is the normal
            # failure here; the position is what tells it where to look.
            line = getattr(exc, "lineno", 0)
            column = getattr(exc, "colno", 0)
            print("Ответ не является JSON: %s" % exc)
            if line:
                rows = raw.splitlines()
                if 0 < line <= len(rows):
                    print("строка %d: %s" % (line, rows[line - 1][:160]))
                    print("         %s^" % (" " * max(0, column - 1)))
            print("Все значения — в двойных кавычках, кавычки внутри текста — «ёлочки», "
                  "запятая в конце не ставится.")
            return 1
    else:
        print("Файла правок нет: %s" % args.patch)
        return 1
    try:
        operations = parse_patch(document, story)
    except Refused as exc:
        print("Правки не приняты: %s" % exc)
        print("Бланк: python3 tools/ru_patch.py template %s --out <файл>.json" % args.path)
        return 1

    real = [o for o in operations if o["kind"] != "skip"]
    print("Правок: %d, пропущено строк: %d" % (len(real), len(operations) - len(real)))

    if args.command == "check":
        for op in operations:
            if op["kind"] == "skip":
                print("  пропуск %s: %s" % (op["id"], op["why"]))
            else:
                print("  %s %s: %s" % (op["kind"], op["id"], op["why"] or "—"))
        try:
            apply_text(args.path, operations)
        except Refused as exc:
            print("Правки не применятся: %s" % exc)
            return 1
        print("Синтаксис разбирается, ids совпадают. Проверено без записи.")
        return 0

    out = args.out or (os.path.splitext(args.path)[0] + ".fixed"
                       + os.path.splitext(args.path)[1])
    try:
        text = apply_text(args.path, operations)
    except Refused as exc:
        print("Правки не применены: %s" % exc)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    problems, before, after = guard(args.path, out)
    if problems:
        os.remove(out)
        print("Запись отменена, файл не тронут:")
        for problem in problems:
            print(" - %s" % problem)
        return 1
    _, findings_before = ru_qa.review(args.path)
    _, findings_after = ru_qa.review(out)
    print("Записано: %s" % out)
    print("Строк: %d → %d, символов текста: %d → %d"
          % (len(before["units"]), len(after["units"]), text_volume(before), text_volume(after)))
    print("Находок: %d → %d (%s)"
          % (len(findings_before), len(findings_after),
             ", ".join("%s %d→%d" % (level, ru_qa.counts(findings_before).get(level, 0),
                                    ru_qa.counts(findings_after).get(level, 0))
                       for level in ("ERROR", "WARN", "INFO"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
