import shutil
import struct
from pathlib import Path
from typing import ClassVar

import pytest
from art98.guestfiles import guest_build
from art98_setup import builder, init_api, pecheck
from art98_setup import setup as install_step
from art98_setup import vm as vm_step

GUEST_BUILD = guest_build()
needs_mtools = pytest.mark.skipif(
    shutil.which("mformat") is None, reason="needs mtools"
)


def fake_disc(path: Path, media: int = 2, indicator: int = 0x88) -> bytes:
    floppy = (b"BOOTFLOPPY" * 200000)[: vm_step.EL_TORITO_FLOPPY_SIZES.get(media, 2048)]
    data = bytearray(30 * vm_step.CD_SECTOR)
    record = bytearray(vm_step.CD_SECTOR)
    record[1:6] = b"CD001"
    record[7:30] = b"EL TORITO SPECIFICATION"
    struct.pack_into("<I", record, 0x47, 20)
    data[17 * vm_step.CD_SECTOR : 18 * vm_step.CD_SECTOR] = record
    entry = bytearray(32)
    entry[0], entry[1] = indicator, media
    struct.pack_into("<I", entry, 8, 25)
    start = 20 * vm_step.CD_SECTOR + 32
    data[start : start + 32] = entry
    path.write_bytes(bytes(data[: 25 * vm_step.CD_SECTOR]) + floppy)
    return floppy


def test_boot_floppy_is_found_through_el_torito(tmp_path):
    iso = tmp_path / "disc.iso"
    expected = fake_disc(iso)
    assert vm_step.boot_floppy_image(iso) == expected


def test_disc_without_el_torito_is_refused(tmp_path):
    iso = tmp_path / "disc.iso"
    iso.write_bytes(bytes(40 * vm_step.CD_SECTOR))
    with pytest.raises(builder.SetupError, match="not a bootable disc"):
        vm_step.boot_floppy_image(iso)


def test_no_emulation_disc_is_refused(tmp_path):
    iso = tmp_path / "disc.iso"
    fake_disc(iso, media=0)
    with pytest.raises(builder.SetupError, match="emulated floppy"):
        vm_step.boot_floppy_image(iso)


def test_mbr_layout():
    mbr = vm_step.build_mbr(b"\xfa" * 100, 4_000_000)
    assert len(mbr) == 512 and mbr[510:] == b"\x55\xaa"
    assert mbr[446] == 0x80 and mbr[450] == vm_step.FAT32_LBA
    assert struct.unpack_from("<II", mbr, 454) == (63, 4_000_000 - 63)


def test_mbr_rejects_oversized_boot_code():
    with pytest.raises(builder.SetupError):
        vm_step.build_mbr(bytes(441), 1000)


@needs_mtools
def test_disk_holds_files_in_a_fat32_partition(tmp_path):
    disk = tmp_path / "disk.img"
    vm_step.create_disk(disk, 600, b"\xfa")
    (tmp_path / "HELLO.TXT").write_text("hi")
    spec = builder.disk_spec(disk)
    builder._mtool("mcopy", "-i", spec, str(tmp_path / "HELLO.TXT"), "::HELLO.TXT")
    assert builder._mtool("mtype", "-i", spec, "::HELLO.TXT").stdout == b"hi"
    boot_sector = disk.read_bytes()[
        builder.PARTITION_OFFSET : builder.PARTITION_OFFSET + 512
    ]
    assert boot_sector[82:87] == b"FAT32"
    assert struct.unpack_from("<I", boot_sector, 28)[0] == builder.PARTITION_START


@needs_mtools
def test_patch_floppy_replaces_boot_files(tmp_path):
    floppy = tmp_path / "boot.img"
    floppy.write_bytes(bytes(1474560))
    builder._mtool("mformat", "-i", str(floppy), "-f", "1440", "::")
    himem = tmp_path / "HIMEM.SYS"
    himem.write_bytes(b"x")
    builder._mtool("mcopy", "-i", str(floppy), str(himem), "::HIMEM.SYS")
    builder._mtool("mcopy", "-i", str(floppy), str(himem), "::JO.SYS")
    builder._mtool("mattrib", "-i", str(floppy), "+h", "+s", "+r", "::JO.SYS")
    vm_step.patch_floppy(floppy, tmp_path)
    autoexec = builder._mtool("mtype", "-i", str(floppy), "::AUTOEXEC.BAT").stdout
    assert b"MSBATCH.INF" in autoexec and b"\r\n" in autoexec
    listing = builder._mtool(
        "mdir", "-a", "-b", "-i", str(floppy), "::", text=True
    ).stdout
    assert "JO.SYS" not in listing.upper()


