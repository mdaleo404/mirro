# mirro Development Guide

Interested in the internals of mirro?

This guide describes the current `mirro` codebase for maintainers. It focuses on how the project is organised, what the command does, how backup and restore data flows through the CLI, and which invariants matter when changing the code.

---

## 1. What mirro does

`mirro` is a small safety-first command-line wrapper for editing text files.

Its main edit pipeline is:

```text
target file
  |
  | mirro FILE
  v
temporary editable copy
  |
  | $EDITOR exits
  v
content comparison
  |
  | changed only
  v
timestamped backup of original content
  |
  v
overwrite target with edited content
```

`mirro` deliberately keeps a narrow scope. It manages text content backups around manual editor sessions. It is not a filesystem snapshotter, a version-control system, a transactional editor, a privilege escalation tool, or a sandbox.

The command also supports backup inspection and maintenance flows:

```text
mirro --list                         list files in the backup directory
mirro --restore-last FILE            restore newest backup matching FILE's basename
mirro --restore BACKUP               restore backup to path from its header
mirro --prune-backups[=N|all]        remove old or all backup files
mirro --diff FILE BACKUP             show unified diff from backup to current file
mirro --status                       show current-directory files with backup history
```

---

## 2. Repository layout

The project is a single Python package under `src/mirro/`.

```text
src/mirro/
  __init__.py              package marker
  main.py                  argparse CLI and all current runtime behavior

tests/
  test_mirro.py            pytest coverage for helpers and CLI branches

pyproject.toml             Poetry package metadata and console script
poetry.lock                locked dependency graph
README.md                  user-facing documentation
LICENCE                    GPL-3.0-or-later licence text
.pre-commit-config.yaml    Bandit, Black, and generic pre-commit hooks
.gitea/workflows/          lint, dependency audit, SBOM, and Grype workflows
dist/                      built release artifacts, not source
mirro.png                  README logo
```

The installed command is configured in `pyproject.toml`:

```toml
[tool.poetry.scripts]
mirro = "mirro.main:main"
```

There is no `src/mirro/__main__.py` at the time of writing, so `python -m mirro` is not the supported entry point. Use the installed `mirro` command or `poetry run mirro` during development.

---

## 3. Main runtime flows

All user-facing behavior enters through `mirro.main.main()`.

```text
mirro command
  -> mirro.main.main()
     -> build argparse parser
     -> install argcomplete hook
     -> parse known args, leaving editor/file positionals untouched
     -> dispatch to diff, list, status, restore-last, restore, prune, or edit flow
```

The current implementation keeps parsing, filesystem operations, editor invocation, backup formatting, restore behavior, pruning, and display in one file. That is acceptable for the current size, but new behavior should avoid making `main.py` harder to reason about. If a feature grows beyond a few focused helpers, consider extracting it into a small module with tests.

### 3.1 CLI dispatch order

Dispatch order matters because each branch returns before later behavior runs:

```text
--diff
--list
--status
--restore-last
--restore
--prune-backups
normal edit flow
```

If a future option can be combined with other options, decide whether it should be a global modifier or an action branch. Most existing options are action branches.

### 3.2 Normal edit flow

The normal edit flow is the core product behavior:

```text
parse positional arguments
  -> choose first non-option/non-+ argument as target file
  -> pass remaining positionals to editor
  -> read $EDITOR, defaulting to nano
  -> resolve target and backup directory
  -> check write access to target or parent directory
  -> read existing target, or prepopulate a new file message
  -> write content to a temporary file
  -> run editor without a shell
  -> read edited temp file
  -> delete temp file
  -> compare edited content to original content
  -> if unchanged, print "file hasn't changed"
  -> if changed, back up original content and overwrite target
```

The implementation reads and writes text as UTF-8:

```python
path.read_text(encoding="utf-8", errors="replace")
path.write_text(content, encoding="utf-8")
```

That means invalid input bytes are replaced during reads and rewritten as UTF-8 if the file is saved. `mirro` is intended for text files, not arbitrary binary files.

### 3.3 Editor argument handling

`main()` parses known `mirro` options and preserves unknown positional arguments for the editor. In normal edit mode, the first positional argument that does not start with `-` or `+` is treated as the target file; the rest are editor extras.

The editor command comes from:

```text
$EDITOR, or nano when unset
```

It is split with `editor.split()` and executed with `subprocess.call()` without `shell=True`.

