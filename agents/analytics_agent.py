from __future__ import annotations

from typing import Any

from agents.base import AgentSpec, execute_agent


ANALYTICS_SPEC = AgentSpec(
    stage="analytics",
    env_prefix="ANALYTICS_AGENT",
    default_imports=(
        "analytics_agent",
        "analytics_agent.main",
        "agents.analytics",
        "agents.analytics_agent_impl",
    ),
    default_functions=("run_analytics_agent", "run", "main"),
)


def run_analytics_agent(sns_result: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return execute_agent(
        ANALYTICS_SPEC,
        call_args=(sns_result, context or {}),
        input_payload={
            "sns_result": sns_result,
            "context": context or {},
        },
    )
