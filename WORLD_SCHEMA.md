# Living VN world contract

The world is plain JSON and intentionally provider-neutral.

Required top-level fields:

- `title`
- `genre`
- `tone`
- `premise`
- `characters`
- `locations`
- `lore`

Runtime fields:

- `flags`
- `time`
- `location`
- `memory_summary`
- `history`
- `buffer`
- `turn`
- `music_catalog`
- `last_supervisor`

## Director bundle

A bundle is `{ "beats": [...] }` and usually contains 4-12 beats. A beat may be:

- `scene`
- `dialogue`
- `narration`
- `choice`
- `wait`
- `music`

The director should generate several sequential beats in one API call. A checkpoint is used for player input, branch points, reveals, or scene transitions.

## Supervisor

Supervisor output:

```json
{
  "score": 0.0,
  "approved": true,
  "summary": "...",
  "issues": [],
  "director_command": "...",
  "repair": false
}
```

The supervisor is advisory but can request one repair pass. Never let it directly mutate arbitrary Python or files.
