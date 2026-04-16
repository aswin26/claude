"""
Developer Agent — Senior Appian Developer

Responsible for:
 - Analysing existing objects to identify reusable components
 - Implementing new/modified Appian objects based on the design spec
 - Producing deployable Appian code (AEL, SAIL, XML stubs)
"""
import json
import re
import anthropic


SYSTEM_PROMPT = """You are a Senior Appian Developer with 9+ years of hands-on experience \
building complex Appian applications. You specialise in:

  Expression Rules (AEL)  — conditional logic, data transforms, validation helpers
  SAIL Interfaces          — forms, grids, cards, record views, navigation
  Process Models           — automated workflows, smart services, integration calls
  Web APIs                 — REST endpoints, request/response mapping
  Record Types             — data model, relationships, record actions

Appian Expression Language (AEL) you write every day:
  if(), choose(), match()               — conditionals
  a!forEach(), filter(), reduce()       — collection operations
  a!localVariables(local!x: …, …)      — local variable scoping
  rule!APP_RuleName(param: value)       — calling other rules
  cons!APP_ConstantName                 — reading constants
  a!save(target: …, value: …)          — saving values in interfaces

SAIL patterns you use:
  a!formLayout / a!sectionLayout        — page structure
  a!gridLayout / a!cardLayout           — data display
  a!textField / a!dropdownField         — input components
  a!buttonArrayLayout / a!buttonWidget  — action buttons
  a!richTextDisplayField                — formatted output

Before implementing, you always:
1. Scan existing objects for reusable rules, constants, or UI fragments
2. Follow the naming convention (APP_ prefix)
3. Add inline comments to explain non-obvious logic
4. Use local variables for expressions longer than 3 lines

Output **valid JSON only** — no markdown fences, no prose.
"""


def _extract_json(text: str) -> dict:
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
    return {
        "new_objects": [],
        "modified_objects": [],
        "implementation_summary": text,
        "reused_components": [],
        "raw_implementation": text,
    }


def _fmt_existing_content(content: dict) -> str:
    if not content:
        return "No existing object content available."
    parts = []
    for path, body in list(content.items())[:15]:
        snippet = str(body)[:600] + " …[truncated]" if len(str(body)) > 600 else str(body)
        parts.append(f"\n--- {path} ---\n{snippet}")
    return "\n".join(parts)


class DeveloperAgent:
    """Senior Appian Developer — implements objects from design specs."""

    def __init__(self, client: anthropic.Anthropic):
        self.client = client
        self.model = "claude-sonnet-4-6"

    def analyze_and_implement(
        self, design_spec: dict, existing_objects_content: dict
    ) -> dict:
        """
        Analyse existing objects and implement every object in the design spec.

        Returns a dict with new_objects, modified_objects, implementation_summary,
        reused_components.
        """
        existing_summary = _fmt_existing_content(existing_objects_content)

        prompt = f"""Implement every Appian object listed in the design specification below.

DESIGN SPECIFICATION:
{json.dumps(design_spec, indent=2)}

EXISTING OBJECTS (inspect for reuse before building anything new):
{existing_summary}

Implementation rules:
- Reuse existing rules / constants wherever possible — don't rebuild what already exists
- Write real Appian AEL / SAIL code in the "content" field — no pseudocode
- Add /* comment */ annotations where logic is non-trivial
- Follow APP_ naming convention exactly

Return a single JSON object (no markdown):
{{
  "new_objects": [
    {{
      "type": "Expression Rule|Interface|Process Model|Constant|Web API",
      "name": "APP_<ObjectName>",
      "filename": "<relative path e.g. Expression Rules/APP_MyRule.rule>",
      "description": "<one-line description>",
      "content": "<full Appian AEL / SAIL / XML code>",
      "reuses": ["<existing object names reused>"],
      "dependencies": ["<other new object names this depends on>"]
    }}
  ],
  "modified_objects": [
    {{
      "name": "<ExistingObjectName>",
      "type": "<object type>",
      "filename": "<relative path in the export>",
      "changes_made": "<description of changes>",
      "modified_content": "<full updated Appian code>"
    }}
  ],
  "implementation_summary": "<paragraph summarising what was built and what was reused>",
  "reused_components": ["<names of existing objects that were reused>"]
}}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_json(response.content[0].text)
