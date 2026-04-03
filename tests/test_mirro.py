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
# strip_mirro_header
# ============================================================


def test_strip_header_removes_header():
    header_text = (
        "# ---------------------------------------------------\n"
        "# mirro backup\n"
        "# something\n"
        "# ---------------------------------------------------\n"
        "\n"
        "#!/bin/bash\n"
        "echo hi\n"
    )

    out = mirro.strip_mirro_header(header_text)
    assert out.startswith("#!/bin/bash")
    assert "mirro backup" not in out


def test_strip_header_preserves_shebang():
    text = "#!/usr/bin/env python3\nprint('hi')\n"
    out = mirro.strip_mirro_header(text)
    assert out == text


def test_strip_header_non_header_file():
    text = "# just a comment\nvalue\n"
    out = mirro.strip_mirro_header(text)
    assert out == text


# ============================================================
# backup_original
# ============================================================


def test_backup_original(tmp_path, monkeypatch):
    original_path = tmp_path / "a.txt"
    original_content = "ABC"
    backup_dir = tmp_path / "backups"

    monkeypatch.setattr(
        time,
        "gmtime",
        lambda: time.struct_time((2023, 1, 2, 3, 4, 5, 0, 0, 0)),
    )
    monkeypatch.setattr(
        time,
        "strftime",
        lambda fmt, _: {
            "%Y-%m-%d %H:%M:%S UTC": "2023-01-02 03:04:05 UTC",
            "%Y%m%dT%H%M%S": "20230102T030405",
        }[fmt],
    )

    backup_path = mirro.backup_original(
        original_path, original_content, backup_dir
    )

    assert backup_path.exists()
    text = backup_path.read_text()
    assert "mirro backup" in text
    assert "Original file" in text
    assert "ABC" in text


# ============================================================
# Helper to simulate main()
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
    monkeypatch.setenv("EDITOR", editor)

    def fake_call(cmd):
        temp = Path(cmd[-1])
        if edited_content is None:
            temp.write_text(start_content or "", encoding="utf-8")
        else:
            temp.write_text(edited_content, encoding="utf-8")
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)

    if override_access:
        monkeypatch.setattr(os, "access", override_access)
    else:
        monkeypatch.setattr(os, "access", lambda p, m: True)

    target = Path(args[-1]).expanduser().resolve()
    if file_exists:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(start_content or "", encoding="utf-8")

    with patch("sys.argv", ["mirro"] + args):
        result = mirro.main()

    out = capsys.readouterr().out
    return result, out


# ============================================================
# main: missing positional file
# ============================================================


def test_main_missing_argument(capsys):
    with patch("sys.argv", ["mirro"]):
        with pytest.raises(SystemExit):
            mirro.main()
    assert (
        "the following arguments are required: file" in capsys.readouterr().err
    )


# ============================================================
# main: unchanged file
# ============================================================


def test_main_existing_unchanged(tmp_path, monkeypatch, capsys):
    target = tmp_path / "file.txt"
    target.write_text("hello\n")

    def fake_call(cmd):
        temp = Path(cmd[-1])
        temp.write_text("hello\n")

    monkeypatch.setenv("EDITOR", "nano")
    monkeypatch.setattr(subprocess, "call", fake_call)
    monkeypatch.setattr(os, "access", lambda p, m: True)

    with patch("sys.argv", ["mirro", str(target)]):
        mirro.main()

    assert "file hasn't changed" in capsys.readouterr().out


# ============================================================
# main: changed file
# ============================================================


def test_main_existing_changed(tmp_path, monkeypatch, capsys):
    target = tmp_path / "f2.txt"

    result, out = simulate_main(
        monkeypatch,
        capsys,
        args=[str(target)],
        start_content="old\n",
        edited_content="new\n",
        file_exists=True,
    )

    assert "file changed; original backed up at" in out
    assert target.read_text() == "new\n"


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
    assert new.read_text() == "XYZ\n"


# ============================================================
# Permission denied branches
# ============================================================


def test_main_permission_denied_existing(tmp_path, monkeypatch, capsys):
    tgt = tmp_path / "blocked.txt"
    tgt.write_text("hi")

    monkeypatch.setenv("EDITOR", "nano")
    monkeypatch.setattr(os, "access", lambda p, m: False)

    with patch("sys.argv", ["mirro", str(tgt)]):
        result = mirro.main()

    assert result == 1
    assert "Need elevated privileges to open" in capsys.readouterr().out


def test_main_permission_denied_create(tmp_path, monkeypatch, capsys):
    new = tmp_path / "sub/xx.txt"
    new.parent.mkdir(parents=True)

    def fake_access(path, mode):
        return False if path == new.parent else True

    monkeypatch.setattr(os, "access", fake_access)
    monkeypatch.setenv("EDITOR", "nano")

    with patch("sys.argv", ["mirro", str(new)]):
        result = mirro.main()

    assert result == 1
    assert "Need elevated privileges to create" in capsys.readouterr().out


# ============================================================
# --list
# ============================================================


def test_main_list_no_dir(tmp_path, capsys):
    with patch(
        "sys.argv", ["mirro", "--list", "--backup-dir", str(tmp_path / "none")]
    ):
        mirro.main()
    assert "No backups found." in capsys.readouterr().out


