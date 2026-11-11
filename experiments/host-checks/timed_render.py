"""Run `art98 render` with Bridge.sync and put_file timed, and write the timings as JSON.

    . .tools/env.sh
    .venv/bin/python experiments/host-checks/timed_render.py TIMINGS.json -- render FILE ...

The arguments after `--` go to art98's CLI. `sync` gives up silently after its
timeout (500 ms per window, a SendMessageTimeout in the guest agent) and still
replies OK, so the host cannot see a give-up directly. A call that takes about
the timeout or longer is the sign of one, and is counted here.
"""

import json
import sys
import time

from art98 import bridge, cli

out, args = sys.argv[1], sys.argv[sys.argv.index("--") + 1:]
log = {"sync": [], "put_file": [], "timeouts": []}

real_sync, real_put = bridge.Bridge.sync, bridge.Bridge.put_file


def sync(self, hwnd=0, timeout_ms=500):
    t = time.monotonic()
    try:
        return real_sync(self, hwnd, timeout_ms)
    except bridge.BridgeTimeout as e:
        log["timeouts"].append(f"sync: {e}")
        raise
    finally:
        log["sync"].append([round(time.monotonic() - t, 4), hwnd])


def put_file(self, path, data):
    t = time.monotonic()
    real_put(self, path, data)
    log["put_file"].append([path, len(data), round(time.monotonic() - t, 4)])


bridge.Bridge.sync, bridge.Bridge.put_file = sync, put_file
real_request = bridge.Bridge.request


def request(self, *a, **k):
    try:
        return real_request(self, *a, **k)
    except bridge.BridgeTimeout as e:
        log["timeouts"].append(f"request {a[:1]}: {e}")
        raise


bridge.Bridge.request = request
code = 1
try:
    code = cli.main(args)
finally:
    with open(out, "w") as f:
        json.dump(log, f)
sys.exit(code)
