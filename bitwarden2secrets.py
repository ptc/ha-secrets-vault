"""
bitwarden2secrets.py
Liest das Bitwarden-Item (Secure Note) mit den Home-Assistant-Secrets aus
und schreibt daraus die secrets.yaml. Gegenstück zu secrets2bitwarden.py.

DRY RUN ist Standard: Ohne --apply wird keine Datei geschrieben,
es wird nur angezeigt, was passieren würde.

Voraussetzungen:
  - Bitwarden CLI installiert:  https://bitwarden.com/help/cli/
  - Angemeldet und entsperrt:   bw login / bw unlock (BW_SESSION setzen)
  - Python:        pip install pyyaml

Beispiele:
  # Dry Run (Standard): nur anzeigen, nichts schreiben:
  python bitwarden2secrets.py --target /config/secrets.yaml

  # secrets.yaml wirklich erzeugen/überschreiben:
  python bitwarden2secrets.py --target /config/secrets.yaml --apply

  # Mit eigenem Item-Namen und Backup der bestehenden Datei:
  python bitwarden2secrets.py --target secrets.yaml --apply \
      --item-name "HA Secrets" --backup
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

log = logging.getLogger("bitwarden2secrets")


def bw(args, session, apply_mode):
    """Führt einen bw-CLI-Befehl aus und gibt stdout zurück."""
    cmd = ["bw"]
    if session:
        cmd += ["--session", session]
    cmd += args
    display = [c if c != session else "***" for c in cmd]
    log.debug("bw-Befehl: %s", " ".join(display))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"bw {args[0]} fehlgeschlagen: {proc.stderr.strip()}")
    log.debug("bw-stdout (gekürzt): %s", proc.stdout[:200])
    return proc.stdout


def get_session(args_session):
    """Session-Key ermitteln: CLI-Arg, Umgebungsvariable oder None."""
    if args_session:
        return args_session
    return os.environ.get("BW_SESSION")


def check_status(session):
    """Prüft Login- und Unlock-Status der CLI."""
    status = json.loads(bw(["status"], session, True))
    state = status.get("status")
    if state == "unauthenticated":
        sys.exit("Nicht angemeldet. Bitte zuerst 'bw login' ausführen.")
    if state == "locked":
        sys.exit(
            "Vault ist gesperrt. Bitte 'bw unlock' ausführen und BW_SESSION "
            "setzen (die Shell gibt nach dem Unlock den export-Befehl aus)."
        )
    log.info("Vault-Status: %s (Konto: %s)", state, status.get("userEmail", "?"))


def get_item_by_name(name, session):
    """Sucht das Item per 'bw list items' und gibt es zurück (oder None)."""
    items = json.loads(bw(["list", "items"], session, True))
    for item in items:
        if item["name"] == name:
            log.debug("Item '%s' gefunden (id=%s).", name, item["id"])
            return item
    return None


def item_to_secrets(item):
    """Extrahiert die Key/Value-Paare aus den (versteckten) Feldern des Items."""
    fields = item.get("fields") or []
    if not fields:
        log.warning("Item '%s' enthält keine Felder.", item.get("name"))
    secrets = {}
    for field in fields:
        key = field.get("name")
        if key is None:
            continue
        value = field.get("value")
        secrets[str(key)] = "" if value is None else str(value)
    log.debug("Felder gelesen: %s", ", ".join(secrets) or "(keine)")
    return secrets


def load_existing(path):
    """Liest eine bestehende secrets.yaml ein (für Merge/Backup)."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def render_yaml(secrets):
    """Erzeugt den YAML-Text mit Kommentar-Header."""
    header = (
        f"# secrets.yaml – erzeugt am {datetime.now():%Y-%m-%d %H:%M} "
        "aus Bitwarden (bitwarden2secrets.py)\n"
    )
    body = yaml.safe_dump(
        secrets, default_flow_style=False, allow_unicode=True, sort_keys=True
    )
    return header + body


def main():
    parser = argparse.ArgumentParser(
        description="Bitwarden-Item in Home Assistant secrets.yaml exportieren "
                    "(Standard: Dry Run, echtes Schreiben nur mit --apply)"
    )
    parser.add_argument("--target", default="secrets.yaml",
                        help="Zielpfad der secrets.yaml (Standard: ./secrets.yaml)")
    parser.add_argument("--item-name", default="Home Assistant Secrets",
                        help="Name des Bitwarden-Items (Standard: 'Home Assistant Secrets')")
    parser.add_argument("--merge", action="store_true",
                        help="Bestehende secrets.yaml nicht ersetzen, sondern "
                             "die Vault-Werte in sie hinein mergen")
    parser.add_argument("--backup", action="store_true",
                        help="Vor dem Schreiben eine Sicherungskopie der "
                             "bestehenden Datei anlegen (.bak.<Zeitstempel>)")
    parser.add_argument("--apply", action="store_true",
                        help="Datei wirklich schreiben (Standard: Dry Run)")
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

    if shutil.which("bw") is None:
        sys.exit("Bitwarden CLI 'bw' nicht gefunden. Installation: "
                 "https://bitwarden.com/help/cli/")

    session = get_session(args.session)
    check_status(session)

    item = get_item_by_name(args.item_name, session)
    if item is None:
        sys.exit(f"Kein Item mit Namen '{args.item_name}' im Vault gefunden.")

    secrets = item_to_secrets(item)
    if not secrets:
        sys.exit("Keine verwertbaren Felder im Item gefunden.")
    log.info("%d Secrets aus Item '%s' gelesen.", len(secrets), args.item_name)

    if args.merge:
        existing = load_existing(args.target)
        log.info("Merge: %d bestehende Einträge in %s berücksichtigt.",
                 len(existing), args.target)
        existing.update(secrets)
        secrets = existing

    content = render_yaml(secrets)

    if not args.apply:
        log.info("[DRY RUN] Würde %s schreiben (%d Einträge):",
                 args.target, len(secrets))
        print("\n" + content)
        log.info("Keine Datei geschrieben. Mit --apply wirklich speichern.")
        return

    if args.backup and os.path.exists(args.target):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = f"{args.target}.bak.{stamp}"
        shutil.copy2(args.target, backup_path)
        log.info("Backup angelegt: %s", backup_path)

    with open(args.target, "w", encoding="utf-8") as f:
        f.write(content)
    log.info("secrets.yaml geschrieben: %s (%d Einträge).", args.target,
             len(secrets))
    log.info("Fertig (APPLY).")


if __name__ == "__main__":
    main()
