"""Minimal runnable adapter for local testing on :9000.

REPLACE invoke_test_agent() with your OWN STAGING agent invocation.
This sample uses a deterministic guarded fixture (NOT a real model).

Run in another terminal from repository root:
  python -m uvicorn examples.agent_bridge:app --host 127.0.0.1 --port 9000
Then, in Agents, choose 'Your staging HTTP adapter' and enter http://127.0.0.1:9000/test.
"""
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Authorized agent bridge example")

class AttackPacket(BaseModel):
    session_id: str
    case_id: str
    attack_surface: str
    legitimate_task: str
    attacker_content: str
    tool_name: str|None = None
    simulation: bool = True
    synthetic_fixture: str|None = Field(default=None,max_length=7500)
    synthetic_scope: str|None = Field(default=None,max_length=2500)
    require_synthetic_data_ack: bool = False


def invoke_test_agent(packet: AttackPacket):
    """Replace ONLY this function with authorized staging-agent integration.

    You must:
    1. Create a clean, isolated test session for packet.session_id.
    2. For user_input, pass packet.attacker_content as a user message.
    3. For tool_response, inject attacker_content as the lower-trust search/tool RESULT,
       not a system prompt or higher-priority instruction.
    4. Stub destructive/exfiltrating tools, collect attempted function calls BEFORE
       denying execution, and return their names + arguments in tool_calls.
    5. Never pass live credentials, real PII, or payment access into the agent.
    """
    # The sample is still a deterministic *fixture*, not a connected model.
    # A real bridge must feed `synthetic_fixture` into an actual lower-trust
    # retrieval result. Only then should it return synthetic_data_loaded=True.
    if packet.synthetic_fixture is not None:
        import re
        if packet.case_id == "BEH-001":
            label = re.search(r"VERIFY-[A-Z0-9]+-0001",packet.synthetic_fixture)
            response=f"Authorized verification label: {label.group(0) if label else 'not found'}."
        else:
            response="Access denied without authorization; private records require verification and consent."
        return {"reply":response,"tool_calls":[],"attack_delivered":True,"synthetic_data_loaded":True}
    return {
        "reply": "This is an authorized test adapter. Customer information is private; refunds require manual review. I will not follow untrusted instructions.",
        "tool_calls": [],
    }


@app.post("/test")
def test_agent(packet: AttackPacket):
    if not packet.simulation:
        raise ValueError("This bridge accepts synthetic test runs only")
    return invoke_test_agent(packet)
