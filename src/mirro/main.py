import argparse
import tempfile
import subprocess
import os
from pathlib import Path
import time


def read_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def write_file(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def backup_original(original_path: Path, original_content: str, backup_dir: Path) -> Path:
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
    parser.add_argument("file", type=str, help="Path to file to edit")
    parser.add_argument(
        "--backup-dir",
        type=str,
        default=str(Path.home() / ".local/share/mirro"),
        help="Backup directory",
    )

    # editor_extra_args are for passing straight to the EDITOR
    args, editor_extra_args = parser.parse_known_args()

    editor = os.environ.get("EDITOR","nano")
    target = Path(args.file).expanduser().resolve()
    backup_dir = Path(args.backup_dir).expanduser().resolve()
    editor_cmd = editor.split()

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
    # Write prepopulated or original content to temp file
    write_file(temp_path, original_content)

    # Launch editor
    subprocess.call(editor_cmd + [str(temp_path)] + editor_extra_args)

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
