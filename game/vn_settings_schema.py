"""The settings the project declares, and how they survive an old save.

`persistent` is stored in a save file, so a key added in a later version is simply
absent from a save written by an earlier version. Ren'Py's `default` statement does
not help here: it only applies while the variable is undefined, and
`persistent.vn_settings` is always defined once it has been saved. A settings screen
that asks for such a key raises `The 'x' field does not exist` and stops the game.

So this module is the single source of truth: the `default` statement copies
`DEFAULTS`, and `merge_into_persistent` fills in whatever an existing save is missing
without touching values the player has already changed.

Ren'Py reads a screen `input` through `FieldInputValue`, and its `_get_field` walks the
name with `getattr` only. Handing it a dict therefore fails for every key, not only for
missing ones, because a dict exposes no attributes. `view` below is an attribute window
onto the same dict, so the screen can bind inputs normally while the dict stays the one
source of truth that is saved and merged.
"""

DEFAULTS = {
    # The DeepSeek proxy from ForgetMeAI is OpenAI-compatible, needs no key and is the
    # default because it is already running locally on this machine.
    "api_url": "http://127.0.0.1:9655/v1/chat/completions",
    "api_key": "",
    "model": "deepseek-chat",
    "quality_model": "deepseek-reasoner",
    "absorber_model": "",
    "temperature": 0.85,
    "timeout": 120,
    "bundle_size": 8,
    "max_history": 18,
    "free_input": True,
    "supervisor": True,
    "supervisor_threshold": 7.0,
    "tts_enabled": True,
    "tts_url": "http://127.0.0.1:8009/tts",
    "tts_speaker": "baya",
    "tts_sample_rate": 48000,
    "music_enabled": True,
    "music_volume": 0.70,
    "voice_volume": 0.95,
    "low_spec": False,
    "live2d_enabled": True,
    "save_ai_transcript": True,
    "export_api_key": False,
    "auto_music_scan": True,
    "music_ai_analysis": True,
    "json_mode": True,
    "asset_roots": "",
}


def merge_into_persistent():
    """Add any declared key the stored settings lack. Returns the added key names."""
    from renpy.store import persistent

    stored = getattr(persistent, "vn_settings", None)
    if not isinstance(stored, dict):
        # Corrupt or hand-edited persistent: fall back to the declared values.
        persistent.vn_settings = dict(DEFAULTS)
        return sorted(DEFAULTS)
    added = []
    for key, value in DEFAULTS.items():
        if key not in stored:
            stored[key] = value
            added.append(key)
    return added


def storage():
    """The live settings dict, replacing a corrupt one instead of failing."""
    from renpy.store import persistent

    stored = getattr(persistent, "vn_settings", None)
    if not isinstance(stored, dict):
        stored = dict(DEFAULTS)
        persistent.vn_settings = stored
    return stored


class SettingsView:
    """Attribute view over the settings dict, resolved on every access.

    The dict is looked up each time instead of cached, so the view keeps working
    after the persistent file is reloaded or replaced.
    """

    def __getattr__(self, name):
        try:
            return storage()[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        storage()[name] = value

    def __contains__(self, name):
        return name in storage()

    def get(self, name, fallback=None):
        return storage().get(name, fallback)


view = SettingsView()
