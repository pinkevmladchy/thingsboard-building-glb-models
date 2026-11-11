# ThingsBoard building GLB models

3D building models for the ThingsBoard **3D Model Viewer** widget, plus the Claude skill that generates them.
Each floor is its own mesh (`Floor.001`, `Floor.002`, …), so a dashboard can color every floor by its
alarms and open the floor when it is clicked.

## Models

| File | Footprint | Floors | URL for the widget |
|---|---|---|---|
| `models/harbor_point_rect_4f.glb` | rectangle 36 × 24 m | 4 | `https://raw.githubusercontent.com/pinkevmladchy/thingsboard-building-glb-models/main/models/harbor_point_rect_4f.glb` |

Meshes: `Floor.001` … `Floor.004` (bound to Floor assets), `Slabs`, `Window_Frames`, `Windows`, `Roof_Plant` (decoration).

## Widget settings

- **Mesh type:** `Floor`
- **Model source:** URL, the raw link above
- Every Floor asset has a server attribute `meshId` = `Floor.001` (ground floor), `Floor.002`, …

## Generate your own

```bash
python scripts/build_building.py --shape rect --width 36 --depth 24 --floors 4 --output building.glb
python scripts/build_building.py --shape L --width 36 --depth 28 --wing 12 --floors 6 --output l.glb
python scripts/build_building.py --shape U --width 42 --depth 28 --wing 12 --floors 3 --output u.glb
```

Pure Python 3, no dependencies. See [`SKILL.md`](SKILL.md) for all options.

## Claude skill

This folder is also a Claude skill (`building-glb-builder`): copy it into `~/.claude/skills/` and ask
Claude for "a 3D model of a 6-storey L-shaped office".
