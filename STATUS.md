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

## Open problems
- **System font (RLE table at ROM 0x40F10)**: the redrawn table makes the boot go black. Under test: checksum over the
  boot segment vs. my table being shorter than retail (walk past the end).
- Speech (bank 16, 453 MP3 streams, ~2 h): Whisper small.en on CPU is transcribing (GPU has no CUDA libs);
  then Piper placeholders (`voices.py`), encode, taint.
- Game code cannot be recompressed (black screen), so no code patches for now.

## Next
- Texture census: format/size per flat id from display-list references, then grid+alpha regeneration.
- Fonts (RLE table 0x40F10), audio banks (bank 17), MP3 speech (bank 16, 453 streams), other banks census.

## For the morning
- (nothing yet)
