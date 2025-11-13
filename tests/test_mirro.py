import os
import time
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import mirro.main as mirro


# ============================================================
# get_version
# ============================================================


def test_get_version_found(monkeypatch):
    monkeypatch.setattr(mirro.importlib.metadata, "version", lambda _: "1.2.3")
    assert mirro.get_version() == "1.2.3"


def test_get_version_not_found(monkeypatch):
    def raiser(_):
        raise mirro.importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(mirro.importlib.metadata, "version", raiser)
    assert mirro.get_version() == "unknown"


# ============================================================
# read_file / write_file
# ============================================================


def test_read_file_exists(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("hello\n", encoding="utf-8")
    assert mirro.read_file(p) == "hello\n"


def test_read_file_missing(tmp_path):
    assert mirro.read_file(tmp_path / "nope.txt") == ""


def test_write_file(tmp_path):
    p = tmp_path / "y.txt"
    mirro.write_file(p, "data")
    assert p.read_text(encoding="utf-8") == "data"


# ============================================================
# backup_original
# ============================================================


def test_backup_original(tmp_path, monkeypatch):
    original_path = tmp_path / "test.txt"
    original_content = "ABC"
    backup_dir = tmp_path / "backups"

    # Freeze timestamps
    monkeypatch.setattr(
        time, "gmtime", lambda: time.struct_time((2023, 1, 2, 3, 4, 5, 0, 0, 0))
    )
    monkeypatch.setattr(
        time,
        "strftime",
        lambda fmt, _: {
            "%Y-%m-%d %H:%M:%S UTC": "2023-01-02 03:04:05 UTC",
            "%Y%m%dT%H%M%S": "20230102T030405",
        }[fmt],
    )

    backup_path = mirro.backup_original(original_path, original_content, backup_dir)

    assert backup_path.exists()
    text = backup_path.read_text(encoding="utf-8")
    assert "mirro backup" in text
    assert "Original file:" in text
    assert original_content in text


# ============================================================
# Helper to run main()
# ============================================================


def simulate_main(
    monkeypatch,
    capsys,
    args,
    *,
    editor="nano",
    start_content=None,
    edited_content=None,
    file_exists=True,
    override_access=None,
):
    """Utility to simulate mirro.main()"""

    monkeypatch.setenv("EDITOR", editor)

    # Fake editor
    def fake_call(cmd):
        temp = Path(cmd[-1])
        if edited_content is None:
            temp.write_text(start_content or "", encoding="utf-8")
        else:
            temp.write_text(edited_content, encoding="utf-8")
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)

    # Access override if provided
    if override_access:
        monkeypatch.setattr(os, "access", override_access)
    else:
        monkeypatch.setattr(os, "access", lambda p, m: True)

    # Set up file as needed
    target = Path(args[-1]).expanduser().resolve()
    if file_exists:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(start_content or "", encoding="utf-8")

    with patch("sys.argv", ["mirro"] + args):
        result = mirro.main()

    out = capsys.readouterr().out
    return result, out


# ============================================================
# main: missing file argument
# ============================================================


def test_main_missing_argument(capsys):
    with patch("sys.argv", ["mirro"]):
        with pytest.raises(SystemExit):
            mirro.main()

    assert "the following arguments are required: file" in capsys.readouterr().err


# ============================================================
# main: unchanged file (line 137)
# ============================================================


def test_main_existing_unchanged(tmp_path, monkeypatch, capsys):
    target = tmp_path / "file.txt"
    target.write_text("hello\n", encoding="utf-8")

    def fake_call(cmd):
        temp = Path(cmd[-1])
        temp.write_text("hello\n", encoding="utf-8")

    monkeypatch.setenv("EDITOR", "nano")
    monkeypatch.setattr(subprocess, "call", fake_call)
    monkeypatch.setattr(os, "access", lambda p, m: True)

    with patch("sys.argv", ["mirro", str(target)]):
        mirro.main()

    out = capsys.readouterr().out
    assert "file hasn't changed" in out


# ============================================================
# main: changed file
# ============================================================


def test_main_existing_changed(tmp_path, monkeypatch, capsys):
    target = tmp_path / "file2.txt"

    result, out = simulate_main(
        monkeypatch,
        capsys,
        args=[str(target)],
        start_content="old\n",
        edited_content="new\n",
        file_exists=True,
    )

    assert "file changed; original backed up at" in out
    assert target.read_text(encoding="utf-8") == "new\n"


# ============================================================
# main: new file unchanged
# ============================================================


def test_main_new_file_unchanged(tmp_path, monkeypatch, capsys):
    new = tmp_path / "new.txt"

    result, out = simulate_main(
        monkeypatch,
        capsys,
        args=[str(new)],
        start_content=None,
        edited_content="This is a new file created with 'mirro'!\n",
        file_exists=False,
    )

    assert "file hasn't changed" in out
    assert not new.exists()


# ============================================================
# main: new file changed
# ============================================================


def test_main_new_file_changed(tmp_path, monkeypatch, capsys):
    new = tmp_path / "new2.txt"

    result, out = simulate_main(
        monkeypatch,
        capsys,
        args=[str(new)],
        start_content=None,
        edited_content="XYZ\n",
        file_exists=False,
    )

    assert "file changed; original backed up at" in out
    assert new.read_text(encoding="utf-8") == "XYZ\n"


# ============================================================
# main: permission denied for existing file (line 78)
# ============================================================


def test_main_permission_denied_existing(tmp_path, monkeypatch, capsys):
    target = tmp_path / "blocked.txt"
    target.write_text("hello", encoding="utf-8")

    monkeypatch.setenv("EDITOR", "nano")
    monkeypatch.setattr(os, "access", lambda p, m: False)

    with patch("sys.argv", ["mirro", str(target)]):
        result = mirro.main()

    out = capsys.readouterr().out
    assert "Need elevated privileges to open" in out
    assert result == 1


# ============================================================
# main: permission denied creating file (line 84)
# ============================================================


def test_main_permission_denied_create(tmp_path, monkeypatch, capsys):
    newfile = tmp_path / "subdir" / "nofile.txt"
    parent = newfile.parent
    parent.mkdir(parents=True, exist_ok=True)

    # Directory is not writable
    def fake_access(path, mode):
        if path == parent:
            return False
        return True

    monkeypatch.setattr(os, "access", fake_access)
    monkeypatch.setenv("EDITOR", "nano")

    with patch("sys.argv", ["mirro", str(newfile)]):
        result = mirro.main()

    out = capsys.readouterr().out
    assert "Need elevated privileges to create" in out
    assert result == 1


# ============================================================
# main: non-nano editor (ordering branch)
# ============================================================


def test_main_editor_non_nano(tmp_path, monkeypatch, capsys):
    target = tmp_path / "vim.txt"
    target.write_text("old\n", encoding="utf-8")

    def fake_call(cmd):
        temp = Path(cmd[1])  # in non-nano mode
        temp.write_text("edited\n", encoding="utf-8")

    monkeypatch.setenv("EDITOR", "vim")
    monkeypatch.setattr(subprocess, "call", fake_call)
    monkeypatch.setattr(os, "access", lambda p, m: True)

    with patch("sys.argv", ["mirro", str(target)]):
        mirro.main()

    assert target.read_text(encoding="utf-8") == "edited\n"
