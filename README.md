# S95H Art Guardian — macOS and Linux

A local Python utility that repairs Samsung S95H artwork-timer resets. An optional
controller runs a 4 AM–9 AM standby window and sends ntfy failure alerts.
Samsung's own Art app displays the artwork; this project supplies no artwork or
Art Store subscription.

**Hardware verification is limited to one US 65-inch S95H
(`QN65S95HAFXZA`, firmware `1235.0`).** That TV accepts the hidden artwork-timer
value `off`, although its advertised options stop at 240 minutes. The setting
has later reverted to 240, so the utility saves the original setting, verifies
changes, and can monitor for resets. It does not guarantee permanent firmware
compatibility, continuous display, or completed OLED maintenance.

## Quick start

Python 3.11+ on macOS or Linux, with the computer and TV on the same local network:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m art_guardian.cli inspect --host YOUR_TV_IP --art
.venv/bin/python -m art_guardian.cli read-timer --host YOUR_TV_IP
```

Replace `YOUR_TV_IP` with the address shown in the TV's Network Status screen.
Inspect the reported model before changing anything. The repair is restricted to
the tested model code.

To explicitly disable the artwork timer:

```sh
.venv/bin/python -m art_guardian.cli timer --host YOUR_TV_IP --value off
```

The command preserves an identity-bound original setting in
`private/timer-baseline.json` and reads back the result. To restore that original:

```sh
.venv/bin/python -m art_guardian.cli timer --host YOUR_TV_IP --value restore
```

To explicitly select Samsung's Art Mode on an awake TV:

```sh
.venv/bin/python -m art_guardian.cli show-art --host YOUR_TV_IP
```

This command does not power on a TV. Standby wake uses a separate, explicitly
paired IP Control client in the optional service.

## Automatic timer repair and overnight schedule

See [controller setup](docs/SERVER_SERVICE.md) for the private configuration,
pairing, foreground execution on either operating system, and Linux systemd
installation. The computer must remain awake and connected for automatic checks
and scheduled actions to run.

The controller checks the timer approximately once per minute outside its quiet
window. It repairs exactly `240` to `off`, alerts on other unexpected values,
and leaves ordinary TV viewing alone when the TV is already in use at the morning
boundary. Scheduled power actions are disabled until separately verified and
explicitly enabled. The current schedule is fixed at 4 AM standby and 9 AM wake,
in the configured time zone.

## Evidence, diagnostics, and privacy

- [Compatibility and observed behavior](docs/COMPATIBILITY.md)
- [Setup and optional diagnostics](docs/SETUP.md)
- [Controller and systemd setup](docs/SERVER_SERVICE.md)
- [Sensitive files and safe sharing](SECURITY.md)
- [Third-party dependencies](THIRD_PARTY.md)

Keep automatic OLED protections enabled. The standby window provides an
opportunity for maintenance; it does not measure its completion. Disable existing
off-to-art wake loops before evaluating this controller. Do not use a smart plug
to cut mains power as a substitute for standby.

## Development

```sh
.venv/bin/python -m pip install '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check art_guardian tests
```

Tests use fabricated device data and reserved example addresses. No real TV,
notification service, or personal configuration is needed.

A [CI template](docs/ci-workflow.example.yml) runs the tests on macOS and Linux
with Python 3.11 and 3.14. Copy it into `.github/workflows/` to enable GitHub
Actions with an account credential permitted to manage workflows.

## Licensing and affiliation

MIT, see [LICENSE](LICENSE). Third-party dependencies keep their own licenses.

This project is independent of Samsung. Samsung, SmartThings, and Art Store are
named only to identify compatibility.
