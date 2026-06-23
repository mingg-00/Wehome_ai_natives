"""OpenAI 래퍼. 키가 없으면 None을 돌려 호출부가 오프라인 폴백을 쓰게 한다.

위홈 CS 챗봇 app/llm.py 와 동일한 클라이언트 초기화 방식을 따른다.
"""
from __future__ import annotations

import json

from .config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def chat(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str | None:
    """일반 텍스트 응답. 오프라인이면 None."""
    if not settings.llm_enabled:
        return None
    resp = _get_client().chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    if not resp.choices:
        return None
    content = resp.choices[0].message.content
    return content.strip() if content else None


def chat_with_tools(system_prompt: str, user_prompt: str, tools: list,
                    dispatch, max_rounds: int = 4) -> dict | None:
    """도구(함수호출)를 쥐여준 채 답하게 한다. AI가 도구를 부르면 dispatch로 실행.
    반환: {answer, used_tools:[name,...]}. 오프라인이면 None."""
    if not settings.llm_enabled:
        return None
    client = _get_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    used: list[str] = []
    for _ in range(max_rounds):
        resp = client.chat.completions.create(
            model=settings.chat_model, messages=messages, tools=tools, temperature=0.3)
        if not resp.choices:
            return {"answer": "", "used_tools": used}
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return {"answer": msg.content or "", "used_tools": used}
        messages.append({
            "role": "assistant", "content": msg.content,
            "tool_calls": [{"id": tc.id, "type": "function",
                            "function": {"name": tc.function.name,
                                         "arguments": tc.function.arguments}}
                           for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            used.append(tc.function.name)
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(dispatch(tc.function.name, args),
                                                   ensure_ascii=False)})
    resp = client.chat.completions.create(
        model=settings.chat_model, messages=messages, temperature=0.3)
    if not resp.choices:
        return {"answer": "", "used_tools": used}
    return {"answer": resp.choices[0].message.content or "", "used_tools": used}


def chat_json(system_prompt: str, user_prompt: str) -> dict | None:
    """구조화된 JSON 응답을 강제해 받는다. 오프라인이면 None."""
    if not settings.llm_enabled:
        return None
    resp = _get_client().chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    if not resp.choices:
        return None
    content = resp.choices[0].message.content
    if not content:
        return None
    return json.loads(content)
