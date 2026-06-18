from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv

from .prompts import ACTOR_SYSTEM, EVALUATOR_SYSTEM, REFLECTOR_SYSTEM
from .schemas import JudgeResult, QAExample, ReflectionEntry
from .utils import normalize_answer

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini-2024-07-18")

# Deterministic fixtures used by the offline mock runtime (the hotpot_mini set).
FIRST_ATTEMPT_WRONG = {"hp2": "London", "hp4": "Atlantic Ocean", "hp6": "Red Sea", "hp8": "Andes"}
FAILURE_MODE_BY_QID = {"hp2": "incomplete_multi_hop", "hp4": "wrong_final_answer", "hp6": "entity_drift", "hp8": "entity_drift"}


@dataclass
class CallStats:
    """Token usage and wall-clock latency for a single model call."""
    tokens: int = 0
    latency_ms: int = 0


# --------------------------------------------------------------------------- #
# Mode switch: "mock" runs fully offline (free, deterministic, for autograding);
# "llm" calls the real OpenAI API. Controlled by REFLEXION_MODE env var or
# set_mode() (run_benchmark.py wires this to its --mode flag).
# --------------------------------------------------------------------------- #
_USE_MOCK = os.getenv("REFLEXION_MODE", "mock").lower() != "llm"


def set_mode(mode: str) -> None:
    global _USE_MOCK
    _USE_MOCK = str(mode).lower() != "llm"


def current_mode() -> str:
    return "mock" if _USE_MOCK else "llm"


# --------------------------------------------------------------------------- #
# OpenAI helpers
# --------------------------------------------------------------------------- #
_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI  # imported lazily so mock mode never needs the key
        _client = OpenAI(max_retries=5)  # reads OPENAI_API_KEY from the environment
    return _client


