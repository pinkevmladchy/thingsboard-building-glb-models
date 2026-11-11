---
name: building-glb-builder
description: Generate GLB 3D models of multi-storey buildings for the ThingsBoard 3D Model Viewer widget — one mesh per floor (Floor.001 …) so floors can be colored by alarms and bound to Floor assets through the meshId attribute. Supports rectangle, L (Г) and U (П) footprints or a custom polygon, any number of floors, windows on every wall, slabs and roof plant. Use whenever the user asks for a 3D building / office / smart building model, a .glb of a building, a floor-by-floor 3D view for ThingsBoard, or wants to change the footprint, size or floor count of such a model. Trigger even without the word "GLB" — "make me a 3D model of our office building" is enough.
---

# Building GLB Builder

Pure-Python generator (no numpy / trimesh needed) for building models used by the
ThingsBoard **3D Model Viewer** widget (`tenant.pinkevych.d_3d_model_viewer`).

## Quick start

```bash
python scripts/build_building.py --shape rect --width 36 --depth 24 --floors 4 --output building.glb
python scripts/build_building.py --shape L --width 36 --depth 28 --wing 12 --floors 6 --output l.glb
python scripts/build_building.py --shape U --width 42 --depth 28 --wing 12 --floors 3 --output u.glb
python scripts/build_building.py --footprint '[[0,0],[30,0],[30,20],[0,20]]' --floors 5 --output custom.glb
```

## Workflow

1. **Ask for the footprint**: rectangle, L (Г), U (П) or a custom polygon in metres.
   For L / U also the wing width. The script checks that the wings fit.
2. **Ask for floors**: number of floors and floor height (default 3.6 m incl. a 0.3 m slab).
   Total height is derived, never asked.
3. Run the script, then render-check the GLB if a browser is available.
4. Tell the user the mesh names and the widget settings below.

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--shape` | `rect` | `rect`, `L`, `U` |
| `--width` / `--depth` | 36 / 24 | overall size, m |
| `--wing` | 12 | wing width for L / U, m |
| `--footprint` | — | custom polygon `[[x,z],...]`, m; overrides `--shape` |
| `--floors` | 4 | number of floors |
| `--floor-height` / `--slab` | 3.6 / 0.3 | m |
| `--window-width` / `--window-height` / `--window-spacing` | 1.6 / 1.9 / 3.0 | m |
| `--scale` | 0.1 | model units per metre (0.1 → a 36 m building is 3.6 units, same scale as the silo models) |

## Output contract

- `Floor.001` … `Floor.NNN` — one mesh per floor, ground floor = `Floor.001`, each with its own material.
  These are the meshes the widget colors.
- `Slabs`, `Window_Frames`, `Windows`, `Roof_Plant` — decoration, not bound to entities.
- +Y up, footprint on XZ centred on the origin, ground at y = 0, identity node transforms, no extras.
- Note: three.js GLTFLoader strips the dot from node names (`Floor.001` → `Floor001`); the widget
  matches them the same way it matches `Silo.001`.

## ThingsBoard binding

- Floor asset attribute (server scope) `meshId` = `Floor.001` for the ground floor, `Floor.002` for the next, …
- Widget: **Mesh type** `Floor`, **Model source** URL (raw GitHub link to the GLB) or a resource,
  datasource = the building's Floor assets with `meshId` + `activeAlertsCount`.
- Color function example:
  ```js
  return entity?.activeAlertsCount > 0 ? '#E5484D' : '#43A047';
  ```
