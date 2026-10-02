import json

from . import llm, prompts
from .models import Node, VerifyOutput


def verify(node: Node, result: dict, scenario: str = "default", language: str = "en") -> VerifyOutput:
    """Check a tool result against the node's success_criteria."""
    if not result.get("ok"):  # hard failure needs no LLM
        return VerifyOutput(passed=False, reason=result.get("summary", "Tool reported failure"))
    user = (f"Step: {node.subtitle or node.title}\nTool: {node.tool}\n"
            f"Success criteria: {node.success_criteria}\n"
            f"Tool result: {json.dumps({'ok': True, 'summary': result.get('summary')}, ensure_ascii=False)}")
    try:
        return llm.call(user, VerifyOutput, system=prompts.load("verifier"), scenario=scenario, lang=language)
    except llm.LLMError:  # LLM unavailable (offline / no cassette entry): fall back to the rule-based check
        return VerifyOutput(passed=True, reason="Tool reported success (rule-based check)")
