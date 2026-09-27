# Build status

## Verified in this environment

- Python syntax checks for `game/*.py`.
- JSON parsing for story data.
- WAV files open as valid RIFF/WAVE files through the project validator.
- Pure-logic smoke test for world generation helpers and music catalog selection.
- Project structure and Ren'Py source brace sanity checks.
- **Ren'Py 8.3.7.25031702 lint is clean**: `0 menus, 0 images, 5 screens`. The SDK is unpacked at `/tmp/opencode/renpy/renpy-8.3.7-sdk` and the project is linted with
  `cd /tmp/opencode/renpy/renpy-8.3.7-sdk && ./renpy.sh /home/alexius/Downloads/LivingVN_MVP lint`.
  The SDK lives in a temporary directory, so it is not part of the archive; reinstall it before re-running lint.
- Asset manager smoke test: catalog discovery, manifest reading, emotion fallback chain, world binding, refusal to bind an external folder, corrupt-manifest tolerance.
- Live2D pack loader smoke test: Ren'Py-compatible motion/expression naming, unresolved outfit reporting, and `None` (sprite fallback) on a platform without Cubism.

## Not executable in this environment

The project is linted but has **not** been launched as a game here. There is no display: the `SDL_VIDEODRIVER=dummy` route fails Ren'Py's GL test with `error: Invalid window`, and `Xvfb` / `xvfb-run` are not installed. A real boot test still needs a user session or a virtual X server, so the archive should be treated as an MVP source project, not as a claimed prebuilt executable.

## Target

Use Ren'Py 8.3.7 for this branch. The project intentionally uses optional Live2D/TTS/LLM integrations with sprite/offline fallbacks.

## Cannibalism feature verification

- Folder, ordinary ZIP, and standard `.rpa` container source scanning passes.
- Candidate classification passes for character art, backgrounds, music, audio, readable script text and Live2D Cubism files.
- MMD models (`.pmx`, `.pmd`, `.vmd`, `.vpd`) are classified as `other_model` and Live2D **Cubism 2** models (`.moc`, `.model.json`, `.mtn`) as `live2d2`. Both are catalogued and never copied into the game, because Ren'Py 8.x can display neither.
- Interface and engine art (`gui/`, `renpy/`) is classified as `gui_art` and scene/cutscene art (`images/cg/`, `images/misc/`) as `scene_art`; neither becomes a character.
- Character art is grouped into one folder per character with its own `character.json`; a folder needs at least four of its own states to become a character, and a scene folder inside a character folder folds back into that character.
- Vendored `unrpa` 2.3.0 (GPL-3.0, commit `005b10abec590db374f23fd8d4b111963792a15a`) is the fallback reader for `.rpi`, RPA-3.2, RPA-4.0, `zix` and `alt`; the built-in reader stays first and unknown containers are still refused.
- A non-standard or protected container is refused with an `archive_refused:` warning and is not unpacked.
- Absorber output is isolated from source story state.
- Selected assets copy into `game/absorbed/<pack>/` with `third_party=true` and `redistributable=false`, byte-exact, including entries read out of an archive, with no overwrite when two entries share a base name.
- Imported character profiles can be attached to the current world.
- Imported character visual asset paths are resolved to copied assets.
- Absorbed music is visible to the packaged music catalog scanner.
- Dedicated `tools/smoke_test_cannibalism.py` passes.

## Field test on real Ren'Py installations

Read-only scan, no files copied into the game:

| source | before `.rpa` support | after | archives read |
| --- | --- | --- | --- |
| Everlasting Summer | 236 files / 2.1 MB | 2142 files / 717.0 MB (821 character art, 421 scene art, 348 gui art, 296 audio, 115 backgrounds, 77 music, 64 text) | `game/archive.rpa`, 1906 entries |
| Doki Doki Literature Club | 59 files / 0.8 MB | 581 files / 194.7 MB (231 character art, 72 scene art, 117 gui art, 60 backgrounds, 39 music, 26 audio, 55 text) | `images.rpa` 455, `audio.rpa` 64, `scripts.rpa` 42, `fonts.rpa` 12 |
| Asuna models (own) | 3659 files / 44.5 MB | unchanged — no `.rpa` | none |

The Asuna model folder contains **Live2D Cubism 2** models: `.moc` (the `moc\x0a` magic), `.model.json`, `.physics.json`, `.exp.json` and motion files `.mtn` (which start with `# Live2D Animator Motion Data`). There is no `.model3.json` anywhere under `Asuna_Ai_Assistant`. Ren'Py 8.3.7 only loads **Cubism 4** (`.model3.json` + `.moc3`), so these models cannot be displayed as models here; the 225 PNG textures are the usable part. Converting Cubism 2 to Cubism 4 is a separate pipeline and is not part of this MVP.

## Real absorb run

| pack | scanned | copied | size | character packs |
| --- | --- | --- | --- | --- |
| `Everlasting_Summer` | 2142 files | 1434 | 556.7 MB | 12 (`cs dv el mi mt mz pi sh sl un us uv`) |
| `Doki_Doki_Literature_Club` | 581 files | 383 | 163.7 MB | 5 (`monika natsuki sayori yuri poem_special`) |

Copy scope for that run: character art, scene art, backgrounds and music. Voice/audio and text were catalogued in the manifest but not copied, and no model format Ren'Py cannot display was copied. `poem_special` is DDLC's poem minigame art, not a person: the folder holds 15 of its own images and nothing generic in a path identifies it as interface art, so the manifest reports it as a candidate rather than guessing.

