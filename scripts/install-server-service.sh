#!/bin/sh
# Install only after testing the user's private configuration in the foreground.
set -eu
if [ "$(id -u)" != 0 ]; then
    printf '%s\n' 'Run with sudo: install-server-service.sh SERVICE_USER' >&2
    exit 1
fi
if [ "$#" != 1 ]; then
    printf '%s\n' 'Usage: install-server-service.sh SERVICE_USER' >&2
    exit 1
fi
app_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python3 - "$1" "$app_dir" <<'PY'
import grp
import json
import os
import pwd
import re
import stat
import sys
from pathlib import Path

name, app_path = sys.argv[1:]
if not re.fullmatch(r"[a-z_][a-z0-9_-]*[$]?", name):
    raise SystemExit("Use an existing local service account name")
account = pwd.getpwnam(name)
if account.pw_uid == 0:
    raise SystemExit("The controller must run as a non-root account")
app = Path(app_path).resolve()
if app.name != "app":
    raise SystemExit("Clone the repository into INSTALL_ROOT/app; see the setup guide")
root = app.parent
if any(ord(character) < 32 for character in str(root)):
    raise SystemExit("Installation path cannot contain control characters")
if not (root / ".venv/bin/python").is_file() or not (root / "private").is_dir():
    raise SystemExit("Prepare the virtual environment and private directory first")
config_path = root / "config.json"
config = json.loads(config_path.read_text())
if config.get("schedule_enabled"):
    raise SystemExit("First install with schedule_enabled set to false")
if "YOUR_" in config_path.read_text():
    raise SystemExit("Replace configuration placeholders before installing")
private = root / "private"
if private.stat().st_uid != account.pw_uid or config_path.stat().st_uid != account.pw_uid:
    raise SystemExit("The service account must own its configuration and private directory")
if stat.S_IMODE(private.stat().st_mode) & 0o077:
    raise SystemExit("Use chmod 700 on the private directory")
if stat.S_IMODE(config_path.stat().st_mode) & 0o077:
    raise SystemExit("Use chmod 600 on config.json")
escaped_root = str(root).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
group = grp.getgrgid(account.pw_gid).gr_name
for filename in ("s95h-art-guardian.service", "s95h-art-guardian-alert.service"):
    text = (app / "examples" / filename).read_text()
    text = text.replace("@SERVICE_USER@", name).replace("@SERVICE_GROUP@", group)
    text = text.replace("@INSTALL_ROOT@", escaped_root)
    destination = Path("/etc/systemd/system") / filename
    destination.write_text(text)
    os.chmod(destination, 0o644)
print("Installed controller and failure-notification units")
PY
systemctl daemon-reload
systemctl enable --now --no-block s95h-art-guardian.service
systemctl show s95h-art-guardian.service -p ActiveState -p SubState -p UnitFileState
