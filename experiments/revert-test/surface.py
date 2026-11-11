"""Throwaway: what flips the screenshot between the 255 and the 248 colours, and the pointer on and off?"""

import faulthandler
import sys
import time
from pathlib import Path

faulthandler.dump_traceback_later(80, exit=True)
from art98.session import boot_local as boot
from art98.session import private_stage
from PIL import Image

OUT = Path(sys.argv[1])
OUT.mkdir(exist_ok=True)
n = 0


def shot(vm, label):
    global n
    n += 1
    p = OUT / f"s{n:02}.ppm"
    vm.screenshot(p, format="ppm")
    im = Image.open(p).convert("RGB")
    c = sorted(im.getcolors(1 << 20))
    top = c[-1][1]
    print(
        f"{n:2} {label:40} {im.size} top {top} white {max(k[0] for _, k in c if k[0] == k[1] == k[2])}",
        flush=True,
    )
    return im


with private_stage("work") as stage, boot(stage) as s:
    g, vm = s.bridge, s.vm
    shot(vm, "fresh boot")
    time.sleep(1)
    shot(vm, "fresh boot, 1 s later")
    g.user32.SetCursorPos(300, 300)
    g.sync()
    time.sleep(0.3)
    shot(vm, "after SetCursorPos")
    g.spawn("notepad.exe")
    g.find_window(class_name="Notepad")
    time.sleep(0.5)
    shot(vm, "notepad open")
    g.set_display_mode(640, 480, 16, persist=False)
    time.sleep(0.3)
    shot(vm, "640x480x16")
    g.set_display_mode(800, 600, 16, persist=False)
    time.sleep(0.3)
    shot(vm, "back to 800x600x16")
    vm.load_snapshot("ready")
    g.ping()
    time.sleep(0.3)
    shot(vm, "after revert 1")
    g.set_display_mode(640, 480, 16, persist=False)
    time.sleep(0.3)
    shot(vm, "after revert, 640x480x16")
    g.set_display_mode(800, 600, 16, persist=False)
    time.sleep(0.3)
    shot(vm, "after revert, back to 800x600")
    vm.load_snapshot("ready")
    g.ping()
    time.sleep(0.3)
    shot(vm, "after revert 2")
    g.spawn("notepad.exe")
    g.find_window(class_name="Notepad")
    time.sleep(0.5)
    shot(vm, "after revert, notepad")
print("done")
