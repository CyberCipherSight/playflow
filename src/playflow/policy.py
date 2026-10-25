from __future__ import annotations

from dataclasses import dataclass

from .analyzer import Analysis
from .models import Manifest


@dataclass
class Question:
    key: str
    prompt: str
    reason: str


def unresolved_questions(manifest: Manifest, analysis: Analysis) -> list[Question]:
    q: list[Question] = []
    facts = manifest.developer_facts
    if facts.contains_ads is None:
        q.append(
            Question(
                "contains_ads",
                "Does this app contain ads?",
                "This cannot be safely inferred from permissions alone.",
            )
        )
    if facts.login_required is None:
        q.append(
            Question(
                "login_required",
                "Does any app functionality require login or credentials?",
                "Play Console app-access answers require developer knowledge.",
            )
        )
    if facts.privacy_policy_url is None and (
        analysis.likely_location_use
        or analysis.likely_camera_use
        or analysis.likely_microphone_use
        or analysis.likely_contacts_use
    ):
        q.append(
            Question(
                "privacy_policy_url",
                "What is the public privacy-policy URL?",
                "Sensitive capabilities are present in the project.",
            )
        )
    if not facts.data_safety_reviewed:
        q.append(
            Question(
                "data_safety_reviewed",
                "Has the Data safety declaration been reviewed by a human?",
                "Data collection/sharing cannot be proven from source scanning alone.",
            )
        )
    return q
