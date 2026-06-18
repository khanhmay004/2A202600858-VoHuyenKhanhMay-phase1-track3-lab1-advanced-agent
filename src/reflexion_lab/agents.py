from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from .mock_runtime import FAILURE_MODE_BY_QID, actor_answer, evaluator, reflector
from .schemas import AttemptTrace, JudgeResult, QAExample, ReflectionEntry, RunRecord


def classify_failure(judge: JudgeResult, qid: str) -> str:
    """Map a final judge result to a failure_mode label from the schema taxonomy."""
    if judge.score == 1:
        return "none"
    if qid in FAILURE_MODE_BY_QID:  # known modes for the deterministic mock set
        return FAILURE_MODE_BY_QID[qid]
    if judge.missing_evidence:
        return "incomplete_multi_hop"
    if judge.spurious_claims:
        return "entity_drift"
    return "wrong_final_answer"


@dataclass
class BaseAgent:
    agent_type: Literal["react", "reflexion"]
    max_attempts: int = 1

    def run(self, example: QAExample) -> RunRecord:
        reflection_memory: list[str] = []
        reflections: list[ReflectionEntry] = []
        traces: list[AttemptTrace] = []
        final_answer = ""
        final_judge: JudgeResult | None = None

        for attempt_id in range(1, self.max_attempts + 1):
            answer, actor_stats = actor_answer(example, attempt_id, self.agent_type, reflection_memory)
            judge, eval_stats = evaluator(example, answer)
            token_estimate = actor_stats.tokens + eval_stats.tokens
            latency_ms = actor_stats.latency_ms + eval_stats.latency_ms
            final_answer = answer
            final_judge = judge

            reflection: ReflectionEntry | None = None
            # Reflexion: when the answer is wrong and attempts remain, reflect on the
            # failure and feed the lesson back into the actor's memory for next time.
            if self.agent_type == "reflexion" and judge.score != 1 and attempt_id < self.max_attempts:
                ref, ref_stats = reflector(example, attempt_id, judge, answer)
                token_estimate += ref_stats.tokens
                latency_ms += ref_stats.latency_ms
                reflections.append(ref)
                reflection_memory.append(
                    f"Attempt {ref.attempt_id} answered '{answer}', which was wrong. "
                    f"Cause: {ref.failure_reason} Lesson: {ref.lesson} Next: {ref.next_strategy}"
                )
                reflection = ref

            traces.append(AttemptTrace(
                attempt_id=attempt_id, answer=answer, score=judge.score, reason=judge.reason,
                reflection=reflection, token_estimate=token_estimate, latency_ms=latency_ms,
            ))
            if judge.score == 1:
                break

        total_tokens = sum(t.token_estimate for t in traces)
        total_latency = sum(t.latency_ms for t in traces)
        final_score = final_judge.score if final_judge else 0
        failure_mode = classify_failure(final_judge, example.qid) if final_judge else "wrong_final_answer"
        return RunRecord(
            qid=example.qid, question=example.question, gold_answer=example.gold_answer,
            agent_type=self.agent_type, predicted_answer=final_answer, is_correct=bool(final_score),
            attempts=len(traces), token_estimate=total_tokens, latency_ms=total_latency,
            failure_mode=failure_mode, reflections=reflections, traces=traces,
        )


class ReActAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_type="react", max_attempts=1)


class ReflexionAgent(BaseAgent):
    def __init__(self, max_attempts: int = 3) -> None:
        super().__init__(agent_type="reflexion", max_attempts=max_attempts)
