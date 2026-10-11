# Current verification scope

## Local candidate 0.4.2rc5 (2026-10-11)

Public release remains 0.4.1. This candidate is not approved for public release.

- Quick: 536 selected, 535 passed, one optional historical OCR archive skipped, zero failures/errors; 66.579 seconds.
- Release: 578 selected, 575 passed, three skipped, zero assertion failures/errors; 289.576 seconds. `release_complete=false`, nonzero exit.
- Two required similarity replays need the original rc16 session `20261010-235332-5fe7c98a`, which was removed with old candidate outputs. The original files were not found in available local copies or supplied ZIP archives. These checks remain selected; they have not been weakened or reclassified to hide missing evidence.
- The other skip is the supplemental historical private OCR archive. No other missing evidence is allowed for a complete release verdict.
- After the release run, the event/persistence compromise integration case was isolated from repeated global refinement. Both service integration cases pass in 4.399 seconds combined; the previous compromise case alone took 63.230 seconds. Production refinement remains unchanged and retains separate real-solver coverage.
- Python, PowerShell and pytest entry points now share the same selector. Pytest collection and the root Python wrapper both select 536 quick tests. Four real desktop representatives remain in quick, with the full UI matrix in release.

## Product changes covered

The input backend accepts a non-1:1 viewport only with verified target-HWND DPI pixel-mapping evidence. Window, process, session, current pose and input-release checks remain active. This does not establish universal support for every hardware/DPI/game-version combination.

The shared time policy keeps a single three-second tail. New rounds are capped at 117 seconds; unknown-age rounds initially use 90 seconds and may gain at most 27 seconds from reliable same-session countdown evidence. The initial 30-second OCR grace and retry epoch are preserved. Input, readback and complete return routes remain dynamically charged.

Global approaches can use controlled rotations up to 90 degrees while generic compilation retains its 12-degree default and fine candidates. Completed candidates survive CPU search exhaustion; late moves require protected recovery. Actual screenshot HEX remains the only precise-match proof. Three-white end-to-end accuracy is not newly verified.

## Evidence and exclusions

Local reports: `outputs/native-integration/verification/optimization-2026-10-11/`.

Required data3 session evidence was recovered from the user-provided archive (about 700 KB). Other retained fixtures remain local and are excluded from Git and portable packages. Do not delete referenced fixtures when cleaning build outputs. Prior version details remain in Git history and `docs/research`.

No real game input, dye item, automatic application or public release was used for this maintenance work. Package integrity and launch evidence are recorded separately in the local report folder; they do not replace missing live or archived route evidence.
