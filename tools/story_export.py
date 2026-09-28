#!/usr/bin/env python3
"""Turn a story file into one readable page: open it in a browser and read it as a novel.

The story lives in JSON or in Python literals, which is fine for the engine and useless for a
person. This renders the same units in reading order: scene heading, who speaks, the line, the
choice options. No dependency, one self-contained file, and the plain text is in the page too,
so it can be copied into a model as is.

    python3 tools/story_export.py data/story_sao.json
    python3 tools/story_export.py game/story_chapter.py --out /tmp/ch1.html
"""

import argparse
import html
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ru_world as rw  # noqa: E402

PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>%(title)s</title>
<style>
body{background:#14110f;color:#e8e0d6;font:18px/1.65 Georgia,'Times New Roman',serif;
     max-width:46em;margin:0 auto;padding:3em 1.5em}
h1{font-size:1.9em;line-height:1.2;margin:0 0 .2em}
h2{font-size:1.1em;color:#c9a227;margin:2.5em 0 .6em;border-bottom:1px solid #3a332c;
   padding-bottom:.3em;font-family:system-ui,sans-serif}
.meta{color:#9a8f83;font:14px/1.5 system-ui,sans-serif;margin:0 0 2.5em}
.narr{color:#cfc6ba;margin:.9em 0}
.who{color:#8ab4d8;font-family:system-ui,sans-serif;font-size:.85em;letter-spacing:.04em}
.who em{color:#6d6259;font-style:normal}
.line{margin:.2em 0 1.1em}
.id{color:#6a5f55;font:11px/1.4 ui-monospace,Menlo,monospace;letter-spacing:0;
    margin:.1em 0 -.6em}
.choice{border-left:3px solid #c9a227;padding:.4em 0 .4em 1em;margin:1.6em 0;background:#1c1815}
.choice p{margin:.3em 0;color:#c9a227}
.choice ol{margin:.3em 0 0;padding-left:1.4em;color:#cfc6ba}
.brief{white-space:pre-wrap;color:#b6aa9d;font:15px/1.6 system-ui,sans-serif;
       border:1px solid #3a332c;padding:1em 1.2em;margin:0 0 2.5em}
hr{border:0;border-top:1px solid #3a332c;margin:3em 0}
</style></head><body>
%(body)s
</body></html>
"""


def _who(story, unit):
    speaker = unit.get("speaker")
    if not speaker:
        return ""
    cast = story.get("characters") or {}
    name = cast.get(str(speaker))
    if isinstance(name, dict):
        name = name.get("name")
    return str(name or speaker)


def render(story):
    fields = dict(story.get("fields") or [])
    out = []
    add = out.append
    title = fields.get("title") or story.name
    add("<h1>%s</h1>" % html.escape(str(title)))
    add('<p class="meta">%s%s%s</p>' % (
        html.escape(str(fields.get("genre") or "")),
        (" · " + html.escape(str(fields["tone"]))) if fields.get("tone") else "",
        " · " + html.escape(story["path"])))
    for key in ("description", "premise"):
        if fields.get(key):
            add('<div class="brief">%s</div>' % html.escape(str(fields[key])))
    cast = story.get("characters") or {}
    if cast:
        add("<h2>Герои</h2><div class='brief'>")
        for cid, record in cast.items():
            if isinstance(record, dict):
                add("%s — %s%s" % (html.escape(str(record.get("name") or cid)),
                                    html.escape(str(record.get("personality") or "")),
                                    (" " + html.escape(str(record.get("background"))))
                                    if record.get("background") else ""))
            else:
                add(html.escape(str(record)))
        add("</div>")
    scene = None
    for unit in story["units"]:
        if unit.get("scene") and unit["scene"] != scene:
            scene = unit["scene"]
            add("<h2>%s</h2>" % html.escape(str(scene)))
        # The address is printed on purpose: a reviewer quotes it in the fix list, and a made-up
        # address is rejected by the tool before anything is written.
        add('<div class="id" data-id="%s">%s</div>'
            % (html.escape(unit["uid"]), html.escape(unit["uid"])))
        text = (unit.get("text") or "").strip()
        if unit["kind"] == "option" or (unit["kind"] == "choice" and False):
            continue
        if unit["kind"] == "choice":
            add('<div class="choice">')
            if text:
                add("<p>%s</p>" % html.escape(text))
            add("<ol>")
            for choice in unit.get("choices") or []:
                add("<li>%s</li>" % html.escape(str(choice.get("text") or "")))
            add("</ol></div>")
            continue
        if not text:
            continue
        if unit["kind"] == "dialogue":
            emotion = unit.get("emotion")
            add('<div class="who">%s<em>%s</em></div>'
                % (html.escape(_who(story, unit)),
                   (" · " + html.escape(str(emotion))) if emotion else ""))
            add('<div class="line">%s</div>' % html.escape(text))
        else:
            add('<p class="narr">%s</p>' % html.escape(text))
    add("<hr><p class='meta'>%d строк сюжета. Адрес строки — то, что нужно писать в "
        "правках: <code>python3 tools/ru_patch.py template %s --out правки.json</code>.</p>"
        % (len(story["units"]), html.escape(story["path"])))
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Сюжет в читаемый HTML")
    parser.add_argument("path")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    story = rw.load(args.path)
    title = dict(story.get("fields") or []).get("title") or story.name
    out = args.out or os.path.splitext(args.path)[0] + ".html"
    page = PAGE % {"title": html.escape(str(title)), "body": render(story)}
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("%s: %d строк, %d КБ -> %s"
          % (story["path"], len(story["units"]), len(page) // 1024, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
