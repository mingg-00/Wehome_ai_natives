from __future__ import annotations

from typing import Any

from agents.base import AgentSpec, execute_agent


SNS_SPEC = AgentSpec(
    stage="sns",
    env_prefix="SNS_AGENT",
    default_imports=(
        "sns_upload_agent",
        "sns_upload_agent.main",
        "agents.sns_upload",
        "agents.sns_upload_agent_impl",
    ),
    default_functions=("run_sns_agent", "run", "main"),
)


def run_sns_agent(video_result: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return execute_agent(
        SNS_SPEC,
        call_args=(video_result, context or {}),
        input_payload={
            "video_result": video_result,
            "context": context or {},
        },
    )
