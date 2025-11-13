import importlib.metadata
import argparse
import tempfile
import subprocess
import os
from pathlib import Path
import time


def get_version():
    try:
        return importlib.metadata.version("mirro")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def read_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def write_file(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def backup_original(
    original_path: Path, original_content: str, backup_dir: Path
) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    shortstamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())

    backup_name = f"{original_path.name}.orig.{shortstamp}.bak"
    backup_path = backup_dir / backup_name

    header = (
        "# ---------------------------------------------------\n"
        "# mirro backup\n"
        f"# Original file: {original_path}\n"
        f"# Timestamp: {timestamp}\n"
        "# Delete this header if you want to restore the file\n"
        "# ---------------------------------------------------\n\n"
    )

    backup_path.write_text(header + original_content, encoding="utf-8")

    return backup_path


def main():
    parser = argparse.ArgumentParser(
        description="Safely edit a file with automatic original backup if changed."
    )

    parser.add_argument(
        "--backup-dir",
        type=str,
        default=str(Path.home() / ".local/share/mirro"),
        help="Backup directory",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"mirro {get_version()}",
    )

    # Parse only options. Leave everything else untouched.
    args, positional = parser.parse_known_args()

    # Flexible positional parsing
    if not positional:
        parser.error("the following arguments are required: file")

    file_arg = None
    editor_extra = []

    for p in positional:
        if file_arg is None and not p.startswith("+") and not p.startswith("-"):
            file_arg = p
        else:
            editor_extra.append(p)

    if file_arg is None:
        parser.error("the following arguments are required: file")

    editor = os.environ.get("EDITOR", "nano")
    editor_cmd = editor.split()

    target = Path(file_arg).expanduser().resolve()
    backup_dir = Path(args.backup_dir).expanduser().resolve()

    # Permission checks
    parent = target.parent
    if target.exists() and not os.access(target, os.W_OK):
        print(f"Need elevated privileges to open {target}")
        return 1
    if not target.exists() and not os.access(parent, os.W_OK):
        print(f"Need elevated privileges to create {target}")
        return 1

    # Read original or prepopulate for new file
    if target.exists():
        original_content = read_file(target)
    else:
        original_content = "This is a new file created with 'mirro'!\n"

    # Temp file for editing
    with tempfile.NamedTemporaryFile(
        delete=False, prefix="mirro-", suffix=target.suffix
    ) as tf:
        temp_path = Path(tf.name)

    write_file(temp_path, original_content)

    if "nano" in editor_cmd[0]:
        subprocess.call(editor_cmd + editor_extra + [str(temp_path)])
    else:
        subprocess.call(editor_cmd + [str(temp_path)] + editor_extra)

    # Read edited
    edited_content = read_file(temp_path)
    temp_path.unlink(missing_ok=True)

    if edited_content == original_content:
        print("file hasn't changed")
        return

    # Changed: backup original
    backup_path = backup_original(target, original_content, backup_dir)
    print(f"file changed; original backed up at {backup_path}")

    # Overwrite target
    target.write_text(edited_content, encoding="utf-8")


if __name__ == "__main__":
    main()
