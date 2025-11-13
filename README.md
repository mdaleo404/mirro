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
filename.ext.orig.20251110T174400.bak
```

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