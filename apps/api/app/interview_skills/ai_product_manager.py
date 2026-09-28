from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class InterviewSkill:
    id: str
    name: str
    interviewer_intent: str
    trigger_claims: tuple[str, ...]
    opening_question_patterns: tuple[str, ...]
    followup_dimensions: tuple[str, ...]
    strong_evidence: tuple[str, ...]
    weak_answer_patterns: tuple[str, ...]
    red_flags: tuple[str, ...]
    source_metadata: dict[str, str] | None = None


INTERVIEW_SKILLS: tuple[InterviewSkill, ...] = (
    InterviewSkill("PRODUCT_SENSE", "Product sense", "Test problem framing and user value.", ("product", "discovery"), ("Who is the user and what problem did you choose?",), ("user", "tradeoffs", "outcome"), ("user research", "prioritization decision"), ("feature list without a user problem",), ("no user or decision"),),
    InterviewSkill("PRODUCT_METRICS", "Product metrics", "Test metric choice and interpretation.", ("metric", "analytics"), ("Which metric would tell you this worked?",), ("north_star", "guardrail", "instrumentation"), ("metric definition", "baseline and target"), ("vanity metric only",), ("invented results"),),
    InterviewSkill("AI_PRODUCT_FUNDAMENTALS", "AI product fundamentals", "Test model capability and product boundary understanding.", ("ai", "llm"), ("What does the model do and what remains product logic?",), ("model_limit", "fallback", "user_control"), ("explicit model boundary",), ("model magic claims",), ("guaranteed output claims"),),
    InterviewSkill("LLM_EVALUATION", "LLM evaluation", "Test whether evaluation is concrete and reproducible.", ("evaluation", "quality"), ("How did you know the LLM behavior was good enough?",), ("dataset", "rubric", "error_analysis", "regression"), ("cases", "labels", "review process"), ("accuracy claim without a set",), ("unverifiable percentage"),),
    InterviewSkill("AGENT_WORKFLOW", "Agent workflow", "Test workflow decomposition, tools, and safeguards.", ("agent", "workflow"), ("Walk me through the agent loop and its stop conditions.",), ("planning", "tools", "guardrails", "failure"), ("traceable steps", "fallback path"), ("autonomous everything",), ("no stop condition"),),
    InterviewSkill("PROJECT_DEEP_DIVE", "Project deep dive", "Test ownership and causal contribution.", ("project", "experience"), ("What did you personally decide and ship?",), ("scope", "decision", "constraint", "result"), ("artifact", "decision log", "demo"), ("team work described as personal",), ("cannot name contribution"),),
    InterviewSkill("TECHNICAL_FLUENCY", "Technical fluency", "Test engineering tradeoffs at the role boundary.", ("api", "engineering"), ("What was the key technical tradeoff?",), ("architecture", "latency", "reliability", "security"), ("constraint-aware design",), ("buzzwords without mechanism",), ("unsafe handling of data"),),
    InterviewSkill("BEHAVIORAL", "Behavioral", "Test reflection and collaboration.", ("collaboration", "behavioral"), ("Tell me about a disagreement and what changed.",), ("context", "action", "reflection"), ("specific decision", "lesson"), ("blame-only story",), ("no reflection"),),
    InterviewSkill("EXPERIMENTATION", "Experimentation", "Test hypothesis, design, and learning.", ("experiment", "a/b"), ("What would you test first and why?",), ("hypothesis", "sample", "confounder", "decision"), ("predefined success rule",), ("post-hoc story",), ("causal overclaim"),),
    InterviewSkill("COMPETITIVE_REASONING", "Competitive reasoning", "Test differentiated judgment and alternatives.", ("competition", "strategy"), ("Why this approach over the obvious alternative?",), ("alternative", "differentiation", "risk"), ("explicit comparison",), ("competitor name dropping",), ("unsupported market facts"),),
)


def skill_records() -> list[dict[str, object]]:
    return [
        {
            **asdict(skill),
            "trigger_claims": list(skill.trigger_claims),
            "opening_question_patterns": list(skill.opening_question_patterns),
            "followup_dimensions": list(skill.followup_dimensions),
            "strong_evidence": list(skill.strong_evidence),
            "weak_answer_patterns": list(skill.weak_answer_patterns),
            "red_flags": list(skill.red_flags),
        }
        for skill in INTERVIEW_SKILLS
    ]
