#!/usr/bin/env python3
"""The bus a language-review agent drives, one short command at a time.

The controller is a small Russian-speaking model, so it never reads a 38 000-character file and
never invents a file format. It runs four commands, and every command prints the next thing to
do:

    python3 tools/ru_qa_bus.py status sao
    python3 tools/ru_qa_bus.py next sao
    python3 tools/ru_qa_bus.py verdict sao sao-01 --file /tmp/answer.json
    python3 tools/ru_qa_bus.py finish sao

`scan` is the only command a human runs, once, when a new story appears. Everything else is the
controller's loop: take a packet, answer it, take the next. The verdict is validated against
the packet, so a malformed answer is refused with a message that names the exact ids to fix
instead of silently entering the report.

Files under `agent_bus/qa_lang/`:

    packets/<tag>/<packet>.txt          what to read
    packets/<tag>/<packet>.json         the empty answer sheet, with every id pre-filled
    verdicts/<packet>.json              the controller's answer, written here
    report.md / report.json             the finished review
    inbox.jsonl / outbox.jsonl          the messages of this bus
"""

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ru_qa  # noqa: E402

BUS = os.path.join(ROOT, "agent_bus", "qa_lang")
PACKETS = os.path.join(BUS, "packets")
VERDICTS = os.path.join(BUS, "verdicts")
TASKS = os.path.join(BUS, "tasks.json")
QUESTIONS = ru_qa.QUESTIONS


def _read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1))
    return path