For `nano`, extras are placed before the temporary path:

```text
nano EXTRA... TEMP
```

For other editors, extras are placed after the temporary path:

```text
editor TEMP EXTRA...
```

Be careful when changing this. Editor option order differs across editors, and the current behavior is intentionally permissive rather than a full editor-specific parser.

---

## 4. Backup storage

The default backup directory is:

```text
~/.local/share/mirro
```

Under `sudo`, `Path.home()` normally resolves to root's home, so the default becomes:

```text
/root/.local/share/mirro
```

Users can override it with:

```bash
mirro --backup-dir /path/to/backups FILE
```

Backups are plain text files named with the original basename and a UTC timestamp:

```text
filename.ext.orig.YYYYMMDDTHHMMSS
```

The backup content starts with a mirro header:

```text
# ---------------------------------------------------
# mirro backup
# Original file: /path/to/original
# Timestamp: 2025-11-10 17:44:00 UTC
# Delete this header if you want to restore the file
# ---------------------------------------------------

original file content follows here
```

The original path in the header is used by `--restore BACKUP` to decide where to write restored content.

### 4.1 Backup creation

`backup_original(original_path, original_content, backup_dir)` owns backup file creation.

It currently:

```text
creates backup_dir if needed
uses UTC timestamps
writes a text header
writes original_content after the header
returns the backup path
```

There is no database or manifest. The backup filename and header are the persistence format.

### 4.2 Backup matching limits

Several features match backups by basename:

```text
--restore-last FILE       matches target.name + ".orig."
--diff FILE BACKUP        requires backup name to start with target.name + ".orig."
--status                  maps backups to current-directory files by basename
```

This is simple and predictable, but two files with the same basename in different directories share the same backup-name prefix in a single backup directory. `--restore BACKUP` is more specific because it reads the original path from the backup header.

### 4.3 Timestamp collisions

Backup filenames have one-second timestamp resolution. If the same basename is backed up twice in the same backup directory during the same second, the later backup can reuse the same path.

If this becomes a practical problem, fix it by making backup names unique while preserving the existing readable prefix format.

---

## 5. Restore, diff, status, and prune behavior

### 5.1 `--restore-last FILE`

Restore-last flow:

```text
resolve backup directory
resolve target file
find backup files whose names start with target.name + ".orig."
choose newest by filesystem mtime
read backup text
strip mirro header only
write restored text to target
```

This action does not read the `Original file:` header to verify the backup belongs to the same absolute path. It is basename-based.

### 5.2 `--restore BACKUP`

Restore flow:

```text
resolve BACKUP as absolute/~ path or backup-dir filename
read backup text
extract Original file path from mirro header
strip mirro header only
check write access to target or target parent
create target parent directories if needed
write restored text to target
```

This action can create parent directories for the target path from the backup header. Treat backup files and backup directories as trusted local state.

### 5.3 Header stripping

`strip_mirro_header()` removes only a header that starts with mirro's separator line and continues through the first blank line.

It intentionally does not strip arbitrary leading comments, shebangs, or non-mirro headers.

### 5.4 `--diff FILE BACKUP`

Diff flow:

```text
resolve current file
resolve backup as absolute/~ path or backup-dir filename
require backup filename to start with current file basename + ".orig."
read current text
read backup text and strip mirro header
print unified diff from backup to current file
```

Diff output uses ANSI colour codes directly for file headers, hunk lines, additions, and removals.

### 5.5 `--status`

Status flow:

```text
read backup directory
group backup files by text before ".orig."
scan regular files in current directory only
print files whose basename has backups
```

`--status` does not recurse into subdirectories and does not validate backup headers.

### 5.6 `--prune-backups`

Prune supports three forms:

```bash
mirro --prune-backups
mirro --prune-backups=14
mirro --prune-backups=all
```

Default mode reads:

```text
MIRRO_BACKUPS_LIFE
```

If the environment variable is missing, invalid, or less than `1`, the code falls back to `30` days after printing a warning for invalid values.

Age-based pruning removes regular files in the backup directory whose mtime is older than the cutoff. `all` mode removes every regular file in the backup directory. There is currently no confirmation prompt, dry-run mode, or mirro-header validation before deletion.

---

## 6. Development commands

Install dependencies:

```bash
poetry install
```

Run the CLI in the development environment:

```bash
poetry run mirro --help
```

Run pre-commit hooks:

```bash
poetry run pre-commit run --all-files
```

