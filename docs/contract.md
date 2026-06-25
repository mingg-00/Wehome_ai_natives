# Integration Contract

## Purpose

This repository is the orchestration layer for the campaign pipeline.

It owns:

- Discord command entrypoints
- orchestration order
- result persistence
- deployment wiring

It does not own:

- the 3 agent codebases
- agent prompt logic
- agent business logic

## Pipeline

The execution order is fixed:

1. `video-agent`
2. `sns-upload-agent`
3. `analytics-agent`

The orchestrator must pass the previous stage result into the next stage.

## Agent contract

Each stage can be wired in one of two ways:

1. Python import
2. subprocess

Preferred import variables:

- `VIDEO_AGENT_IMPORT`
- `SNS_AGENT_IMPORT`
- `ANALYTICS_AGENT_IMPORT`

Fallback command variables:

- `VIDEO_AGENT_CMD`
- `SNS_AGENT_CMD`
- `ANALYTICS_AGENT_CMD`

## Input payload

Each agent receives a structured payload that includes:

- `campaign_id`
- `notes`
- `contract_version`
- the previous stage result where applicable

## Output payload

Each agent should return a JSON-compatible dictionary.

The orchestrator normalizes and stores:

- `data/video_result.json`
- `data/sns_result.json`
- `data/analytics_result.json`
- `data/summary.json`

## Failure rule

If an agent returns `ok=false` or exits non-zero, the orchestrator keeps the result payload and marks the summary as `partial_failure`.

