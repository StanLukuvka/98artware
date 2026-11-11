"""Real QEMU, with no Windows involved: firmware, MBR, serial, QMP, snapshots."""

import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
from art98 import disc
from art98.guestfiles import guest_build
from art98.qemu import QEMU_BINARY, VM, QemuError, VMConfig
from art98.recorder import ppm_size
from art98.session import Session
from art98_setup import builder
from art98_setup import vm as vm_step

MBR = guest_build() / "mbr.bin"
pytestmark = [
    pytest.mark.qemu,
    pytest.mark.skipif(shutil.which(QEMU_BINARY) is None, reason="needs QEMU"),
    pytest.mark.skipif(not MBR.exists(), reason="MBR not built"),
    pytest.mark.skipif(shutil.which("mformat") is None, reason="needs mtools"),
]

MESSAGE = b"BOOT-SECTOR-REACHED\n"
# mov dx,0x3f8 / mov si,msg / print loop with out dx,al / hlt
FAKE_BOOT_SECTOR = bytes.fromhex("baf803be117cac84c07403eeebf8f4ebfd") + MESSAGE + b"\0"


def serial_output(path: Path, wanted: bytes, timeout: float = 20.0) -> bytes:
    sock = socket.socket(socket.AF_UNIX)
    sock.connect(str(path))
    sock.settimeout(0.5)
    data = b""
    deadline = time.monotonic() + timeout
    while wanted not in data and time.monotonic() < deadline:
        try:
            data += sock.recv(4096)
        except TimeoutError:
            pass
    sock.close()
    return data


@pytest.fixture
def disk(tmp_path):
    path = tmp_path / "disk.img"
    vm_step.create_disk(path, 600, MBR.read_bytes())
    with open(path, "r+b") as image:
        image.seek(builder.PARTITION_OFFSET)
        image.write(FAKE_BOOT_SECTOR)
        image.seek(builder.PARTITION_OFFSET + 510)
        image.write(b"\x55\xaa")
    return path


def test_mbr_chains_to_the_active_partition(disk):
    config = VMConfig(disk=disk, disk_format="raw")
    with VM(config) as vm:
        assert MESSAGE in serial_output(vm.serial_path, MESSAGE)


def test_blank_partition_gets_a_message_rather_than_a_hang(tmp_path):
    path = tmp_path / "disk.img"
    with open(path, "wb") as image:
        image.truncate(32 * 1024 * 1024)
        image.write(vm_step.build_mbr(MBR.read_bytes(), 65000))
    dump = tmp_path / "vga.bin"
    with VM(VMConfig(disk=path, disk_format="raw")) as vm:
        deadline = time.monotonic() + 15
        text = b""
        while time.monotonic() < deadline and b"no bootable partition" not in text:
            time.sleep(0.25)
            vm.qmp.execute("pmemsave", val=0xB8000, size=4000, filename=str(dump))
            text = dump.read_bytes()[::2]
    assert b"art98: no bootable partition" in text


def test_guest_reboot_ends_the_vm(disk):
    with VM(VMConfig(disk=disk, disk_format="raw", sound=False)) as vm:
        vm.qmp.execute("system_reset")
        assert vm.wait_exit(10)
        assert not vm.running


def test_screenshot_formats(disk, tmp_path):
    with VM(VMConfig(disk=disk, disk_format="raw")) as vm:
        assert vm.screenshot(tmp_path / "a.png").read_bytes()[:4] == b"\x89PNG"
        assert vm.screenshot(tmp_path / "a.ppm", format="ppm").read_bytes()[:2] == b"P6"


def test_snapshot_restores_at_launch(tmp_path, disk):
    golden = tmp_path / "golden.qcow2"
    subprocess.run(
        ["qemu-img", "convert", "-O", "qcow2", str(disk), str(golden)], check=True
    )
    config = VMConfig(disk=golden)
    with VM(config) as vm:
        serial_output(vm.serial_path, MESSAGE)
        vm.pause()
        vm.save_snapshot("ready")
    config.loadvm = "ready"
    with VM(config) as vm:
        assert vm.qmp.execute("query-status")["running"] is True
        assert "ready" in vm.qmp.human("info snapshots")


