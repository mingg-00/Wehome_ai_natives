# Developer Handoff

## Current state

This repository should stay as a thin integration layer.

## Non-negotiable rule

- Do not copy the 3 agent codebases into this repo.
- Keep source in the agent repos.
- Only maintain the contract and the execution path here.

## What to update here

- `env.example` for external command settings
- `docs/contract.md` when the command contract changes
- `orchestrator/main.py` when the execution flow changes
- `scripts/run.ps1` and `scripts/deploy.ps1` when the runner or package layout changes

## What not to update here

- agent business logic
- agent prompts
- agent source trees

## Checklist

- [ ] Each agent is still owned by its own repository
- [ ] The orchestrator only calls external commands
- [ ] No agent source code was copied into this repo
- [ ] Logs still go to `output/`

