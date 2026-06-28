# mirro Threat Model and Security Scope

`mirro` is a command-line systems administration tool. It is designed to be executed intentionally by an operator, sometimes with elevated privileges, to edit text files through a temporary copy and save a backup before changed content is written back.

Because of that design, `mirro`'s security model is different from that of a network service, web application, daemon, sandbox, or setuid program. `mirro` does not attempt to defend against arbitrary local compromise of the account executing it. If an attacker can control the command line, environment, working directory, `EDITOR`, selected backup directory, installed Python package, or editor binary used by the operator, they may be able to influence what `mirro` does. That situation is considered a local trust-boundary failure outside `mirro`'s intended security model.

`mirro` is for text-file editing safety. It does not provide full filesystem rollback, access-control enforcement, sandboxing, cryptographic integrity, or protection from a hostile local environment.

## Core Assumptions

`mirro` assumes that the person running the tool understands what they are asking it to do.

In particular:

- If `mirro` is run as root, the root user is assumed to control and understand the command line, environment, `EDITOR`, backup directory, and target file being used.
- If `--backup-dir` is used, the selected directory and its contents are assumed to be trusted local administrative state chosen by the operator.
- If `--restore` is used, the selected backup file is assumed to be trusted and intentionally selected by the operator.
- If `--restore-last` is used, the operator accepts basename-based matching in the selected backup directory.
- If `--prune-backups` is used, the operator intends to delete regular files from the selected backup directory according to the requested mode.
- The configured editor is assumed to be the trusted editor implementation that the operator intended to execute.
- The operator is expected to understand the impact of editing or restoring privileged files, especially when running as root.

## What mirro Records

`mirro` backups are plain text files. A backup records:

- The original file path in a header.
- A UTC timestamp in the header.
- The original text content after the header.

Backup filenames include:

- The original file basename.
- The `.orig.` marker.
- A UTC timestamp with one-second resolution.

`mirro` does not record:

- File ownership.
- File permissions.
- ACLs.
- Extended attributes.
- Capabilities.
- SELinux, AppArmor, or other MAC labels.
- File hashes or signatures.
- A database manifest.
- A transactional history across multiple files.

Backups can contain sensitive file contents. Backup directories must be protected accordingly.

## What Is In Scope

`mirro` tries to protect careful administrators from common editing mistakes that occur when changing text files.

In-scope security and safety concerns include:

- Normal edit mode must not edit the target file directly through the editor.
- Normal edit mode must use a temporary file for the editor session.
- Normal edit mode must not overwrite the target when edited content is unchanged.
- Normal edit mode must create the backup before writing changed content to the target.
- The editor should be invoked without `shell=True`.
- The temporary file should be removed after the editor session is read back.
- Backup headers should preserve enough information to identify the original path.
- Header stripping should remove only mirro's own backup header, not arbitrary comments or shebangs.
- `--diff` should reject backups whose filename does not match the target file basename.
- Permission checks should fail clearly when the current process cannot write the target or target parent.
- Dependency and source scans should continue to run in project automation.

These measures are defense-in-depth. They reduce the chance of accidental data loss or unintended edits when `mirro` is used normally by an administrator.

## What Is Out Of Scope

The following are generally out of scope and should not be reported as `mirro` vulnerabilities unless they also bypass one of `mirro`'s explicit safety mechanisms:

- A malicious local user who can already control the root user's command line, shell environment, working directory, `EDITOR`, `PATH`, Python environment, installed package, or editor binary.
- A root user intentionally editing or restoring a sensitive file.
- A root user intentionally selecting a malicious backup file with `--restore`.
- A root user intentionally pointing `--backup-dir` at a malicious or shared directory.
- A user intentionally setting `EDITOR` to a malicious command.
- A user relying on `mirro` to preserve ownership, permissions, ACLs, xattrs, capabilities, MAC labels, or binary file bytes.
- A user relying on `mirro` as a sandbox for untrusted editors, untrusted local users, or untrusted backup files.
- A compromised system where an attacker already controls root-owned files, root's shell, root's Python packages, root's environment, or editor binaries.
- Reports that amount to "if root runs this tool with malicious options, root can overwrite files."

`mirro` is a tool for administrators, not a sandbox for hostile local users. It cannot make unsafe local trust decisions safe if the operator's own execution environment is already attacker-controlled.

## Trusted Backup Directories

By default, `mirro` stores backups in:

```text
~/.local/share/mirro
```

Operators may override this with `--backup-dir`.

Backup directories should be treated as trusted local state. Backups contain file contents and an `Original file:` path that `--restore` uses as the write target. A maliciously edited backup can cause `mirro --restore` to write attacker-chosen content to the path recorded in the header, subject to the privileges of the user running `mirro`.

