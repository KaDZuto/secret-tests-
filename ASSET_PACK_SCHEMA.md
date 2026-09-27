# Living VN asset pack contract

This is the stable contract for future agents. Do not couple story logic to individual file names.

## Character pack

```text
characters/asuna/character.json
characters/asuna/sprites/neutral.png
characters/asuna/sprites/happy.png
characters/asuna/live2d/model.model3.json
characters/asuna/live2d/...
```

`character.json`:

```json
{
  "id": "asuna",
  "name": "Асуна",
  "visual": {
    "type": "live2d",
    "model": "characters/asuna/live2d/model.model3.json",
    "states": {
      "neutral": "characters/asuna/sprites/neutral.png",
      "happy": "characters/asuna/sprites/happy.png"
    },
    "expressions": {
      "embarrassed": "..."
    },
    "motions": {
      "idle": "..."
    },
    "outfits": {
      "school": "..."
    }
  }
}
```

The engine must always have a sprite fallback for unsupported Live2D targets.

## Backgrounds

Use `locations/<location-id>/background.*` where possible. Story data references a logical location id, not a physical path.

## Music

Music is referenced by catalog path and semantic tags. The director emits `music_intent`; the local catalog selects an actual track. Never hard-code a particular filename into generated story JSON.

## TTS

Text is the source of truth. A TTS provider may synthesize it on demand. Caches must be disposable and must never become part of story state.

## Absorbed third-party packs

Imported game assets live under `game/absorbed/<pack>/` and have a `manifest.json` with:

- `third_party: true`
- `redistributable: false` by default
- copied asset paths
- isolated character profiles
- source identifier

The story generator receives imported characters only through the character state when the player chooses to add them. No source plot/labels are imported into the current world.

The importer accepts directly accessible folders and ordinary ZIP archives. It does not decrypt protected archives, bypass DRM, execute imported code, or treat compiled save data as source lore.
