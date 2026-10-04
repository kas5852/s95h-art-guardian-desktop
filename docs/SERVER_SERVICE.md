# Timer watcher and overnight schedule

The controller runs on macOS or Linux using `python -m art_guardian.service`.
Linux can also run it as a systemd service. It needs an awake computer on the TV's
local network; the TV continues to display Samsung's own artwork.

## Private configuration

For a service installation, use this layout:

```text
INSTALL_ROOT/
  app/          this repository
  .venv/        Python environment
  config.json   local TV details and notification configuration
  private/      tokens, original timer baseline, controller state, pause file
```

For Linux, prepare the layout as your ordinary account:

```sh
mkdir -p "$HOME/.local/share/s95h-art-guardian"
cd "$HOME/.local/share/s95h-art-guardian"
git clone https://github.com/kas5852/s95h-art-guardian-desktop.git app
python3 -m venv .venv
.venv/bin/python -m pip install ./app
cp app/examples/config.service.json config.json
mkdir -m 700 private
chmod 600 config.json
```

Edit `config.json` locally. Set your TV address, exact `duid` identity from the
device-info endpoint, wake MAC address, time zone, and your own HTTPS ntfy topic
URL. Keep both `schedule_enabled` and `power_mapping_verified` false initially.
If ntfy authentication is required, add `token_file` with the absolute path of a
private file containing that token, and protect it with mode 600. Never put these
values in a public issue or commit.

The same layout works on macOS. Keep the computer awake and run the controller
in the foreground; the systemd installer is Linux-only. A launchd installation is
not supplied in this release.

The saved device identity is deliberately omitted by the shareable `inspect`
report. To obtain it locally without printing it to the terminal, run this from
`INSTALL_ROOT`, replacing the placeholder address:

```sh
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from art_guardian.samsung import Samsung
config = json.loads(Path("config.json").read_text())
device = Samsung(config["tv"]["host"], Path("private/tv-token.json")).info()["device"]
config["tv"]["identity"] = device["duid"]
Path("config.json").write_text(json.dumps(config, indent=2) + "\n")
PY
```

## Pairing and foreground checks

On the TV, enable IP Remote and Power On with Mobile if available. Pair IP
Control explicitly, then accept the TV prompt:

```sh
.venv/bin/python app/scripts/pair-ip-control.py --host YOUR_TV_IP --directory private
```

This saves the credential locally and sends no power commands. A failed or
uncertain pairing is not automatically repeated.

Run the timer watcher with scheduling disabled:

```sh
.venv/bin/python -m art_guardian.service --config config.json
```

It will repair a 240-minute timer while the known TV is awake. Stop it with
Ctrl-C. Before enabling the schedule, supervise separate explicit standby and
wake tests using the IP Control client, confirm the display behavior physically,
and verify a full overnight window. A twenty-minute successful wake test does
not prove a five-hour wake test will succeed.

## Current policy

- Outside 4 AM–9 AM in the configured time zone, read the timer approximately
  once per minute while the TV reports awake. Repair exactly `240` to `off` and
  read it back. Preserve the identity-bound original baseline. Other timer
  values generate an alert and remain unchanged.
- At 4 AM, reserve the nightly action durably and send one explicit IP
  `powerOff` request if needed. A five-minute dispatch window tolerates a small
  delay but prevents late daytime power-off.
- During the quiet window, send no timer reads, repairs, Art commands, or wake
  packets after the initial standby action. Leave mains power connected. The
  controller provides a maintenance opportunity; it does not measure completion.
- At 9 AM, request explicit IP power-on when off or unreachable. Send one
  Wake-on-LAN fallback if needed, verify the TV identity, wait for Art readiness,
  select Art Mode, and repair the timer. Leave existing normal TV viewing alone
  if the TV is already on.
- Reserve power actions before sending. A restart cannot repeat an uncertain
  scheduled action. Failed or interrupted actions generate an alert.

An unreachable TV during an ordinary timer check is recorded without waking it.
Three failed timer checks while awake, identity mismatches, failed scheduled
actions, and controller failures generate ntfy alerts, limited to once an hour
per issue. A complete computer or network outage cannot send its own alert.

The schedule is fixed in the current code. `schedule_enabled` is reread each
minute; other configuration changes require a restart. Enable it only after
physical verification and set `power_mapping_verified` to true as well.

## Linux systemd installation

Install first with scheduling disabled. From `INSTALL_ROOT`, use the ordinary
account that owns the private configuration:

```sh
sudo sh app/scripts/install-server-service.sh "$USER"
systemctl status s95h-art-guardian --no-pager
journalctl -u s95h-art-guardian -n 50 --no-pager
```

The installer substitutes your account, primary group, and installation path
into generic unit templates. It validates private-file ownership and
permissions, starts the timer watcher, and enables it at boot. It does not alter
your schedule flags. Do not install it alongside another copy controlling the
same TV.

To pause TV actions:

```sh
touch private/PAUSE
```

Remove that file to resume. To stop the Linux service:

```sh
sudo systemctl disable --now s95h-art-guardian
```

Stopping the service does not restore the original timer. Use the CLI's
`timer --value restore` command when you explicitly want that restoration.
