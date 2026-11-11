#!/bin/sh
# Cross-container attach: the VM runs over TCP on the docker0 gateway, a second container of
# the same image (its baked art98 is old, so the checkout's core/art98 is mounted over it: code, not work/) attaches with ONLY a client art98.toml and the token file mounted (never work/).
# Usage, from the repo root, with Docker reachable and ART98_TRANSPORT unset:
#   env -u DOCKER_HOST sg docker -c 'sh experiments/vm-service/probe_container_client.sh SCRATCH'
# SCRATCH is a new folder outside the repo. It is deleted at the end, token included.
set -eu
. .tools/env.sh
REPO=$(pwd)
S=$(readlink -f "${1:?scratch dir}")
trap 'rm -rf "$S"' EXIT
GW=$(ip -4 -o addr show docker0 | sed 's/.*inet \([0-9.]*\)\/.*/\1/')
ART=$REPO/.venv/bin/art98
pressure() { printf 'cpu %s: ' "$1"; grep some /proc/pressure/cpu; }
mkdir -p "$S/host" "$S/client"
cat > "$S/host/art98.toml" <<TOML
[vm]
transport  = "tcp"
token_file = "$S/keys/vm.token"
[ports]
bind = "$GW"
TOML
cat > "$S/client/art98.toml" <<TOML
[vm]
transport  = "tcp"
token_file = "vm.token"
[ports]
connect = "$GW"
TOML
pressure before
"$ART" vm stop
(cd "$S/host" && "$ART" vm start --work "$REPO/work")
cp "$S/keys/vm.token" "$S/client/vm.token"
run() {
  docker run --rm --security-opt label=disable -w /client \
    -v "$S/client/art98.toml:/client/art98.toml:ro" \
    -v "$S/client/vm.token:/client/vm.token:ro" \
    -v "$REPO/core/art98:/opt/art98/core/art98:ro" \
    --entrypoint "$@"
}
IMG=localhost/art98:latest
pressure "before ping"
run art98 $IMG ping 2>&1 | head -5 || true
pressure "after ping"
(cd "$S/host" && "$ART" vm status --work "$REPO/work")
run python3 $IMG -c '
import time
from art98 import service, settings
s = settings.load()
t = time.monotonic()
with service.attach(s) as session:
    session.vm.screenshot("/tmp/shot.png")
    print("screenshot bytes", len(open("/tmp/shot.png", "rb").read()))
print("attach+screenshot+release s", round(time.monotonic() - t, 2))
'
pressure "after attach"
"$ART" vm stop
"$ART" vm start
"$ART" vm status
pressure after
