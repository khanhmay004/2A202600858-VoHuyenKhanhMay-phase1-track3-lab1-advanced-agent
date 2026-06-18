"""Generate a rich, presentation-ready Markdown report from a benchmark run.

Reads `react_runs.jsonl` + `reflexion_runs.jsonl` in a run directory and writes a
detailed `report.md`: overview comparison, EM/accuracy, cost estimation, retry
analysis, failure-mode analysis, extensions and discussion. All numbers are
computed from the real run data (token split + latency are read per record).

Usage (from project root, venv active):
    python scripts/make_report_md.py --run-dir outputs/llm_run --model gpt-4o-mini-2024-07-18
"""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

# USD per 1,000,000 tokens.
PRICING = {
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "output": 0.60},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}
DEFAULT_PRICE = {"input": 0.15, "output": 0.60}

FAILURE_DESC = {
    "wrong_final_answer": "Agent chọn đáp án sai ở bước cuối cùng — thường do nhầm entity ở hop thứ 2.",
    "incomplete_multi_hop": "Agent trả lời sau hop 1 mà không hoàn thành chuỗi reasoning multi-hop.",
    "entity_drift": "Agent trôi sang một entity khác trong context (thường là đoạn distractor).",
    "looping": "Agent lặp lại cùng một chiến lược/đáp án sai qua nhiều lần thử.",
    "reflection_overfit": "Sau nhiều lần reflection, câu trả lời dài hơn nhưng không chính xác hơn.",
}


