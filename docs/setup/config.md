# Configuration: art98.toml

`art98.toml` at the repository root holds the names, the work folder and the ports that
`art98 vm`, `render` and `ping` use. Every key is optional. The file in the repository shows
the everyday keys with their defaults, and nothing else. Three more, `[vm] transport`, `[vm] token_file` and
`[ports] connect`, are left out of it: they are for
[attaching from another container](#attach-from-another-container).

```toml
[vm]
container = "art98-vm"                 # name of the long-lived container
image     = "localhost/art98:latest"   # image built by `art98 up`
work      = "work"                     # prepared image, vm.token, vm.cid; relative to this file

[ports]                                # HOST side; fixed per purpose, a taken port is an error
bind      = "127.0.0.1"                # interface for every published port
control   = 7598                       # control/agent port, published only when the transport is tcp
vnc       = 5900                       # `art98 vm start --vnc`
setup_vnc = 5998                       # `art98 up --watch`
```

## Where the file is found

art98 looks for the first `art98.toml` in the current folder, then in each folder above it,
and stops at the first one it finds. With none, the defaults below are used.

A file with an unknown section, an unknown key, a value of the wrong type or a port outside
1 to 65535 stops the command with an `error:` line that names the file and the key.

## Precedence

From lowest to highest:

1. The built-in defaults.
2. `art98.toml`.
3. `ART98_IMAGE`, which sets `[vm] image` only, and `ART98_TRANSPORT`, which sets `[vm] transport` only.
4. The `--work DIR` flag of the command.

A relative `work` in the file is taken from the folder that holds the file. A relative
`--work` is taken from the current folder.

## Keys

| Key | Default | Meaning |
|-----|---------|---------|
| `[vm] container` | `art98-vm` | Name of the long-lived container that runs the VM. |
| `[vm] image` | `localhost/art98:latest` | The image `art98 up` builds. `ART98_IMAGE` overrides it. |
| `[vm] work` | `work` | The work folder: the prepared image, `vm.token` and `vm.cid`. |
| `[vm] transport` | `unix` on Linux, `tcp` elsewhere | How a client reaches the VM service: `"unix"` or `"tcp"`. `ART98_TRANSPORT` overrides it. |
| `[vm] token_file` | `<work>/vm.token` | Where the token is kept. A relative path is taken from the folder that holds this file; an absolute path is kept as it is, and `~` is expanded. `art98 vm start` creates the file if it is missing (mode 0600, with any missing parent folders), and clients read it from there. A token file outside `work/` is mounted read-only into the VM's container. |
| `[ports] bind` | `127.0.0.1` | The host interface for the VM's published ports: `control` (only when the transport is tcp) and `vnc`. `art98 up --watch` publishes the setup screen on it too. Give an IPv4 address: an IPv6 address in brackets isn't handled. |
| `[ports] connect` | `bind`, or `127.0.0.1` when `bind` is `0.0.0.0` or `::` | The host a client dials to reach `control`. `bind` still says where `vm start` publishes the port; `connect` only matters to clients. |
| `[ports] control` | `7598` | The host port for the control and agent channels, when the transport is tcp. The transport is a Unix socket on Linux, so the port is not published there. Inside the container the port is always 7598. |
| `[ports] vnc` | `5900` | The host port for `art98 vm start --vnc`. |
| `[ports] setup_vnc` | `5998` | The host port for `art98 up --watch`. |

A running VM keeps the ports it was started with. To change `[ports]`, run `art98 vm stop`,
then `art98 vm start`.

## Files the VM uses

| Path | Made by | Removed by | What it is |
|------|---------|------------|------------|
| `$XDG_RUNTIME_DIR/art98/<container>-<hash8>/` | `art98 vm start` | `art98 vm start` and `vm stop` | The Unix socket `serve.sock`, and the screenshots written into the folder. `hash8` is the first 8 hex digits of the SHA-256 of the work folder's absolute path, so two checkouts never share a folder. Without `XDG_RUNTIME_DIR` the folder is under the system temp directory. |

`vm.token` and `vm.cid` are in `work/` unless `[vm] token_file` says otherwise: see
[the work directory](cli.md#the-work-directory). The token is the one real secret: it lets a
client run any Win32 call in the guest.

## VNC

`art98 vm start --vnc` shows the screen at `<bind>:<vnc>`, `127.0.0.1:5900` by default. There
is no password, so keep it on loopback.

Connect a viewer in **view-only** mode. A normal viewer sends its keys and mouse to the guest,
which changes what the VM does and so the recording. A view-only viewer did not change the
frames in the probe (see [experiments/vm-service](../../experiments/vm-service/README.md)).

The `--vnc` choice is fixed at start. Run `art98 vm stop`, then `art98 vm start`, to change it.

## Transport and a lost client

On Linux a client reaches the VM over a Unix socket by default, which frees the VM's lock as
soon as the client's process dies. Elsewhere, or with `[vm] transport = "tcp"` or
`ART98_TRANSPORT=tcp`, `vm start` publishes the TCP port `[ports] control` on `bind`, and clients
dial it on `connect`.

Over TCP both ends turn on keepalive: after 20 seconds of silence they send up to 3 probes,
10 seconds apart. So a client that vanishes without closing its connection, such as a container
that was killed, frees the lock in about a minute. A client that is alive but idle keeps it, as
on the Unix socket.

## Attach from another container

A client in a second container, for example an agent's container, can render on the VM without
seeing `work/`. It needs only a small `art98.toml` and the token file. Use TCP for this, and
plain IPv4 addresses.

1. **On the VM host**, put these keys in the `art98.toml` that `art98 vm start` will find, then
   start the VM (run `art98 vm stop` first if it is running, since the transport and ports are
   fixed at start):

   ```toml
   [vm]
   transport  = "tcp"
   token_file = "/srv/art98/vm.token"   # any path outside work/

   [ports]
   bind = "172.17.0.1"                  # an address the other container can reach
   ```

   `172.17.0.1` is Docker's usual `docker0` gateway: a container on the default network can
   reach it, the outside network can't. `vm start` creates the token file there and mounts it
   read-only into the VM's container.

2. **In the client container**, mount only a client `art98.toml` and a copy of that token file,
   never `work/`. The client's file:

   ```toml
   [vm]
   transport  = "tcp"
   token_file = "vm.token"              # beside this art98.toml

   [ports]
   connect = "172.17.0.1"               # the host's bind address
   ```

3. **Render.** `art98 ping` and `art98 render` now work in the client container. It needs art98
   installed and ffmpeg, because the client encodes the video; the VM's image has no ffmpeg.

The token is what lets a client drive the VM, and the VM runs any Win32 call it's sent. Give
the token file only to containers you trust, and keep `bind` off any address the outside network
can reach. Share that one file and never `work/`, which holds the installed Windows.

A client that vanishes frees the lock in about a minute, as above. The probe that checked this
setup from a second Docker container is
[`probe_container_client.sh`](../../experiments/vm-service/probe_container_client.sh).

## See also

- [Commands](cli.md#art98-vm): `vm start`, `vm stop`, `vm status`, and the errors they print.
- [The container design](../design/container.md#the-vm-service): how the VM service is put together.
- [`ART98_TRANSPORT`](cli.md#environment-variables), which overrides `[vm] transport`.