def test_snapshot_failures_are_raised(disk):
    with VM(VMConfig(disk=disk, disk_format="raw")) as vm:
        with pytest.raises(QemuError, match="does not support snapshots"):
            vm.save_snapshot("ready")
        with pytest.raises(QemuError):
            vm.load_snapshot("missing")


def test_software_emulation_with_virtual_clock(disk):
    config = VMConfig(disk=disk, disk_format="raw", icount_shift=3)
    with VM(config) as vm:
        assert MESSAGE in serial_output(vm.serial_path, MESSAGE)


def settled(vm, tmp_path, quiet=1.0, timeout=30.0) -> None:
    """Wait until the screen size has not changed for `quiet` seconds (BIOS 640x480 -> 720x400)."""
    shot, last, since = tmp_path / "probe.ppm", None, time.monotonic()
    deadline = since + timeout
    while time.monotonic() < deadline:
        size = ppm_size(vm.screenshot(shot, format="ppm").read_bytes())
        if size != last:
            last, since = size, time.monotonic()
        elif time.monotonic() - since >= quiet:
            return
        time.sleep(0.2)
    raise AssertionError(f"the screen size never settled (last {last})")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_recorder_writes_exactly_the_requested_frames(disk, tmp_path):
    class Settled:
        syncs = 0

        def sync(self):
            self.syncs += 1

        def close(self):
            pass

    video = tmp_path / "out.mp4"
    bridge = Settled()
    with VM(VMConfig(disk=disk, disk_format="raw")) as vm:
        settled(vm, tmp_path)
        session = Session(vm, bridge)
        with session.record(video, fps=10) as recorder:
            recorder.frame()
            recorder.frame(hold=4)
            recorder.live(0.3)
    assert bridge.syncs == 2 and recorder.count == 8
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "csv=p=0",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert probe.stdout.strip() == "8"


def test_machine_type_is_pinned_to_a_real_version(tmp_path):
    tool = builder.Setup(work=tmp_path, guest_build=tmp_path)
    assert tool._machine().startswith("pc-i440fx-")


def test_broken_config_reports_the_failure(tmp_path):
    log = tmp_path / "qemu.log"
    config = VMConfig(disk=tmp_path / "missing.qcow2")
    with pytest.raises(RuntimeError, match="qemu.log"):
        VM(config, log=log).start()
    assert log.read_bytes()


def test_config_survives_json(tmp_path):
    config = VMConfig(
        disk=tmp_path / "d.qcow2", machine="pc-i440fx-10.2", icount_shift=2
    )
    assert VMConfig.from_json(config.to_json()) == config


def test_disc_insert_and_eject(tmp_path):
    """The real QMP calls on a paused machine, no guest: device= and the qdev id both work."""
    disk = tmp_path / "disk.img"
    disk.write_bytes(bytes(1024 * 1024))
    iso = disc.build_iso({"WALL0001.BMP": b"BM" + bytes(5000)})
    with VM(
        VMConfig(disk=disk, disk_format="raw", sound=False, extra_args=["-S"])
    ) as vm:
        assert vm.disc_state() == {
            "present": True,
            "inserted": False,
            "tray_open": False,
        }
        vm.eject_disc()  # empty drive: harmless
        vm.insert_disc(iso)
        assert (vm._dir / "art98.iso").read_bytes() == iso
        assert vm.disc_state()["inserted"] is True
        vm.eject_disc()
        assert vm.disc_state() == {
            "present": True,
            "inserted": False,
            "tray_open": False,
        }
        vm.insert_disc(iso)  # and again
        assert vm.disc_state()["inserted"] is True
