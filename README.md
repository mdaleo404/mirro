# mirro

**mirro** is a tiny safety-first editing wrapper for text files.
You edit a temporary file, **mirro** detects whether anything changed, and if it did, it saves a backup of the original before writing your changes.


## Why mirro?

Well... have you ever been in the _“ugh, I forgot to back this up first”_ situation? 

No?

Stop lying... (:))

**mirro** gives you a built-in safety net:

- never edits the real file directly

- detects whether the edit actually changed content

- creates a timestamped backup only when changes occurred

- clearly labels backups so you know exactly what they came from

- respects the user’s `$EDITOR` when possible

- requires `sudo` only when actually needed

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

**NOTE**: To use mirro with sudo, the path to mirro must be in the $PATH seen by root.
Either install mirro as root (preferred), use sudo -E mirro, or add the $PATH to /etc/sudoers using its Defaults secure_path parameter.

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
