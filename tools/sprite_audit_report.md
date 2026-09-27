# Sprite asset audit — LivingVN_MVP

Read-only audit. No file under `game/` was modified. All numbers come from PNG
headers (bytes 16..24) and ImageMagick 7.1.2-31 pixel statistics.

**Summary:** all 1074 files referenced by the 18 `character.json` manifests exist,
are readable PNGs, are ≥ 32 px on both sides and are above the 400-byte
placeholder threshold, and none of them is flat or under 8 colours — so the black
square is **not** a broken pack file. It is `game/images/char_demo.png`, the
600×1000 opaque near-black demo placeholder that the engine draws whenever a
character has no resolved pack sprite. The "wrong size" complaint is real and is
measured: character states inside one pack differ by up to 26× in height.

Method: `tools/sprite_fit.py` uses the same `MIN_USABLE_SIDE = 32` rule, so the
usable/unusable boundary here matches what the engine itself enforces.

---

## 1. Manifests under `game/absorbed/`

| character id | pack | visual.type | states | poses |
|---|---|---|---|---|
| monika | Doki_Doki_Literature_Club | sprite | 28 | 0 |
| natsuki | Doki_Doki_Literature_Club | sprite | 68 | 0 |
| poem_special | Doki_Doki_Literature_Club | sprite | 15 | 0 |
| sayori | Doki_Doki_Literature_Club | sprite | 44 | 0 |
| yuri | Doki_Doki_Literature_Club | sprite | 75 | 0 |
| cs | Everlasting_Summer | sprite | 18 | 0 |
| dv | Everlasting_Summer | sprite | 113 | 0 |
| el | Everlasting_Summer | sprite | 54 | 0 |
| mi | Everlasting_Summer | sprite | 78 | 0 |
| mt | Everlasting_Summer | sprite | 69 | 0 |
| mz | Everlasting_Summer | sprite | 48 | 0 |
| pi | Everlasting_Summer | sprite | 6 | 0 |
| sh | Everlasting_Summer | sprite | 39 | 0 |
| sl | Everlasting_Summer | sprite | 108 | 0 |
| un | Everlasting_Summer | sprite | 108 | 0 |
| us | Everlasting_Summer | sprite | 112 | 0 |
| uv | Everlasting_Summer | sprite | 60 | 0 |
| asuna | SAO | layered | 0 | 13 |

17 plain sprite packs, 1 layered pack (`asuna`: 13 `visual.poses`, each with a
`base/` composed body plus `base/option*.png` extras, and separate
`eyes/<set>/*.png` + `mouth/<set>/*.png` layers). Total referenced files: 1074
(1059 plain/base states + 15 eye/mouth layers).

---

## 2. UNUSABLE referenced state files

| character id | state | path | size px | bytes | rule failed |
|---|---|---|---|---|---|
| _(none)_ | | | | | |

0 of 1074 failed. Every referenced file exists, is a readable PNG (IHDR at
offset 12), has both sides ≥ 32 px, and is ≥ 400 bytes on disk. Smallest file in
the set: `game/absorbed/SAO/character_art/asuna/base/pose_01_000/option1.png`
at 32×40 px / 1036 bytes — exactly at the engine's `MIN_USABLE_SIDE` boundary,
not below it.

---

## 3. Flat / low-colour referenced states

| character id | state | path | distinct colours | std. dev. | mean | rule failed |
|---|---|---|---|---|---|---|
| _(none)_ | | | | | | |

0 of 1059 content-checked states were flagged. Command used per file:
`magick <file> -format "%k %[fx:standard_deviation] %[fx:mean]" info:`, with the
15 `eyes/`+`mouth/` layer parts of `asuna` exempted from the content check as
specified (small mostly-transparent layers).

Lowest standard deviation among content-checked states, for reference — all
above the 0.01 threshold, all real content:

| path | colours | std. dev. | mean |
|---|---|---|---|
| Everlasting_Summer/character_art/mz/mz_2_glasses_1.png | 412 | 0.01155 | 0.00022 |
| Everlasting_Summer/character_art/mz/mz_1_glasses_1.png | 463 | 0.01279 | 0.00026 |
| Everlasting_Summer/character_art/mz/mz_2_glasses_2.png | 548 | 0.01309 | 0.00027 |
| Everlasting_Summer/character_art/mz/mz_3_glasses_1.png | 508 | 0.01377 | 0.00028 |
| Everlasting_Summer/character_art/mz/mz_1_glasses_2.png | 630 | 0.01427 | 0.00032 |
| Everlasting_Summer/character_art/mz/mz_2_glasses.png | 687 | 0.01439 | 0.00033 |
| Doki_Doki_Literature_Club/character_art/yuri/oneeye2.png | 667 | 0.01833 | 0.74987 |
| Doki_Doki_Literature_Club/character_art/poem_special/poem_special2.png | 98 | 0.01853 | 0.96668 |

