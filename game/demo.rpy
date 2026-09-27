## The opening scene: Asuna at the camp gate, and a playable demo that needs no AI.
##
## The story engine writes scenes from a world, which needs an AI endpoint. Until one is
## configured, the game still has to show something real, so this opening runs on the
## imported art. It is also the asset test for the layered pack: Asuna's eyes and mouth
## are separate files drawn over her body, so every step here changes her expression.

define demo_steps = [
    {
        "characters": [{"id": "asuna", "position": "center", "emotion": "neutral"}],
        "text": "Лето. Ворота лагеря. Ты всё-таки доехал.",
    },
    {
        "characters": [{"id": "asuna", "position": "center", "emotion": "happy"}],
        "text": "Асуна: «Я не знала, что ты правда приедешь!»",
        "who": "Асуна",
    },
    {
        "characters": [{"id": "asuna", "position": "center", "emotion": "surprised"}],
        "text": "Асуна: «Стоп. У меня растрёпаны волосы, да?..»",
        "who": "Асуна",
    },
    {
        "characters": [{"id": "asuna", "position": "center", "emotion": "sad"}],
        "text": "Асуна: «Здесь всегда так. Сначала кажется весело.»",
        "who": "Асуна",
    },
    {
        "characters": [{"id": "asuna", "position": "center", "emotion": "smile"}],
        "text": "Асуна: «Заходи. Расскажу, что тут вообще происходит.»",
        "who": "Асуна",
    },
]


## Draw one step and speak its line. Kept in one place so the demo and the real engine
## show art the same way.
label demo_step(step):
    if step.get("background"):
        $ apply_visuals({"background": step["background"], "characters": step.get("characters") or []})
    elif step.get("characters"):
        $ apply_visuals({"characters": step["characters"]})

    $ renpy.say(step.get("who"), step["text"])
    return


label demo_start:
    $ apply_visuals({"background": "ext_camp_entrance_day"})
    scene

    ## Ren'Py has no `for` statement, so the step list is walked with an index.
    $ demo_index = 0
    while demo_index < len(demo_steps):
        call demo_step(demo_steps[demo_index])
        $ demo_index += 1

    ## A `menu` builds the caption/action objects the choice screen expects; a raw list of
    ## tuples raises `'tuple' object has no attribute 'caption'`.
    menu:
        "Ещё раз":
            jump demo_start
        "В главное меню":
            $ renpy.full_restart()

    return


## An expression sheet for the layered pack.
##
## The emotions are the whole point of a layered character: the body never changes and only
## the eyes and the mouth do. Showing every one of them side by side in text is the only
## way to tell a wrong offset or a missing frame from a wrong look, which is why the
## caption names the frame that was picked for each part.
define demo_expressions = ["neutral", "smile", "happy", "laugh", "surprised",
                           "sad", "closed", "think", "shy"]


label demo_expression_sheet:
    $ apply_visuals({"background": "ext_camp_entrance_day", "characters": []})

    python:
        import json, os
        _path = os.path.join(config.gamedir, "absorbed", "SAO", "character_art",
                             "asuna", "character.json")
        with open(_path, encoding="utf-8") as _fh:
            demo_expression_table = json.load(_fh).get("expressions", {})

    $ demo_shown = []
    $ demo_index = 0
    while demo_index < len(demo_expressions):
        python:
            _emotion = demo_expressions[demo_index]
            _parts = demo_expression_table.get(_emotion, {})
            demo_shown.append("%s — глаза: %s, рот: %s" % (
                _emotion, _parts.get("eyes", "?"), _parts.get("mouth", "?")))
            apply_visuals({"characters": [{"id": "asuna", "position": "center",
                                           "emotion": _emotion}]})
        $ renpy.say(None, demo_shown[-1])
        $ demo_index += 1

    $ renpy.say(None, "Девять выражений: тело одно, меняются только глаза и рот.")
    return
