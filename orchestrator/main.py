from __future__ import annotations

import argparse
import os
import shlex
import subprocess
from pathlib import Path


def load_agent_commands() -> list[tuple[str, str]]:
    commands: list[tuple[str, str]] = []
    for index in range(1, 4):
        key = f"AGENT_{index}_CMD"
        value = os.environ.get(key, "").strip()
        if value:
            commands.append((key, value))
    return commands


def run_command(name: str, command: str, output_dir: Path, dry_run: bool) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"{name.lower()}.log"

    if dry_run:
        print(f"[dry-run] {name}: {command}")
        log_path.write_text(f"[dry-run] {command}\n", encoding="utf-8")
        return 0

    print(f"[run] {name}: {command}")
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.run(
            command,
            shell=True,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return process.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Integration orchestrator")
    parser.add_argument("--output-dir", default=os.environ.get("OUTPUT_DIR", "output"))
    parser.add_argument("--execute", action="store_true", help="run commands instead of dry-run")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    commands = load_agent_commands()

    if not commands:
        print("No agent commands configured. Set AGENT_1_CMD, AGENT_2_CMD, or AGENT_3_CMD.")
        return 1

    exit_code = 0
    for name, command in commands:
        code = run_command(name, command, output_dir, dry_run=not args.execute)
        if code != 0:
            exit_code = code
            print(f"{name} failed with exit code {code}")
            break

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

