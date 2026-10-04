# Overnight Report

Date: 2026-10-04. Status: **partial**. Work was done by the main agent alone (no subagents were run:
RAM is 960 MB, and the UI/ASSET subagents of the earlier pass had failed on rate limits).
The earlier version of this report named files that do not exist (`game/screens.py`, `game/script.py`);
it is replaced by this one.

## Start snapshot
Repo 112M (113M at the end), game/absorbed 30M (85 png, 17 json), game/cache 740K, WIP_baking 5.3M,
no dist/. .rpyc 11, .pyc 33, qa_lang files 11, png 176, character.json 17. Disk 3.8G free, RAM 960M
total (about 600-670M used; peak not measured beyond `free` samples).

## Fixed / added (commits 79a4fd0, 0c056e5)
- Untracked build artefacts that were committed (.rpyc, .rpyb, __pycache__, saves, log/traceback/errors.txt).
  Files stay on disk; they were already in .gitignore.
- LVN-008: `game/story_external.py` (validating loader) + `engine.story_start_external`, mode `external`,
  labels `story_external_start/finished` in `story_chapter.rpy`, main-menu buttons for stories found on disk.
  Plays `data/story_pines.json` and `data/story_sao.json` through the normal buffer. Missing file -> False and the
  written chapter; bad JSON -> None; bad steps skipped and listed in `issues`. Nothing is queued past a choice.
- TTS race: `_PENDING_VOICE` is now a locked queue (max 3) with an in-flight counter; the poll timer is one-shot
  and re-arms itself only while work is pending (previously one repeating timer per line, never stopped).
- Live2D outfit: `live2d_pack.resolve_outfit` + `used_nonexclusive`; an outfit not owned by the pack is ignored
  (never borrowed). Removed dead `outfit` branch in `expression_for`.
- Missing background: a labelled dark panel instead of an empty screen or the unrelated `bg_demo.png`.
- Flaky `smoke_test_cannibalism` assertion (depended on filesystem scan order) fixed.
- `tools/audit_stories.py`: compact reference audit of the ready-made stories.

## Tests (all run, PASS)
validate_project, smoke_test_logic, smoke_test_assets (+outfit resolution), smoke_test_cannibalism,
smoke_test_story_parser (70/70), smoke_test_story_flow (+TTS queue, external stories pines/sao to the end,
missing file, bad JSON, bad steps, bg placeholder), smoke_test_layout, ru_qa_smoke.
Not run: smoke_test_importer (SKIP, ImageMagick missing).

## NOT verified
- **Ren'Py lint and any real launch**: no Ren'Py SDK in this environment (`~/.local/share/renpy` absent). The new
  `.rpy` code (labels in story_chapter.rpy, menu loop in screens.rpy) is validated only by validate_project.
  `used_nonexclusive` is a Live2D argument I could not confirm against the 8.3.7 source here.
- Full play-through (menu -> new game -> TTS -> save/load -> asset inspector -> export/import) needs a display.
- Live2D rendering, Cubism models (Asuna is Cubism 2, not displayable).

## Findings (not fixed)
- Pines and SAO reference backgrounds that have no image in this checkout (8 and 7 ids); they will show the
  labelled placeholder. Pines has no choices at all (0); SAO has 6, all on a linear path (effects set flags only).
- `game/data/story_example.json` is in another format and is not loadable by the new loader.
- Not done: WIP_baking for the 8 SAO characters (needs ImageMagick for offset measurement), UI pass at
  1280/1920/2560 (only the layout smoke test ran), story-quality critique/rewrite, bundle check chain
  (schema -> outfit -> repetition -> choice -> language) beyond what story_pipeline already does,
  compact per-scene prompt context, character inventory table.
- Per-character outfit/pose lists are not yet injected into the AI prompt in a compact form.

## Cleanup / resources
Nothing deleted from disk; derived files were only untracked. No dist/ built, no copies, no RPA unpacked.
