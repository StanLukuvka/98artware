"""A minimal VIEW-ONLY RFB 3.8 client: handshake, security None, ClientInit shared=1, then a loop of
FramebufferUpdateRequest. Raw encoding only (the most work for the server). It never sends a key or
pointer event.

usage: rfb_viewer.py HOST PORT MODE [SECONDS]     MODE: stay | reconnect (every ~0.5 s)
Prints one stats line when SECONDS pass (default: runs until killed; stats on SIGTERM).
"""

import signal
import socket
import struct
import sys
import time


def recv(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(n - len(buf), 1 << 20))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def connect(host, port):
    sock = socket.create_connection((host, port), 5)
    recv(sock, 12)  # "RFB 003.008\n"
    sock.sendall(b"RFB 003.008\n")
    count = recv(sock, 1)[0]
    types = recv(sock, count)
    assert 1 in types, f"no security None in {list(types)}"
    sock.sendall(b"\x01")  # security None
    assert struct.unpack(">I", recv(sock, 4))[0] == 0, "security failed"
    sock.sendall(b"\x01")  # ClientInit shared=1
    w, h = struct.unpack(">HH", recv(sock, 4))
    pixfmt = recv(sock, 16)
    recv(sock, struct.unpack(">I", recv(sock, 4))[0])  # desktop name
    bpp = pixfmt[0] // 8
    sock.sendall(struct.pack(">BxHi", 2, 1, 0))  # SetEncodings: Raw only
    return sock, w, h, bpp


def request(sock, w, h, incremental):
    sock.sendall(struct.pack(">BBHHHH", 3, incremental, 0, 0, w, h))


def read_update(sock, bpp):
    """One server message; returns the number of rectangles, bytes read."""
    kind = recv(sock, 1)[0]
    if kind == 0:
        n = struct.unpack(">xH", recv(sock, 3))[0]
        size = 0
        for _ in range(n):
            _x, _y, w, h, enc = struct.unpack(">HHHHi", recv(sock, 12))
            if enc != 0:
                raise ValueError(f"unexpected encoding {enc}")
            size += len(recv(sock, w * h * bpp))
        return n, size
    if kind == 2:
        return 0, 0
    if kind == 3:
        recv(sock, 3)
        recv(sock, struct.unpack(">I", recv(sock, 4))[0])
        return 0, 0
    raise ValueError(f"unexpected message {kind}")


stats = {"connects": 0, "updates": 0, "rects": 0, "bytes": 0}


def report(*_):
    print(" ".join(f"{k}={v}" for k, v in stats.items()), flush=True)
    sys.exit(0)


def main():
    host, port, mode = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    end = time.monotonic() + float(sys.argv[4]) if len(sys.argv) > 4 else None
    signal.signal(signal.SIGTERM, report)
    while end is None or time.monotonic() < end:
        sock, w, h, bpp = connect(host, port)
        stats["connects"] += 1
        stop = time.monotonic() + 0.5 if mode == "reconnect" else None
        request(sock, w, h, 0)
        while stop is None or time.monotonic() < stop:
            n, size = read_update(sock, bpp)
            stats["updates"] += 1
            stats["rects"] += n
            stats["bytes"] += size
            request(sock, w, h, 1)
        sock.close()
    report()


main()
