from __future__ import annotations

from typing import Any

from agents.base import AgentSpec, execute_agent


VIDEO_SPEC = AgentSpec(
    stage="video",
    env_prefix="VIDEO_AGENT",
    default_imports=(
        "video_agent",
        "video_agent.main",
        "agents.video",
        "agents.video_agent_impl",
    ),
    default_functions=("run_video_agent", "run", "main"),
)


def run_video_agent(context: dict[str, Any] | None = None) -> dict[str, Any]:
    return execute_agent(
        VIDEO_SPEC,
        call_args=(context or {},),
        input_payload={
            "context": context or {},
        },
    )
