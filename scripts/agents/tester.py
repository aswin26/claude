"""
Tester Agent — Appian QA / Unit Testing

Responsible for:
 - Generating unit test cases for every new / modified object
 - Evaluating whether each test would pass given the implementation
 - Producing a deployment-readiness verdict
"""
import json
import re
import anthropic


SYSTEM_PROMPT = """You are a Senior Appian QA Engineer specialising in automated and unit \
testing of Appian applications.

For Expression Rules you write test rules following the pattern:
  rule!APP_RuleTest_<RuleName>  — returns a list of test result CDTs

Each test rule calls the target rule with specific inputs and uses:
  a!assertEqual(expected: …, actual: rule!APP_TargetRule(…))

For Interfaces you write scenario descriptions covering:
  - Happy-path user interaction
  - Validation error conditions
  - Edge cases (empty inputs, max-length, special characters)

For Process Models you describe:
  - Start node inputs and expected outcomes
  - Gateway decision branches
  - Exception / timeout paths

Your test philosophy: every object needs at minimum one happy-path test, \
one boundary/edge test, and one error-condition test.

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
        "test_results": [],
        "summary": {"total_tests": 0, "passed": 0, "failed": 0,
                    "warnings": 0, "ready_for_deployment": False},
        "deployment_recommendation": text,
        "raw_results": text,
    }


class TesterAgent:
    """Appian QA Engineer — generates and evaluates unit tests."""

    def __init__(self, client: anthropic.Anthropic):
        self.client = client
        self.model = "claude-sonnet-4-6"

    def run_tests(self, implementation: dict, design_spec: dict) -> dict:
        """
        Generate test cases for all implemented objects and evaluate pass/fail.

        Returns a dict with test_results, summary, deployment_recommendation.
        """
        test_scenarios = design_spec.get("test_scenarios", [])

        prompt = f"""Generate and evaluate unit tests for every Appian object in the implementation.

IMPLEMENTED OBJECTS:
{json.dumps(implementation, indent=2)}

DESIGN TEST SCENARIOS:
{json.dumps(test_scenarios, indent=2)}

For each object produce at least:
  - 1 happy-path test
  - 1 edge / boundary test
  - 1 error-condition test

Evaluate each test against the implementation and determine PASS / FAIL / WARN.

Return a single JSON object (no markdown):
{{
  "test_results": [
    {{
      "object_name": "APP_RuleName",
      "object_type": "Expression Rule|Interface|Process Model|Constant|Web API",
      "tests": [
        {{
          "test_name": "<short description>",
          "category": "happy-path|edge|error",
          "test_expression": "rule!APP_RuleName(param: \"value\") = \"expectedResult\"",
          "expected": "<expected output>",
          "actual_assessment": "<what the implementation would return>",
          "status": "PASS|FAIL|WARN",
          "notes": "<explanation if FAIL or WARN>"
        }}
      ],
      "overall_status": "PASS|FAIL",
      "coverage": "High|Medium|Low"
    }}
  ],
  "summary": {{
    "total_tests": <int>,
    "passed": <int>,
    "failed": <int>,
    "warnings": <int>,
    "ready_for_deployment": <true|false>
  }},
  "deployment_recommendation": "<one-paragraph recommendation>"
}}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_json(response.content[0].text)
