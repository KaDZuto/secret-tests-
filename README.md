# Living VN — AI-Driven Visual Novel MVP

Living VN is a Ren'Py 8.3.7 project template for a visual novel whose world and short-term plot can be generated and repaired by an OpenAI-compatible LLM, while the player still experiences a normal visual novel interface.

## Why Ren'Py 8.3.7 for this MVP

The project deliberately targets the 8.3.x generation rather than the current Ren'Py 8.5 line. Ren'Py 8.3 still supports Windows 7/8/8.1, Android, Linux and other targets, while the 8.4 release removed Windows 7 support. The project therefore prioritizes a conservative compatibility baseline. Live2D remains optional and is disabled automatically when unavailable.

## Main MVP features

- Story bootstrap from a short description, imported JSON, or full random generation.
- OpenAI-compatible API settings: URL, model, API key, temperature, timeout, bundle size.
- Generation in **micro-scene bundles** (default 8 beats), not one network call per line.
- Meaningful choices and optional free-form player responses.
- Separate **Plot Supervisor** request that reads recent history + future buffer and can order a repair pass.
- Character state, relationship values, flags, lore and location state.
- Manual Lore/World Codex that can be edited during a run.
- Character sprites with emotion/outfit state metadata.
- Optional Live2D Cubism model support with automatic sprite fallback.
- Background and character positioning.
- Music folder scanning at game creation; optional AI metadata analysis of track names/paths and context-aware selection.
- Optional Silero TTS bridge compatible with the TTS server in the user's Hermes repository.
- Failure-safe fallback story mode when the LLM/TTS server is unavailable.
- JSON export/import of a world state for sharing a personalized experience.
- Low-spec mode that disables expensive optional effects.
- Agent handoff bus in `agent_bus/` so another coding agent can continue development.

## Run

1. Install/download **Ren'Py 8.3.7**.
2. Open the `LivingVN_MVP` project from the Ren'Py launcher.
3. Click **Launch Project**.
4. The demo starts without an API or TTS server.
5. Open **Настройки → ИИ** and enter an OpenAI-compatible endpoint when needed.

For a local OpenAI-compatible server, an example is:

```text
http://127.0.0.1:1234/v1/chat/completions
```

For OpenRouter, use its chat-completions endpoint and a model available to your account.

## Hermes / Silero voice bridge

The MVP defaults to:

```text
http://127.0.0.1:8009/tts
```

This matches the current Hermes TTS server design: `POST /tts`, JSON `{text, speaker, sample_rate, put_accent, put_yo}` and a WAV response.

## Music library workflow

There are two ways to feed music:

1. Put tracks under `game/music/` (portable with the game).
2. In the creator settings, enter one or more desktop folders separated by `;` and click **Сканировать музыку**.

The scanner does not copy tracks. It creates a compact catalog containing filenames, paths, extensions and lightweight heuristics. The AI then receives the catalog and can assign roles such as:

- `calm`
- `romance`
- `nostalgia`
- `tension`
- `mystery`
- `sad`
- `comedy`
- `horror`
- `triumph`

This MVP intentionally avoids requiring a heavy audio-ML stack. A later agent task can add optional sample-based audio understanding for providers that accept audio input.

## Inspiration references

The design notes use the following visual-novel traditions as references, not as content to copy:

- Doki Doki Literature Club — controlled meta-awareness and shifts in presentation.
- Everlasting Summer — atmosphere, time/day structure and soundtrack-led scene changes.
- CLANNAD — character arcs, route structure and emotional pacing.
- STEINS;GATE — causality, foreshadowing and consequence chains.
- The House in Fata Morgana — framing narrative, mystery and atmosphere.
- Katawa Shoujo — character-driven routes and meaningful relationship progression.

See `DESIGN_NOTES.md` for the synthesis.

## Important legal note

Do not ship copyrighted music, Live2D models, sprites, voices or backgrounds from third-party games unless you have redistribution rights. The demo assets in this repository are generated locally for testing.

## Music analysis scope

At startup, the creator can receive one or more desktop music folders. The MVP scans them without copying files and can ask the configured LLM to classify the tracks from filenames/paths. This is deliberately lightweight. It does **not** pretend to hear arbitrary MP3/OGG files. An optional audio-input extension is reserved for providers that explicitly support audio analysis.

## AI Cannibalism / local game absorption

