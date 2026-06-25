from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def load_agent_commands() -> list[dict[str, str]]:
    agents: list[dict[str, str]] = []
    for index in range(1, 4):
        command = os.environ.get(f"AGENT_{index}_CMD", "").strip()
        if not command:
            continue

        agent: dict[str, str] = {
            "name": f"agent-{index}",
            "command": command,
        }

        cwd = os.environ.get(f"AGENT_{index}_CWD", "").strip()
        if cwd:
            agent["cwd"] = cwd

        label = os.environ.get(f"AGENT_{index}_LABEL", "").strip()
        if label:
            agent["label"] = label

        agents.append(agent)
    return agents


def run_command(agent: dict[str, str], output_dir: Path, dry_run: bool) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"{agent['name']}.log"
    label = agent.get("label", agent["name"])
    cwd = agent.get("cwd")
    command = agent["command"]

    if dry_run:
        message = f"[dry-run] {label}: {command}"
        if cwd:
            message += f" (cwd={cwd})"
        print(message)
        log_path.write_text(message + "\n", encoding="utf-8")
        return 0

    message = f"[run] {label}: {command}"
    if cwd:
        message += f" (cwd={cwd})"
    print(message)

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.run(
            command,
            shell=True,
            cwd=cwd or None,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return process.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Wehome integration orchestrator")
    parser.add_argument("--output-dir", default=os.environ.get("OUTPUT_DIR", "output"))
    parser.add_argument("--execute", action="store_true", help="run commands instead of dry-run")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    agents = load_agent_commands()

    if not agents:
        print("No external agent commands configured. Set AGENT_1_CMD, AGENT_2_CMD, or AGENT_3_CMD.")
        return 1

    exit_code = 0
    for agent in agents:
        code = run_command(agent, output_dir, dry_run=not args.execute)
        if code != 0:
            exit_code = code
            print(f"{agent['name']} failed with exit code {code}")
            break

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
