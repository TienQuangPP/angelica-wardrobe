# Angelica Wardrobe — an MMO's fashion window, rebuilt as a standalone 3D app

*[Tiếng Việt](README.vi.md)*

Tools that read the data files of the **Thế Giới Hoàn Mỹ** client (the Vietnamese release of Perfect World,
Angelica engine) and rebuild its in-game fashion collection window ("Thu thập") as a standalone 3D web app:
every fashion set on the player's own character, with the game's UI, dyes, effects and animations.

> **No game content is included.** This repository only contains code. Models, textures, UI images and game data
> belong to their publisher; the tools generate them locally from a client you already have.

## What it does

- **Reads the undocumented formats** of the engine, all reverse engineered: `.pck/.pkx` packages,
  `elements.data` (game database, per-record MPPC compression), `.ski` skinned meshes, `.bon` skeletons,
  `.stck` animations, `.gfx` particle effects, `.mtl` materials, AUI dialog XML and `.stf` string tables.
- **Converts** the 2,300+ fashion models it needs to skinned glTF (`.glb`) and keeps the game's own DDS
  textures, so the browser samples the same DXT blocks and mipmaps as the game.
- **Rebuilds the fashion window from the game's own UI files** (positions, frames, fonts, scroll behaviour),
  with the real collection data: 315 female / 258 male sets in 6 collection groups, names, descriptions,
  rarity, default colours, pets, effects.
- **Re-implements engine logic found in the client executable** (x86 disassembly):
  - the character-creator face morph (bone groups, slider factors, move / rotate / scale operations),
  - the body-shape sliders (per-bone length / thickness / whole scale, as the engine's bone update applies them),
  - the fashion shaders (dye masks in gamma space, channel maps, reflection, transparency rules).
- **Checks itself against the game**: screenshots of the game window are compared with renders of the page to fit
  the camera (Nelder–Mead on edge correlation), the lights (colour error) and the texture sharpness
  (high-frequency energy); the body-shape values were confirmed against the running client.
- **Ships as a desktop app**: a tiny C# launcher starts a local server and opens the page in an app window;
  works fully offline.

## Layout

```
tools/
  pck_reader.py elements_reader.py game_data.py      game packages and database
  ski_reader.py bon_reader.py stck_reader.py         meshes, skeletons, animations
  gfx_reader.py mtl_reader.py                        effects, materials
  extract_fashion.py fashion_classify.py vn_names.py find and extract the fashion assets
  ski_to_glb.py anim_export.py skinning.py           conversion to glTF
  build_sets.py build_fx.py build_ui.py              sets, effects, UI layout
  face_morph.py body_shape.py                        engine logic re-implemented from the executable
  build_wardrobe.py deploy_viewer.py                 wardrobe data + page deployment
  check_wardrobe.py check_glb.py prune_wardrobe.py   audits
  tghm_paths.py                                      where the client and the output are (see below)
  viewer/      tu_do.html / tu_do.js (wardrobe), aui.js (game UI renderer), fx.js (particles),
               xem_3d.html (plain model browser), server.ps1, launcher/ (C# app window)
  _ref/        reverse-engineering and comparison helpers (disassembly, pack search, image metrics)
docs/FORMATS.md  notes on the file formats and engine behaviour
```

## Running it with your own client

Requirements: Windows, Python 3.11+, `pip install -r requirements.txt`, a TGHM / Perfect World client.

1. Put `tools/` inside the client folder, or create `tools/config.local.json`:
   `{"game": "D:\\Games\\TGHM Online", "data": "E:\\TGHM_Data"}` (output folder, ~4 GB).
2. Extract the fashion assets: `py tools/extract_fashion.py`
3. Export the game UI dialogs: `py tools/build_ui.py`
4. Build the wardrobe (models, textures, catalog): `py tools/build_wardrobe.py`
5. Copy the pages and fetch three.js: `py tools/deploy_viewer.py`, then
   `powershell -File tools/viewer/get_three.ps1 -Out <data>\3D`
6. Open `<data>\3D\XEM_TU_DO.bat`, or build the app with `tools/viewer/launcher/build.ps1`.

The sample character is the newest appearance saved by the game's character creator
(`element\userdata\character\customize`).

## How it was built

Built as an AI-assisted project with Claude Code: the agent did most of the reverse engineering, code and
image comparisons; I drove the goals, played the game to provide reference screenshots, checked the results
against the client and decided what "identical to the game" meant at each step.

## License

Code: MIT (see `LICENSE`). Game data, models, textures and UI art are not covered and not distributed.
