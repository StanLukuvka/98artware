# 98artware_container

Everything that runs art98 in a Podman or Docker container. With it the host needs only Python,
ffmpeg and a container engine: QEMU, mtools, 7-Zip and the guest programs are in the image.

```bash
uv run art98 up --iso /path/to/win98se.iso
```

| File | What it is |
| --- | --- |
| [Containerfile](Containerfile) | The image, in two stages: a Fedora 44 build of `windows_handlers/`, then Fedora minimal with QEMU 10.2.2 pinned, mtools, 7-Zip, Python and the art98 packages. The build context is the repository root |
| [Containerfile.dockerignore](Containerfile.dockerignore) | What stays out of the build context: `work/` above all, whose disk images are installed copies of Windows. Docker reads it by itself; `art98 up` passes it to Podman with `--ignorefile` |
| [art98_container/serve.py](art98_container/serve.py) | `art98 serve`, inside the container: boots `ready` on a run copy and relays the agent and a JSON control channel to the host |
| [art98_container/host.py](art98_container/host.py) | On the host: `Engine`, `ContainerStage`, `RemoteVM`, `boot` and `up` |
| [tests/test_container.py](tests/test_container.py) | serve and the host side against a fake VM and a fake agent. No container needed |
| [tests/test_stage.py](tests/test_stage.py) | The prepared image booted on the local and the container backend |

`art98.session.boot(work, backend="container")`, or `ART98_BACKEND=container`, is the only way
the rest of art98 reaches this package. The design, the wire format and the timings are in
[docs/design/container.md](../docs/design/container.md); the setup guide covers
[running it](../docs/setup/README.md#quick-path-in-a-container).

The image never holds the disc, the key or `work/`. They are mounted at run time, and the key
goes in as a secret.
