# The art98 stage: QEMU, the setup tools and the art98 packages, with no disk
# image, disc or key inside. Build from the repo root, where .dockerignore
# keeps work/ out of the context:
#   docker build -t localhost/art98:latest -f setup/Dockerfile .
# `art98 up` does this.

# ---- build: the programs that run on the guest ----
FROM registry.fedoraproject.org/fedora:44 AS build
RUN dnf -y install --setopt=install_weak_deps=False mingw32-gcc make syslinux-nonlinux \
 && dnf clean all
COPY guest /src/guest
RUN make -C /src/guest

# ---- run ----
FROM registry.fedoraproject.org/fedora-minimal:44
# Pinned to the build that saved the `ready` snapshot: a snapshot only loads on
# the QEMU machine type that made it (pc-i440fx-10.2). Fedora 44's release
# repository is frozen, so this exact version stays available.
ARG QEMU_VERSION=10.2.2-1.fc44
RUN microdnf -y install --setopt=install_weak_deps=0 \
        qemu-system-x86-core-${QEMU_VERSION} qemu-img-${QEMU_VERSION} \
        mtools 7zip python3 \
 && microdnf clean all

COPY core/art98 /opt/art98/core/art98
COPY setup/art98_setup /opt/art98/setup/art98_setup
COPY --from=build /src/guest/build /opt/art98/guest/build
# art98.container.entry drops to the host's uid on a rootful engine, then runs the CLI.
RUN printf '#!/bin/sh\nexec python3 -m art98.container.entry "$@"\n' > /usr/local/bin/art98 \
 && chmod 755 /usr/local/bin/art98
ENV PYTHONPATH=/opt/art98/core:/opt/art98/setup \
    PYTHONUNBUFFERED=1 \
    XDG_RUNTIME_DIR=/tmp

# The work folder is bind-mounted here; it is never part of the image.
WORKDIR /work
EXPOSE 7598
ENTRYPOINT ["art98"]
CMD ["serve"]
