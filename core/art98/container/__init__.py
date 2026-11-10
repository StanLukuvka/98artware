"""The container backend: a stage whose QEMU runs in a Docker container.

serve.py runs inside the container, started by entry.py. host.py runs on the host: it starts the
container and gives `art98.session.boot(backend="container")` its Session.
Building the image is setup's job, in art98_setup.up.
"""
