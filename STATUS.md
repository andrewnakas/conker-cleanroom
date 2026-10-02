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

## Update 2026-10-01 ~13:15 (second publish)
- All 453 speech streams transcribed (`spec/voices.json`, Whisper small.en on CPU) and replaced by Piper placeholders
  with the lip-sync cues re-attached; no fillers left. Taint still **0 failing of 21,565**; Pages "built".
- Re-typeset text (`text_briefs.json`, ~90 textures): signs, posters, gravestones, labels, A-Z name-entry blocks,
  newspapers, NEW GAME / OPTIONS / PLAY. Eyes (`face_briefs.json`, 54 textures) drawn from coarse briefs
  (`eyefit.py`): Conker's eyes verified in-game (blue iris, pupil, highlight).
- Conker's face frames 1934-1945 are fur with a cut-out eye hole (kept alpha), so they need no brief.
- Dev server port is 8137 now (another session took 8131: its page answered "problem loading rom").

## Update 2026-10-01 ~13:45 (third publish)
- 182 textures drawn (text briefs + eye/face briefs incl. hand-written whole faces); taint 0 failing; pushed.
- In-game: tavern patrons' and Conker's eyes are drawn correctly (boot, Rareware scene, save select).
- Headless emulation is very slow while other sessions build (6.5 min of wall time = still in the logo scene), so
  nothing past the intro has been checked in-game yet. Re-run `python -m games.conker.look clean.z64 "<script>"`
  (dev server: `python ports/wasm/serve.py D:/n64work/conker/devsite 8137`) when the machine is idle.

## Update 2026-10-01 ~14:40
- **Gameplay verified** in headless Edge on the clean ROM: after the (unskippable; Start only pauses) intro, Conker is
  controllable in the first area (field, fence, scarecrow, signpost) and walks with the stick keys. About 10 min
  from boot to control: script `"50:Enter:0.3,80:Enter:0.3,90:x:0.3,100:x:0.3,...600:shot,605:ArrowUp:6,..."`.
- Pause menu lettering (PAUSED, EXIT, CONT.., Y/N) is not re-typeset: ids not found yet (EXIT shows a grey block,
  CONT.. keeps the retail letter shapes through its alpha outline).
- More sign briefs: stone ROCK SOLID (454-456), LIGHTER FLUID, WARNING, Booze.

## Update 2026-10-01 ~15:10 (menus)
- Fourth publish done (188 drawn, taint 0). Then: the whole menu label set (ids 1977-2165: CONT.., EXIT, ERASE, PLAY,
  RESTART, SET-UP, Y/N, chapter names BARN BOYS / BATS TOWER / SLOPRANO / UGA BUGA / SPOOKY / IT'S WAR / HEIST /
  HUNGOVER / WINDY, multiplayer words, GAME 1-3) is re-typeset as spans over their 32x32 RGBA32 tiles
  (stored top-down: `"flip": false`). 18 blank-looking tiles there were mis-guessed CI8: fixed in `layout_overrides.json`.
  Checked on a clean sheet only; a text is split evenly over its tiles, which assumes the game draws them side by side.
- Not identified: 2136-2138 (a green team name), 2080/2081, 2020-2022, 1985/1987, OPTIONS dim (2001/2002), "PAUSED".

## Update 2026-10-01 ~15:20 (fifth publish, loop stopped)
- Published with the menu labels; taint 0 failing. In-game: "GAME 1", "NEW GAME", pause "EXIT" / "CONT.." read
  cleanly and their tiles join correctly. "PAUSED" (3D letters with a blurred texture) is still unreadable.
- Loop stopped here: what is left needs either the tile arrangement of the title logo / splash screens
  (ids 2415-2440, 2530-2608) or play-testing deeper than the first area. Restart with /loop to continue.

## Update 2026-10-01 evening (sixth publish 22:41 after the user said to push)
- The first push attempt was denied by the auto-mode permission check; the user then said "keep on going and push".
  Sixth publish: rom sha1 e3a01bd188bd, taint 0 failing of 21,565.
- GAME OVER (2481-2504 white layer 8x3, 2505-2525 red layer 7x3, 32x32 tiles) re-typeset as screens; 2441-2460
  (Conker portrait, 5x4) and 2461-2480 ("CONKER 64" logo) look like unused leftovers and are left as grids.
- New dev tool, **id tiles**: `CONKER_IDS=guess python -m games.conker.generate <retail> devsite/ids.z64` prints the flat id on
  every not-yet-identified tile (white line = first stored row), so one screenshot gives the tile arrangement and
  orientation. `python -m games.conker.mosaic <rom> out.png <ids> r<rows>` lays tiles out (column-major).
- Tiled pictures solved this way and re-typeset as whole screens (`"_screens"` in `text_briefs.json`, ids run down each
  column): NINTENDO / PRESENTS (2530-2547, 9x2 of 32x64 RGBA16), A RAREWARE GAME (2568-2585, 9x2), STARRING CONKER & BERRI
  (2586-2609, 8x3), PRESS START + its shadow layer (2558-2567 / 2548-2557, 5x2 of 32x32). 22 tiles of those sets had a
  wrong guessed layout (fixed in `layout_overrides.json`).
- PAUSED (2193-2195), Dolby label (1756), GREENS, HAY, WAR, COLORS, Ai, HEIST, LAPS, MULTI, TANK, P1-P4, numerals 1-9,
  "?", Dino / Poops / War, FECK OFF CROWS signs, FEDERAL RESERVE: re-typeset. BOSS was stored top-down (fixed).
