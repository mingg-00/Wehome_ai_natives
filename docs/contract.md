# Integration Contract

## Principle

This repo is an integration shell, not a source bundle.

- Do not copy agent source code into this repository.
- Keep each agent's implementation in its own repository.
- Use this repo to define the command contract and to run those commands.

## Contract

Each agent entry must provide:

- `AGENT_n_CMD`: the command to execute
- `AGENT_n_CWD` optional: the working directory for that command

The orchestrator will:

- run the configured commands in order
- capture stdout and stderr into `output/`
- stop at the first non-zero exit code

## Output contract

- `output/agent-1.log`
- `output/agent-2.log`
- `output/agent-3.log`

Each log contains the exact command output for that agent run.

## Rule for new work

If a new agent is added later:

1. create a new repository for that agent
2. add a new contract entry here
3. add a new external command in `.env`
4. do not bring the source code into this repo

