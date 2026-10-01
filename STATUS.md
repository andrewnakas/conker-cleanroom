# Conker's Bad Fur Day clean room: status

## Decisions (log)
- 2026-10-01 09:05 ROM `Conker's Bad Fur Day (USA).z64` sha1 4cbadd3c… = the decomp's US target. Unpacked to `D:/n64work/conker/baserom.us.z64`.
- Decomp: DevOldSchool/conkers-bfd-decomp (LF clone, `D:/n64work/conker/pristine`; dirty tree `…/dirty` with the decomp's own
  `rzip_extract` output in `build/rzip/us`). Its build is Docker-only and assets stay ROM blobs, but its Python asset tools and
  `docs/rzip-assets.md` document every container. `conker64-recompiled` is only an asset viewer (does not run the game).
- **Web route = 3: clean ROM + WASM N64 emulator** (EmulatorJS 4.2.3 + mupen64plus_next/GLideN64, same as BK/MK64; `ports/ejs`).
  Why: no PC port, no N64Recomp port that runs. Retail boots in headless Edge to the intro (logo, Rareware, tavern) — dev only.
- **Clean ROM = retail code + regenerated assets**, rebuilt by `games/conker/romtool.py` (no decomp build needed: code is 84% asm
  from the ROM anyway; code counts as kept, as in the PW64 recomp route).
  - Identity rebuild is byte-identical (sha1 match). Flat texture stream (7760 chunks, u16 size table in game data at
    D_80091D20, 2 empty ids 1767/1768), 29 banks re-laid with 8-byte alignment, header CRC (CIC-6105).
  - Compression = Rare's gzip 1.2.4 deflate (`tools/rarezip/rarezip.dll`, from the BK session): reproduces ~79% of retail chunks
    byte for byte. Recompressed banks + game data boot fine; an unknown MD5 also boots.
  - **Do not recompress game code chunks**: that ROM stays black (probably an integrity check). Code is never changed.

## Works (2026-10-01 midday)
- `python -m games.conker.generate <retail> <clean.z64>` builds the clean ROM; it boots in headless Edge (EmulatorJS) to the
  save-select menu with every flat texture regenerated.
- Textures: `texscan.py` (display-list usages) + `texspec.py` -> `spec/textures.json` for all 7760 flat ids
  (format, mip layout, 4x4 grid, 2-bit alpha). Layout evidence: 1751 from display-list tiles, 1429 from palette mode /
  loaded size, 2855 background-view tiles (64x32, proven by the decomp), 1720 guessed from size class + image statistics.
  Generator: grid + alpha outline + own median-cut palette (CI8 limited to 64 colours, grain 1.5) so the flat stream
  fits its fixed span (9.07 of 9.49 MB).
- Bank 00 sprites (56 sets, 270 frames: RGBA16 + I4 plane, frame size found by statistics): regenerated.
- Sound bank (bank 17): 2258 samples / 29 min resynthesised from outlines, own 4-predictor books, loop states from our data;
  sizes unchanged. Cache: `D:/n64work/conker/work/audio_cache.pkl`.
- Taint (`python -m games.conker.taint <retail> <clean>`): textures, sprites, font, ADPCM, books, loops = 0 failing.
  Decoded-RGBA rule is 32 texels (not 32 bytes): 8-texel runs of similar 5-bit browns recur by chance in 16 MB of pixels.
- Other banks checked: 05 = Huffman-coded per-scene structure data (not pixels), 06/08/13/1A/1C nested text/data,
  02/0F animation, 0B/0C/0E placements, 14 scripts: all kept (geometry / text / code-like).

## Published (2026-10-01 ~11:55)
- Repo https://github.com/andrewnakas/conker-cleanroom (public), site https://andrewnakas.github.io/conker-cleanroom/
  (gh-pages = EmulatorJS 4.2.3 + mupen64plus-next with its ROM-DB entry "Conker's BFD (U) [T+Fre1.3]" pointed at our
  ROM's MD5 for EEPROM 16 KB). `games/conker/publish.sh` regenerates, refuses to publish unless taint passes, pushes.
- Taint: **0 failing of 21,565 streams** (flat raw + RGBA, sprites, font, ADPCM, books, loop states, MP3 speech).
- Verified in headless Edge on the clean ROM: N64 logo, Rareware scene, save select, NEW GAME, intro cutscenes
  (Conker close-up, throne room, title), pause menu. No hangs with the regenerated audio or speech streams.
- **Note on scope**: the decomp is only ~16% C, so the ROM's program code is the game's own code (not compiled from
  the decomp), as in the PW64 recomp route / the option named in CLAUDE.md. Say if that is not wanted for this one.

## Facts learned (traps)
- The RLE font table must fill exactly the retail span (the game walks it to the end): a shorter table = black boot.
  Runs are split until the size matches (`fonts.build`).
- MP3 speech frames with the copyright bit carry a 9-byte `L:` lip-sync cue record after the frame (standard
  decoders lose sync there). `voice_spec.plain_mp3` strips them to decode; `voices.with_cues` re-attaches the kept cues.
- Flat ids are runtime ids (two empty slots at 1767/1768): decomp "flat index" + 2 above 1767.
- Text on a cut-out keeps the retail lettering in its alpha outline: `drawn.draw_text` always redraws alpha there.
- Headless Edge can take > 20 s to start under load (`cdp_shot.py` waits up to 2 min now).

## Open problems
- Speech: Whisper small.en on CPU is still transcribing (GPU has no CUDA libs). Streams without a transcript are
  faint-noise fillers for now; rerun `python -m games.conker.voices build` + `publish.sh` when `spec/voices.json` exists.
- Game code cannot be recompressed (black screen), so no code patches.
- Layout of 1720 textures is a guess from statistics; a few may have the wrong width (they show as noise in-game).

## Next
- Eyes: lids and two-eye textures in `eyefit.py`; Conker's own face frames (64x32 CI4, dynamic segments).
- Text: menu chapter-name letter tiles (ids ~1977-2165, 2419-2435, 2530-2605), A-Z blocks (2876-2906), newspapers
  (3403-3406), title logo tiles, intro legal/logo screens, "The Weasels" (1821), EXIT (4089/4090).
- Skyboxes (35 views of 60x30 tiles) are plain colour grids; fine at a distance.

## For the morning
- Play https://andrewnakas.github.io/conker-cleanroom/ : boot, save select, intro, first area. Report what is unreadable
  or wrong first (signs, faces, HUD).
- Voices are placeholder Piper TTS by pitch band (deep/low/mid/high/female/squeaky), not per character.
  Practice pack (dirty, never publish): `python -m games.conker.voices practice D:/n64work/conker/baserom.us.z64 D:/n64work/conker/practice`
  then record each track and `python -m games.conker.voices cut <recording.wav> <track>`.
- Decide whether shipping the game's own program code (see "Note on scope") is OK for this title.
