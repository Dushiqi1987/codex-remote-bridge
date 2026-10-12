#!/usr/bin/env python3
"""Linux launcher: read only proxy keys, then replace this process with Codex."""
import argparse
import os
from pathlib import Path
import re
import shutil
from configure_remote import default_env_file, KEYS


def load_proxy(path):
    values = {}
    pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match or match.group(1) not in KEYS:
            continue
        key, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key.lower() != "no_proxy":
            if not re.fullmatch(r"http://127\.0\.0\.1:([0-9]{1,5})", value):
                raise ValueError(f"{key} must be an HTTP loopback proxy")
            if not 1 <= int(value.rsplit(":", 1)[1]) <= 65535:
                raise ValueError(f"Invalid port in {key}")
        values[key] = value
    for upper in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        value = values.get(upper, values.get(upper.lower()))
        if value is None:
            raise ValueError(f"Missing {upper}; run configure_remote.py first")
        values[upper] = values[upper.lower()] = value
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=default_env_file())
    parser.add_argument("--check", action="store_true", help="Validate config without launching Codex")
    parser.add_argument("codex_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        values = load_proxy(args.env_file.expanduser())
        if args.check:
            print("Proxy config valid; this does not test network connectivity.")
            return
        executable = shutil.which("codex")
        if executable is None:
            raise ValueError("codex is not on PATH; install Codex CLI first")
        forwarded = args.codex_args
        if forwarded[:1] == ["--"]:
            forwarded = forwarded[1:]
        environment = os.environ.copy()
        environment.update(values)
        os.execvpe(executable, [executable] + forwarded, environment)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Cannot launch Codex: {error}\n")


if __name__ == "__main__":
    main()