@needs_mtools
def test_patch_floppy_accepts_a_disc_without_the_menu(tmp_path):
    floppy = tmp_path / "boot.img"
    floppy.write_bytes(bytes(1474560))
    builder._mtool("mformat", "-i", str(floppy), "-f", "1440", "::")
    himem = tmp_path / "HIMEM.SYS"
    himem.write_bytes(b"x")
    builder._mtool("mcopy", "-i", str(floppy), str(himem), "::HIMEM.SYS")
    vm_step.patch_floppy(floppy, tmp_path)


def test_msbatch_carries_key_and_starts_the_agent():
    text = vm_step.render_msbatch("AAAAA-BBBBB")
    assert 'ProductKey="AAAAA-BBBBB"' in text
    assert "Express=1" in text and "EBD=0" in text
    assert r'"Art98Agent",,"C:\ART98\AGENT.EXE"' in text
    assert 'ComputerName="art98"' in text and 'Workgroup="WORKGROUP"' in text
    assert "OptionalComponents=1" in text
    assert "[OptionalComponents]" in text and '"Games"=1' in text
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")


def test_msdos_sys_patch_updates_adds_and_keeps():
    original = "[Paths]\r\nWinDir=C:\\WINDOWS\r\n\r\n[Options]\r\nBootMulti=1\r\nlogo=1\r\n;xxx\r\n"
    patched = init_api.patch_msdos_sys(original, {"Logo": "0", "AutoScan": "0"})
    assert "WinDir=C:\\WINDOWS" in patched and "BootMulti=1" in patched
    assert "Logo=0" in patched and "logo=1" not in patched
    assert "AutoScan=0" in patched and ";xxx" in patched


def test_msdos_sys_patch_stops_at_the_next_section():
    original = "[Options]\r\nA=1\r\n[Other]\r\nB=2\r\n"
    patched = init_api.patch_msdos_sys(original, {"Logo": "0"})
    assert patched.index("Logo=0") < patched.index("[Other]")


@pytest.mark.skipif(not (GUEST_BUILD / "agent.exe").exists(), reason="agent not built")
def test_built_agent_can_load_on_windows_98():
    pecheck.check_agent(GUEST_BUILD / "agent.exe")


@pytest.mark.skipif(not (GUEST_BUILD / "agent.exe").exists(), reason="agent not built")
def test_unreviewed_import_is_caught(monkeypatch):
    monkeypatch.setitem(pecheck.ALLOWED_IMPORTS, "USER32.dll", set())
    with pytest.raises(pecheck.PEError, match="unreviewed"):
        pecheck.check_agent(GUEST_BUILD / "agent.exe")


@pytest.mark.skipif(not (GUEST_BUILD / "view.exe").exists(), reason="viewer not built")
def test_built_viewer_can_load_on_windows_98():
    pecheck.check_viewer(GUEST_BUILD / "view.exe")


