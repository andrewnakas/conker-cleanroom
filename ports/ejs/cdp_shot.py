"""Dev tool: drive the EmulatorJS page in headless Edge over CDP; real key events, page screenshots.

    python ports/ejs/cdp_shot.py <out dir> --url http://localhost:8093/index.html?rom=clean.z64
        --script "10:shot,12:Enter:0.2,14:shot,16:x:0.2,..." [--webgl] [--wait 60]

Times are seconds after the page logs "CBFD: game started". Keys: Enter, x, c, z, s, q,
ArrowUp/Down/Left/Right, i, j, k, l (see ports/ejs/index.html for the N64 mapping).
Writes shot_<t>.png, console.txt and prints a one-line summary.
"""
import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
VK = {"Enter": 13, "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40, "Shift": 16, " ": 32}
CODE = {"Enter": "Enter", "ArrowLeft": "ArrowLeft", "ArrowUp": "ArrowUp", "ArrowRight": "ArrowRight",
        "ArrowDown": "ArrowDown", " ": "Space"}


def keyinfo(k):
    if len(k) == 1:
        return dict(key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()), nativeVirtualKeyCode=ord(k.upper()))
    return dict(key=k, code=CODE.get(k, k), windowsVirtualKeyCode=VK[k], nativeVirtualKeyCode=VK[k])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--url", required=True)
    ap.add_argument("--script", default="10:shot")
    ap.add_argument("--webgl", action="store_true", help="software WebGL (SwiftShader, slow)")
    ap.add_argument("--gpu", action="store_true", help="hardware WebGL via ANGLE/D3D11 (fast)")
    ap.add_argument("--wait", type=float, default=None)
    ap.add_argument("--port", type=int, default=9341)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for f in os.listdir(a.out):
        if f.startswith("shot_"):
            os.remove(os.path.join(a.out, f))
    ev = []
    for item in a.script.split(","):
        parts = item.split(":")
        t = float(parts[0])
        if parts[1] == "shot":
            ev.append((t, "shot", parts[0]))
        else:
            dur = float(parts[2]) if len(parts) > 2 else 0.15
            ev.append((t, "down", parts[1]))
            ev.append((t + dur, "up", parts[1]))
    ev.sort(key=lambda e: e[0])
    wait = a.wait or (ev[-1][0] + 30)
    prof = tempfile.mkdtemp(prefix="cdpshot_")
    args = [EDGE, "--headless=new", f"--user-data-dir={prof}", f"--remote-debugging-port={a.port}", "--remote-allow-origins=*",
            "--no-first-run", "--autoplay-policy=no-user-gesture-required", "--window-size=960,760",
            "--disable-renderer-backgrounding", "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows", "--disable-features=CalculateNativeWinOcclusion"]
    if os.environ.get("CDP_MUTE"):
        args.append("--mute-audio")
    if a.webgl:
        args += ["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"]
    if a.gpu:
        args += ["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-webgl"]
    p = subprocess.Popen(args + ["about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    console, shots = [], 0
    try:
        for _ in range(80):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{a.port}/json"))
                break
            except OSError:
                time.sleep(0.25)
        tab = next(t for t in tabs if t.get("type") == "page")
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30)
        n = [0]
        pending = {}

        def send(method, **params):
            n[0] += 1
            ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
            return n[0]

        send("Runtime.enable")
        send("Page.enable")
        # headless pages can look hidden/unfocused and EmulatorJS then pauses: pin them visible + focused
        send("Emulation.setFocusEmulationEnabled", enabled=True)
        send("Page.addScriptToEvaluateOnNewDocument", source=(
            "Object.defineProperty(document,'hidden',{get:()=>false});"
            "Object.defineProperty(document,'visibilityState',{get:()=>'visible'});"
            "document.hasFocus=()=>true;"
            "for (const t of ['visibilitychange','blur','pagehide','freeze'])"
            "{window.addEventListener(t,e=>e.stopImmediatePropagation(),true);"
            "document.addEventListener(t,e=>e.stopImmediatePropagation(),true);}"))
        send("Page.navigate", url=a.url)
        t_start = time.time()
        t0 = None
        ws.settimeout(0.05)
        i = 0
        while time.time() - t_start < wait:
            try:
                m = json.loads(ws.recv())
                if m.get("method") == "Runtime.consoleAPICalled":
                    txt = " ".join(str(x.get("value", x.get("description", ""))) for x in m["params"]["args"])
                    if "Translation not found" not in txt:
                        console.append(f"{time.time() - t_start:6.1f} {txt[:300]}")
                    if t0 is None and "CBFD: game started" in txt:
                        t0 = time.time()
                        for typ in ("mousePressed", "mouseReleased"):      # focus the game element
                            send("Input.dispatchMouseEvent", type=typ, x=480, y=300, button="left", clickCount=1)
                elif m.get("method") == "Runtime.exceptionThrown":
                    console.append("EXCEPTION " + m["params"]["exceptionDetails"].get("text", "")[:200])
                elif m.get("id") in pending and "result" in m:
                    tag = pending.pop(m["id"])
                    open(os.path.join(a.out, f"shot_{tag}.png"), "wb").write(base64.b64decode(m["result"]["data"]))
                    shots += 1
            except websocket.WebSocketTimeoutException:
                pass
            if t0 is None:
                continue
            while i < len(ev) and time.time() - t0 >= ev[i][0]:
                t, kind, arg = ev[i]
                if kind == "shot":
                    pending[send("Page.captureScreenshot", format="png")] = arg
                else:
                    info = keyinfo(arg)
                    send("Input.dispatchKeyEvent", type="keyDown" if kind == "down" else "keyUp", **info)
                i += 1
            if i >= len(ev) and not pending:
                break
    finally:
        p.kill()
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    open(os.path.join(a.out, "console.txt"), "w", encoding="utf-8").write("\n".join(console))
    print(f"{shots} screenshots, {len(console)} console lines, started={'yes' if t0 else 'NO'} -> {a.out}")


if __name__ == "__main__":
    main()