The low `mean` on the Everlasting_Summer entries is transparency, not black: the
whole palette of those files sits at RGB ≈ 0 in the transparent area, so the
channel mean collapses while the standard deviation stays just above the
threshold. The files are real face overlays (e.g. `mz_2_glasses_1.png` is
675×1080, 412 colours, not opaque).

### 3b. Supplementary sweep (outside the referenced-state set)

A wider sweep of all 1453 PNGs under `game/` was run to locate the black square.
One file in the game directory is a uniform dark rectangle:

| path | px | bytes | colours | std. dev. | mean | channels | content |
|---|---|---|---|---|---|---|---|
| `game/images/char_demo.png` | 600×1000 | 2090 | 68 | 0.02612 | 0.10130 | srgb, **no alpha** | every one of its 68 colours lies in `#0A0D14`…`#1B2233` (max channel 27/255 = 10.6 %) — a flat near-black rectangle with no figure |

`game/images/bg_demo.png` is the same image content (68 colours, same mean
0.10130) at 1280×720. Two other legitimate near-uniform PNGs exist
(`game/gui/button/*_background.png`, `game/gui/namebox.png`: 1 colour, 269–1413
bytes) but they are GUI chrome, not character art.
`game/absorbed/Everlasting_Summer/scene_art/none.png` is 1×1 px, 1245 bytes,
1 colour — a scene-art placeholder, not referenced by any manifest.

---

## 4. Resolution distribution per pack (usable referenced states)

| pack | n | h min | h median | h max | w min | w median | w max | flags |
|---|---|---|---|---|---|---|---|---|
| Doki_Doki_Literature_Club | 230 | 37 | 960.0 | 982 | 46 | 960.0 | 1280 | height mix > 2×, width mix > 2× |
| Everlasting_Summer | 813 | 200 | 1080.0 | 1080 | 200 | 900.0 | 1125 | height mix > 2×, width mix > 2× |
| SAO | 31 | 40 | 124.0 | 1080 | 32 | 248.0 | 776 | **median h outside 700..1400**, height mix > 2×, width mix > 2× |

Distinct sizes per pack:

- **Doki_Doki_Literature_Club** (13 distinct): 960×960 ×189, 800×720 ×12,
  894×894 ×7, 1280×720 ×4, 264×279 ×4, 623×982 ×3, 720×960 ×3, 651×893 ×2,
  340×315 ×2, 46×46 ×1, 115×85 ×1, 55×37 ×1, 270×282 ×1.
- **Everlasting_Summer** (4 distinct): 900×1080 ×256, 1125×1080 ×254,
  675×1080 ×252, 200×200 ×51. The median is inside range, but 51 states are
  200×200 face/bust overlays mixed with 1080 px bodies inside the same pack.
- **SAO** (8 distinct): 90×90 ×8, 248×124 ×7, 776×1064 ×6, 768×1056 ×6,
  720×1080 ×1, 240×72 ×1, 208×48 ×1, 32×40 ×1. The 1 body-only entry
  (720×1080) and the 15 eye/mouth layers pull the median down to 124 px; the
  six pose bodies (768×1056, 776×1064) are normal.

Per-character height mix > 2× inside one pack:

| pack | character | n | h min | h max | ratio | what is mixed |
|---|---|---|---|---|---|---|
| Doki_Doki_Literature_Club | natsuki | 68 | 37 | 960 | 25.95 | 960 px bodies with `mouth.png` 55×37, `eye.png` 46×46, `ghost_blood.png` 115×85 |
| Doki_Doki_Literature_Club | sayori | 44 | 282 | 960 | 3.40 | 960 px bodies with 282 px states |
| Doki_Doki_Literature_Club | yuri | 75 | 279 | 960 | 3.44 | 960 px bodies, 279 px states, and full-screen 1280×720 states (`4_wipe`, `eyes1`, `eyes2`) |
| Everlasting_Summer | dv | 113 | 200 | 1080 | 5.40 | 1080 px bodies with 200×200 overlays, incl. the state key `dv-body.png` itself at 200×200 |
| Everlasting_Summer | sl | 108 | 200 | 1080 | 5.40 | same, state key `sl-body.png` at 200×200 |
| Everlasting_Summer | un | 108 | 200 | 1080 | 5.40 | same, state key `un-body.png` at 200×200 |
| Everlasting_Summer | us | 112 | 200 | 1080 | 5.40 | same, state key `us-body.png` at 200×200 |