@pytest.fixture
def rehearsal_disc(tmp_path):
    """A small bootable disc laid out like the real one."""
    pycdlib = pytest.importorskip("pycdlib")
    floppy = tmp_path / "source-floppy.img"
    floppy.write_bytes(bytes(1474560))
    builder._mtool("mformat", "-i", str(floppy), "-f", "1440", "::")
    himem = tmp_path / "HIMEM.SYS"
    himem.write_bytes(b"himem")
    builder._mtool("mcopy", "-i", str(floppy), str(himem), "::HIMEM.SYS")

    disc = pycdlib.PyCdlib()
    disc.new(interchange_level=3, joliet=3)
    disc.add_fp(open(floppy, "rb"), 1474560, "/BOOT.IMG;1", joliet_path="/boot.img")  # noqa: SIM115
    disc.add_eltorito(
        "/BOOT.IMG;1", "/BOOT.CAT;1", media_name="floppy", boot_load_size=2880
    )
    disc.add_directory("/WIN98", joliet_path="/WIN98")
    for name, body in (("SETUP.EXE", b"setup"), ("PRECOPY1.CAB", b"cab")):
        data = tmp_path / name
        data.write_bytes(body)
        disc.add_file(str(data), f"/WIN98/{name};1", joliet_path=f"/WIN98/{name}")
    iso = tmp_path / "disc.iso"
    disc.write(str(iso))
    disc.close()
    return iso


@needs_mtools
@pytest.mark.skipif(shutil.which("7z") is None, reason="needs 7z")
@pytest.mark.skipif(not (GUEST_BUILD / "mbr.bin").exists(), reason="guest not built")
def test_media_and_disk_stages_lay_out_a_ready_to_install_disk(
    rehearsal_disc, tmp_path
):
    tool = builder.Setup(
        work=tmp_path / "work",
        guest_build=GUEST_BUILD,
        iso=rehearsal_disc,
        product_key="AAAAA-BBBBB",
        disk_mb=600,
        log=lambda _: None,
    )
    vm_step.media(tool)
    autoexec = builder._mtool("mtype", "-i", str(tool.floppy), "::AUTOEXEC.BAT").stdout
    assert b"SETUP.EXE" in autoexec

    vm_step.disk(tool)
    spec = builder.disk_spec(tool.raw)
    listing = builder._mtool("mdir", "-b", "-i", spec, "::WIN98").stdout.upper()
    assert (
        b"SETUP.EXE" in listing
        and b"PRECOPY1.CAB" in listing
        and b"MSBATCH.INF" in listing
    )
    answer = builder._mtool("mtype", "-i", spec, "::WIN98/MSBATCH.INF").stdout
    assert b'ProductKey="AAAAA-BBBBB"' in answer
    agent = builder._mtool("mtype", "-i", spec, "::ART98/AGENT.EXE").stdout
    assert agent == (GUEST_BUILD / "agent.exe").read_bytes()
    assert not list(tool.work.glob("MSBATCH*"))


def test_disk_stage_refuses_to_run_without_a_key(tmp_path):
    tool = builder.Setup(work=tmp_path, guest_build=tmp_path, log=lambda _: None)
    with pytest.raises(builder.SetupError, match="--key"):
        vm_step.disk(tool)


def test_steps_resume_and_can_be_redone(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        builder.Setup, "_execute", lambda self, step: calls.append(step)
    )
    tool = builder.Setup(work=tmp_path, guest_build=tmp_path, log=lambda _: None)
    tool.run()
    assert calls == ["vm", "setup", "init_api", "ready"]
    assert builder.Setup.STAGES == ("vm", "setup", "init_api", "ready")
    calls.clear()
    tool.run()
    assert calls == []
    tool.run("init_api")
    assert calls == ["init_api", "ready"]


def test_a_failed_step_is_not_marked_done(tmp_path, monkeypatch):
    def execute(self, step):
        if step == "setup":
            raise builder.SetupError("boom")

    monkeypatch.setattr(builder.Setup, "_execute", execute)
    tool = builder.Setup(work=tmp_path, guest_build=tmp_path, log=lambda _: None)
    with pytest.raises(builder.SetupError):
        tool.run()
    assert tool._done() == ["vm"]


def test_from_rejects_unknown_and_old_stage_names(tmp_path):
    tool = builder.Setup(work=tmp_path, guest_build=tmp_path, log=lambda _: None)
    for name in ("bogus", "media", "disk", "install", "patch", "harden"):
        with pytest.raises(builder.SetupError, match="unknown step"):
            tool.run(name)


def test_init_api_boots_the_converted_image_and_shuts_it_down(tmp_path, monkeypatch):
    order = []
    monkeypatch.setattr(init_api, "patch", lambda setup: order.append("patch"))
    monkeypatch.setattr(init_api, "boot_and_ping", lambda setup: order.append("boot"))
    init_api.run(None)
    assert order == ["patch", "boot"]


