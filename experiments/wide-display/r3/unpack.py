"""Zip-slip-checked extract of the driver zip. usage: python3 -I unpack.py ZIP EMPTY_DIR"""
import stat, sys, zipfile
from pathlib import Path, PurePosixPath

zpath, out = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
assert out.is_dir() and not any(out.iterdir()), "target must be an empty dir"
with zipfile.ZipFile(zpath) as z:
    for i in z.infolist():
        n = i.filename
        p = PurePosixPath(n)
        mode = i.external_attr >> 16
        bad = (n.startswith(("/", "\\")) or "\\" in n or ":" in n or ".." in p.parts
               or len(p.parts) != 1 or i.is_dir() or stat.S_ISLNK(mode))
        assert not bad, f"unsafe entry {n!r}"
        t = (out / n).resolve()
        assert t.parent == out, n
        t.write_bytes(z.read(i))
        print(n, i.file_size)
