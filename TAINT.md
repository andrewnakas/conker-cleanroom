# Taint scan evidence

Verbatim output of the last taint scan saved in the local work directory, committed as evidence.
It was not re-run for this commit; check the log date against the date of the published build.

Command: `python -m games.conker.taint <retail rom> <clean rom> (inside the publish script; log = D:/n64work/conker/work/publish.log)`

Live-build check (2026-10-19): the published `conker.z64` (git blob 8a94785ece) equals `D:/n64work/conker/build/conker.z64`, sha1 951bd1962a3d, the ROM named in this log.

## `publish.log` (written 2026-10-02 03:05)

```
textures: 7760 regenerated (536 drawn)
font: 95 glyphs redrawn
sprites: bank 00 regenerated
audio: wave table resynthesised
voices: 453 placeholder streams, 0 silent fillers
flat stream 8826077/9494881 bytes
clean rom -> D:/n64work/conker/build/conker.z64 sha1 951bd1962a3d
taint: 21565 streams; FAILING (>= 32 B shared run): 0
  flat 7760/0 fail, flat.rgba 7760/0 fail, sprite 56/0 fail, font 1/0 fail, adpcm 2258/0 fail, book 2786/0 fail, loop 491/0 fail, mp 453/0 fail
site: D:/n64work/conker/site (641056 KB), rom sha1 951bd1962a3d
patch_core: CBFD settings entry -> md5 714362fe5537edb9e0201388f9e0735a
remote: warning: See https://gh.io/lfs for more information.        
remote: warning: File conker.z64 is 64.00 MB; this is larger than GitHub's recommended maximum file size of 50.00 MB        
remote: warning: GH001: Large files detected. You may want to try Git Large File Storage - https://git-lfs.github.com.        
pushed gh-pages
```