def wizard_screen(heading: int = 0, wizard: bool = True) -> bytes:
    rgb = bytearray(bytes((0, 0, 255)) * (640 * 480))

    def paint(left, top, right, bottom, color):
        for y in range(top, bottom):
            for x in range(left, right):
                rgb[(y * 640 + x) * 3 : (y * 640 + x) * 3 + 3] = bytes(color)

    if wizard:
        paint(76, 60, 562, 80, (0, 0, 168))
        paint(76, 80, 562, 420, (192, 199, 200))
        paint(230, 100, 230 + heading, 104, (0, 0, 0))
    return b"P6\n640 480\n255\n" + bytes(rgb)


def test_screen_reads_the_ppm_qemu_writes():
    screen = builder.Screen.from_ppm(wizard_screen())
    assert (screen.width, screen.height) == (640, 480)
    assert screen.pixel(300, 70) == (0, 0, 168)
    assert len(screen.crop(10, 20, 30, 25)) == 20 * 5 * 3


def test_wizard_is_told_from_other_setup_screens():
    assert builder.setup_wizard_showing(builder.Screen.from_ppm(wizard_screen()))
    assert not builder.setup_wizard_showing(
        builder.Screen.from_ppm(wizard_screen(wizard=False))
    )
    assert not builder.setup_wizard_showing(
        builder.Screen(800, 600, bytes(800 * 600 * 3))
    )


class WizardVM:
    """A guest whose wizard moves on when a page's last key arrives."""

    def __init__(self, stuck_at=None):
        self.page, self.keys, self.stuck_at = 0, [], stuck_at
        self.pending = 0

    def screenshot(self, path, format="png"):
        showing = self.page < len(builder.WIZARD_PAGES)
        path.write_bytes(wizard_screen(self.page * 8 + 8, wizard=showing))
        return path

    def send_keys(self, *chord):
        self.keys.append(chord)
        self.pending += 1
        if self.page != self.stuck_at and self.pending == len(
            builder.WIZARD_PAGES[self.page]
        ):
            self.page, self.pending = self.page + 1, 0


def wizard_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(builder.time, "sleep", lambda _: None)
    tool = builder.Setup(work=tmp_path, guest_build=tmp_path, log=lambda _: None)
    tool.shots.mkdir(parents=True, exist_ok=True)
    return tool


def test_wizard_pages_are_answered_in_order(tmp_path, monkeypatch):
    vm = WizardVM()
    wizard_tool(tmp_path, monkeypatch)._answer_setup_prompts(vm)
    assert vm.keys == [("ret",), ("alt", "a"), ("ret",), ("ret",), ("ret",)]


def test_no_keys_are_sent_without_a_wizard(tmp_path, monkeypatch):
    vm = WizardVM()
    vm.page = len(builder.WIZARD_PAGES)
    wizard_tool(tmp_path, monkeypatch)._answer_setup_prompts(vm)
    assert vm.keys == []


def test_wizard_that_stops_advancing_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "WIZARD_PAGE_TIMEOUT", -1)
    with pytest.raises(builder.SetupError, match="did not advance"):
        wizard_tool(tmp_path, monkeypatch)._answer_setup_wizard(WizardVM(stuck_at=1))


def test_a_second_wizard_pass_means_the_product_key_was_rejected(tmp_path, monkeypatch):
    tool = wizard_tool(tmp_path, monkeypatch)
    tool._answer_setup_prompts(WizardVM())
    with pytest.raises(builder.SetupError, match="rejected the product key") as seen:
        tool._answer_setup_prompts(WizardVM())
    assert "--from vm" in str(seen.value)
    assert (tool.shots / "product-key.png").exists()


def test_one_wizard_pass_is_fine_and_later_screens_do_not_count(tmp_path, monkeypatch):
    tool = wizard_tool(tmp_path, monkeypatch)
    vm = WizardVM()
    tool._answer_setup_prompts(vm)
    tool._answer_setup_prompts(vm)  # wizard gone: nothing to answer
    assert tool.wizard_passes == 1


