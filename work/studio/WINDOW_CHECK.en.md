# Window and DPI preflight

Copy the complete ColorStudio folder to the target PC and keep `_internal`. Start the game and stay on an ordinary screen. No dye round or consumable item is needed.

Open PowerShell in this folder and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\native-window-check.ps1
```

The script reads process and window information without sending game input. Records are saved under `data/window-check-YYYYMMDD-HHMMSS/`. Include `native-preflight.json` and `native-preparation.json` when reporting a problem.

Preflight locates supported modules across installation paths and measures the target window in its DPI context before converting to physical pixels. When rendering and physical window dimensions differ, the tool builds and verifies an integer pixel mapping for search and fine adjustment. No fixed game resolution is required. The topmost overlay supports clicks and dragging without taking focus. It briefly hides while sending game gestures, then returns. F9 or Stop cancels the run.

Reader cursor differences are diagnostic rather than a reason to stop before actual game readback. `pixel_mapping_diagnostics` retains raw coordinates, differences and native mouse-cache observations. Identical repeated cache reads do not prove a fresh input frame. Process/window changes, failed mapping checks, F9 and deadlines still stop execution.

If coordinate mapping is unavailable, the records contain rendering size, original and target-context client bounds, physical corners and the failed conversion check. Ordinary-screen preflight is sufficient; do not spend a dye item just to collect these files. Only verified mappings are used.

If game-process access is denied, match the tool’s privilege level to the game. When the game runs as administrator, exit the tool and right-click `ColorStudio.exe` → Run as administrator. Retry on an ordinary screen. Records include elevation and integrity diagnostics, or explicit unknown values when queries are restricted. The tool never elevates itself or changes game protection automatically.
