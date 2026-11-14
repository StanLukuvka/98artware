"""Probe R3b: can an in-guest step make Windows enumerate PCI so vmdisp9x binds to -vga std?

usage (host QEMU: `. .tools/env.sh`):
  python3 r3b.py prep PROBE          cold cirrus boot: put the R3 driver files in C:\\DRIVERS\\VMDISP (+DevicePath), diag, reboot
  python3 r3b.py drive PROBE [vga]   cold boot, obey lines appended to PROBE/cmd.txt (log PROBE/drive.out):
      keys a b | shot NAME | win | click X Y | type TEXT | py EXPR | exec STMT | tree KEY [DEPTH] | diag | reboot | quit
  python3 r3b.py observe PROBE [vga] cold boot, dump display state (R3's observe), reboot
PROBE holds vm/{golden.qcow2,image.json} (a copy, never a real work dir), ext/, shots/. Every boot goes through safe_boot.
Reuses r3.py's helpers (reg_*, dump_modes, wait_agent, reboot, make_vm).
"""

from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "r3"))
import r3  # noqa: E402
from art98.bridge import Bridge, BridgeError  # noqa: E402
from art98.protocol import Out  # noqa: E402
from r3 import HKLM, dump_modes, make_vm, reboot, reg_get, reg_open, reg_subkeys, say, wait_agent  # noqa: E402

REG_NAMES = {1: "SZ", 3: "BIN", 4: "DWORD"}


def reg_values(b: Bridge, key: str) -> dict:
    h, out, i = reg_open(b, key), {}, 0
    while h is not None:
        r = b.advapi32.RegEnumValueA(h, i, Out(260), struct.pack("<I", 260), 0, Out(4), Out(512), struct.pack("<I", 512))
        if r.value:
            break
        name = r.buffers[0].split(b"\0", 1)[0].decode("cp1252")
        typ = struct.unpack("<I", r.buffers[2])[0]
        raw = r.buffers[3]
        if typ == 4:
            val = struct.unpack("<I", raw[:4])[0]
        elif typ in (1, 2):
            val = raw.split(b"\0", 1)[0].decode("cp1252")
        else:
            val = raw.rstrip(b"\0").hex() or raw[:16].hex()  # lazy: binary length unknown (buffer padded to 512), trailing NULs trimmed
        out[name or "(default)"] = (REG_NAMES.get(typ, typ), val)
        i += 1
    if h is not None:
        b.advapi32.RegCloseKey(h)
    return out


def tree(b: Bridge, key: str, depth: int = 2, indent: str = "") -> list[str]:
    lines = [f"{indent}[{key.split(chr(92))[-1]}]"]
    for n, (t, v) in reg_values(b, key).items():
        lines.append(f"{indent}  {n} = {t}:{v}")
    if depth:
        for s in reg_subkeys(b, key):
            lines += tree(b, f"{key}\\{s}", depth - 1, indent + "    ")
    return lines


def diag(b: Bridge) -> None:
    say("Enum branches:", reg_subkeys(b, "Enum"))
    say("Enum\\Root:", reg_subkeys(b, r"Enum\Root"))
    for k in ("Enum\\BIOS", "Enum\\PCI"):
        say(k, reg_subkeys(b, k))
    for sub in reg_subkeys(b, r"Enum\Root"):
        if sub.upper().startswith("*PNP0C") or sub.upper().startswith("*PNP0A") or sub.upper() in ("SYSTEM", "*PNP0000", "*PNP0100", "*PNP0200", "*PNP0800", "*PNP0303"):
            say("\n".join(tree(b, f"Enum\\Root\\{sub}", 2)))
    cls = r"System\CurrentControlSet\Services\Class\System"
    say("Class\\System subkeys:", reg_subkeys(b, cls))
    for s in reg_subkeys(b, cls):
        say("\n".join(tree(b, f"{cls}\\{s}", 0)))
    say("DISPLAY:", dump_modes(b)["caps"])


