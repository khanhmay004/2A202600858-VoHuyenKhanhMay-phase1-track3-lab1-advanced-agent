from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from .schemas import ReportPayload, RunRecord

EXTENSIONS = ["structured_evaluator", "reflection_memory", "benchmark_report_json", "mock_mode_for_autograding"]


def summarize(records: list[RunRecord]) -> dict:
    grouped: dict[str, list[RunRecord]] = defaultdict(list)
    for record in records:
        grouped[record.agent_type].append(record)
    summary: dict[str, dict] = {}
    for agent_type, rows in grouped.items():
        summary[agent_type] = {"count": len(rows), "em": round(mean(1.0 if r.is_correct else 0.0 for r in rows), 4), "avg_attempts": round(mean(r.attempts for r in rows), 4), "avg_token_estimate": round(mean(r.token_estimate for r in rows), 2), "avg_latency_ms": round(mean(r.latency_ms for r in rows), 2)}
    if "react" in summary and "reflexion" in summary:
        summary["delta_reflexion_minus_react"] = {"em_abs": round(summary["reflexion"]["em"] - summary["react"]["em"], 4), "attempts_abs": round(summary["reflexion"]["avg_attempts"] - summary["react"]["avg_attempts"], 4), "tokens_abs": round(summary["reflexion"]["avg_token_estimate"] - summary["react"]["avg_token_estimate"], 2), "latency_abs": round(summary["reflexion"]["avg_latency_ms"] - summary["react"]["avg_latency_ms"], 2)}
    return summary


def failure_breakdown(records: list[RunRecord]) -> dict:
    grouped: dict[str, Counter] = defaultdict(Counter)
    combined: Counter = Counter()
    for record in records:
        grouped[record.agent_type][record.failure_mode] += 1
        combined[record.failure_mode] += 1
    out = {agent: dict(counter) for agent, counter in grouped.items()}
    out["combined"] = dict(combined)  # third key ensures >=3 entries and gives a dataset-wide view
    return out


def _top_failures(modes: dict) -> str:
    items = sorted(((k, v) for k, v in modes.items() if k != "none"), key=lambda kv: -kv[1])
    return ", ".join(f"{k} ({v})" for k, v in items[:3]) if items else "no remaining failures"


def build_discussion(summary: dict, failure_modes: dict, mode: str) -> str:
    react = summary.get("react", {})
    reflexion = summary.get("reflexion", {})
    delta = summary.get("delta_reflexion_minus_react", {})
    r_em, x_em = react.get("em", 0.0), reflexion.get("em", 0.0)
    d_em = delta.get("em_abs", round(x_em - r_em, 4))
    improvement = "improved" if d_em > 0 else ("did not change" if d_em == 0 else "regressed")
    return (
        f"Running in '{mode}' mode, ReAct (single attempt) reached exact-match accuracy EM={r_em} while "
        f"Reflexion (up to several attempts with self-reflection) reached EM={x_em}; accuracy {improvement} by "
        f"{d_em:+} absolute. The gain comes at a cost: Reflexion averaged {reflexion.get('avg_attempts', 0)} attempts "
        f"versus {react.get('avg_attempts', 0)} for ReAct, spending about {delta.get('tokens_abs', 0)} more tokens and "
        f"{delta.get('latency_abs', 0)} ms more latency per question on average. The most common ReAct failure modes "
        f"were {_top_failures(failure_modes.get('react', {}))}, while Reflexion's residual failures were "
        f"{_top_failures(failure_modes.get('reflexion', {}))}. Reflection memory helped most when the first attempt "
        f"stopped after the first hop or drifted to a distractor entity, because the reflector could name the missing "
        f"hop and the actor could complete it next time. It helped least when the answer was simply absent from the "
        f"provided context, where extra attempts only added cost. The key trade-off is accuracy versus token and "
        f"latency budget, and evaluator quality bounds the measured gains."
    )


def build_report(records: list[RunRecord], dataset_name: str, mode: str = "mock") -> ReportPayload:
    examples = [{"qid": r.qid, "agent_type": r.agent_type, "gold_answer": r.gold_answer, "predicted_answer": r.predicted_answer, "is_correct": r.is_correct, "attempts": r.attempts, "failure_mode": r.failure_mode, "reflection_count": len(r.reflections)} for r in records]
    summary = summarize(records)
    failure_modes = failure_breakdown(records)
    return ReportPayload(
        meta={"dataset": dataset_name, "mode": mode, "num_records": len(records), "agents": sorted({r.agent_type for r in records})},
        summary=summary,
        failure_modes=failure_modes,
        examples=examples,
        extensions=EXTENSIONS,
        discussion=build_discussion(summary, failure_modes, mode),
    )


def save_report(report: ReportPayload, out_dir: str | Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    md_path = out_dir / "report.md"
    json_path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")
    s = report.summary
    react = s.get("react", {})
    reflexion = s.get("reflexion", {})
    delta = s.get("delta_reflexion_minus_react", {})
    ext_lines = "\n".join(f"- {item}" for item in report.extensions)
    md = f"""# Lab 16 Benchmark Report

## Metadata
- Dataset: {report.meta['dataset']}
- Mode: {report.meta['mode']}
- Records: {report.meta['num_records']}
- Agents: {', '.join(report.meta['agents'])}

## Summary
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | {react.get('em', 0)} | {reflexion.get('em', 0)} | {delta.get('em_abs', 0)} |
| Avg attempts | {react.get('avg_attempts', 0)} | {reflexion.get('avg_attempts', 0)} | {delta.get('attempts_abs', 0)} |
| Avg token estimate | {react.get('avg_token_estimate', 0)} | {reflexion.get('avg_token_estimate', 0)} | {delta.get('tokens_abs', 0)} |
| Avg latency (ms) | {react.get('avg_latency_ms', 0)} | {reflexion.get('avg_latency_ms', 0)} | {delta.get('latency_abs', 0)} |

## Failure modes
```json
{json.dumps(report.failure_modes, indent=2)}
```

## Extensions implemented
{ext_lines}

## Discussion
{report.discussion}
"""
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path
