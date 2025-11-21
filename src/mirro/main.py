import importlib.metadata
import argparse
import tempfile
import subprocess
import os
import textwrap
import difflib
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

    backup_name = f"{original_path.name}.orig.{shortstamp}"
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


def strip_mirro_header(text: str) -> str:
    """
    Strip only mirro's backup header (if present).
    Never removes shebangs or anything else.
    """
    lines = text.splitlines(keepends=True)

    # If there's no mirro header, return the text unchanged
    if not lines or not lines[0].startswith(
        "# ---------------------------------------------------"
    ):
        return text

    # Otherwise skip all header lines until the first blank line
    i = 0
    while i < len(lines):
        if lines[i].strip() == "":
            i += 1  # skip the blank separator line
            break
        i += 1

    # 'i' now points to the first real line of the original file
    return "".join(lines[i:])


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

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all backups in the backup directory and exit",
    )

    parser.add_argument(
        "--restore-last",
        metavar="FILE",
        type=str,
        help="Restore the last backup of the given file and exit",
    )

    parser.add_argument(
        "--prune-backups",
        nargs="?",
        const="default",
        help="Prune backups older than MIRRO_BACKUPS_LIFE days, or 'all' to delete all backups",
    )

    parser.add_argument(
        "--diff",
        nargs=2,
        metavar=("FILE", "BACKUP"),
        help="Show a unified diff between FILE and BACKUP and exit",
    )

    # Parse only options. Leave everything else untouched.
    args, positional = parser.parse_known_args()

    if args.diff:
        file_arg, backup_arg = args.diff

        file_path = Path(file_arg).expanduser().resolve()

        # Resolve backup: if it’s not absolute or ~, treat it as a filename in the backup dir
        if os.path.isabs(backup_arg) or backup_arg.startswith("~"):
            backup_path = Path(backup_arg).expanduser().resolve()
        else:
            backup_dir = Path(args.backup_dir).expanduser().resolve()
            backup_path = backup_dir / backup_arg

        if not file_path.exists():
            print(f"File not found: {file_path}")
            return 1
        if not backup_path.exists():
            print(f"Backup not found: {backup_path}")
            return 1

        # Enforce same base filename while diffing
        target_name = file_path.name
        backup_name = backup_path.name

        if not backup_name.startswith(target_name + ".orig."):
            print(
                f"Error: Backup '{backup_name}' does not match the file being diffed.\n"
                f"Expected backup file starting with: {target_name}.orig."
            )
            return 1

        original = file_path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        backup_raw = backup_path.read_text(encoding="utf-8", errors="replace")

        backup_stripped = strip_mirro_header(backup_raw)
        backup = backup_stripped.splitlines()

        # Generate a clean diff (no trailing line noise)
        diff = difflib.unified_diff(
            backup,
            original,
            fromfile=f"a/{file_path.name}",
            tofile=f"b/{file_path.name}",
            lineterm="",
        )

        # Colors
        RED = "\033[31m"
        GREEN = "\033[32m"
        CYAN = "\033[36m"
        RESET = "\033[0m"

        for line in diff:
            if (
                line.startswith("---")
                or line.startswith("+++")
                or line.startswith("@@")
            ):
                print(f"{CYAN}{line}{RESET}")
            elif line.startswith("+"):
                print(f"{GREEN}{line}{RESET}")
            elif line.startswith("-"):
                print(f"{RED}{line}{RESET}")
            else:
                print(line)

        return

    if args.list:
        import pwd, grp

        backup_dir = Path(args.backup_dir).expanduser().resolve()
        if not backup_dir.exists():
            print("No backups found.")
            return

        backups = sorted(
            backup_dir.iterdir(), key=os.path.getmtime, reverse=True
        )
        if not backups:
            print("No backups found.")
            return

        def perms(mode):
            is_file = "-"
            perms = ""
            flags = [
                (mode & 0o400, "r"),
                (mode & 0o200, "w"),
                (mode & 0o100, "x"),
                (mode & 0o040, "r"),
                (mode & 0o020, "w"),
                (mode & 0o010, "x"),
                (mode & 0o004, "r"),
                (mode & 0o002, "w"),
                (mode & 0o001, "x"),
            ]
            for bit, char in flags:
                perms += char if bit else "-"
            return is_file + perms

        for b in backups:
            stat = b.stat()
            mode = perms(stat.st_mode)

            try:
                owner = pwd.getpwuid(stat.st_uid).pw_name
            except KeyError:
                owner = str(stat.st_uid)

            try:
                group = grp.getgrgid(stat.st_gid).gr_name
            except KeyError:
                group = str(stat.st_gid)

            owner_group = f"{owner} {group}"

            mtime = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.gmtime(stat.st_mtime)
            )

            print(f"{mode:11} {owner_group:20} {mtime}  {b.name}")

        return

    if args.restore_last:
        backup_dir = Path(args.backup_dir).expanduser().resolve()
        target = Path(args.restore_last).expanduser().resolve()

        if not backup_dir.exists():
            print("No backup directory found.")
            return 1

        # backup filenames look like: <name>.orig.<timestamp>
        prefix = f"{target.name}.orig."

        backups = [
            b for b in backup_dir.iterdir() if b.name.startswith(prefix)
        ]

        if not backups:
            print(f"No backups found for {target}")
            return 1

        # newest backup
        last = max(backups, key=os.path.getmtime)

        # read and strip header
        raw = last.read_text(encoding="utf-8", errors="replace")
        restored_text = strip_mirro_header(raw)
        target.write_text(restored_text, encoding="utf-8")

        print(f"Restored {target} from backup {last.name}")
        return

    if args.prune_backups is not None:
        mode = args.prune_backups

        # ALL mode
        if mode == "all":
            prune_days = None

        # default
        elif mode == "default":
            raw_env = os.environ.get("MIRRO_BACKUPS_LIFE", "30")
            try:
                prune_days = int(raw_env)
                if prune_days < 1:
                    raise ValueError
            except ValueError:
                print(
                    f"Invalid MIRRO_BACKUPS_LIFE value: {raw_env}. "
                    "It must be an integer >= 1. Falling back to 30."
                )
                prune_days = 30

        # numeric mode e.g. --prune-backups=7
        else:
            try:
                prune_days = int(mode)
                if prune_days < 1:
                    raise ValueError
            except ValueError:
                msg = f"""
                    Invalid value for --prune-backups: {mode}

                    --prune-backups          use MIRRO_BACKUPS_LIFE (default: 30 days)
                    --prune-backups=N        expire backups older than N days (N >= 1)
                    --prune-backups=all      remove ALL backups
                """
                print(textwrap.dedent(msg))
                return 1

        backup_dir = Path(args.backup_dir).expanduser().resolve()

        if not backup_dir.exists():
            print("No backup directory found.")
            return 0

        # prune EVERYTHING
        if prune_days is None:
            removed = []
            for b in backup_dir.iterdir():
                if b.is_file():
                    removed.append(b)
                    b.unlink()
            print(f"Removed ALL backups ({len(removed)} file(s)).")
            return 0

        # prune by age
        cutoff = time.time() - (prune_days * 86400)
        removed = []

        for b in backup_dir.iterdir():
            if b.is_file() and b.stat().st_mtime < cutoff:
                removed.append(b)
                b.unlink()

        if removed:
            print(
                f"Removed {len(removed)} backup(s) older than {prune_days} days."
            )
        else:
            print(f"No backups older than {prune_days} days.")

        return 0

    # Flexible positional parsing
    if not positional:
        parser.error("the following arguments are required: file")

    file_arg = None
    editor_extra = []

    for p in positional:
        if (
            file_arg is None
            and not p.startswith("+")
            and not p.startswith("-")
        ):
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