Run the pytest suite:

```bash
poetry run pytest
```

Run the README's full coverage command:

```bash
poetry run pytest -vvvv --cov=mirro --cov-report=term-missing --disable-warnings
```

Build release artifacts:

```bash
poetry build
```

When adding behavior, add focused tests under `tests/`. Prefer temporary directories and monkeypatching over tests that modify real user files or depend on a real editor.

---

## 7. Automation and security scanning

Gitea pull request workflow:

```text
.gitea/workflows/lint-and-security.yml
  -> install pre-commit
  -> pre-commit run --all-files
  -> install Poetry and poetry-plugin-export
  -> export Poetry dependencies
  -> pip-audit dependency audit
```

Scheduled/manual security workflow:

```text
.gitea/workflows/security-scan.yml
  -> install Cosign
  -> verify and install Syft
  -> verify and install Grype
  -> generate SBOM
  -> scan for vulnerabilities
  -> notify Node-RED on fixable Medium/High/Critical vulnerabilities
  -> fail workflow on those vulnerabilities
```

Pre-commit currently includes Bandit, Black, trailing whitespace, EOF, YAML, and TOML checks.

---

## 8. Common maintenance tasks

### 8.1 Add a new CLI option

1. Add the argparse option in `main.py`.
2. Decide whether it is a global modifier or an action branch.
3. Place action branches before normal edit flow.
4. Preserve editor positional parsing unless the option intentionally changes it.
5. Update README usage examples.
6. Add tests for parser behavior and the affected operation.

### 8.2 Change backup format

1. Update `backup_original()`.
2. Update `strip_mirro_header()` or `extract_original_path()` if header semantics change.
3. Decide whether existing backup files must remain restorable.
4. Update README examples and this guide.
5. Add tests with representative old and new backup text.

Existing backups are user data. Do not break restoration of current backup headers without a deliberate compatibility decision.

### 8.3 Change restore behavior

Start with the `--restore` and `--restore-last` branches in `main.py`.

Be explicit about whether the change affects:

```text
basename matching
header parsing
target path creation
write permission checks
backup directory trust
confirmation requirements
```

If adding confirmation or dry-run support, cover both interactive and non-interactive behavior in tests.

### 8.4 Change editor handling

Start with normal edit flow near `$EDITOR` parsing.

Preserve these invariants unless intentionally redesigning editor invocation:

```text
do not edit the real file directly
write the initial content to a temporary file
run the editor without shell=True
compare content before creating a backup
create a backup before overwriting the target
delete the temporary file after reading it
```

If changing how editor arguments are ordered, test at least `nano` and one non-`nano` editor shape with monkeypatched `subprocess.call()`.

### 8.5 Add tests

Good first test areas:

```text
backup filename/header creation
header stripping preserves shebangs
restore rejects missing backup files
restore uses Original file from header
restore-last chooses newest basename match
diff rejects mismatched backup basenames
prune rejects invalid values and handles all mode
normal edit does not write unchanged files
normal edit backs up before changed writes
permission-denied branches return 1
```

Avoid tests that require root. Use `tmp_path`, `monkeypatch`, `capsys`, and patched `sys.argv` as the current suite does.

---

## 9. Important maintenance hazards

### 9.1 `main.py` owns everything

The project is currently simple enough for one runtime module, but `main.py` contains parsing, editor invocation, backup I/O, restore, diff, status, prune, and display. Keep new changes focused. If a branch becomes complicated, extract helper functions before adding more nested logic.

### 9.2 Backups are plain trusted files

Backups are not signed, checksummed, authenticated, or stored in a database. The restore path comes from the text header. Do not treat arbitrary attacker-controlled backup files as safe input.

### 9.3 Basename matching is intentionally simple

`--restore-last`, `--diff`, and `--status` mainly use backup filenames, not the `Original file:` header. This is convenient but can mix history for files with the same basename. Be careful when changing matching semantics because existing users may rely on the current naming scheme.

### 9.4 Prune removes regular files in the backup directory

`--prune-backups=all` removes every regular file in the selected backup directory, not only files with mirro headers or `.orig.` names. Age-based pruning has the same broad backup-directory scope. This makes `--backup-dir` a powerful option.

### 9.5 Restore can create parent directories

`--restore BACKUP` creates missing parent directories for the path stored in the backup header. This is useful for recovery, but it also means backup header paths are operationally significant.

### 9.6 Text encoding is lossy for invalid bytes