The MVP now includes a separate **AI Cannibalism** mode available from the settings while playing. It can scan a directly accessible game folder, a normal ZIP, or the standard Ren'Py `.rpa` containers inside a folder, and build a candidate catalog of:

- character art / portraits / sprites;
- backgrounds / location art;
- music and audio;
- Live2D Cubism files;
- scene and event art (cutscenes, gallery images) as `scene_art`, kept as art but never as a character;
- interface and engine art (`gui/`, `renpy/`) as `gui_art`: catalogued, never copied;
- MMD models (`.pmx`, `.pmd`, `.vmd`, `.vpd`) as `other_model` and Live2D **Cubism 2** models
  (`.moc` + `.model.json` + `.mtn`) as `live2d2`, because Ren'Py 8.x can display neither of them;
- readable character/lore text (`.rpy`, `.json`, `.txt`, `.csv`, `.yaml`, `.xml`).

`.rpa` support matters more than it sounds: a Ren'Py game normally keeps nearly all of its art and audio inside those containers, so a scanner that only walks loose files finds the engine and nothing else. In a measured test, adding `.rpa` reading took Everlasting Summer from 236 files / 2.1 MB to 2142 files / 717 MB, and DDLC from 59 files / 0.8 MB to 581 files / 195 MB. The reader is read-only and uses the public container format Ren'Py's own loader uses. It prefers the engine's own loader when Ren'Py is importable, then its own reader for the standard `RPA-1.0/2.0/3.0` archives, and only then falls back to **vendored** `unrpa` 2.3.0 (GPL-3.0, `game/vendor/unrpa/`) for the unofficial variants: `.rpi` index files, RPA-3.2, RPA-4.0, `zix` and `alt`. Anything outside all of that — a protected archive, or an unknown container — is reported as refused and never unpacked. Vendoring GPL code is a project decision recorded in `game/vendor/unrpa/README.md`; if the game is ever distributed, GPL-3.0 applies to the distribution as a whole.

The **AI Absorber** is a separate evaluation role. It receives only the catalog and small text samples, decides which resources are useful, and separately proposes character profiles. The source game's plot is not inserted into the current world. The player can optionally add the imported character profiles to the current run.

Character art is grouped into **one folder per character** with its own `character.json`, because that is how a hand-made Ren'Py pack is built and because two characters then cannot be merged by a shared file name. A folder only becomes a character when it holds at least four of its own states, so a container such as `images/sprites/normal/` never becomes a character, and a scene folder inside a character folder (`images/yuri/stab/`) folds back into that character.

Imported binaries are copied into `game/absorbed/<pack>/` and marked `third_party=true` / `redistributable=false`. Normal world export includes only metadata about these packs and does not copy their third-party binaries. This prevents accidentally making a portable package containing third-party assets without the user explicitly taking responsibility for redistribution rights.

This feature is intentionally an asset importer, not a DRM/unpacking tool: it does not decrypt protected archives, bypass access controls, execute files from imported games, or import compiled save state as lore.

## Asset manager

The settings screen has an **Ассеты** tab that scans what is actually on disk and reports it, instead of relying on a hardcoded asset list. It looks at `game/characters`, `game/locations`, `game/live2d`, `game/assets`, `game/absorbed` and `game/images`, reading both the filesystem and the game archive, so it also works in a built `.rpyc`/`.rpa` distribution.

- `characters/<pack>/character.json` is the explicit form; see `ASSET_PACK_SCHEMA.md`. A folder without a manifest is still discovered, and its sprite state keys are guessed from the file names.
- Emotion resolution walks a fallback chain (`happy` → `neutral` → any other state), so a state a manifest promises but that does not exist on disk degrades instead of breaking the scene.
- Folders added in the `asset_roots` field are **inspect-only**: they appear in the report, but their absolute paths are never bound as sprites, because Ren'Py loads through its own search path. A pack outside `game/` is always `third_party` and `redistributable=false`.
- The tab also shows which world characters were bound to a real pack, and a per-model Live2D report.

`game/live2d_pack.py` loads a Cubism model without ever making it mandatory. It reproduces Ren'Py's own motion/expression naming rule (the lower-cased file stem with the model name prefix removed), maps `expressions` / `motions` / `outfits` / `aliases` from the manifest onto real Cubism names, marks outfit expressions non-exclusive so several can blend at once, and returns `None` whenever Cubism is unavailable, the setting is off, or the model cannot be built — the sprite path then runs.

# RenPy_game_generator
