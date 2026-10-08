"""Run the integrated API with deterministic five-round interview questions for browser QA.

This is a local verification fixture. It does not change the production provider.
"""

from pathlib import Path
import sys

API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.interview_provider import set_interview_provider  # noqa: E402
from app.main import app  # noqa: E402
from app.proof_schemas import InterviewResponsePayload  # noqa: E402


class FiveRoundProvider:
    def ask(self, *, target_job, claim, evidence, skills, turns, answer):
        round_number = len(turns)
        if answer is None or round_number < 5:
            return InterviewResponsePayload.model_validate({
                "question": f"QA 第 {round_number + 1} 题：请说明真实项目中的个人动作、决策依据和结果。",
                "skill_id": "DECISION_MAKING",
                "followup_dimensions": ["决策", "结果"],
                "evaluation": {
                    "strong_points": ["回答已保存"],
                    "weak_points": ["请补充可核验资料"],
                },
            })
        return InterviewResponsePayload.model_validate({
            "question": None,
            "skill_id": None,
            "followup_dimensions": [],
            "evaluation": {
                "strong_points": ["已完成五轮回答"],
                "weak_points": ["请保留项目证据"],
                "gap_type": "EVIDENCE_GAP",
                "why": "需要可核验的项目资料。",
                "evidence_refs": [],
                "recommended_next_action": "整理项目资料并再次练习。",
            },
        })


set_interview_provider(FiveRoundProvider())
