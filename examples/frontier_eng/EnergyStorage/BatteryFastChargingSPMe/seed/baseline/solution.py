#!/usr/bin/env python3

from __future__ import annotations


def build_charging_policy() -> dict:
    return {
        "currents_c": [3.4, 2.8, 2.0, 1.2],
        "switch_soc": [0.22, 0.52, 0.78],
    }


def main() -> None:
    print(build_charging_policy())


if __name__ == "__main__":
    main()
