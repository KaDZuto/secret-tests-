# Design notes

## Reference traditions

### Doki Doki Literature Club
Use the idea that the *presentation layer itself* can become part of the narrative. The engine can later expose selected meta-state variables without turning the normal game loop into a chat UI.

### Everlasting Summer
Borrow the feeling of a place that has a daily rhythm. The AI can maintain a time-of-day value, recurring activities and a small schedule graph. Music should reinforce place and time rather than simply follow dialogue keywords.

### CLANNAD
Character arcs should exist independently of the immediate scene. Relationship values are not the story by themselves: each important character needs personal goals, conflicts, secrets and turning points.

### STEINS;GATE
The world state should preserve causality. A new event must be able to reference an earlier fact, and the supervisor should flag impossible knowledge, unexplained teleportation and broken cause/effect chains.

### The House in Fata Morgana
Use layered lore and an unreliable or incomplete understanding of locations when the game genre requests mystery. The Lore Codex should distinguish facts the player knows from facts known only to a character or the director.

### Katawa Shoujo
Character-centric routes should remain possible even when the director is generating new scenes. The player should feel that spending time with one character changes later content rather than merely changing a numeric affection score.

## AI pacing strategy

Never generate a huge novel in one request and never generate every line with a fresh request.

The recommended unit is a **micro-scene bundle**:

- 6–12 beats by default.
- Usually 1 coherent exchange or short scene.
- May contain movement, expression, dialogue, narration, music intent and one checkpoint.
- Ends at a choice, a scene transition, a reveal, an emotional turn, or an explicit `checkpoint`.

The player sees only one beat at a time. The next bundle is requested when the buffer becomes low or reaches a checkpoint.

## Supervisor loop

1. Director creates a micro-scene bundle.
2. Supervisor reads recent history, world state, and the generated future buffer.
3. Supervisor checks:
   - continuity
   - character consistency
   - pacing
   - repetition
   - foreshadowing
   - agency
   - lore consistency
   - scene/transition clarity
4. If acceptable, the bundle is approved.
5. If not, the supervisor returns targeted repair instructions.
6. Director gets one repair pass.
7. If the repair still fails, the engine falls back to a safe local scene rather than hanging.
