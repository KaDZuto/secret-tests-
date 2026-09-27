init python:
    from engine import *

    def make_save_json(d):
        d["living_vn"] = {
            "world_title": game_state.get("title", ""),
            "turn": game_state.get("turn", 0),
            "location": game_state.get("location", ""),
            "memory_summary": game_state.get("memory_summary", "")[:1200],
        }

    config.save_json_callbacks.append(make_save_json)
