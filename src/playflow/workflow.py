from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analyzer import Analysis, analyze_project
from .config import load_manifest
from .gradle import build as gradle_build
from .gradle import find_aab
from .models import Manifest
from .policy import unresolved_questions
from .readiness import readiness_report, resolve_track, testing_plan
from .state import StateStore


@dataclass
class Workflow:
    """Shared use cases for the CLI and future agent/API adapters."""

    manifest: Manifest
    project: Path
    state: StateStore

    @classmethod
    def from_file(cls, path: Path) -> Workflow:
        manifest, manifest_path = load_manifest(path)
        project = manifest.resolved_project_dir(manifest_path)
        return cls(
            manifest, project, StateStore(project, manifest.resolved_state_dir(manifest_path))
        )

    def preflight(self) -> dict:
        analysis = analyze_project(self.project, self.manifest.build.module)
        return readiness_report(self.manifest, self.project, analysis)

    def testing_plan(self) -> dict:
        return testing_plan(self.manifest)

    def _approved(self, step: str, commit: bool, approve: Callable[[], bool] | None) -> bool:
        if commit and self.manifest.approvals.require_final_submit_approval:
            if approve is None or not approve():
                self.state.mark(step, "blocked", reason="final_approval_required")
                return False
        return True

    def configure_testers(
        self,
        *,
        commit: bool = False,
        approve: Callable[[], bool] | None = None,
    ) -> dict:
        testing = self.manifest.testing
        if not testing or testing.mode != "closed" or not testing.google_groups:
            raise ValueError(
                "Configure testing.mode: closed and a nonempty testing.google_groups list"
            )
        track = resolve_track(self.manifest)
        package = self.manifest.play.package_name
        if not package:
            analysis = analyze_project(self.project, self.manifest.build.module)
            package = analysis.package_name
        if not package:
            raise ValueError("Set play.package_name before configuring testers")
        if not self._approved("testers", commit, approve):
            return {"status": "blocked", "reason": "final_approval_required"}
        from .play_api import PlayPublisher

        with self.state.stage("testers") as details:
            publisher = PlayPublisher.from_manifest(self.manifest)
            result = publisher.configure_testers(
                package, track, testing.google_groups, commit=commit
            )
            details["result"] = result
        self.state.mark("testers", "done" if commit else "validated", result=result)
        return {
            "status": "configured" if commit else "validated",
            "result": result,
            "country_availability": "requires_console_configuration_and_verification",
        }

    def inspect(self) -> Analysis:
        with self.state.stage("inspect") as details:
            analysis = analyze_project(self.project, self.manifest.build.module)
            details["analysis"] = analysis.to_dict()
        return analysis

    def policy_check(self, analysis: Analysis) -> list[dict[str, str]]:
        questions = [q.__dict__ for q in unresolved_questions(self.manifest, analysis)]
        self.state.mark("policy_gate", "blocked" if questions else "done", questions=questions)
        return questions

    def build(self) -> Path:
        with self.state.stage("build") as details:
            gradle_build(self.project, self.manifest.build.task)
            aab = find_aab(self.project, self.manifest.build.aab_path, self.manifest.build.module)
            details["aab"] = str(aab)
        return aab

    def publish(
        self,
        analysis: Analysis,
        *,
        commit: bool = False,
        track: str | None = None,
        approve: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        # Recheck here so every caller, including the pipeline, uses the same gate.
        if questions := self.policy_check(analysis):
            return {"status": "blocked", "reason": "policy_questions", "questions": questions}
        package = self.manifest.play.package_name or analysis.package_name
        if not package:
            raise ValueError("Package name unknown; set play.package_name for the built variant")
        aab = find_aab(self.project, self.manifest.build.aab_path, self.manifest.build.module)
        selected_track = resolve_track(self.manifest, track)
        if (
            self.manifest.testing
            and self.manifest.testing.mode == "closed"
            and not self.manifest.testing.google_groups
        ):
            raise ValueError("Provide testing.google_groups for this closed-testing workflow")
        if not self._approved("publish", commit, approve):
            return {"status": "blocked", "reason": "final_approval_required"}
        from .play_api import PlayPublisher

        with self.state.stage("publish") as details:
            publisher = PlayPublisher.from_manifest(self.manifest)
            result = publisher.publish_bundle(
                package_name=package,
                aab=aab,
                track=selected_track,
                release_status=self.manifest.play.release_status,
                release_notes=[x.model_dump() for x in self.manifest.release_notes],
                commit=commit,
                user_fraction=self.manifest.play.user_fraction,
                google_groups=self.manifest.testing.google_groups
                if self.manifest.testing
                else None,
            )
            details["result"] = result
        self.state.mark("publish", "done" if commit else "validated", result=result)
        return {"status": "published" if commit else "validated", "result": result}


def run_pipeline(
    manifest_file: Path,
    publish: bool = False,
    commit: bool = False,
    approve: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if commit and not publish:
        raise ValueError("--commit requires --publish")
    workflow = Workflow.from_file(manifest_file)
    analysis = workflow.inspect()
    if questions := workflow.policy_check(analysis):
        return {"status": "blocked", "reason": "policy_questions", "questions": questions}
    aab = workflow.build()
    if not publish:
        return {"status": "ready", "aab": str(aab)}
    return workflow.publish(analysis, commit=commit, approve=approve)
