#!/usr/bin/env python3

from __future__ import annotations


def build_charging_profile() -> dict:
    return {
        "currents_c": [4.2, 3.0, 2.0, 1.15],
        "switch_soc": [0.30, 0.55, 0.72],
    }


def main() -> None:
    print(build_charging_profile())


if __name__ == "__main__":
    main()
