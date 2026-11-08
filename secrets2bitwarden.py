#!/usr/bin/env python3
"""
secrets2bitwarden.py
Liest die secrets.yaml von Home Assistant ein und legt alle Key/Value-Paare
als versteckte Custom Fields in einem einzigen Bitwarden-Item (Secure Note) ab.

DRY RUN ist Standard: Ohne --apply wird nichts im Vault geschrieben,
es wird nur angezeigt, was passieren würde.

Voraussetzungen:
  - Bitwarden CLI installiert:  https://bitwarden.com/help/cli/
  - Angemeldet:    bw login
  - Entsperrt:     bw unlock   (Session-Key via BW_SESSION Umgebungsvariable
                   oder --session übergeben)
  - Python:        pip install pyyaml

Beispiele:
  # Dry Run (Standard): nur anzeigen, kein Schreibzugriff:
  python secrets2bitwarden.py /pfad/zu/config/secrets.yaml

  # Echter Import ins Item "Home Assistant Secrets":
  python secrets2bitwarden.py secrets.yaml --apply

  # Eigenen Item-Namen, Ordner, Update und Debug-Ausgabe:
  python secrets2bitwarden.py secrets.yaml --apply --debug \
      --item-name "HA Secrets" --folder "Home Assistant" --update
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime

try:
    import yaml
except ImportError:
    sys.exit("PyYAML fehlt: pip install pyyaml")

log = logging.getLogger("secrets2bitwarden")


def bw(args, session, apply_mode, input_data=None):
    """Führt einen bw-CLI-Befehl aus und gibt stdout zurück (nur mit --apply)."""
    cmd = ["bw"]
    if session:
        cmd += ["--session", session]
    cmd += args
    display = [c if c != session else "***" for c in cmd]
    log.debug("bw-Befehl: %s%s", " ".join(display),
              "" if input_data is None else " (JSON via stdin)")
    if not apply_mode:
        log.debug("DRY RUN: Befehl nicht ausgeführt.")
        return "[]"
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          input=input_data)
    if proc.returncode != 0:
        raise RuntimeError(f"bw {args[0]} fehlgeschlagen: {proc.stderr.strip()}")
    log.debug("bw-stdout (gekürzt): %s", proc.stdout[:200])
    return proc.stdout


def encode_json(data, session, apply_mode):
    """Kodiert JSON-Item-Daten base64, wie es 'bw create/edit' erwartet."""
    out = bw(["encode"], session, apply_mode, input_data=json.dumps(data))
    encoded = out.strip()
    log.debug("Kodierte Item-Daten: %s...", encoded[:50])
    return encoded


def get_session(args_session):
    """Session-Key ermitteln: CLI-Arg, Umgebungsvariable oder None."""
    if args_session:
        return args_session
    return os.environ.get("BW_SESSION")


def check_status(apply_mode):
    """Prüft Login- und Unlock-Status der CLI (nur mit --apply)."""
    if not apply_mode:
        log.info("DRY RUN: Vault-Statusprüfung übersprungen.")
        return
    status = json.loads(bw(["status"], None, apply_mode))
    state = status.get("status")
    if state == "unauthenticated":
        sys.exit("Nicht angemeldet. Bitte zuerst 'bw login' ausführen.")
    if state == "locked":
        sys.exit(
            "Vault ist gesperrt. Bitte 'bw unlock' ausführen und BW_SESSION "
            "setzen (die Shell gibt nach dem Unlock den export-Befehl aus)."
        )
    log.info("Vault-Status: %s (Konto: %s)", state, status.get("userEmail", "?"))


def load_secrets(path):
    """Liest die secrets.yaml ein: einfache key: value Paare."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        sys.exit(f"{path} enthält keine Key/Value-Struktur.")
    secrets = {str(k): str(v) for k, v in data.items()}
    log.debug("%d Secrets geladen: %s", len(secrets), ", ".join(secrets))
    return secrets


def find_folder(name, session, apply_mode):
    """Gibt die ID eines vorhandenen Ordners zurück oder None."""
    if not apply_mode:
        log.info("[DRY RUN] Würde nach Ordner '%s' suchen.", name)
        return None
    folders = json.loads(bw(["list", "folders"], session, apply_mode))
    for folder in folders:
        if folder["name"] == name:
            log.debug("Ordner '%s' gefunden (id=%s).", name, folder["id"])
            return folder["id"]
    log.debug("Ordner '%s' nicht gefunden.", name)
    return None


def create_folder(name, session, apply_mode):
    """Legt einen neuen Ordner an und gibt dessen ID zurück."""
    log.info("Ordner '%s' wird angelegt...", name)
    if not apply_mode:
        log.info("[DRY RUN] Ordner-Anlegung nur simuliert.")
        return "dryrun-folder-id"
    out = bw(["create", "folder", encode_json({"name": name}, session, apply_mode)],
             session, apply_mode)
    return json.loads(out)["id"]


