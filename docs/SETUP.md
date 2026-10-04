# Setup and optional diagnostics

Use the TV's Network Status screen or your router's client list to find the TV's
address. On macOS, AirPlay discovery can also help:

```sh
dns-sd -B _airplay._tcp local.
dns-sd -L 'YOUR_TV_SERVICE_NAME' _airplay._tcp local.
dns-sd -G v4 YOUR_TV_HOSTNAME
```

Stop each discovery command with Ctrl-C when finished. Do not copy another
owner's network address or assume that a discovery hostname is the right target.
Inspect the TV model using the CLI before making a change.

The TV may present a permission prompt when an Art connection is opened. Keep
all saved tokens in `private/`. IP Control pairing is a separate operation; see
[controller setup](SERVER_SERVICE.md).

## Validate the timer repair

1. Disable any existing off-to-art wake loop.
2. Inspect metadata and read the timer.
3. Apply `timer --value off`, then independently use `read-timer` to verify it.
4. Leave artwork displayed for over four hours without other inputs, then check
   the display and timer.
5. Separately test the owner's usual standby and restart methods. Read the timer
   before reapplying anything so a reset is not hidden.
6. Verify standby and maintenance behavior before enabling automatic power
   actions. A successful network response alone is insufficient.

## Read-only observation

The overnight observer checks after four hours ten minutes and eight hours twenty
minutes. It sends no power or setting commands:

```sh
.venv/bin/python -m art_guardian.overnight --host YOUR_TV_IP
```

Keep the computer awake. Observation records remain in `private/`. Sampled reads
cannot exclude an interruption between checkpoints, and reads themselves might
affect undocumented inactivity behavior.

## Earlier guarded recovery prototype

The `run` subcommand is an earlier experimental controller, separate from the
timer-repair service. It observes by default. Its live recovery transitions have
not been validated, and it is not needed for the timer repair:

```sh
cp examples/config.local.json config.json
# Edit the local configuration before running.
.venv/bin/python -m art_guardian.cli run --config config.json
```

`--live` requires a physically verified state mapping. The default policy waits
for thirty minutes of observed active mode followed by twenty minutes of observed
standby before considering one recovery. Those intervals do not establish that
maintenance completed. Unknown state, gaps, manual pause, or normal TV viewing
cancel a candidate. Ambiguous sends latch the controller off.

The Home Assistant adapter is optional. It requires a fresh, genuinely observed
mode source or an explicitly configured scene. Cached state or a fabricated
observation timestamp does not prove TV health. Credentials stay in local files.

To pause either controller, create `private/PAUSE`. Stop the earlier recovery
controller before inspecting and resetting its latch. No controller or startup
service is installed automatically by `pip install`.
