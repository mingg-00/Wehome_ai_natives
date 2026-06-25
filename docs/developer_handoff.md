# Developer Handoff

## Current state

The repo is now structured for a Discord-driven campaign pipeline.

## What to touch

- `config/settings.py` for environment variables
- `agents/` for import-first or subprocess fallback wiring
- `orchestrator/main.py` for execution flow changes
- `discord_bot/main.py` for slash commands and Discord output
- `docker-compose.yml` and `docker/*.Dockerfile` for deployment wiring

## What not to touch casually

- agent implementation repos
- agent source trees outside this repo
- contract semantics without updating `docs/contract.md`

## Operational notes

- Use `ORCHESTRATOR_MODE=direct` for in-process execution.
- Use `ORCHESTRATOR_MODE=worker` when a separate orchestrator worker should poll `runtime/jobs/`.
- The bot always writes the final summary to `data/summary.json`.