def _text(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(data)
    return path


def tasks():
    return _read_json(TASKS, {"tasks": {}})


def _save_tasks(data):
    return _write_json(TASKS, data)


def _task(tag):
    return tasks()["tasks"].get(tag)


def _set_task(tag, **kw):
    data = tasks()
    entry = data["tasks"].setdefault(tag, {})
    entry.update(kw)
    _save_tasks(data)
    return entry


def _packet_ids(tag):
    entry = _task(tag)
    if not entry:
        return []
    return list(entry.get("packets") or [])


def _load_packet(tag, packet_id):
    """The answer sheet the controller fills in."""
    return _read_json(os.path.join(PACKETS, tag, packet_id + ".json"))


def _built_packets(tag):
    """The real packets, rebuilt from the story.

    The sheet on disk carries ids and empty fields, which is what the model should see. The
    verdict is checked against the packets as they were built, because those carry the text each
    id refers to.
    """
    entry = _task(tag)
    story, findings = ru_qa.review(entry["story"])
    packets = ru_qa.build_packets(story, findings, size=entry.get("size") or 8)
    for number, packet in enumerate(packets, 1):
        packet["id"] = entry["packets"][number - 1]
    return story, findings, packets


def _built_packet(tag, packet_id):
    _, _, packets = _built_packets(tag)
    for packet in packets:
        if packet["id"] == packet_id:
            return packet
    return None


def _verdict_path(packet_id):
    return os.path.join(VERDICTS, packet_id + ".json")


# --------------------------------------------------------------------- commands

def cmd_scan(args):
    """Prepare one story for review. A human runs this once per new story file."""
    tag = args.tag
    story, findings = ru_qa.review(args.path, engine_checks=not args.no_engine)
    packets = ru_qa.build_packets(story, findings, size=args.size)
    folder = os.path.join(PACKETS, tag)
    os.makedirs(folder, exist_ok=True)
    ids = []
    for number, packet in enumerate(packets, 1):
        packet["id"] = "%s-%02d" % (tag, number)
        ids.append(packet["id"])
        _write_json(os.path.join(folder, packet["id"] + ".json"),
                    ru_qa.verdict_document(packet))
        _text(os.path.join(folder, packet["id"] + ".txt"), ru_qa.packet_text([packet], story))
    os.makedirs(VERDICTS, exist_ok=True)
    for packet_id in ids:
        path = _verdict_path(packet_id)
        if not os.path.exists(path):
            _write_json(path, _load_packet(tag, packet_id))
    _set_task(tag, story=story["path"], name=story.name, packets=ids, size=args.size,
              findings=ru_qa.counts(findings), questions=list(QUESTIONS), done=[])
    print("Сюжет: %s" % story["path"])
    print("Строк: %d, пакетов: %d, машинных находок: %d"
          % (len(story["units"]), len(ids), len(findings)))
    print("Дальше: python3 tools/ru_qa_bus.py next %s" % tag)
    return 0


def cmd_status(args):
    entry = _task(args.tag)
    if not entry:
        print("Неизвестная задача «%s». Список: %s" % (args.tag, ", ".join(tasks()["tasks"]) or "—"))
        print("Создать: python3 tools/ru_qa_bus.py scan <файл> --tag %s" % args.tag)
        return 1
    done = list(entry.get("done") or [])
    print("Сюжет: %s (%s)" % (entry["name"], entry["story"]))
    print("Машинные находки: %s" % entry.get("findings"))
    print("Пакетов: %d, отвечено: %d" % (len(entry["packets"]), len(done)))
    for packet_id in entry["packets"]:
        mark = "готово" if packet_id in done else "ждёт"
        print("  %s  %s" % (packet_id, mark))
    remaining = [p for p in entry["packets"] if p not in done]
    if remaining:
        print("Дальше: python3 tools/ru_qa_bus.py next %s" % args.tag)
    else:
        print("Дальше: python3 tools/ru_qa_bus.py finish %s" % args.tag)
    return 0


def cmd_next(args):
    entry = _task(args.tag)
    if not entry:
        print("Задача «%s» не найдена." % args.tag)
        return 1
    done = list(entry.get("done") or [])
    for packet_id in entry["packets"]:
        if packet_id in done:
            continue
        text_path = os.path.join(PACKETS, args.tag, packet_id + ".txt")
        with io.open(text_path, encoding="utf-8") as fh:
            text = fh.read()
        print(text)
        print("=" * 60)
        print("Ответь на каждый пункт: meaning, link, facts, voice, grammar = ok | bad | unsure.")
        print("Вопросы: " + " / ".join(QUESTIONS))
        print("Готово? Скопируй и заполни: %s"
              % os.path.join(PACKETS, args.tag, packet_id + ".json"))
        print("Затем: python3 tools/ru_qa_bus.py verdict %s %s --file <твой файл.json>"
              % (args.tag, packet_id))
        return 0
    print("Все пакеты отвечены. Дальше: python3 tools/ru_qa_bus.py finish %s" % args.tag)
    return 0


def cmd_verdict(args):
    entry = _task(args.tag)
    if not entry:
        print("Задача «%s» не найдена." % args.tag)
        return 1
    packet = _built_packet(args.tag, args.packet)
    if packet is None:
        print("Пакет %s не найден в %s" % (args.packet, os.path.join(PACKETS, args.tag)))
        return 1
    document = _read_json(args.file)
    if document is None:
        print("Не читается %s" % args.file)
        print("Шаблон: %s" % os.path.join(PACKETS, args.tag, args.packet + ".json"))
        return 1
    # A controller that answered nothing but pasted the sheet is not a review: an untouched sheet
    # is refused the same way a missing answer is.
    if ru_qa.is_untouched(document):
        print("Ответ не принят: в бланке нет ни одного ответа, все поля остались ok.")
        print("Проверь, что файл заполнен, и повтори.")
        return 1
    try:
        rows = ru_qa.normalize_verdict(document, packet)
    except ValueError as exc:
        print("Ответ не принят: %s" % exc)
        print("Исправь и повтори. Шаблон: %s"
              % os.path.join(PACKETS, args.tag, args.packet + ".json"))
        return 1
    _write_json(_verdict_path(args.packet), document)
    done = list(entry.get("done") or [])
    if args.packet not in done:
        done.append(args.packet)
    _set_task(args.tag, done=done)
    bad = [r for r in rows if r["verdict"] == "bad"]
    unsure = [r for r in rows if r["verdict"] == "unsure"]
    print("Принято: %d строк, плохих %d, спорных %d" % (len(rows), len(bad), len(unsure)))
    for row in bad + unsure:
        print("  %s %s %s" % (row["id"], row["verdict"], row.get("note") or ""))
    remaining = [p for p in entry["packets"] if p not in done]
    if remaining:
        print("Дальше: python3 tools/ru_qa_bus.py next %s" % args.tag)
    else:
        print("Дальше: python3 tools/ru_qa_bus.py finish %s" % args.tag)
    return 0


def cmd_finish(args):
    entry = _task(args.tag)
    if not entry:
        print("Задача «%s» не найдена." % args.tag)
        return 1
    story, findings, packets = _built_packets(args.tag)
    rows, problems = [], []
    for packet in packets:
        document = _read_json(_verdict_path(packet["id"]))
        if document is None:
            problems.append("нет ответа: %s" % packet["id"])
            continue
        if ru_qa.is_untouched(document):
            problems.append("ответ не заполнен: %s" % packet["id"])
            continue
        try:
            rows += ru_qa.normalize_verdict(document, packet)
        except ValueError as exc:
            problems.append("%s: %s" % (packet["id"], exc))
    report = ru_qa.report_text(story, findings, verdicts=rows, limit=10 ** 6)
    _text(os.path.join(BUS, "report.md"), report)
    _write_json(os.path.join(BUS, "report.json"),
                {"story": story["path"], "tag": args.tag, "findings": list(findings),
                 "verdicts": rows, "problems": problems})
    print(report)
    for problem in problems:
        print("!! %s" % problem)
    _post(args.tag, "report", "Отчёт по «%s»: машинных находок %d, строк с вердиктом «плохо»: %d"
          % (story.name, len(findings), sum(1 for r in rows if r["verdict"] == "bad")))
    print("Отчёт: agent_bus/qa_lang/report.md")
    return 1 if problems else 0


def _post(tag, kind, text):
    path = os.path.join(BUS, "outbox.jsonl")
    os.makedirs(BUS, exist_ok=True)
    message = {"id": "qa-%s-%s" % (tag, kind), "from": "qa_lang_bus", "to": "main",
               "type": kind, "task": "text_review:%s" % tag, "payload": {"message": text},
               "created_at": _now()}
    with io.open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(message, ensure_ascii=False) + "\n")
    return message


def _now():
    import datetime
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Шина проверки русского текста")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="подготовить пакеты для нового сюжета (делает человек)")
    p.add_argument("path")
    p.add_argument("--tag", required=True)
    p.add_argument("--size", type=int, default=8)
    p.add_argument("--no-engine", action="store_true")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("status", help="сколько пакетов готово")
    p.add_argument("tag")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("next", help="показать следующий пакет")
    p.add_argument("tag")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("verdict", help="записать ответ на пакет")
    p.add_argument("tag")
    p.add_argument("packet")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_verdict)

    p = sub.add_parser("finish", help="собрать итоговый отчёт")
    p.add_argument("tag")
    p.set_defaults(func=cmd_finish)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
