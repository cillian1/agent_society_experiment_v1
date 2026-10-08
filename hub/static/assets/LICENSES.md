# Third-party art assets

Every image in this directory is by **Kenney (www.kenney.nl)** and is released under
**Creative Commons Zero 1.0 (CC0 1.0, public domain dedication)**:
https://creativecommons.org/publicdomain/zero/1.0/

> This content is free to use in personal, educational and commercial projects.
> Support us by crediting Kenney or www.kenney.nl (this is not mandatory).
> — License.txt shipped with each Kenney pack

Files were downloaded on 2026-10-08 from the `series-ai/jam-ready-assets` GitHub mirror
(a curated library that keeps each pack's original Kenney `License.txt` next to the art;
binary files are stored in Git LFS and were fetched through `media.githubusercontent.com`).
Original file names are kept. Only PNG files were saved, and each one was checked to be a real PNG.
Only a subset of each pack is included.

| Folder | Kenney pack | Original page | Mirror path (source) | License | Files |
|---|---|---|---|---|---|
| `kenney-isometric-landscape/` | Isometric Tiles Base / "Isometric Landscape" (1.0), `landscapeTiles_000–127` | https://kenney.nl/assets/isometric-landscape | https://media.githubusercontent.com/media/series-ai/jam-ready-assets/main/kenney-isometric-tiles-base/2D/prototype-blocks/PNG/ (license: https://raw.githubusercontent.com/series-ai/jam-ready-assets/main/kenney-isometric-tiles-base/2D/prototype-blocks/License.txt) | CC0 1.0 | 128 (all) |
| `kenney-isometric-nature/` | Isometric Nature (1.0), `naturePack_NNN_0` (rotation 0 only; cliff/waterfall pieces 096–106, 115–128 and 141–143 left out) | https://kenney.nl/assets/isometric-nature | https://media.githubusercontent.com/media/series-ai/jam-ready-assets/main/kenney-isometric-nature/2D/nature/PNG/ (license: .../kenney-isometric-nature/2D/nature/License.txt) | CC0 1.0 | 147 |
| `kenney-isometric-medieval-town/` | Isometric Medieval Town (1.0), rotations `_0` and `_1` of 25 pieces | https://kenney.nl/assets/isometric-medieval-town | https://media.githubusercontent.com/media/series-ai/jam-ready-assets/main/kenney-isometric-medieval-town/2D/city/PNG/ (license: .../kenney-isometric-medieval-town/2D/city/License.txt) | CC0 1.0 | 50 |
| `kenney-isometric-miniature-farm/` | Isometric Miniature Farm (2.0), `Isometric/*_S.png` (plus `fence*_E`) | https://kenney.nl/assets/isometric-miniature-farm | PNGs taken from `Isometric Miniature Farm (2.0).zip` at https://media.githubusercontent.com/media/series-ai/jam-ready-assets/main/kenney-isometric-miniature-farm/2D/farm/ (the zip's own License.txt says CC0) | CC0 1.0 | 16 |
| `kenney-isometric-miniature-overworld/` | Isometric Miniature Overworld (2.0), `Isometric/*_S.png` | https://kenney.nl/assets/isometric-miniature-overworld | PNGs taken from `Isometric Miniature Overworld (2.0).zip` at https://media.githubusercontent.com/media/series-ai/jam-ready-assets/main/kenney-isometric-miniature-overworld/2D/top-down-rpg/ (the zip's own License.txt says CC0) | CC0 1.0 | 13 |
| `kenney-cube-pets/` | Cube Pets (2.0), `Previews/animal-*.png` (64×64 renders) | https://kenney.nl/assets/cube-pets | https://media.githubusercontent.com/media/series-ai/jam-ready-assets/main/kenney-cube-pets/3D/characters/Previews/ (license: https://raw.githubusercontent.com/series-ai/jam-ready-assets/main/kenney-cube-pets/3D/characters/License.txt) | CC0 1.0 | 12 |

Credit (optional under CC0): "Art by Kenney (www.kenney.nl), CC0."

## Usage notes for `manifest.json`

`manifest.json` is a JSON array with one entry per PNG:
`{path, w, h, kind, label, diamond_w, anchor}`. Landscape tiles also have `top_anchor` and `base_anchor`.

- **anchor**: the pixel that goes on the map tile's centre point.
  - *Landscape tiles*: `[w/2, h-66]`. This is the centre of a standard-height top surface, measured up from
    the bottom of the tile. If every tile is drawn this way, the 83 px-tall water and low-dirt tiles sit 16 px lower,
    as Kenney intended, and the 131 px-tall hill tiles stand higher. `top_anchor` is the centre of the top diamond
    itself (66, 32), and `base_anchor` is the centre of the bottom footprint.
  - *Nature / medieval / farm / overworld*: each pack draws every sprite on the same fixed canvas
    (220×379, 210×244 and 256×512), already placed relative to one tile. So all sprites in a pack share one
    anchor, the tile centre on that canvas: nature (110, 304), medieval (105, 170), farm and overworld (128, 436).
  - *Cube pets*: the bottom centre of the visible pixels.
- **diamond_w** (width of the top diamond on ground tiles): landscape 132 (132×64, about 2:1); nature and medieval 182
  (182×104, a bit steeper than 2:1); farm and overworld 256 (256×128).
  To fit the 132 px landscape grid, scale nature and medieval sprites by about 0.725 and farm and overworld sprites by about 0.516.
- Medieval-town walls, railings and fences are *edge pieces*: they stand along one edge of a tile, and the `_0`/`_1`
  suffix is the rotation. The roofs (`roof_point_*`) cover a whole tile and make a simple hut top.
- `_contact.png` is a preview sheet only, and the game does not need it.
