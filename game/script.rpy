label start:
    if not persistent.vn_player_name:
        $ persistent.vn_player_name = renpy.call_screen("player_name_input")
    jump creator

label creator:
    call screen creator
    return

label play:
    ## One notice, not one per turn: the endpoint being off has to be visible once.
    python:
        try:
            _ai_error = str(game_state.get("ai_error") or "")
        except Exception:
            _ai_error = ""
        if _ai_error and not persistent.ai_notice_shown:
            persistent.ai_notice_shown = True
            renpy.notify("ИИ недоступен: " + _ai_error[:80])

    while True:
        $ step = next_step()
        $ apply_visuals(step)

        if step.get("type") in ["dialogue", "narration"]:
            if step.get("speaker"):
                $ _who = next((c.get("name") for c in game_state.get("characters", []) if c.get("id") == step.get("speaker")), step.get("speaker"))
                $ _char = Character(_who)
                $ renpy.say(_char, step.get("text", ""))
            else:
                $ renpy.say(None, step.get("text", ""))
            $ consume_dialogue(step)

        elif step.get("type") == "choice":
            $ _choice = renpy.call_screen("dynamic_choices", step.get("choices", []))
            if _choice == "__FREE__":
                $ _free = renpy.input("Скажи своими словами:", length=500).strip()
                $ free_response(_free)
            else:
                $ apply_choice(step, _choice)

        elif step.get("type") == "music":
            $ apply_visuals(step)

        else:
            $ _apply_patch = step.get("state_patch", {})
            $ _apply_patch and apply_choice(step, "__none__")
            $ renpy.pause(float(step.get("seconds", 0.5)))