def prep(probe: Path) -> None:
    vm = make_vm(probe, "cirrus", "prep")
    with vm as v:
        b = Bridge.connect(v.serial_path)
        try:
            if wait_agent(v, b, probe / "shots", "prep") is None:
                raise SystemExit("agent never answered")
            b.wait_ready()
            for d in ("C:\\DRIVERS", r3.DRV_DIR):
                say("mkdir", d, b.kernel32.CreateDirectoryA(d, 0).value)
            for f in sorted((probe / "ext").iterdir()):
                b.put_file(f"{r3.DRV_DIR}\\{f.name.upper()}", f.read_bytes())
            say("put done")
            diag(b)
            reboot(v, b)
        finally:
            b.close()


QC = {":": "shift semicolon", "\\": "backslash", ".": "dot", " ": "spc", "_": "shift minus", "-": "minus", "/": "slash"}


def type_text(v, text: str) -> None:
    for c in text:
        if c in QC:
            v.send_keys(*QC[c].split())
        elif c.isupper():
            v.send_keys("shift", c.lower())
        else:
            v.send_keys(c)


def click(v, x: int, y: int, w: int = 640, h: int = 480) -> None:
    ax, ay = x * 32767 // (w - 1), y * 32767 // (h - 1)
    ev = lambda down: [  # noqa: E731
        {"type": "abs", "data": {"axis": "x", "value": ax}},
        {"type": "abs", "data": {"axis": "y", "value": ay}},
        {"type": "btn", "data": {"button": "left", "down": down}},
    ]
    v.qmp.execute("input-send-event", events=ev(False)[:2])
    time.sleep(0.2)
    v.qmp.execute("input-send-event", events=ev(True))
    time.sleep(0.15)
    v.qmp.execute("input-send-event", events=ev(False))


def drive(probe: Path, vga: str) -> None:
    cmd = probe / "cmd.txt"
    cmd.write_text("")
    vm = make_vm(probe, vga, "drive")
    done, n = False, 0
    with vm as v:
        b = Bridge.connect(v.serial_path)
        ns = {"b": b, "v": v, "reg_subkeys": reg_subkeys, "reg_get": reg_get, "reg_values": reg_values, "tree": tree, "json": json, "struct": struct, "Out": Out, "HKLM": HKLM, "BridgeError": BridgeError}
        try:
            while not done and v.running:
                lines = cmd.read_text().splitlines()
                for line in lines[n:]:
                    a = line.split()
                    try:
                        if not a:
                            pass
                        elif a[0] == "keys":
                            v.send_keys(*a[1:])
                        elif a[0] == "shot":
                            say("shot", v.screenshot(probe / "shots" / f"{a[1]}.png"), r3.psi())
                        elif a[0] == "win":
                            say("win", [(w.class_name, w.title, w.visible) for w in b.windows()], r3.psi())
                        elif a[0] == "click":
                            click(v, int(a[1]), int(a[2]))
                        elif a[0] == "type":
                            type_text(v, line[5:])
                        elif a[0] == "tree":
                            say("\n".join(tree(b, a[1], int(a[2]) if len(a) > 2 else 1)))
                        elif a[0] == "diag":
                            diag(b)
                        elif a[0] == "dump":
                            say("DUMP", json.dumps({"info": r3.display_info(b), "display": dump_modes(b)}, default=str))
                        elif a[0] == "reboot":
                            reboot(v, b)
                        elif a[0] == "py":
                            say("py", repr(eval(line[3:], ns))[:3000])
                        elif a[0] == "exec":
                            exec(line[5:], ns)  # noqa: S102
                        elif a[0] == "quit":
                            done = True
                    except Exception as e:  # noqa: BLE001
                        say("ERR", line, repr(e)[:300])
                    say("did", line)
                n = len(lines)
                time.sleep(0.5)
        finally:
            b.close()


if __name__ == "__main__":
    c, probe = sys.argv[1], Path(sys.argv[2]).resolve()
    vga = sys.argv[3] if len(sys.argv) > 3 else "std"
    if c == "prep":
        prep(probe)
    elif c == "drive":
        drive(probe, vga)
    else:
        r3.observe(probe, vga)