Verification: every copied archive entry was re-read from the source and compared byte for byte — **1817 entries byte-exact, 0 missing, 0 size mismatches, 0 byte mismatches**, plus one `character.json` per pack with all state files present. The resulting asset catalog reports **17 characters, 1724 states, 157 backgrounds, `broken: 0`**, all 17 flagged `third_party=true` / `redistributable=false`. The four `missing_directory` issues are the not-yet-created skeleton roots (`game/characters`, `game/locations`, `game/live2d`, `game/assets`).

## 2026-09-27 — GUI, settings and the layered sprite format

* The interface is now the stock Ren'Py 8.3.7 project: `game/gui.rpy`, `game/screens.rpy`
  and the 42 images of `game/gui/`, so save, load, preferences, history and the game menu
  behave the way the engine documents. `game/vn_styles.rpy` only changes the look: a
  236px textbox, a name plate on its edge, a blinking continuation marker, and a quick
  menu that rides the box instead of being a global overlay.
* Russian text uses bundled Noto Sans in `game/fonts` (OFL 1.1). The stock interface
  strings are Russian too; the game shipped a half-English menu before.
* Settings: the crash was `FieldInputValue` on a dict. Ren'Py reads a field with
  `getattr`, so a dict never had the key, on a fresh or a stale save.
  `game/vn_settings_schema.py` now exposes an attribute view over the same dict.
  The screen is rebuilt around six tabs; the AI tab has named profiles, a model list read
  from the live server, a connection test, and sliders for the generation parameters.
* Default provider is the local DeepSeek proxy: `http://127.0.0.1:9655/v1/chat/completions`,
  model `deepseek-chat`, 120s timeout, no key. Vision and `response_format` both work
  against it; its image descriptions are not reliable, which matters for any future
  asset-tagging feature.
* Asuna imported from the Sword Art Online portrait set: 13 full-height `out` bodies plus
  strips of 22 eye frames and 22 mouth frames. Expressions are **baked at import time**:
  the importer composites the chosen eyes and mouth onto the full-height body and writes one
  finished sprite per pose and emotion, which is what the stage draws. Composing the parts
  at runtime is gone from the normal path — see the 2026-09-27 entry below for why.
  Expressions work for the 6 poses of the default outfit; 2 further layer sets are imported
  as plain bodies until their geometry is measured.
* New tools: `tools/import_sprite_pack.py` for finished-sprite packs and
  `tools/import_layered_pack.py` for layered ones, driven by a measured-geometry config
  (`tools/face_sets_asuna.json`).
* `game/demo.rpy` has an Asuna-only demo and expression sheet on the main menu, and the
  default story is the summer camp and Asuna.

Open: which Everlasting Summer pack is Slavya. `sl` reads as her (blonde, pioneer uniform)
and is what the demo uses; `us` is the other candidate (orange hair, CCCP shirt).

## 2026-09-27 — Asuna's face: measured offsets, baked sprites, correct framing

Three separate faults made her look wrong, and only the third was visible on screen.

**1. The offset metric was the wrong one.** Measuring a face layer against the body cannot
work: the layer *replaces* the face under it, so the error is minimised by sliding the layer
onto the cheek rather than onto the eyes, which is how the first hand-measured values
(235,187) ended up wrong. The metric that works scores the **result** — how many pixels of
the body change when the layer is pasted on — because the correct offset is the one where the
hair strands fall on the same hair strands. Measured for the default outfit
(`e1807_mbfa8`): eyes **(251, 203)**, mouth **(336, 329)**; the mouth leaves only 304 changed
pixels, which is the mouth line itself.

The first implementation of that search spawned one ImageMagick process per candidate offset
and needed ~40 minutes for the pack, so it was interrupted. It now ranks candidates with a
big-integer XOR per image row over a raw RGBA dump, then confirms the top three with an exact
`compare -metric AE`: **33 seconds for the whole pack**, and per pose rather than per set.
`--auto-offset` is the default; `--no-auto-offset` trusts the config.

**2. Every emotion drew the same face.** `assets.py` folds a layered pack's pose bodies into
`states` *only when the manifest has no `visual.states` key*, so the baked expressions were
dropped and `state_chain` fell through to the first bare body. The importer now writes the
state map into `visual.states` as well as at the top level, and `tools/smoke_test_assets.py`
pins it: removing that key makes `resolve_state("happy")` return the body again.

**3. The character was drawn half height and cut off at the waist.** `draw_layered` put the
`Fixed` group *inside* a transform and also passed it as `what`, so Ren'Py scaled it twice
(0.663² = 0.44) and positioned the outer box instead of the body. The stage is now verified
in the engine: `at_list = [position, Transform(zoom=…)]` with a plain `Image`, and a pack
with baked sprites never reaches the overlay path at all.

Verified by rendering the real project in Ren'Py and reading the frames back: 9 distinct
expressions, no seams, full-height framing, background and positions intact. Lint clean, all
three smoke suites pass, distributions rebuilt (819M Linux / 805M Windows x86_64).

Still open: two of the three layer sets have no measured geometry, so those 7 poses show a
body without a face; the Cubism 2 models remain unusable in Ren'Py 8; and there is no 32-bit
Windows runtime, so a Windows 7 target would need a Ren'Py 7.x port.