class SilentBridge:
    def wait_event(self, name, timeout):
        raise builder.BridgeTimeout("nothing yet")


def test_blinking_screen_with_an_idle_disk_counts_as_a_stall(tmp_path, monkeypatch):
    disk = tmp_path / "disk.img"
    disk.write_bytes(b"x")

    class BlinkingVM:
        config = type("Config", (), {"disk": disk})
        blink = 0

        def screenshot(self, path, format="png"):
            self.blink += 1
            path.write_bytes(bytes([self.blink % 2]))
            return path

    monkeypatch.setattr(builder, "STALL_LIMIT", -1)
    tool = wizard_tool(tmp_path, monkeypatch)
    with pytest.raises(builder.SetupError, match="no disk writes"):
        tool._wait_for_agent(BlinkingVM(), SilentBridge(), "install", 60)


def logon_screen() -> bytes:
    rgb = bytearray(bytes((0, 128, 128)) * (640 * 480))
    for y in range(64, 258):
        for x in range(90, 548):
            navy = y < 82
            rgb[(y * 640 + x) * 3 : (y * 640 + x) * 3 + 3] = bytes(
                (0, 0, 128) if navy else (192, 192, 192)
            )
    return b"P6\n640 480\n255\n" + bytes(rgb)


def test_logon_prompt_is_answered_once_with_enter(tmp_path, monkeypatch):
    class LogonVM:
        keys: ClassVar[list[tuple[str, ...]]] = []

        def screenshot(self, path, format="png"):
            path.write_bytes(logon_screen())
            return path

        def send_keys(self, *chord):
            self.keys.append(chord)

    vm = LogonVM()
    wizard_tool(tmp_path, monkeypatch)._answer_setup_prompts(vm)
    assert vm.keys == [("ret",)]
    assert not builder.setup_wizard_showing(builder.Screen.from_ppm(logon_screen()))
    assert not builder.logon_prompt_showing(builder.Screen.from_ppm(wizard_screen()))


class RestartingVM:
    """Stands in for VM: each boot either reboots or brings up the agent."""

    boots: ClassVar[list[tuple]] = []

    def __init__(self, config, log=None):
        self.config, self.serial_path = config, None

    def __enter__(self):
        RestartingVM.boots.append((self.config.floppy, self.config.boot_once))
        return self

    def __exit__(self, *exc):
        pass

    def wait_exit(self, timeout):
        return True


class RestartingBridge:
    """Reports the link closing until the third boot, when the agent says hello."""

    calls: ClassVar[list] = []

    @classmethod
    def connect(cls, path):
        return cls()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def wait_event(self, name, timeout):
        if len(RestartingVM.boots) < 3:
            raise builder.BridgeError("link to the guest closed")
        return []

    def wait_ready(self):
        pass

    def acall(self, *args):
        RestartingBridge.calls.append(args)


def test_install_starts_a_new_vm_after_each_guest_reboot(tmp_path, monkeypatch):
    RestartingVM.boots, RestartingBridge.calls = [], []
    monkeypatch.setattr(install_step, "VM", RestartingVM)
    monkeypatch.setattr(install_step, "Bridge", RestartingBridge)
    monkeypatch.setattr(builder.Setup, "_machine", lambda self: "pc")
    tool = wizard_tool(tmp_path, monkeypatch)
    install_step.install(tool)
    assert RestartingVM.boots == [(tool.floppy, "a"), (None, None), (None, None)]
    assert RestartingBridge.calls == [("user32", "ExitWindowsEx", 6, 0)]


def test_install_gives_up_when_windows_never_comes_up(tmp_path, monkeypatch):
    RestartingVM.boots = []
    monkeypatch.setattr(install_step, "VM", RestartingVM)
    monkeypatch.setattr(install_step, "Bridge", RestartingBridge)
    monkeypatch.setattr(install_step, "SETUP_BOOTS", 2)
    monkeypatch.setattr(builder.Setup, "_machine", lambda self: "pc")
    with pytest.raises(builder.SetupError, match="after 2 boots"):
        install_step.install(wizard_tool(tmp_path, monkeypatch))
