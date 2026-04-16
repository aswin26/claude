"""
Multi-Agent Orchestrator

Drives the 4-stage Appian development workflow:
  1. Designer Agent  — design the solution
  2. Developer Agent — analyse existing objects + implement
  3. Designer Agent  — verify implementation
  4. Tester Agent    — unit tests + deployment readiness

Only new / modified objects are surfaced in the final result.
"""
import json
from typing import Callable, Optional
import anthropic

from .designer import DesignerAgent
from .developer import DeveloperAgent
from .tester import TesterAgent


class MultiAgentOrchestrator:
    """Coordinates the Designer → Developer → Verify → Test workflow."""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.designer = DesignerAgent(self.client)
        self.developer = DeveloperAgent(self.client)
        self.tester = TesterAgent(self.client)

    # ── public API ────────────────────────────────────────────────────────────

    def run_workflow(
        self,
        requirement: str,
        existing_objects: dict,
        existing_objects_content: dict,
        on_event: Optional[Callable[[dict], None]] = None,
    ) -> dict:
        """
        Execute the full multi-agent workflow.

        Args:
            requirement: Plain-English requirement text from the user.
            existing_objects: Dict of {object_type: [object_names]} from the export.
            existing_objects_content: Dict of {relative_path: file_content}.
            on_event: Optional callback that receives structured progress events.

        Returns:
            {
              "new_objects": [...],
              "modified_objects": [...],
              "test_summary": {...},
              "ready_for_deployment": bool,
              "stages": {design, implementation, verification, testing}
            }
        """

        def emit(stage: str, status: str, message: str, data: dict = None):
            if on_event:
                on_event({
                    "stage": stage,
                    "status": status,   # start | running | done | error
                    "message": message,
                    "data": data or {},
                })

        results: dict = {
            "stages": {},
            "new_objects": [],
            "modified_objects": [],
            "test_summary": {},
            "ready_for_deployment": False,
        }

        # ── Stage 1: Design ──────────────────────────────────────────────────
        emit("designer", "start", "Designer Agent (Appian Architect) is analysing the requirement…")
        try:
            design_spec = self.designer.design_requirements(requirement, existing_objects)
            results["stages"]["design"] = design_spec
            emit("designer", "done",
                 f"Design complete — {len(design_spec.get('new_objects', []))} new object(s), "
                 f"{len(design_spec.get('modified_objects', []))} modification(s).",
                 design_spec)
        except Exception as exc:
            emit("designer", "error", f"Designer agent error: {exc}")
            results["error"] = str(exc)
            return results

        # ── Stage 2: Implement ───────────────────────────────────────────────
        emit("developer", "start",
             "Developer Agent (Senior Appian Dev) is analysing existing objects and implementing…")
        try:
            implementation = self.developer.analyze_and_implement(
                design_spec, existing_objects_content
            )
            results["stages"]["implementation"] = implementation
            emit("developer", "done",
                 f"Implementation complete — "
                 f"{len(implementation.get('new_objects', []))} new, "
                 f"{len(implementation.get('modified_objects', []))} modified. "
                 f"Reused: {', '.join(implementation.get('reused_components', [])) or 'none'}.",
                 implementation)
        except Exception as exc:
            emit("developer", "error", f"Developer agent error: {exc}")
            results["error"] = str(exc)
            return results

        # ── Stage 3: Verify ──────────────────────────────────────────────────
        emit("designer_verify", "start",
             "Designer Agent is verifying the implementation against the design spec…")
        try:
            verification = self.designer.verify_implementation(
                requirement, design_spec, implementation
            )
            results["stages"]["verification"] = verification
            score = verification.get("completeness_score", 0)
            approved = verification.get("approved", False)
            emit("designer_verify", "done",
                 f"Verification complete — score {score}/100, "
                 f"{'approved ✓' if approved else 'needs revision ✗'}.",
                 verification)

            # If critical issues found, ask developer to fix them
            critical = [i for i in verification.get("issues", [])
                        if i.get("severity") == "critical"]
            if critical and not approved:
                emit("developer", "start",
                     f"Developer Agent is fixing {len(critical)} critical issue(s)…")
                fix_spec = {**design_spec, "critical_fixes": critical}
                implementation = self.developer.analyze_and_implement(
                    fix_spec, existing_objects_content
                )
                results["stages"]["implementation"] = implementation
                emit("developer", "done",
                     "Revised implementation ready after fixing critical issues.",
                     implementation)

        except Exception as exc:
            emit("designer_verify", "error", f"Verification error: {exc}")
            # Non-fatal — continue to testing

        # ── Stage 4: Unit Testing ────────────────────────────────────────────
        emit("tester", "start", "Tester Agent is generating and evaluating unit tests…")
        try:
            test_results = self.tester.run_tests(implementation, design_spec)
            results["stages"]["testing"] = test_results
            summary = test_results.get("summary", {})
            emit("tester", "done",
                 f"Testing complete — {summary.get('passed', 0)}/{summary.get('total_tests', 0)} "
                 f"tests passed. "
                 f"{'Ready for deployment ✓' if summary.get('ready_for_deployment') else 'Not ready ✗'}.",
                 test_results)
        except Exception as exc:
            emit("tester", "error", f"Tester agent error: {exc}")
            test_results = {}

        # ── Compile final output (only new / modified objects) ───────────────
        results["new_objects"] = implementation.get("new_objects", [])
        results["modified_objects"] = implementation.get("modified_objects", [])
        results["test_summary"] = test_results.get("summary", {})
        results["ready_for_deployment"] = (
            test_results.get("summary", {}).get("ready_for_deployment", False)
        )
        results["deployment_recommendation"] = test_results.get(
            "deployment_recommendation", ""
        )

        return results