`poem_special` additionally mixes 720–982 px character states with a full-screen
1280×720 state (`poem_end_clearall.png`).

The four 200×200 `*-body.png` states are real artwork (35 855–37 702 bytes,
5 217–7 218 colours, std. dev. 0.31–0.40), not placeholders — they are simply a
bust-sized sprite registered under the key that otherwise means "full body".

---

## 5. `assets.resolve_state(record, "happy")` per character

`game/assets.py` was imported with `renpy` stubbed exactly as
`tools/smoke_test_assets.py` does (`renpy.config.gamedir` set, `renpy.loader`
module installed, `renpy.loadable` → False). `assets.build_catalog()` returned
18 characters; `assets.status_of()` reports `sprite` for all 18, including the
layered `asuna`.

| id | `resolve_state(record, "happy")` | reason | px |
|---|---|---|---|
| monika | absorbed/Doki_Doki_Literature_Club/character_art/monika/1l.png | ok | 960×960 |
| natsuki | absorbed/Doki_Doki_Literature_Club/character_art/natsuki/0.png | ok | 960×960 |
| poem_special | absorbed/Doki_Doki_Literature_Club/character_art/poem_special/poem_end.png | ok | 800×720 |
| sayori | absorbed/Doki_Doki_Literature_Club/character_art/sayori/1bl.png | ok | 960×960 |
| yuri | absorbed/Doki_Doki_Literature_Club/character_art/yuri/0a.png | ok | 960×960 |
| cs | absorbed/Everlasting_Summer/character_art/cs/cs_1_normal.png | ok | 1125×1080 |
| dv | absorbed/Everlasting_Summer/character_art/dv/dv_4_normal.png | ok | 1125×1080 |
| el | absorbed/Everlasting_Summer/character_art/el/el_1_normal.png | ok | 1125×1080 |
| mi | absorbed/Everlasting_Summer/character_art/mi/mi_2_happy.png | ok | 1125×1080 |
| mt | absorbed/Everlasting_Summer/character_art/mt/mt_1_normal.png | ok | 1125×1080 |
| mz | absorbed/Everlasting_Summer/character_art/mz/mz_1_normal.png | ok | 1125×1080 |
| pi | absorbed/Everlasting_Summer/character_art/pi/pi_1_pioneer.png | ok | 1125×1080 |
| sh | absorbed/Everlasting_Summer/character_art/sh/sh_2_normal_smile.png | ok | 1125×1080 |
| sl | absorbed/Everlasting_Summer/character_art/sl/sl_2_happy.png | ok | 1125×1080 |
| un | absorbed/Everlasting_Summer/character_art/un/un_1_normal.png | ok | 1125×1080 |
| us | absorbed/Everlasting_Summer/character_art/us/us_1_normal.png | ok | 1125×1080 |
| uv | absorbed/Everlasting_Summer/character_art/uv/uv_2_normal.png | ok | 1125×1080 |
| asuna | absorbed/SAO/character_art/asuna/base/pose_01_000.png | ok | 776×1064 |

Sweeping `resolve_state` over the whole `EMOTION_WORDS` vocabulary for all 18
characters returned 0 paths smaller than 200 px or larger than 1200 px, so no
emotion lookup lands on a 200×200 overlay, a 46×46 face part or a 1280×720
full-screen state. No catalog record lacks `visual.states`, so no absorbed
character can reach the demo fallback through `visual_for_world`.

---

## Conclusion

**The black square is `game/images/char_demo.png` — the demo placeholder
sprite (600×1000, opaque, no alpha, 68 colours all between `#0A0D14` and
`#1B2233`, mean 0.1013, no figure).** Not one referenced pack asset is
unusable or flat, so the black rectangle comes from the fallback path, not from
a corrupt file: `engine.py` falls back to `images/char_demo.png` inside
`_asset_path()` and also uses `visual.states[emotion|neutral]` when
`resolve_state` finds no record, and the default world at `game/world.py:29-31,
43, 53` and `game/data/story_example.json` points every unbound character's
states at exactly that file. A character that is not one of the 18 packed ids
therefore draws that black rectangle.

The "wrong size" complaint is separate and is measured in §4: `natsuki` mixes
37 px to 960 px states inside one character (26×), `dv`/`sl`/`un`/`us` mix
200×200 states — including each one's own `*-body.png` — with 1080 px bodies
(5.4×), and `yuri`/`poem_special` mix 960 px bodies with 1280×720 full-screen
states.
