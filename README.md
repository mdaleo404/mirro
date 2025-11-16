# mirro

**mirro** is a tiny safety-first editing wrapper for text files.
You edit a temporary file, **mirro** detects whether anything changed, and if it did, it saves a backup of the original before writing your changes.


## Why mirro?

Well... have you ever been in the _“ugh, I forgot to back this up first”_ situation?

No?

Stop lying... 🥸

**mirro** gives you a built-in safety net:

- never edits the real file directly

- detects whether the edit actually changed content

- creates a timestamped backup only when changes occurred

- clearly labels backups so you know exactly what they came from

- respects the user’s `$EDITOR` when possible

- requires `sudo` only when actually needed

- accepts most of your favourite editor's flags

It’s simple, predictable, and hard to misuse.

I mean... the only thing you need to remember is _to use it_.

## How it works

**mirro** reads the original file (or pre-populates new files with a friendly message).

It writes that content into a temporary file.

It launches your `$EDITOR` to edit the temp file.

When the editor closes, **mirro** compares old vs new.

If nothing changed:
```
file hasn't changed
```

If changed:
```
file changed; original backed up at: ~/.local/share/mirro/ (or /root/.local/share/mirro/ under sudo)
```

Backed up files include a header:
```
# ---------------------------------------------
# mirro backup
# Original file: /path/to/whatever.conf
# Timestamp: 2025-11-10 17:44:00 UTC
# ---------------------------------------------
```

So you never lose track of the original location.

### Backup directory

By default all the backups will be stored at:
```
~/.local/share/mirro/
```
so under `sudo`:
```
/root/.local/share/mirro/
```

Backups are named like:
```
filename.ext.orig.20251110T174400
```

## Functionalities

### List all backup files stored in your backup directory.
```
mirro --list
```
Output includes permissions, owner/group, timestamps, and backup filenames.

### Restore the most recent backup for a given file.
```
mirro --restore-last ~/.config/myapp/config.ini
```
This:
1. finds the newest backup matching the filename,

2. strips the mirro header from it,

3. and overwrites the target file with its original contents.

### Remove old backup files.
```
mirro --prune-backups
```
This removes backups older than the number of days set in `MIRRO_BACKUPS_LIFE`.

### Remove backups older than _N_ days
```
mirro --prune-backups=14
```
This keeps the last 14 days of backups and removes everything older.

### Remove all backups
```
mirro --prune-backups=all
```
This deletes every backup in the backup directory.

### Environment Variable
`MIRRO_BACKUPS_LIFE` controls the default number of days to keep when using `mirro --prune-backups`.
Its default value is **30** if not set otherwise.
```
export MIRRO_BACKUPS_LIFE=7
```
Backups older than 7 days will be removed.

Invalid or non-numeric values fall back to 30 days.

**Note:** _a value of 0 is **invalid**_.


## Installation

**NOTE:** To use `mirro` with `sudo`, the path to `mirro` must be in the `$PATH` seen by `root`.\
Either:

 * install `mirro` as `root` (_preferred_), or
 * add the path to `mirro` to the `secure_path` parameter in `/etc/sudoers`. For example, where `/home/user/.local/bin` is where `mirro` is:

``` bash
Defaults secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/user/.local/bin"
```

Install via PyPI (preferred):
```
pip install mirro
```

Or clone the repo and install locally:
```
git clone https://github.com/mdaleo404/mirro.git
cd mirro/
poetry install
```

## How to run the tests

- Clone this repository

- Ensure you have Poetry installed

- Run `poetry run pytest -vvvv --cov=mirro --cov-report=term-missing --disable-warnings`

## pre-commit
This project uses [**pre-commit**](https://pre-commit.com/) to run automatic formatting and security checks before each commit (Black, Bandit, and various safety checks).

To enable it:
```
poetry install
poetry run pre-commit install
```
This ensures consistent formatting, catches common issues early, and keeps the codebase clean.
