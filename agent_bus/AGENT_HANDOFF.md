# Living VN — agent handoff

You are a coding agent continuing an existing MVP. Do not redesign the whole project.

1. Read `README.md`, `DESIGN_NOTES.md`, `WORLD_SCHEMA.md`, `ASSET_PACK_SCHEMA.md`.
2. Read `agent_bus/STATE.json` and `agent_bus/QUEUE.jsonl`.
3. Work through the queue by priority. Mark finished tasks in `STATE.json`.
4. Keep the project on **Ren'Py 8.3.7** unless compatibility research proves a better portable baseline.
5. Never make AI/TTS/Live2D mandatory. A missing provider must return a playable fallback scene.
6. Keep generated story data JSON-only and validated before execution.
7. Never expose API keys in world exports by default.
8. Do not execute arbitrary model-generated Python, shell commands, or filesystem writes.
9. Prefer stdlib and existing Ren'Py APIs. Avoid heavyweight dependencies in the runtime.
10. Run `python tools/validate_project.py` after each meaningful change.
11. For the AI Cannibalism feature, only process directly accessible folders/ordinary ZIPs; never add DRM bypass, decryption, arbitrary code execution, or compiled-save importing.
12. Imported third-party assets default to `redistributable=false` and must remain excluded from portable world exports.

## Fastest useful continuation order

- Character/asset pack importer → Live2D mapping → music AI analysis cache → async/prefetch → lint/smoke test → UI polish.

## Definition of done

The player can create a world from brief/import/random, see a normal VN, choose options or type a free response at selected checkpoints, hear optional TTS, hear contextual music, edit lore, save/load, export/import a world, and survive API/TTS/Live2D failures without crashing.