- Verified in-game (headless, clean ROM): NINTENDO PRESENTS, both intro cards and PAUSED read cleanly. Not yet seen
  in-game: PRESS START, the new menu labels.
- Local build `devsite/clean.z64` (455 drawn textures): taint **0 failing of 21,565**. Ready to publish once allowed.

- First-area walk on this build (headless, ~13 min): Conker is controllable and the field, fence and scarecrow render
  fine; emulation was too slow under load to reach any sign or character. Loop stopped: waiting on the publish.

## Update 2026-10-01 ~23:20 (seventh publish live; eighth NOT published)
- Seventh publish 22:56 (GAME OVER, rom sha1 36afb4895143, taint passed). Source `main` pushed too.
- Verified in-game on that build: multiplayer menu MULTI / WAR / SET-UP / COLORS read cleanly.
- **Eighth publish did not happen**: Claude Code stopped the job (system low on memory) before the push. Run
  `bash games/conker/publish.sh` when RAM is free. Committed but not yet live: TOTAL WAR pills (1984-1987, the left half still showed retail lettering through its
  alpha), ON / OFF bubbles (1988/1989), CHEATS (1997/1998), BATS (1974-1976), dim COLORS (1999/2000).

## Update 2026-10-02 ~01:10 (blocked on memory)
- The machine is out of memory (taint scan died with MemoryError, git/bash could not fork). Heavy work paused.
- The eighth build (rom sha1 522c4d173002) passed taint in the 23:17 run and is committed in `D:/n64work/conker/site`
  (57f3705). **Pushed 2026-10-02 ~01:50** (eighth publish live). RAM still tight (7 GB free): light work only.

## Update 2026-10-02 ~02:20 (committed, waiting for RAM to publish)
- Text briefs can now be placed with `"box": [x0,y0,x1,y1]` (fractions of the upright picture).
- New since the eighth publish (contact sheets only, not built/tainted yet): B pads (92, 1575, 2847), timer 00:00 (3436),
  target (4389), clocks (7179-7182), fire icon (2858), TNT barrel (876/877), $ bag, 4 HIRE / 4 PLAY signs, blueprint
  and plan labels (1061, 1063, 3594-3599), manual cover WHAT TO DO (7741-7744, 2x2 guessed).
- Left as grids: tavern sign pieces 1505-1508, Conker icon 1560, portrait 3408, manual body pages.
- Publish when free RAM is back above ~10 GB (at 6 GB the taint scan dies with MemoryError).

## Update 2026-10-02 ~02:50 (ninth publish live)
- Ninth publish 02:32: rom sha1 c8f65a990e8f, taint 0 failing of 21,565; boots to save select (headless check).
  Contains everything listed in the 02:20 update.
- `publish.sh` now keeps the site repo at a single commit and gc's it (it had grown to 578 MB).
- After that publish: Dolby logo is two tiles (1755 + 1756); the left one still showed retail lettering through its
  alpha. Now one span "DOLBY SURROUND" (committed, goes out with the next publish).

## Update 2026-10-02 ~03:10 (tenth publish live, loop stopped)
- Tenth publish: rom sha1 951bd1962a3d, taint 0 failing of 21,565, with the Dolby span. Site repo is one commit (62 MB).
- Headless play-testing is unreliable under load: a 13 min run only reached save select and the timed key presses
  missed. Nothing past the menus / first field has been verified in-game. Needs a person playing the site.

## Open problems
- Title logo (ids 2415-2440): each 3D letter is its own object made of 2-4 tiles that fly in during the throne-room
  scene, too small to map with id tiles. It keeps colour grid + letter silhouette (alpha outline). Same for the
  Rareware badge lettering (2461-2525) and the Conker portrait mosaic (2441-2460).
- Whole-face textures (Berri 815-817, grey squirrel 965-969/1757-1758, frogs 3690-3695, sunflower 4305-4307,
  two-eye strips, Conker close-ups 7705/7706) now have hand-written briefs (approximate positions; checked on a
  clean sheet only, not in-game).
- In-game checks so far cover boot, menus and the intro only; signs are checked on contact sheets, audio is not
  listened to (only: no hang).
- Game code cannot be recompressed (black screen), so no code patches.
- Machine ran out of RAM around noon; heavy jobs are run one at a time.

## Next
- Eyes: lids and two-eye textures in `eyefit.py`; Conker's own face frames (64x32 CI4, dynamic segments).
- Text: menu chapter-name letter tiles (ids ~1977-2165, 2419-2435, 2530-2605), A-Z blocks (2876-2906), newspapers
  (3403-3406), title logo tiles, intro legal/logo screens, "The Weasels" (1821), EXIT (4089/4090).
- Skyboxes (35 views of 60x30 tiles) are plain colour grids; fine at a distance.

## For the morning
- Unverified in-game (preview sheets only): GAME OVER, PRESS START, B pads, timer, target, clocks, fire icon, TNT,
  $ bag, 4 HIRE / 4 PLAY, plan labels, manual cover (2x2 layout guessed), TOTAL WAR / ON / OFF / CHEATS / BATS.
- Play https://andrewnakas.github.io/conker-cleanroom/ : boot, save select, intro, first area. Report what is unreadable
  or wrong first (signs, faces, HUD).
- Voices are placeholder Piper TTS by pitch band (deep/low/mid/high/female/squeaky), not per character.
  Practice pack is built (dirty, never publish): `D:/n64work/conker/practice` = 34 call-and-response tracks,
  1795 phrases, `SCRIPT.txt`. Record each track and `python -m games.conker.voices cut <recording.wav> <track>`.
- Decide whether shipping the game's own program code (see "Note on scope") is OK for this title.
