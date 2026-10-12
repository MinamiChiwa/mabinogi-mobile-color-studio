# Recorded color text conflict

`cards.png` is an unchanged RGB crop `(730,250,1168,345)` of the user's rc8
session `20261012-215038-99247e34`, `candidate_0_step_2_after_frame0.png`.
It contains only the three card swatches/texts. Their boxes in this crop are
`(17,10,80,80)`, `(181,10,80,80)`, `(346,10,79,79)`.

Printed and CPU/client checkpoint codes are `#F27233 / #EAD310 / #72514A`.
The original single-pass reader produces `#725148` on the third card; both
plausible codes pass its swatch proximity gate. Independent enlarged text
reads at two thresholds produce the printed `#72514A` without expected digits.

This fixture verifies reading recorded pixels, not live game input or target
search success. Root fixtures are excluded from portable distributions.
