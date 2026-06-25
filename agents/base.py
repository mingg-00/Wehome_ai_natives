from __future__ import annotations

import importlib
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from shared.json_utils import utc_now_iso


@dataclass(frozen=True, slots=True)
class AgentSpec:
    stage: str
    env_prefix: str
    default_imports: tuple[str, ...]
    default_functions: tuple[str, ...]


def _parse_import_path(value: str) -> tuple[str, str] | None:
    value = value.strip()
    if not value:
        return None
    if ":" in value:
        module_name, function_name = value.split(":", 1)
        return module_name.strip(), function_name.strip()
    if "." in value:
        module_name, function_name = value.rsplit(".", 1)
        return module_name.strip(), function_name.strip()
    return value, ""


def _try_import_runner(spec: AgentSpec) -> Callable[..., Any] | None:
    explicit_import = os.getenv(f"{spec.env_prefix}_IMPORT", "").strip()
    explicit_function = os.getenv(f"{spec.env_prefix}_FUNCTION", "").strip()

    import_candidates: list[tuple[str, str]] = []
    parsed = _parse_import_path(explicit_import)
    if parsed:
        import_candidates.append(parsed)

    for module_name in spec.default_imports:
        import_candidates.append((module_name, explicit_function))

    function_candidates = (explicit_function,) if explicit_function else spec.default_functions

    for module_name, function_name in import_candidates:
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001
            continue

        candidate_names = (function_name,) if function_name else function_candidates
        for candidate_name in candidate_names:
            if not candidate_name:
                continue
            runner = getattr(module, candidate_name, None)
            if callable(runner):
                return runner
    return None


def _invoke_runner(runner: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    attempts: list[tuple[tuple[Any, ...], dict[str, Any]]] = [
        (args, kwargs),
        ((args[0],) if args else tuple(), kwargs),
        ((args[0],) if args else tuple(), {}),
        (tuple(), kwargs),
        (tuple(), {}),
    ]
    last_error: TypeError | None = None
    for call_args, call_kwargs in attempts:
        try:
            return runner(*call_args, **call_kwargs)
        except TypeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return runner(*args, **kwargs)


def _try_parse_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def _subprocess_command(spec: AgentSpec) -> str:
    return os.getenv(f"{spec.env_prefix}_CMD", "").strip()


def execute_agent(
    spec: AgentSpec,
    *,
    call_args: tuple[Any, ...],
    call_kwargs: dict[str, Any] | None = None,
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    call_kwargs = call_kwargs or {}
    started_at = utc_now_iso()
    runner = _try_import_runner(spec)

    if runner is not None:
        output = _invoke_runner(runner, *call_args, **call_kwargs)
        if output is None:
            output = {}
        if not isinstance(output, dict):
            output = {"result": output}
        output.setdefault("agent", spec.stage)
        output.setdefault("runner", "import")
        output.setdefault("ok", True)
        output.setdefault("started_at", started_at)
        output.setdefault("completed_at", utc_now_iso())
        output.setdefault("input", input_payload)
        return output

    command = _subprocess_command(spec)
    if not command:
        raise RuntimeError(
            f"No importable runner or subprocess command found for {spec.stage}. "
            f"Set {spec.env_prefix}_IMPORT or {spec.env_prefix}_CMD."
        )

    env = os.environ.copy()
    env[f"WEHOME_{spec.env_prefix}_INPUT_JSON"] = json.dumps(input_payload, ensure_ascii=False)
    env[f"WEHOME_{spec.env_prefix}_STAGE"] = spec.stage

    process = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    completed_at = utc_now_iso()
    stdout = process.stdout or ""
    stderr = process.stderr or ""

    return {
        "agent": spec.stage,
        "runner": "subprocess",
        "ok": process.returncode == 0,
        "returncode": process.returncode,
        "started_at": started_at,
        "completed_at": completed_at,
        "input": input_payload,
        "command": command,
        "stdout": _try_parse_json(stdout),
        "stderr": stderr.strip(),
    }
