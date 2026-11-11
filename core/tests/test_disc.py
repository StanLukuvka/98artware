import io
import os

import pycdlib
import pytest
from art98.disc import build_iso


def read_back(iso: bytes) -> dict[str, bytes]:
    cd = pycdlib.PyCdlib()
    cd.open_fp(io.BytesIO(iso))
    out = {}
    for child in cd.list_children(iso_path="/"):
        if child.is_dot() or child.is_dotdot():
            continue
        name = child.file_identifier().decode()
        buf = io.BytesIO()
        cd.get_file_from_iso_fp(buf, iso_path="/" + name)
        out[name] = buf.getvalue()
    assert cd.pvd.volume_identifier.rstrip(b" ") == b"ART98"
    cd.close()
    return out


def test_one_file():
    iso = build_iso({"WALL0001.BMP": b"hello"})
    assert len(iso) % 2048 == 0
    assert read_back(iso) == {"WALL0001.BMP;1": b"hello"}


def test_two_files_and_big_file():
    big = os.urandom(1_400_000)
    iso = build_iso({"WALL0001.BMP": big, "A.TXT": b"x" * 2048})
    assert len(iso) % 2048 == 0
    assert read_back(iso) == {"A.TXT;1": b"x" * 2048, "WALL0001.BMP;1": big}


def test_volume_is_uppercased():
    cd = pycdlib.PyCdlib()
    cd.open_fp(io.BytesIO(build_iso({"A.B": b""}, volume="disc")))
    assert cd.pvd.volume_identifier.rstrip(b" ") == b"DISC"


@pytest.mark.parametrize(
    "name", ["wall.bmp", "WALL.BMPX", "TOOLONGNAME.BMP", "NODOT", ".BMP", "A B.TXT"]
)
def test_bad_names_raise(name):
    with pytest.raises(ValueError):
        build_iso({name: b"x"})
