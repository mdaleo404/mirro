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
    assert out == text  # unchanged


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
# Editor ordering: non-nano branch
# ============================================================


def test_main_editor_non_nano(tmp_path, monkeypatch, capsys):
    target = tmp_path / "vim.txt"
    target.write_text("old\n")

    def fake_call(cmd):
        temp = Path(cmd[1])
        temp.write_text("edited\n")

    monkeypatch.setenv("EDITOR", "vim")
    monkeypatch.setattr(subprocess, "call", fake_call)
    monkeypatch.setattr(os, "access", lambda p, m: True)

    with patch("sys.argv", ["mirro", str(target)]):
        mirro.main()

    assert target.read_text() == "edited\n"


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

    assert result == 1
    assert "No backups found" in capsys.readouterr().out


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

    # ensure newest
    os.utime(b2, (time.time(), time.time()))

    with patch(
        "sys.argv",
        ["mirro", "--restore-last", str(target), "--backup-dir", str(d)],
    ):
        mirro.main()

    assert target.read_text() == "old2"
    assert "Restored" in capsys.readouterr().out


# ============================================================
# --prune-backups
# ============================================================


def test_prune_all(tmp_path, capsys):
    d = tmp_path / "bk"
    d.mkdir()
    (d / "a").write_text("x")
    (d / "b").write_text("y")

    with patch(
        "sys.argv", ["mirro", "--prune-backups=all", "--backup-dir", str(d)]
    ):
        mirro.main()

    out = capsys.readouterr().out
    assert "Removed ALL backups" in out
    assert not any(d.iterdir())


def test_prune_numeric(tmp_path, capsys):
    d = tmp_path / "bk"
    d.mkdir()

    old = d / "old"
    new = d / "new"
    old.write_text("x")
    new.write_text("y")

    one_day_seconds = 86400

    os.utime(
        old,
        (
            time.time() - one_day_seconds * 10,
            time.time() - one_day_seconds * 10,
        ),
    )
    os.utime(new, None)

    with patch(
        "sys.argv", ["mirro", "--prune-backups=5", "--backup-dir", str(d)]
    ):
        mirro.main()

    out = capsys.readouterr().out
    assert "Removed 1" in out
    assert new.exists()
    assert not old.exists()


def test_prune_default_env(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MIRRO_BACKUPS_LIFE", "1")

    d = tmp_path / "bk"
    d.mkdir()

    f = d / "x"
    f.write_text("hi")

    os.utime(f, (time.time() - 86400 * 2, time.time() - 86400 * 2))

    with patch(
        "sys.argv", ["mirro", "--prune-backups", "--backup-dir", str(d)]
    ):
        mirro.main()

    assert "Removed 1" in capsys.readouterr().out


def test_prune_invalid_env(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MIRRO_BACKUPS_LIFE", "nope")

    d = tmp_path / "bk"
    d.mkdir()

    with patch(
        "sys.argv", ["mirro", "--prune-backups", "--backup-dir", str(d)]
    ):
        mirro.main()

    out = capsys.readouterr().out
    assert "Invalid MIRRO_BACKUPS_LIFE value" in out


def test_prune_invalid_arg(tmp_path, capsys):
    with patch("sys.argv", ["mirro", "--prune-backups=zzz"]):
        result = mirro.main()

    assert result == 1
    assert "Invalid value for --prune-backups" in capsys.readouterr().out


# ============================================================
# --diff tests
# ============================================================


def test_diff_basic(tmp_path, capsys):
    d = tmp_path / "bk"
    d.mkdir()

    file = tmp_path / "t.txt"
    file.write_text("line1\nline2\n")

    backup = d / "t.txt.orig.20250101T010203"
    backup.write_text(
        "# ---------------------------------------------------\n"
        "# mirro backup\n"
        "# whatever\n"
        "\n"
        "line1\nold\n"
    )

    with patch(
        "sys.argv",
        ["mirro", "--diff", str(file), backup.name, "--backup-dir", str(d)],
    ):
        mirro.main()

    out = capsys.readouterr().out

    assert "--- a/t.txt" in out
    assert "+++ b/t.txt" in out
    assert "@@" in out
    assert "-old" in out
    assert "+line2" in out


def test_diff_wrong_backup_name_rejected(tmp_path, capsys):
    d = tmp_path / "bk"
    d.mkdir()

    file = tmp_path / "foo.txt"
    file.write_text("hello\n")

    bad = d / "bar.txt.orig.20250101T010203"
    bad.write_text("stuff\n")

    with patch(
        "sys.argv",
        ["mirro", "--diff", str(file), bad.name, "--backup-dir", str(d)],
    ):
        result = mirro.main()

    out = capsys.readouterr().out

    assert result == 1
    assert "does not match the file being diffed" in out
    assert "foo.txt.orig." in out
