# ha-secrets-vault

Bidirectional sync between the Home Assistant `secrets.yaml` and a
Bitwarden vault.

- **`secrets2bitwarden.py`**: `secrets.yaml` → Bitwarden. All key/value pairs
  are stored as **hidden custom fields** in **a single** secure-note item
  (default name: "Home Assistant Secrets").
- **`bitwarden2secrets.py`**: Bitwarden → `secrets.yaml`. Reads the item from
  the vault and generates the `secrets.yaml` from it (the reverse direction).

Both scripts run in **dry run** mode by default and only write something for
real when `--apply` is passed.

## Features (both scripts)

- **Dry run by default**: Without `--apply`, nothing is changed; it only shows
  what would happen.
- **`--apply`**: Real access (write to the vault or file).
- **`-v` / `--debug`**: Debug output with the executed `bw` commands,
  found IDs, and the field list.
- **`--session KEY`** or the `BW_SESSION` environment variable for the
  unlock session key.

### Additionally in `secrets2bitwarden.py`

- **`--update`**: Update an existing item instead of aborting.
- **`--folder NAME`**: Optionally place the item in a Bitwarden folder
  (the folder is created if needed).

### Additionally in `bitwarden2secrets.py`

- **`--target PATH`**: Target path of the `secrets.yaml` (default: `./secrets.yaml`).
- **`--merge`**: Do not replace an existing `secrets.yaml`, but merge the
  vault values into it.
- **`--backup`**: Create a backup copy
  (`secrets.yaml.bak.<timestamp>`) before writing.

## Prerequisites

- **Bitwarden CLI (`bw`)**: <https://bitwarden.com/help/cli/>
- **Python 3.10+**
- Dependencies from `requirements.txt` (only `PyYAML`)

## Installation

### 1. Set up a virtual environment

```bash
cd secrets2bitwarden

# create venv
python3 -m venv .venv

# activate
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows (PowerShell: .venv\Scripts\Activate.ps1)
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Log in and unlock the Bitwarden CLI

```bash
bw login
bw unlock
# After unlocking, the shell prints a line:
#   export BW_SESSION="xxxx..."
# Run it (or call the scripts with --session "xxxx...").
```

## Usage

### secrets.yaml → Bitwarden (up)

```bash
# 1. Dry run (default): only show, write nothing
python secrets2bitwarden.py /path/to/config/secrets.yaml

# Dry run with debug output
python secrets2bitwarden.py secrets.yaml -v

# 2. Real import
python secrets2bitwarden.py secrets.yaml --apply

# With custom item name, folder, and updating existing items
python secrets2bitwarden.py secrets.yaml --apply \
    --item-name "HA Secrets" --folder "Home Assistant" --update
```

### Bitwarden → secrets.yaml (down, e.g. on a new system)

```bash
# 1. Dry run (default): only shows the generated file
python bitwarden2secrets.py --target /config/secrets.yaml

# 2. Actually write
python bitwarden2secrets.py --target /config/secrets.yaml --apply

# With custom item name, merge, and backup
python bitwarden2secrets.py --target secrets.yaml --apply \
    --item-name "HA Secrets" --merge --backup
```

### Example output (dry run)

```text
INFO    Mode: DRY RUN
INFO    Vault status: unlocked (account: you@example.com)
INFO    Read 3 secrets from item 'Home Assistant Secrets'.
INFO    [DRY RUN] Would write /config/secrets.yaml (3 entries):
INFO    No file written. Use --apply to save for real.
```

## All options

### `secrets2bitwarden.py`

| Option | Description |
|---|---|
| `secrets_file` | Path to the `secrets.yaml` (required) |
| `--apply` | Perform real write operations (default: dry run) |
| `--item-name NAME` | Name of the Bitwarden item (default: `Home Assistant Secrets`) |
| `--folder NAME` | Optional Bitwarden folder |
| `--update` | Update an existing item instead of aborting |
| `--session KEY` | Session key from `bw unlock` (alternatively `BW_SESSION` env) |
| `-v`, `--debug` | Debug output |

### `bitwarden2secrets.py`

| Option | Description |
|---|---|
| `--target PATH` | Target path of the `secrets.yaml` (default: `./secrets.yaml`) |
| `--apply` | Actually write the file (default: dry run) |
| `--item-name NAME` | Name of the Bitwarden item (default: `Home Assistant Secrets`) |
| `--merge` | Merge vault values into an existing `secrets.yaml` instead of replacing it |
| `--backup` | Backup copy `.bak.<timestamp>` before writing |
| `--session KEY` | Session key from `bw unlock` (alternatively `BW_SESSION` env) |
| `-v`, `--debug` | Debug output |

## Security notes

- Secret values are **never** printed, even in debug mode — only the key names.
- The generated `secrets.yaml` lies in plaintext on the filesystem:
  set permissions accordingly (`chmod 600 secrets.yaml`).
- The `secrets.yaml` is still needed by Home Assistant; the Bitwarden item
  is the encrypted backup, and downloading it to a new system serves as
  recovery.
- Both scripts run exclusively locally; all vault access goes through the
  official `bw` CLI.

## Project structure

```text
secrets2bitwarden/
├── secrets2bitwarden.py   # secrets.yaml → Bitwarden (up)
├── bitwarden2secrets.py   # Bitwarden → secrets.yaml (down)
├── requirements.txt       # Python dependencies
└── README.md              # This file
```
