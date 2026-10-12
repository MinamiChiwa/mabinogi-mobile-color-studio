# Countdown regression crops

These fixtures contain unchanged saved HUD pixels on a black 240×240 canvas.
The canvas preserves enough area for the actual hourglass locator; it does not
render or guess any text. Labels were transcribed manually from the source.

- `timer-105.png`: historical screenshot in which the previous icon-relative
  cutoff excluded the leading 1. Label: 105.
- `timer-117.png`: original stage66 failed screenshot previously read as 17.
  Label: 117.
- `timer-115.png`: manually labeled startup HUD. A test dims the first 1 to
  205 to reproduce the previous locator dropping it and confirming 15.
- `timer-9.png`: Korean server final countdown. Label: 9.

Source hashes and crop boundaries are retained in the local development corpus
`project/outputs/game-font-20261012/corpus/manifest.json`. Fixtures and source
game fonts are excluded from the portable distribution.