def find_item(name, session, apply_mode):
    """Sucht ein vorhandenes Item mit exakt diesem Namen."""
    if not apply_mode:
        log.info("[DRY RUN] Würde nach Item '%s' suchen.", name)
        return None
    items = json.loads(bw(["list", "items"], session, apply_mode))
    for item in items:
        if item["name"] == name:
            log.debug("Existierendes Item '%s' gefunden (id=%s).", name, item["id"])
            return item
    log.debug("Kein existierendes Item '%s' gefunden.", name)
    return None


def build_item_json(secrets, item_name, folder_id, notes):
    """Baut das Item-JSON: Secure Note mit jedem Secret als verstecktes Feld."""
    fields = [
        {"name": key, "value": value, "type": 1}  # type 1 = hidden
        for key, value in secrets.items()
    ]
    log.debug("Felder geplant: %s", ", ".join(f["name"] for f in fields))
    return {
        "type": 2,  # 2 = Secure Note
        "secureNote": {"type": 0},
        "name": item_name,
        "notes": notes,
        "fields": fields,
        "folderId": folder_id,
    }


def main():
    parser = argparse.ArgumentParser(
        description="secrets.yaml aus Home Assistant in Bitwarden importieren "
                    "(Standard: Dry Run, echtes Schreiben nur mit --apply)"
    )
    parser.add_argument("secrets_file", help="Pfad zur secrets.yaml")
    parser.add_argument("--item-name", default="Home Assistant Secrets",
                        help="Name des Bitwarden-Items (Standard: 'Home Assistant Secrets')")
    parser.add_argument("--folder", default=None,
                        help="Optional: Ordner, in dem das Item abgelegt wird")
    parser.add_argument("--update", action="store_true",
                        help="Existierendes Item mit gleichem Namen aktualisieren")
    parser.add_argument("--apply", action="store_true",
                        help="Echte Schreibzugriffe auf den Vault ausführen "
                             "(ohne diesen Flag läuft das Skript im Dry Run)")
    parser.add_argument("--session", default=None,
                        help="Session-Key von 'bw unlock' (alternativ BW_SESSION env)")
    parser.add_argument("-v", "--debug", action="store_true",
                        help="Debug-Ausgabe (bw-Befehle, gefundene IDs, Feldliste)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    mode = "APPLY" if args.apply else "DRY RUN"
    log.info("Modus: %s", mode)

    if args.apply and shutil.which("bw") is None:
        sys.exit("Bitwarden CLI 'bw' nicht gefunden. Installation: "
                 "https://bitwarden.com/help/cli/")

    session = get_session(args.session)
    check_status(args.apply)

    secrets = load_secrets(args.secrets_file)
    log.info("%d Secrets aus %s gelesen.", len(secrets), args.secrets_file)

    folder_id = None
    if args.folder:
        folder_id = find_folder(args.folder, session, args.apply)
        if folder_id is None:
            folder_id = create_folder(args.folder, session, args.apply)
        else:
            log.info("Ordner '%s' gefunden.", args.folder)

    notes = (
        f"Automatisch importiert am {datetime.now():%Y-%m-%d %H:%M} "
        f"aus {os.path.basename(args.secrets_file)}. "
        "Alle secrets.yaml-Einträge sind als versteckte Felder hinterlegt."
    )
    item_json = build_item_json(secrets, args.item_name, folder_id, notes)

    existing = find_item(args.item_name, session, args.apply)
    if existing:
        if not args.update:
            sys.exit(
                f"Item '{args.item_name}' existiert bereits. "
                "Mit --update überschreiben/aktualisieren."
            )
        item_json["id"] = existing["id"]
        existing.update(item_json)
        log.info("Aktualisiere Item '%s' (%d versteckte Felder)...",
                 args.item_name, len(secrets))
        if args.apply:
            bw(["edit", "item", existing["id"],
                encode_json(existing, session, args.apply)],
               session, args.apply)
            log.info("Item '%s' aktualisiert.", args.item_name)
    else:
        log.info("Erstelle Item '%s' (%d versteckte Felder)...",
                 args.item_name, len(secrets))
        if args.apply:
            bw(["create", "item", encode_json(item_json, session, args.apply)],
               session, args.apply)
            log.info("Item '%s' erstellt.", args.item_name)

    log.info("Fertig (%s).", mode)
    if not args.apply:
        log.info("Keine Änderungen am Vault vorgenommen. "
                 "Für den echten Import '--apply' anhängen.")


if __name__ == "__main__":
    main()