def test_main_list_entries(tmp_path, capsys):
    d = tmp_path / "bk"
    d.mkdir()
    (d / "a.txt.orig.1").write_text("x")
    (d / "b.txt.orig.2").write_text("y")

    with patch("sys.argv", ["mirro", "--list", "--backup-dir", str(d)]):
        mirro.main()

    out = capsys.readouterr().out
    assert "a.txt.orig.1" in out
    assert "b.txt.orig.2" in out


# ============================================================
# --restore-last
# ============================================================


def test_restore_last_no_dir(tmp_path, capsys):
    d = tmp_path / "none"
    target = tmp_path / "x.txt"
    with patch(
        "sys.argv",
        ["mirro", "--restore-last", str(target), "--backup-dir", str(d)],
    ):
        result = mirro.main()

    assert result == 1
    assert "No backup directory found." in capsys.readouterr().out


def test_restore_last_no_backups(tmp_path, capsys):
    d = tmp_path / "bk"
    d.mkdir()
    target = tmp_path / "t.txt"

    with patch(
        "sys.argv",
        ["mirro", "--restore-last", str(target), "--backup-dir", str(d)],
    ):
        result = mirro.main()

    out = capsys.readouterr().out
    assert result == 1
    assert "No history found for" in out
    assert str(target) in out


def test_restore_last_success(tmp_path, capsys):
    d = tmp_path / "bk"
    d.mkdir()
    target = tmp_path / "t.txt"

    mirro_header = (
        "# ---------------------------------------------------\n"
        "# mirro backup\n"
        "# Original file: x\n"
        "# Timestamp: test\n"
        "# Delete this header if you want to restore the file\n"
        "# ---------------------------------------------------\n"
        "\n"
    )

    b1 = d / "t.txt.orig.2020"
    b2 = d / "t.txt.orig.2021"

    b1.write_text(mirro_header + "old1")
    b2.write_text(mirro_header + "old2")

    os.utime(b2, (time.time(), time.time()))

    with patch(
        "sys.argv",
        ["mirro", "--restore-last", str(target), "--backup-dir", str(d)],
    ):
        mirro.main()

    assert target.read_text() == "old2"
    assert "Restored" in capsys.readouterr().out


# ============================================================
# --restore (new)
# ============================================================


def test_restore_backup_to_original_location(tmp_path, capsys):
    backup_dir = tmp_path / "bk"
    backup_dir.mkdir()

    original_dir = tmp_path / "orig"
    original_dir.mkdir()

    target = original_dir / "file.txt"

    mirro_header = (
        "# ---------------------------------------------------\n"
        "# mirro backup\n"
        f"# Original file: {target}\n"
        "# Timestamp: test\n"
        "# Delete this header if you want to restore the file\n"
        "# ---------------------------------------------------\n"
        "\n"
    )

    backup = backup_dir / "file.txt.orig.20250101T010203"
    backup.write_text(mirro_header + "restored content\n")

    with patch(
        "sys.argv",
        ["mirro", "--restore", backup.name, "--backup-dir", str(backup_dir)],
    ):
        result = mirro.main()

    assert result == 0
    assert target.exists()
    assert target.read_text() == "restored content\n"
    assert "Restored" in capsys.readouterr().out


def test_restore_missing_backup(tmp_path, capsys):
    backup_dir = tmp_path / "bk"
    backup_dir.mkdir()

    with patch(
        "sys.argv",
        [
            "mirro",
            "--restore",
            "nope.orig.123",
            "--backup-dir",
            str(backup_dir),
        ],
    ):
        result = mirro.main()

    assert result == 1
    assert "Backup not found" in capsys.readouterr().out


def test_restore_missing_original_path_in_header(tmp_path, capsys):
    backup_dir = tmp_path / "bk"
    backup_dir.mkdir()

    bad_backup = backup_dir / "x.txt.orig.123"
    bad_backup.write_text(
        "# ---------------------------------------------------\n"
        "# mirro backup\n"
        "# Timestamp: test\n"
        "\n"
        "data\n"
    )

    with patch(
        "sys.argv",
        [
            "mirro",
            "--restore",
            bad_backup.name,
            "--backup-dir",
            str(backup_dir),
        ],
    ):
        result = mirro.main()

    assert result == 1
    assert (
        "Could not determine original file location" in capsys.readouterr().out
    )


# ============================================================
# --status
# ============================================================


def test_status_no_backups(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    backup_dir = tmp_path / "bk"
    with patch(
        "sys.argv", ["mirro", "--status", "--backup-dir", str(backup_dir)]
    ):
        result = mirro.main()

    out = capsys.readouterr().out
    assert result == 0
    assert f"No mirro backups found in {tmp_path}" in out


def test_status_backups_found(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    cwd = tmp_path
    backup_dir = tmp_path / "bk"
    backup_dir.mkdir()

    (tmp_path / "a.txt").write_text("data1")
    (tmp_path / "b.txt").write_text("data2")

    (backup_dir / "a.txt.orig.1").write_text("x")
    (backup_dir / "a.txt.orig.2").write_text("y")
    (backup_dir / "b.txt.orig.3").write_text("z")

    with patch(
        "sys.argv", ["mirro", "--status", "--backup-dir", str(backup_dir)]
    ):
        result = mirro.main()

    out = capsys.readouterr().out
    assert result == 0
    assert f"Files with history in {cwd}:" in out
    assert "a.txt" in out
    assert "b.txt" in out