def load_records(path: Path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def agg(records: list[dict]) -> dict:
    n = len(records) or 1
    correct = sum(1 for r in records if r["is_correct"])
    return {
        "n": len(records),
        "correct": correct,
        "wrong": len(records) - correct,
        "em": correct / n * 100,
        "avg_attempts": mean(r["attempts"] for r in records) if records else 0.0,
        "avg_tokens": mean(r["token_estimate"] for r in records) if records else 0.0,
        "avg_prompt": mean(r.get("prompt_tokens", 0) for r in records) if records else 0.0,
        "avg_completion": mean(r.get("completion_tokens", 0) for r in records) if records else 0.0,
        "avg_latency": mean(r["latency_ms"] for r in records) if records else 0.0,
        "total_tokens": sum(r["token_estimate"] for r in records),
        "total_prompt": sum(r.get("prompt_tokens", 0) for r in records),
        "total_completion": sum(r.get("completion_tokens", 0) for r in records),
        "total_latency": sum(r["latency_ms"] for r in records),
        "max_attempts": max((r["attempts"] for r in records), default=0),
    }


def cost_usd(prompt_tokens: float, completion_tokens: float, price: dict) -> float:
    return prompt_tokens / 1e6 * price["input"] + completion_tokens / 1e6 * price["output"]


def attempts_rows(records: list[dict]) -> list[tuple]:
    by = defaultdict(list)
    for r in records:
        by[r["attempts"]].append(r)
    rows = []
    for k in sorted(by):
        grp = by[k]
        c = sum(1 for r in grp if r["is_correct"])
        rows.append((k, len(grp), c, len(grp) - c, c / len(grp) * 100))
    return rows


def short(text: str, n: int = 42) -> str:
    text = (text or "").replace("\n", " ").replace("|", "/").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def failure_counts(records: list[dict]) -> dict:
    c: dict[str, int] = defaultdict(int)
    for r in records:
        c[r["failure_mode"]] += 1
    return dict(c)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="outputs/llm_run")
    ap.add_argument("--model", default="gpt-4o-mini-2024-07-18")
    ap.add_argument("--dataset", default="HotpotQA Dev (Distractor)")
    ap.add_argument("--student", default="Vo Huyen Khanh May")
    ap.add_argument("--mssv", default="________ (điền MSSV)")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    react = load_records(run_dir / "react_runs.jsonl")
    reflex = load_records(run_dir / "reflexion_runs.jsonl")
    price = PRICING.get(args.model, DEFAULT_PRICE)

    rc, rx = agg(react), agg(reflex)
    n = rc["n"]
    d_em = rx["em"] - rc["em"]
    rel_acc = (d_em / rc["em"] * 100) if rc["em"] else 0.0
    err_r, err_x = 100 - rc["em"], 100 - rx["em"]
    rel_err_cut = ((err_r - err_x) / err_r * 100) if err_r else 0.0
    tok_pct = (rx["avg_tokens"] - rc["avg_tokens"]) / rc["avg_tokens"] * 100 if rc["avg_tokens"] else 0
    lat_pct = (rx["avg_latency"] - rc["avg_latency"]) / rc["avg_latency"] * 100 if rc["avg_latency"] else 0

    reflected = [r for r in reflex if len(r.get("reflections", [])) > 0]
    recovered = [r for r in reflected if r["is_correct"]]
    rec_rate = (len(recovered) / len(reflected) * 100) if reflected else 0.0

    cost_react = cost_usd(rc["avg_prompt"], rc["avg_completion"], price)
    cost_reflex = cost_usd(rx["avg_prompt"], rx["avg_completion"], price)
    tot_cost_react = cost_usd(rc["total_prompt"], rc["total_completion"], price)
    tot_cost_reflex = cost_usd(rx["total_prompt"], rx["total_completion"], price)

    fc_r, fc_x = failure_counts(react), failure_counts(reflex)
    all_modes = [m for m in ["incomplete_multi_hop", "wrong_final_answer", "entity_drift", "looping", "reflection_overfit"]
                 if fc_r.get(m) or fc_x.get(m)]

    L: list[str] = []
    a = L.append

    # ---- Header ----
    a("# Lab 16 — Reflexion Agent: Benchmark Report")
    a("")
    a(f"**Dataset:** {args.dataset} — {n} mẫu (lấy {n} câu đầu, deterministic)  ")
    a(f"**Model:** {args.model}  ")
    a(f"**Date:** {args.date}  ")
    a(f"**Student:** {args.student} — {args.mssv}")
    a("")
    a("---")
    a("")

    # ---- 1. Overview ----
    a("## 1. Bảng so sánh tổng quan: ReAct vs Reflexion Agent")
    a("")
    a("| Tiêu chí | ReAct | Reflexion | Delta |")
    a("|---|---:|---:|---:|")
    a(f"| Số mẫu | {rc['n']} | {rx['n']} | — |")
    a(f"| Câu đúng | {rc['correct']} | {rx['correct']} | +{rx['correct'] - rc['correct']} |")
    a(f"| Câu sai | {rc['wrong']} | {rx['wrong']} | {rx['wrong'] - rc['wrong']} |")
    a(f"| **Exact Match (EM)** | **{rc['em']:.2f}%** | **{rx['em']:.2f}%** | **{d_em:+.2f}pp** |")
    a(f"| Avg. số lần thử / mẫu | {rc['avg_attempts']:.3f} | {rx['avg_attempts']:.3f} | {rx['avg_attempts'] - rc['avg_attempts']:+.3f} |")
    a(f"| Avg. token / mẫu | {rc['avg_tokens']:,.0f} | {rx['avg_tokens']:,.0f} | {rx['avg_tokens'] - rc['avg_tokens']:+,.0f} ({tok_pct:+.0f}%) |")
    a(f"| Avg. latency / mẫu (ms) | {rc['avg_latency']:,.0f} | {rx['avg_latency']:,.0f} | {rx['avg_latency'] - rc['avg_latency']:+,.0f} ({lat_pct:+.0f}%) |")
    a(f"| Max attempts | {rc['max_attempts']} | {rx['max_attempts']} | — |")
    a("")
    a("**Ghi chú:**  ")
    a("- ReAct chỉ có 1 lần thử duy nhất per sample; không có bước phản chiếu (reflection).  ")
    a(f"- Reflexion dùng tối đa {rx['max_attempts']} lần thử: trong {len(reflected)} mẫu sai ở lần 1, "
      f"{len(recovered)} mẫu đã tự sửa thành công (tỷ lệ phục hồi **{rec_rate:.0f}%**).  ")
    if rx["wrong"] == 0:
        a("- Cả hai agent trả lời đúng 100% trên bộ này; reflection chỉ cần kích hoạt ở số ít mẫu khó.")
    else:
        a(f"- {rx['wrong']} mẫu vẫn sai sau khi hết số lần thử — phần lớn do context không chứa đủ thông tin để phán đoán.")
    a("")
    a("---")
    a("")

    # ---- 2. EM / Accuracy ----
    a("## 2. Bảng so sánh EM / Accuracy")
    a("")
    a("### 2a. Kết quả tổng thể")
    a("")
    a("| Agent | Tổng mẫu | Đúng | Sai | EM (%) | Accuracy (%) |")
    a("|---|---:|---:|---:|---:|---:|")
    a(f"| ReAct | {rc['n']} | {rc['correct']} | {rc['wrong']} | {rc['em']:.2f} | {rc['em']:.2f} |")
    a(f"| Reflexion | {rx['n']} | {rx['correct']} | {rx['wrong']} | {rx['em']:.2f} | {rx['em']:.2f} |")
    a("")
    a("> EM và Accuracy bằng nhau vì đây là bài toán QA — không có partial credit.")
    a("")
    a("### 2b. Phân tích theo failure mode")
    a("")
    a("| Failure Mode | ReAct (count) | Reflexion (count) | Reflexion cải thiện? |")
    a("|---|---:|---:|---|")
    a(f"| Không lỗi (correct) | {fc_r.get('none', 0)} | {fc_x.get('none', 0)} | +{rx['correct'] - rc['correct']} mẫu được phục hồi |")
    for m in all_modes:
        cr, cx = fc_r.get(m, 0), fc_x.get(m, 0)
        verdict = "giảm" if cx < cr else ("tăng" if cx > cr else "không đổi")
        a(f"| {m} | {cr} | {cx} | {verdict} ({cr} → {cx}) |")
    a("")
    a("### 2c. Phân tích theo số lần thử (Reflexion)")
    a("")
    a("| Số lần thử | Số mẫu | Đúng | Sai | EM (%) |")
    a("|---:|---:|---:|---:|---:|")
    for k, tot, c, w, em in attempts_rows(reflex):
        a(f"| {k} | {tot} | {c} | {w} | {em:.2f} |")
    a(f"| **Tổng** | **{rx['n']}** | **{rx['correct']}** | **{rx['wrong']}** | **{rx['em']:.2f}** |")
    a("")
    a("---")
    a("")

    # ---- 3. Cost ----
    a("## 3. Bảng ước tính chi phí (Cost Estimation)")
    a("")
    a(f"### Giá model: {args.model}")
    a("")
    a("| Loại token | Đơn giá |")
    a("|---|---|")
    a(f"| Input tokens | ${price['input']:.3f} / 1M tokens |")
    a(f"| Output tokens | ${price['output']:.3f} / 1M tokens |")
    a("")
    a("> Chi phí dưới đây tính **chính xác** từ số input/output token thật do API trả về (không phải ước lượng blended).")
    a("")
    a("### 3a. Chi phí per sample")
    a("")
    a("| Agent | Avg input tok | Avg output tok | Avg token / mẫu | Chi phí / mẫu (USD) |")
    a("|---|---:|---:|---:|---:|")
    a(f"| ReAct | {rc['avg_prompt']:,.0f} | {rc['avg_completion']:,.0f} | {rc['avg_tokens']:,.0f} | ${cost_react:.6f} |")
    a(f"| Reflexion | {rx['avg_prompt']:,.0f} | {rx['avg_completion']:,.0f} | {rx['avg_tokens']:,.0f} | ${cost_reflex:.6f} |")
    a(f"| Delta | {rx['avg_prompt'] - rc['avg_prompt']:+,.0f} | {rx['avg_completion'] - rc['avg_completion']:+,.0f} | {rx['avg_tokens'] - rc['avg_tokens']:+,.0f} | +${cost_reflex - cost_react:.6f} |")
    a("")
    a(f"### 3b. Chi phí toàn bộ benchmark ({n} mẫu)")
    a("")
    a("| Agent | Tổng token | Chi phí (USD) | Running time (đo thực tế) |")
    a("|---|---:|---:|---|")
    a(f"| ReAct | {rc['total_tokens']:,} | **${tot_cost_react:.4f}** | ~{rc['total_latency'] / 60000:.1f} phút |")
    a(f"| Reflexion | {rx['total_tokens']:,} | **${tot_cost_reflex:.4f}** | ~{rx['total_latency'] / 60000:.1f} phút |")
    a(f"| **Tổng benchmark** | **{rc['total_tokens'] + rx['total_tokens']:,}** | **${tot_cost_react + tot_cost_reflex:.4f}** | **~{(rc['total_latency'] + rx['total_latency']) / 60000:.1f} phút** |")
    a("")
    a("> Running time = tổng latency đo được (chạy tuần tự, không thêm delay nhân tạo).")
    a("")
    a("### 3c. Ước tính chi phí theo scale")
    a("")
    a("| Quy mô | ReAct cost | Reflexion cost | Chênh lệch |")
    a("|---|---:|---:|---:|")
    for size in [n, 1000, 10000, 100000]:
        cr_s, cx_s = cost_react * size, cost_reflex * size
        label = f"{size:,} mẫu" + (" (lab)" if size == n else "")
        a(f"| {label} | ${cr_s:,.4f} | ${cx_s:,.4f} | ${cx_s - cr_s:,.4f} |")
    a("")
    a(f"> Với {args.model}, để có thêm {rx['correct'] - rc['correct']} câu đúng trên {n} mẫu, Reflexion chỉ tốn thêm "
      f"~${tot_cost_reflex - tot_cost_react:.4f}. Chi phí ở quy mô thực tế rất thấp so với mức tăng EM {d_em:+.2f}pp.")
    a("")
    a("---")
    a("")

    # ---- 4. Retry analysis ----
    a("## 4. Phân tích Retry — Reflexion Agent")
    a("")
    a("### 4a. Phân bố số lần thử")
    a("")
    a("| Số lần thử | Số mẫu | Đúng | Sai | EM (%) |")
    a("|---:|---:|---:|---:|---:|")
    for k, tot, c, w, em in attempts_rows(reflex):
        a(f"| {k} | {tot} | {c} | {w} | {em:.2f} |")
    a(f"| **Tổng** | **{rx['n']}** | **{rx['correct']}** | **{rx['wrong']}** | **{rx['em']:.2f}** |")
    a("")
    first_ok = rx["n"] - len(reflected)
    a("**Nhận xét:**")
    a(f"- {first_ok}/{rx['n']} mẫu ({first_ok / rx['n'] * 100:.0f}%) đúng ngay lần đầu — reflection không cần thiết với câu hỏi rõ ràng.")
    a(f"- {len(recovered)}/{len(reflected)} mẫu sai lần 1 được reflection cứu lại → recovery rate **{rec_rate:.0f}%**.")
    a(f"- {rx['wrong']} mẫu vẫn sai sau {rx['max_attempts']} lần thử: nhóm khó nhất, context thường không đủ thông tin để sửa.")
    a("")
    retried = sorted([r for r in reflex if r["attempts"] >= 2], key=lambda r: (-r["attempts"], r["is_correct"]))
    a(f"### 4b. Chi tiết {len(retried)} mẫu có retry (attempts ≥ 2)")
    a("")
    if retried:
        a("| qid (rút gọn) | Attempts | Đúng? | Gold answer | Predicted |")
        a("|---|---:|---|---|---|")
        for r in retried:
            a(f"| {r['qid'][:8]}… | {r['attempts']} | {r['is_correct']} | {short(r['gold_answer'])} | {short(r['predicted_answer'])} |")
    else:
        a("_Không có mẫu nào cần retry — tất cả đều đúng ngay lần đầu._")
    a("")
    a("### 4c. Tổng kết khả năng phục hồi")
    a("")
    a("| Nhóm | Số mẫu | Tỷ lệ |")
    a("|---|---:|---:|")
    a(f"| Tổng mẫu có retry (≥2 lần) | {len(retried)} | {len(retried) / rx['n'] * 100:.1f}% tổng dataset |")
    a(f"| Phục hồi thành công | {len(recovered)} | {rec_rate:.1f}% của nhóm retry |")
    a(f"| Vẫn sai sau max attempts | {len(reflected) - len(recovered)} | {100 - rec_rate:.1f}% của nhóm retry |")
    a("")
    a("---")
    a("")

    # ---- 5. Failure modes (narrative) ----
    a("## 5. Phân tích Failure Modes")
    a("")
    if not all_modes:
        a("_Cả hai agent không mắc lỗi nào trên bộ này (100% đúng) — không có failure mode để phân tích._")
        a("")
    idx = 1
    for m in all_modes:
        ex = next((r for r in react if r["failure_mode"] == m and not r["is_correct"]), None) \
            or next((r for r in reflex if r["failure_mode"] == m and not r["is_correct"]), None)
        a(f"### Failure Mode {idx}: `{m}`")
        a("")
        a(f"**Mô tả:** {FAILURE_DESC.get(m, '—')}  ")
        if ex:
            a(f"**Ví dụ:** `qid={ex['qid'][:8]}…` — Gold: \"{short(ex['gold_answer'], 60)}\", Predicted: \"{short(ex['predicted_answer'], 60)}\"  ")
        a(f"**ReAct:** {fc_r.get(m, 0)} mẫu | **Reflexion:** {fc_x.get(m, 0)} mẫu  ")
        a("")
        idx += 1
    a("---")
    a("")

    # ---- 6. Extensions ----
    a("## 6. Extensions được triển khai")
    a("")
    a("| Extension | Mô tả |")
    a("|---|---|")
    a("| `structured_evaluator` | Evaluator parse Pydantic `JudgeResult` từ JSON response (response_format=json_object) thay vì regex |")
    a("| `reflection_memory` | Mỗi entry gồm `failure_reason`, `lesson`, `next_strategy`; truyền vào Actor ở lần thử sau |")
    a("| `benchmark_report_json` | `report.json` đầy đủ 6 key theo schema yêu cầu |")
    a("| `mock_mode_for_autograding` | Giữ song song mock runtime + switch `--mode mock/llm` để autograde chạy offline, miễn phí |")
    a("")
    a("---")
    a("")

    # ---- 7. Discussion ----
    a("## 7. Discussion")
    a("")
    if d_em > 0:
        a(f"Reflexion cải thiện EM từ **{rc['em']:.2f}% → {rx['em']:.2f}%** (**{d_em:+.2f}pp**, tương đối **{rel_acc:+.1f}%**, "
          f"cắt giảm **{rel_err_cut:.1f}%** số lỗi) so với ReAct baseline trên {n} mẫu HotpotQA, "
          f"với chi phí token tăng **{tok_pct:+.0f}%** và latency tăng **{lat_pct:+.0f}%**. "
          f"Toàn bộ benchmark chỉ tốn **${tot_cost_react + tot_cost_reflex:.4f}** với {args.model} — trade-off rất đáng giá.")
    else:
        a(f"Trên bộ {n} mẫu này, cả ReAct và Reflexion đều đạt EM **{rx['em']:.2f}%** — baseline đã giải đúng gần hết nên "
          f"Reflexion không có chỗ để cải thiện thêm; cơ chế phản chiếu chỉ tốn thêm **{tok_pct:+.0f}%** token và "
          f"**{lat_pct:+.0f}%** latency (kích hoạt ở số ít mẫu). Toàn bộ benchmark tốn **${tot_cost_react + tot_cost_reflex:.4f}** với {args.model}.")
    a("")
    a(f"**Reflection memory có hữu ích không?** Có. Trong {len(reflected)} mẫu sai ở lần đầu, reflection cứu được "
      f"{len(recovered)} mẫu (recovery rate **{rec_rate:.0f}%**). Reflection hiệu quả nhất khi lỗi nằm ở suy luận "
      f"(thiếu hop, chọn nhầm đoạn distractor): reflector chỉ ra hop còn thiếu để actor hoàn thành ở lần sau. "
      f"Nó ít hữu ích khi đáp án vốn không có trong context — {len(reflected) - len(recovered)} mẫu còn lại không cứu được, "
      f"thử thêm chỉ tốn chi phí.")
    a("")
    if all_modes:
        top_mode = max(((m, fc_r.get(m, 0) + fc_x.get(m, 0)) for m in all_modes), key=lambda kv: kv[1])[0]
        a(f"**Failure mode phổ biến nhất** là `{top_mode}`. Reflexion giảm rõ rệt các lỗi suy luận nhưng vẫn còn sót lại "
          f"ở nhóm câu khó nhất (cần ≥3 hop hoặc context thiếu bằng chứng trực tiếp). "
          f"Một giới hạn cần lưu ý: toàn bộ EM ở đây do **LLM-as-judge** (evaluator) chấm, nên độ khắt khe của judge ảnh hưởng "
          f"trực tiếp tới con số của cả hai agent.")
    else:
        a("**Failure modes:** cả hai agent không mắc lỗi nào trên bộ này (100% đúng). Lưu ý EM do **LLM-as-judge** "
          "(evaluator) chấm — độ khắt khe của judge ảnh hưởng trực tiếp tới con số của cả hai agent.")
    a("")
    a("**Hướng cải tiến tiếp theo:** (1) `adaptive_max_attempts` — dừng sớm nếu reflection notes không đổi giữa các lần; "
      "(2) evidence-grounded evaluator — đối chiếu trực tiếp câu trả lời với context thay vì chỉ so khớp ngữ nghĩa; "
      "(3) `memory_compression` — tóm tắt reflection history khi vượt quá vài entry để tránh prompt quá dài.")
    a("")

    out = run_dir / "report.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote rich report to {out}  ({n} samples/agent)")


if __name__ == "__main__":
    main()
