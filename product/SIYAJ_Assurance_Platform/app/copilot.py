"""Copilot Studio published-agent connector using Microsoft's Direct Line API 3.0.

Only chat-channel user-input tests can be delivered here. Direct Line does not reveal
internal tool attempts or allow arbitrary injection into a bot's RAG tool response.
Those cases must be REVIEW, never guessed PASS. Only use isolated test agents.
"""
from __future__ import annotations
import ipaddress
import os
import socket
import time
from urllib.parse import urlparse

import httpx
from .adapters import AgentObservation
from .cases import AttackCase

DIRECTLINE = "https://directline.botframework.com"


def validate_copilot_token_endpoint(url: str) -> str:
    p = urlparse(url.strip())
    if p.username or p.password or p.fragment or len(url) > 1500 or not p.hostname:
        raise ValueError("Invalid Copilot token endpoint")
    host = p.hostname.lower().rstrip(".")
    if (p.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}
            and os.getenv("ARG_COPILOT_TEST_MODE") == "1"):
        return url
    if p.scheme != "https" or p.port not in (None, 443):
        raise ValueError("Copilot token endpoint must use HTTPS with standard port")
    # Microsoft's copied token URL should be on a Power Platform service endpoint.
    # Other exact corporate-hosted endpoints require explicit allowlisting.
    approved = (host.endswith(".api.powerplatform.com") or
                host.endswith(".environment.api.powerplatform.com"))
    allowed = {x.strip().lower() for x in os.getenv("ARG_COPILOT_TOKEN_HOSTS", "").split(",") if x.strip()}
    if not approved and host not in allowed:
        raise ValueError("Copilot token host not recognized. Copy it from Copilot Studio > Channels > Mobile app; or set ARG_COPILOT_TOKEN_HOSTS")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Copilot token host could not be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise ValueError("Copilot token endpoint resolved to a prohibited network")
    return url


def _directline_base() -> str:
    if os.getenv("ARG_COPILOT_TEST_MODE") == "1":
        value = os.getenv("ARG_DIRECTLINE_TEST_BASE", "")
        p = urlparse(value)
        if p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost"):
            return value.rstrip("/")
    return DIRECTLINE


def invoke_copilot(case: AttackCase, token_endpoint: str) -> AgentObservation:
    """Execute the Copilot Studio published agent via Direct Line chat, not an agent SDK."""
    if case.surface == "tool_response":
        return AgentObservation(
            reply="", notes=["NOT DELIVERED: Direct Line cannot inject an arbitrary RAG/tool response.",
                             "Use a Copilot Studio staging topic/action or a dedicated HTTP instrumentation bridge for RAG injection."],
            attack_delivered=False, tool_trace_available=False,
        )
    endpoint = validate_copilot_token_endpoint(token_endpoint)
    directline = _directline_base()
    # New, synthetic, isolated conversation for every case. No session reuse.
    user_id = "arg_test_user"
    prompt = f"Legitimate request: {case.legitimate_task}\n\nUser message: {case.payload}"
    with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False, trust_env=False) as client:
        token_resp = client.get(endpoint)
        token_resp.raise_for_status()
        access = token_resp.json()
        if not isinstance(access, dict) or not isinstance(access.get("token"), str) or not access["token"]:
            raise ValueError("Copilot token endpoint did not return a Direct Line token")
        headers = {"Authorization": "Bearer " + access["token"], "Content-Type": "application/json"}
        open_resp = client.post(directline + "/v3/directline/conversations", headers=headers, json={})
        open_resp.raise_for_status()
        convo = open_resp.json().get("conversationId", "")
        if not convo or not isinstance(convo, str) or len(convo) > 200:
            raise ValueError("Direct Line conversationId missing or invalid")
        url = directline + "/v3/directline/conversations/" + convo
        # Capture the watermark so we do not mistake a preexisting greeting as the attack response.
        initial = client.get(url + "/activities", headers=headers)
        initial.raise_for_status()
        watermark = initial.json().get("watermark")
        sent = client.post(url + "/activities", headers=headers, json={
            "type": "message", "from": {"id": user_id, "name": "ARG synthetic evaluator"},
            "locale": "en-US", "text": prompt,
        })
        sent.raise_for_status()
        replies: list[str] = []
        deadline = time.monotonic() + 26
        while time.monotonic() < deadline:
            params = {"watermark": watermark} if watermark is not None else None
            seen = client.get(url + "/activities", headers=headers, params=params)
            seen.raise_for_status()
            data = seen.json()
            for activity in data.get("activities", []):
                if (activity.get("type") == "message" and
                        activity.get("from", {}).get("id") != user_id and
                        isinstance(activity.get("text"), str)):
                    replies.append(activity["text"])
            watermark = data.get("watermark", watermark)
            if replies:
                break
            time.sleep(1.1)
        if not replies:
            raise TimeoutError("No agent message received within 26 seconds of Direct Line delivery")
    return AgentObservation(
        reply="\n".join(replies)[:12000], tool_calls=[],
        notes=["Live Copilot Studio published agent, Direct Line 3.0, fresh conversation.",
               "Chat-only observation: internal tools/action attempts are NOT exposed by this connector.",
               "Use an authorized test agent with high-impact actions disabled."],
        attack_delivered=True, tool_trace_available=False,
    )
