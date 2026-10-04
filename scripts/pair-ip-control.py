#!/usr/bin/env python3
"""Explicitly pair the tested S95H's IP Control interface; never send power commands."""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from art_guardian.ipcontrol import IPControl
from art_guardian.samsung import Samsung


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--directory", type=Path, default=ROOT / "private")
    args = parser.parse_args()
    try:
        tv = Samsung(args.host, args.directory / "tv-token.json")
        if tv.info()["device"].get("modelName") != "QN65S95HAFXZA":
            raise ValueError("This pairing utility is restricted to the tested S95H model")
        print("Accept the IP Control permission prompt on the TV if it appears.")
        IPControl(args.host, args.directory / "ip-control-token.json").pair()
        print("Paired. The credential was saved in the local private directory.")
    except Exception as error:  # noqa: BLE001 — do not print authenticated URLs or responses
        print(f"Pairing failed ({type(error).__name__}); check permissions and try manually.",
              file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
