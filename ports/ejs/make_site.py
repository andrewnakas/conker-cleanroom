"""Assemble the web site: EmulatorJS runtime + mupen64plus_next core + our page + clean ROM.

    python ports/ejs/make_site.py <clean rom .z64> <emulatorjs dir> <site dir>

Refuses a ROM whose SHA1 is the retail one (never publish retail data).
"""
import hashlib
import os
import shutil
import sys

RETAIL_SHA1 = ("ded6ee166e740ad1bc810fd678a84b48e245ab80", "1fe1632098865f639e22c11b9a81ee8f29c75d7a")
HERE = os.path.dirname(os.path.abspath(__file__))

NOTICE = """# Third-party runtime in this site

- EmulatorJS 4.2.3 (`data/`), GPL-3.0: https://github.com/EmulatorJS/EmulatorJS (license: `data/LICENSE.EmulatorJS`)
- libretro mupen64plus-next core (`data/cores/mupen64plus_next-*.data`), GPL-2.0:
  source https://github.com/libretro/mupen64plus-libretro-nx (built by the EmulatorJS project)
- `bk.z64` is built from the n64decomp/banjo-kazooie decompilation with every ROM-extracted asset regenerated
  (see https://github.com/andrewnakas/bk-cleanroom).
"""


def main(argv):
    rom, ejs, site = argv[1], argv[2], argv[3]
    data = open(rom, "rb").read()
    if hashlib.sha1(data).hexdigest() in RETAIL_SHA1:
        sys.exit("refusing: that is the retail ROM")
    if os.path.exists(site):
        for n in os.listdir(site):
            if n == ".git":
                continue
            p = os.path.join(site, n)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    os.makedirs(site, exist_ok=True)
    shutil.copytree(os.path.join(ejs, "data"), os.path.join(site, "data"), dirs_exist_ok=True)
    shutil.copyfile(os.path.join(ejs, "LICENSE"), os.path.join(site, "data", "LICENSE.EmulatorJS"))
    shutil.copyfile(os.path.join(HERE, "index.html"), os.path.join(site, "index.html"))
    open(os.path.join(site, "bk.z64"), "wb").write(data)
    open(os.path.join(site, "THIRD_PARTY.md"), "w").write(NOTICE)
    open(os.path.join(site, ".nojekyll"), "w").close()
    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(site) for f in fs)
    print(f"site: {site} ({total // 1024} KB), rom sha1 {hashlib.sha1(data).hexdigest()[:12]}")


if __name__ == "__main__":
    main(sys.argv)
