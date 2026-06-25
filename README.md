# wehome-integration

Integration layer for the Wehome agents.

This repository does not contain the source code for the agents themselves.
Keep each agent in its own repository, such as `wehome-analytics-agent`, and use this repo only for:

- contracts
- execution paths
- orchestration and logs

## Rule

- Do not copy the source code of the 3 agents into this repository.
- Keep the source code in each agent's own repository.
- Let this repository call those agents only through approved commands.

## Layout

```text
wehome-integration/
  docs/
  orchestrator/
  scripts/
  output/
  env.example
  README.md
```

## Setup

1. Copy `env.example` to `.env`.
2. Set each `AGENT_n_CMD` to a command that runs the agent from its own repository or workspace.
3. Optionally set `AGENT_n_CWD` when the command must run inside that external repository.

Example:

```powershell
AGENT_1_CMD=python C:\repos\wehome-analytics-agent\main.py
AGENT_1_CWD=C:\repos\wehome-analytics-agent
```

## Run

```powershell
.\scripts\run.ps1
.\scripts\run.ps1 -Execute
```

- Without `-Execute`, the orchestrator runs in dry-run mode.
- With `-Execute`, it runs the configured external commands.

## Outputs

- `output/<agent>.log` for each agent
- dry-run notes when execution is not enabled
- command exit codes in the terminal