def _estimate_tokens(*parts: str) -> int:
    return max(1, sum(len(p) for p in parts) // 4)


def _complete(system: str, user: str, json_mode: bool = False, temperature: float = 0.0) -> tuple[str, CallStats]:
    """Single chat-completion call. Returns (text, CallStats) with real token
    counts from usage metadata and measured latency."""
    client = _get_client()
    kwargs: dict = {
        "model": MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    start = time.perf_counter()
    resp = client.chat.completions.create(**kwargs)
    latency_ms = int((time.perf_counter() - start) * 1000)
    text = (resp.choices[0].message.content or "").strip()
    usage = getattr(resp, "usage", None)
    tokens = usage.total_tokens if usage and usage.total_tokens else _estimate_tokens(system, user, text)
    return text, CallStats(tokens=tokens, latency_ms=latency_ms)


def _parse_json(text: str) -> dict | None:
    """Best-effort JSON parse: handles raw JSON, ```json fenced blocks, and trailing prose."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t[:4].lower() == "json":
            t = t[4:].strip()
    try:
        return json.loads(t)
    except Exception:
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except Exception:
                return None
        return None


def _format_context(example: QAExample) -> str:
    return "\n".join(f"[{i}] {c.title}: {c.text}" for i, c in enumerate(example.context, 1))


def _actor_user_msg(example: QAExample, reflection_memory: list[str]) -> str:
    parts = [f"QUESTION:\n{example.question}", f"\nCONTEXT:\n{_format_context(example)}"]
    if reflection_memory:
        notes = "\n".join(f"- {m}" for m in reflection_memory)
        parts.append(f"\nPREVIOUS REFLECTION NOTES (do not repeat these mistakes):\n{notes}")
    parts.append("\nFinal answer (answer only):")
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Real LLM runtime
# --------------------------------------------------------------------------- #
def llm_actor_answer(example: QAExample, attempt_id: int, agent_type: str, reflection_memory: list[str]) -> tuple[str, CallStats]:
    memory = reflection_memory if agent_type == "reflexion" else []
    text, stats = _complete(ACTOR_SYSTEM, _actor_user_msg(example, memory), json_mode=False)
    return text.strip(), stats


def llm_evaluator(example: QAExample, answer: str) -> tuple[JudgeResult, CallStats]:
    user = (
        f"QUESTION:\n{example.question}\n\n"
        f"GOLD ANSWER:\n{example.gold_answer}\n\n"
        f"PREDICTED ANSWER:\n{answer}\n\n"
        "Return the grading JSON."
    )
    text, stats = _complete(EVALUATOR_SYSTEM, user, json_mode=True)
    data = _parse_json(text)
    if not data:
        score = 1 if normalize_answer(example.gold_answer) == normalize_answer(answer) else 0
        return JudgeResult(score=score, reason="Evaluator JSON parse failed; fell back to normalized exact match."), stats
    try:
        judge = JudgeResult(
            score=1 if int(data.get("score", 0)) == 1 else 0,
            reason=str(data.get("reason") or "No reason provided."),
            missing_evidence=[str(x) for x in (data.get("missing_evidence") or [])],
            spurious_claims=[str(x) for x in (data.get("spurious_claims") or [])],
        )
    except Exception:
        score = 1 if normalize_answer(example.gold_answer) == normalize_answer(answer) else 0
        judge = JudgeResult(score=score, reason="Malformed evaluator JSON; fell back to normalized exact match.")
    return judge, stats


def llm_reflector(example: QAExample, attempt_id: int, judge: JudgeResult, answer: str = "") -> tuple[ReflectionEntry, CallStats]:
    user = (
        f"QUESTION:\n{example.question}\n\n"
        f"WRONG ANSWER (attempt {attempt_id}):\n{answer}\n\n"
        f"GRADER'S REASON IT WAS WRONG:\n{judge.reason}\n"
        + (f"MISSING EVIDENCE: {judge.missing_evidence}\n" if judge.missing_evidence else "")
        + (f"SPURIOUS CLAIMS: {judge.spurious_claims}\n" if judge.spurious_claims else "")
        + "\nReturn the reflection JSON."
    )
    text, stats = _complete(REFLECTOR_SYSTEM, user, json_mode=True)
    data = _parse_json(text) or {}
    ref = ReflectionEntry(
        attempt_id=attempt_id,
        failure_reason=str(data.get("failure_reason") or judge.reason or "Unknown failure."),
        lesson=str(data.get("lesson") or "Re-read the context and complete every reasoning hop before answering."),
        next_strategy=str(data.get("next_strategy") or "Identify the intermediate entity first, then use it to find the final answer."),
    )
    return ref, stats


# --------------------------------------------------------------------------- #
# Offline mock runtime (deterministic, no API needed)
# --------------------------------------------------------------------------- #
def mock_actor_answer(example: QAExample, attempt_id: int, agent_type: str, reflection_memory: list[str]) -> tuple[str, CallStats]:
    if example.qid not in FIRST_ATTEMPT_WRONG:
        answer = example.gold_answer
    elif agent_type == "react":
        answer = FIRST_ATTEMPT_WRONG[example.qid]
    elif attempt_id == 1 and not reflection_memory:
        answer = FIRST_ATTEMPT_WRONG[example.qid]
    else:
        answer = example.gold_answer
    return answer, CallStats(tokens=_estimate_tokens(example.question, answer), latency_ms=5)


def mock_evaluator(example: QAExample, answer: str) -> tuple[JudgeResult, CallStats]:
    stats = CallStats(tokens=_estimate_tokens(example.question, example.gold_answer, answer), latency_ms=4)
    if normalize_answer(example.gold_answer) == normalize_answer(answer):
        return JudgeResult(score=1, reason="Final answer matches the gold answer after normalization."), stats
    if normalize_answer(answer) == "london":
        return JudgeResult(score=0, reason="The answer stopped at the birthplace city and never completed the second hop to the river.", missing_evidence=["Need to identify the river that flows through London."]), stats
    return JudgeResult(score=0, reason="The final answer selected the wrong second-hop entity.", missing_evidence=["Need to ground the answer in the second paragraph."], spurious_claims=[answer]), stats


def mock_reflector(example: QAExample, attempt_id: int, judge: JudgeResult, answer: str = "") -> tuple[ReflectionEntry, CallStats]:
    strategy = "Do the second hop explicitly: birthplace city -> river through that city." if example.qid == "hp2" else "Verify the final entity against the second paragraph before answering."
    ref = ReflectionEntry(attempt_id=attempt_id, failure_reason=judge.reason, lesson="A partial first-hop answer is not enough; the final answer must complete all hops.", next_strategy=strategy)
    return ref, CallStats(tokens=_estimate_tokens(example.question, judge.reason), latency_ms=4)


# --------------------------------------------------------------------------- #
# Dispatchers used by the agents (mock vs. real LLM)
# --------------------------------------------------------------------------- #
def actor_answer(example: QAExample, attempt_id: int, agent_type: str, reflection_memory: list[str]) -> tuple[str, CallStats]:
    fn = mock_actor_answer if _USE_MOCK else llm_actor_answer
    return fn(example, attempt_id, agent_type, reflection_memory)


def evaluator(example: QAExample, answer: str) -> tuple[JudgeResult, CallStats]:
    fn = mock_evaluator if _USE_MOCK else llm_evaluator
    return fn(example, answer)


def reflector(example: QAExample, attempt_id: int, judge: JudgeResult, answer: str = "") -> tuple[ReflectionEntry, CallStats]:
    fn = mock_reflector if _USE_MOCK else llm_reflector
    return fn(example, attempt_id, judge, answer)