The backup directory should not be world-writable or shared with untrusted users. Before restoring, especially as root, the operator should be confident that the selected backup is the intended one and has not been tampered with.

## Restore Behavior

`mirro` has two restore modes:

```bash
mirro --restore-last /path/to/file
mirro --restore file.orig.20250101T010203
```

`--restore-last` finds the newest backup whose filename starts with the target file's basename plus `.orig.`. It does not verify that the backup header's original path matches the requested target path.

`--restore` reads the selected backup file, extracts the `Original file:` path from its header, strips the mirro header, creates missing parent directories if needed, and writes the restored text to that target.

Both restore modes overwrite text at the target path when the current process has permission. There is currently no confirmation prompt or dry-run mode for restore.

This is intentional current behavior, but it means restore operations should be treated as privileged file writes when run with elevated permissions.

## Prune Behavior

`mirro --prune-backups` deletes regular files from the selected backup directory.

Supported forms are:

```bash
mirro --prune-backups
mirro --prune-backups=14
mirro --prune-backups=all
```

Default mode reads `MIRRO_BACKUPS_LIFE`, falling back to `30` days for missing or invalid values. Numeric mode removes regular files older than the cutoff. `all` mode removes every regular file in the backup directory.

Prune does not currently require confirmation, provide a dry run, or validate that files contain mirro headers before deleting them. Operators should use `--backup-dir` carefully.

## Editor Execution

`mirro` runs the configured editor as the current user:

```text
$EDITOR, or nano when unset
```

The editor command is split with `editor.split()` and executed with `subprocess.call()` without `shell=True`. This avoids shell expansion by `mirro` itself, but it does not make the editor trusted. A malicious editor can read, modify, delete, or exfiltrate files accessible to the current user.

`EDITOR` is part of the local trust boundary. Do not run `mirro` with elevated privileges while inheriting an untrusted environment.

## Text Encoding and Binary Files

`mirro` reads text using UTF-8 with replacement for invalid bytes and writes UTF-8 text.

This means `mirro` is not byte-preserving for arbitrary binary files or text files with invalid UTF-8. If such a file is edited and saved, invalid byte sequences may be replaced.

Reports that `mirro` is not a binary-safe editor wrapper are not security issues by themselves. User-facing documentation should keep describing `mirro` as a text-file editing wrapper.

## Symlinks and Filesystem Races

`mirro` does not currently implement no-follow symlink protections. It uses normal path operations such as `Path.exists()`, `read_text()`, `write_text()`, and `os.access()`. If the selected target path is a symlink, operations generally affect the symlink target.

Because `mirro` operates on a live filesystem, concurrent changes can affect what exists at the moment it reads, backs up, restores, prunes, or writes. `mirro` does not claim to provide transactional filesystem semantics.

Avoid using `mirro` in hostile writable directories or on paths that untrusted users can replace while the command is running, especially with elevated privileges.

## Local Compromise

`mirro` includes some hardening for ordinary safe editing, such as editing a temporary file, comparing before writeback, creating a backup before overwrite, and avoiding `shell=True` for editor invocation.

However, local compromise cannot be ruled out completely for a privileged CLI tool. If an attacker can influence the administrator's shell, environment, backup directory, backup files, Python packages, current working directory, editor binary, or command-line arguments, they may be able to influence `mirro`'s behavior.

Such scenarios are treated as local compromise or operator trust failures, not as vulnerabilities in `mirro` by themselves.

## Security Report Guidance

Useful vulnerability reports include issues where `mirro` behaves unsafely despite the documented trust model. Examples include:

- Normal edit mode overwrites the target file even though edited content is unchanged.
- Normal edit mode writes changed content before creating the backup.
- Normal edit mode invokes the editor through a shell in a way that enables shell injection.
- Header stripping removes non-mirro content such as a shebang or ordinary leading comments.
- `--diff` accepts a clearly mismatched backup filename despite its basename check.
- A permission failure is silently ignored and `mirro` proceeds with a write that should have been rejected.
- Temporary files are predictably named or left behind with sensitive content in ordinary successful operation.
- Project automation stops running meaningful lint, dependency audit, or security scans.

Less useful reports, and normally out of scope, include:

- "Root can edit dangerous files."
- "Root can restore malicious content from a malicious backup."
- "Root can choose a dangerous backup directory."
- "A malicious `$EDITOR` can execute code."
- "A malicious local user can compromise `mirro` after already controlling root's environment, Python packages, backup files, or editor binary."
- "`mirro` does not preserve file permissions, ownership, ACLs, xattrs, capabilities, or binary bytes."
- "`mirro --prune-backups=all` deletes files from the backup directory selected by the operator."

Reports about concrete bypasses of `mirro`'s documented safety behavior are welcome. The project does not treat intentional administrator-controlled execution as a vulnerability by itself.
