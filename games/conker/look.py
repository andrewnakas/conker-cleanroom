"""Dev: boot a ROM from the dev site in headless Edge and write one contact sheet.

    python -m games.conker.look <rom name in devsite> [script] [--port 8131]

script is cdp_shot's ("15:shot,40:shot,45:Enter:0.3,70:shot"). Prints the sheet path.
"""
import os
import subprocess
import sys

from PIL import Image

DEV = "D:/n64work/conker"


def main(argv):
    rom = argv[1]
    script = argv[2] if len(argv) > 2 and not argv[2].startswith("--") else "15:shot,40:shot,45:Enter:0.3,70:shot"
    out = f"{DEV}/shots/{os.path.splitext(rom)[0]}"
    r = subprocess.run([sys.executable, "ports/ejs/cdp_shot.py", out, "--url",
                        f"http://localhost:8131/index.html?rom={rom}&hb=1", "--script", script, "--gpu", "--port", "9351"],
                       capture_output=True, text=True)
    print((r.stdout + r.stderr).strip().splitlines()[-1])
    shots = sorted((f for f in os.listdir(out) if f.startswith("shot_")), key=lambda f: float(f[5:-4]))
    if not shots:
        return
    w = 480
    ims = [Image.open(f"{out}/{f}").convert("RGB") for f in shots]
    ims = [i.crop((int(i.width * 0.19), 0, int(i.width * 0.81), int(i.height * 0.6))) for i in ims]
    ims = [i.resize((w, int(i.height * w / i.width))) for i in ims]
    cols = min(4, len(ims))
    rows = (len(ims) + cols - 1) // cols
    s = Image.new("RGB", (w * cols, ims[0].height * rows))
    for k, i in enumerate(ims):
        s.paste(i, ((k % cols) * w, (k // cols) * ims[0].height))
    s.save(f"{out}/sheet.png")
    print(f"{out}/sheet.png", [f[5:-4] for f in shots])


if __name__ == "__main__":
    main(sys.argv)
