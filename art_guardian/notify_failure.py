"""Independent systemd failure alert, including failures before controller startup."""

import argparse
import json
import os
from pathlib import Path

from .notifications import Notifications


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    directory = args.config.resolve().parent / "private"
    path = directory / "failure-notifications.json"
    try:
        state = json.loads(path.read_text())
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    alerts = Notifications(config["ntfy"], directory, state, state_file=path.name)
    alerts.send(
        "systemd-failure", "S95H: controller service failed",
        "The TV controller failed to start or stopped unexpectedly. "
        "Please check systemctl status s95h-art-guardian on the server.",
    )


if __name__ == "__main__":
    main()
