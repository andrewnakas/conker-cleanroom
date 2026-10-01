# Conker's Bad Fur Day — clean room web build

Play: **https://andrewnakas.github.io/conker-cleanroom/**

Conker's Bad Fur Day running in the browser (EmulatorJS, mupen64plus-next) with **every texture, sprite,
font glyph, sound sample and voice line regenerated**: no retail pixels or audio. No ROM is needed to play.

Controls: **Arrows** move · **X** A (jump) · **C** B (attack) · **Z** Z (crouch) · **S** R ·
**Q** L · **Enter** Start · **I J K L** C-buttons. Gamepads work too. Saves stay in your browser.

## What is kept, what is generated

The [DevOldSchool/conkers-bfd-decomp](https://github.com/DevOldSchool/conkers-bfd-decomp) project is a
partial decompilation (about 16% C); its documentation describes every container in the ROM. This build
does not compile that decomp: `games/conker/romtool.py` rebuilds the cartridge image around the game's
**program code, which is kept as it is**, and replaces the assets. A ROM is read once, in "dirty room"
steps that keep only the facts below.

| Asset | Kept fact | Generated |
|---|---|---|
| Program code, RSP microcode, boot code | kept (as in every clean-room build of this series) | — |
| Flat textures (7,760) | format, size, mip layout, a 4×4 colour grid (16×16 from 128 px), a 2-bit alpha outline | colour from the grid, our own grain and CI palettes, mip chains |
| Sprite sets (270 frames) | size, 4×4 colour grid, 1-bit alpha, 2-bit plane outline | regenerated |
| System font (95 glyphs) | glyph box sizes, character map | redrawn with our stroke font |
| Text inside textures (signs, posters, labels) | the words | re-typeset with OFL fonts (`text_briefs.json`) |
| Geometry, collision, animation, placements, scripts, dialogue text | kept | — |
| Music | note sequences, bank structure (envelopes, key maps, tuning) | played by the resynthesised instruments |
| Sound samples (2,258, 29 min) | length, loop points, coarse spectral outline, median pitch | resynthesised; our own VADPCM books and loop states |
| Speech (453 MP3 streams, about two hours) | words (speech recognition), phrase times, one median pitch per phrase, lip-sync cue times | placeholder Piper TTS stock voices (no cloning); the game's subtitles are its own text |

`python -m games.conker.taint <retail> <clean>` compares every regenerated stream with the retail data and
fails on any shared run of 32 bytes (32 texels for decoded pixels). The site is only published when it
reports **0 failing**.

## Build

```sh
python -m games.conker.generate <retail .z64> <clean .z64>     # needs spec/ (committed) and the ROM as container
python -m games.conker.taint <retail .z64> <clean .z64>
games/conker/publish.sh --no-push
```

Dirty-room steps (only needed to rebuild `games/conker/spec/`): `texscan.py`, `texspec.py`, `fonts.py spec`,
`sprites.py spec`, `audio.py spec`, `voice_spec.py`. See `STATUS.md` for decisions and open items.

Third-party runtime: EmulatorJS (GPL-3.0) and the libretro mupen64plus-next core (GPL-2.0); fonts in
`games/conker/fonts` are OFL / Apache-2.0. Not affiliated with Rare, Nintendo or Microsoft.