Reads use `errors="replace"`. If a file contains invalid UTF-8 and the edit is saved, replacement characters may be written. Keep user-facing language clear that `mirro` is for text files.

### 9.7 Symlinks are not special-cased

The current code uses `Path.exists()`, `read_text()`, `write_text()`, and `os.access()` in their normal path-following forms. If a target path is a symlink, operations generally affect the symlink target. Do not document or assume no-follow semantics unless the implementation is changed.

### 9.8 `$EDITOR` is trusted local configuration

`mirro` runs the configured editor as the current user. This is expected behavior, but it means `$EDITOR` is part of the local trust boundary.

---

## 10. Troubleshooting guide

### 10.1 `Need elevated privileges to open` or `create`

The target file or parent directory is not writable by the current process. Re-run in the correct account, adjust permissions, or use `sudo` when intentionally editing privileged files.

### 10.2 `file hasn't changed`

The content after the editor exited matched the content initially placed in the temporary file. No backup was created and the target was not overwritten.

### 10.3 `No history found for FILE`

`--restore-last` could not find backup files whose names start with `FILE`'s basename plus `.orig.` in the selected backup directory. Check `--backup-dir` and `mirro --list`.

### 10.4 `Could not determine original file location from backup header`

`--restore` found the backup file, but the text did not contain a readable `# Original file:` line before the first blank line.

### 10.5 Diff says the backup does not match the file

`--diff` requires the backup filename to start with the current file's basename plus `.orig.`. Use the matching backup file or pass the intended current file.

### 10.6 Prune did not use the expected age

`mirro --prune-backups` reads `MIRRO_BACKUPS_LIFE`. Invalid, missing, zero, or negative values fall back to `30` days. Use `mirro --prune-backups=N` to pass an explicit age.

---

## 11. Practical code-reading map

Feature/question | Start with | Then read
--- | --- | ---
Version output | `get_version()` | `pyproject.toml`
Backup writing | `backup_original()` | normal edit flow near end of `main()`
Header stripping | `strip_mirro_header()` | restore and diff branches
Original path parsing | `extract_original_path()` | `--restore` branch
CLI option behavior | `main()` parser setup | action branch dispatch order
Editor invocation | normal edit flow | tests using patched `subprocess.call()`
Backup listing | `--list` branch | README examples
Restore latest | `--restore-last` branch | backup filename format
Restore specific backup | `--restore` branch | `extract_original_path()`
Diff output | `--diff` branch | `difflib.unified_diff`
Status output | `--status` branch | basename grouping logic
Pruning | `--prune-backups` branch | `MIRRO_BACKUPS_LIFE` docs
Tests | `tests/test_mirro.py` | pytest docs
Packaging | `pyproject.toml` | Poetry docs
Automation | `.gitea/workflows/` | `.pre-commit-config.yaml`

---

## 12. Glossary

**Target file** The file the user asked `mirro` to edit or restore.

**Temporary file** The editable copy passed to `$EDITOR` during normal edit flow.

**Backup directory** The directory containing mirro backup files, defaulting to `~/.local/share/mirro`.

**Backup file** A plain text file named like `name.orig.YYYYMMDDTHHMMSS` containing a mirro header and original content.

**Mirro header** The leading comment block that records the original path and backup timestamp.

**Restore-last** The action that restores the newest backup matching a target basename.

**Restore** The action that restores a specific backup to the original path recorded in its header.

**Prune** Deletion of files from the selected backup directory by age or all-at-once mode.

---

## 13. Final maintenance model

Most changes should preserve this model:

```text
Edit a temporary text copy
  -> compare before writing
  -> back up original content only when changed
  -> then overwrite the target with edited content
  -> keep backup inspection and restoration simple and explicit
```

Before changing code, ask:

1. Is this a CLI parsing concern, backup-format concern, editor-invocation concern, or restore/prune concern?
2. Does the change preserve the temporary-file editing model?
3. Is the backup created before the target is overwritten?
4. Are existing backup files still restorable?
5. Does basename-based matching still behave predictably?
6. Does `--backup-dir` remain clearly treated as trusted local state?
7. Are text encoding and binary-file limitations explicit?
8. Are README examples and shell completion expectations still accurate?
9. Are there focused tests for the edge case being changed?

Keeping those boundaries clear is the main way to maintain `mirro` without turning a narrow safe-editing wrapper into a misleading general-purpose recovery system.
