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

## Next
- Texture census: format/size per flat id from display-list references, then grid+alpha regeneration.
- Fonts (RLE table 0x40F10), audio banks (bank 17), MP3 speech (bank 16, 453 streams), other banks census.

## For the morning
- (nothing yet)
