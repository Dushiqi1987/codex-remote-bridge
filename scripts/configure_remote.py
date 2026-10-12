#!/usr/bin/env python3
"""Update only proxy variables in the remote Codex environment file, with backup."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import tempfile

KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy")
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?(" + "|".join(KEYS) + r")\s*=")


def default_env_file():
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / ".env"


def render(old, port):
    kept = [line for line in old.splitlines() if not ASSIGNMENT.match(line)]
    while kept and not kept[-1].strip():
        kept.pop()
    url = f"http://127.0.0.1:{port}"
    values = {key: "localhost,127.0.0.1,::1" if key.lower() == "no_proxy" else url for key in KEYS}
    return "\n".join(kept + ([""] if kept else []) + [f'{key}="{values[key]}"' for key in KEYS]) + "\n"


def configure(path, port, dry_run=False):
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlink; select the real environment file")
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    new = render(old, port)
    if dry_run:
        print(f"Would update {path}: " + ", ".join(KEYS))
        print(f"Proxy: http://127.0.0.1:{port}; other settings preserved (not displayed).")
        return None
    if old == new:
        print(f"Already configured: {path}")
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = path.with_name(path.name + ".backup-" + stamp)
        shutil.copy2(path, backup)
        backup.chmod(0o600)
    fd, name = tempfile.mkstemp(prefix=".proxy-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(new)
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print(f"Configured: {path}")
    print(f"Backup: {backup}" if backup else "New file; no previous file to back up.")
    print("Load/export this environment before starting Codex; writing the file alone is insufficient.")
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=17891)
    parser.add_argument("--env-file", type=Path, default=default_env_file())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    try:
        configure(args.env_file.expanduser(), args.port, args.dry_run)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Configuration failed: {error}\n")


if __name__ == "__main__":
    main()
