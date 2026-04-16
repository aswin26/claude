"""
Designer Agent — Appian Solution Architect

Responsible for:
 1. Translating business requirements into Appian technical design specs
 2. Verifying that developer implementations match the design
"""
import json
import re
import anthropic


SYSTEM_PROMPT = """You are a Senior Appian Solution Architect with 12+ years of experience designing \
enterprise-grade Appian applications across banking, insurance, and healthcare domains.

Your responsibilities:
- Translate business requirements into precise Appian technical design specifications
- Identify which Appian object types are needed (Expression Rules, Constants, Interfaces, \
Process Models, Web APIs, Record Types, Sites)
- Design solutions that follow Appian best practices: reusability, modularity, performance
- Enforce naming conventions from the project config

Naming conventions you follow:
  Expression Rules : rule!APP_<RuleName>
  Constants        : cons!APP_<ConstantName>
  Interfaces       : rule!APP_<InterfaceName>
  Web APIs         : /api/APP/<endpointName>
  Process Models   : APP - <Process Name>

When producing a design specification always output **valid JSON only** — no markdown fences, \
no prose before or after the JSON object. Every design spec must contain these keys:
  summary, new_objects, modified_objects, dependencies, implementation_notes, test_scenarios
"""


def _extract_json(text: str) -> dict:
    """Parse JSON from model output; fall back to a raw-text envelope."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return {"summary": text, "new_objects": [], "modified_objects": [],
            "dependencies": [], "implementation_notes": text, "test_scenarios": [],
            "raw_design": text}


def _fmt_existing(existing: dict) -> str:
    if not existing:
        return "No existing objects (new application or export unavailable)."
    parts = []
    for obj_type, names in existing.items():
        parts.append(f"\n{obj_type} ({len(names)}):")
        for n in names[:25]:
            parts.append(f"  - {n}")
        if len(names) > 25:
            parts.append(f"  ... and {len(names) - 25} more")
    return "\n".join(parts)


class DesignerAgent:
    """Appian Solution Architect — designs solutions and verifies implementations."""

    def __init__(self, client: anthropic.Anthropic):
        self.client = client
        self.model = "claude-opus-4-6"

    # ── Stage 1: design ──────────────────────────────────────────────────────

    def design_requirements(self, requirement: str, existing_objects: dict) -> dict:
        """Produce a full design specification for the given requirement."""
        prompt = f"""Analyze this Appian requirement and produce a complete design specification.

REQUIREMENT:
{requirement}

EXISTING APPLICATION OBJECTS:
{_fmt_existing(existing_objects)}

Output a single JSON object with this exact schema (no extra keys, no markdown):
{{
  "summary": "<one-paragraph description of the overall design>",
  "new_objects": [
    {{
      "type": "Expression Rule|Interface|Process Model|Constant|Web API|Record Type",
      "name": "APP_<ObjectName>",
      "purpose": "<what this object does>",
      "inputs": [{{"name": "...", "type": "Text|Number|Boolean|List|CDT|Any", "description": "..."}}],
      "output": {{"type": "...", "description": "..."}},
      "logic": "<high-level logic the developer must implement>"
    }}
  ],
  "modified_objects": [
    {{
      "name": "<existing object name>",
      "type": "<object type>",
      "changes": "<exactly what must change>",
      "reason": "<why this change is required>"
    }}
  ],
  "dependencies": ["<dependency description>"],
  "implementation_notes": "<key instructions for the developer>",
  "test_scenarios": [
    {{
      "scenario": "<description>",
      "input": "<sample input>",
      "expected": "<expected output or behaviour>"
    }}
  ]
}}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_json(response.content[0].text)

    # ── Stage 3: verification ────────────────────────────────────────────────

    def verify_implementation(
        self, requirement: str, design_spec: dict, implementation: dict
    ) -> dict:
        """Verify the developer's implementation against the design spec."""
        prompt = f"""Review the developer's implementation against the requirement and design.

ORIGINAL REQUIREMENT:
{requirement}

DESIGN SPECIFICATION:
{json.dumps(design_spec, indent=2)}

DEVELOPER IMPLEMENTATION:
{json.dumps(implementation, indent=2)}

Check:
1. Every designed object is implemented
2. Naming conventions are respected
3. Logic matches what was designed
4. Inputs / outputs are correct
5. No missing dependencies

Output a single JSON object (no markdown):
{{
  "approved": true|false,
  "completeness_score": <0-100>,
  "issues": [
    {{
      "severity": "critical|major|minor",
      "object": "<object name>",
      "issue": "<description>",
      "suggestion": "<how to fix>"
    }}
  ],
  "approved_objects": ["<name of each correctly implemented object>"],
  "feedback": "<overall feedback for the developer>",
  "ready_for_testing": true|false
}}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_json(response.content[0].text)
