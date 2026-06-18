# Lab 16 — Reflexion Agent — Báo cáo tổng hợp

**Student:** Võ Huyền Khánh Mây - 2A202600858
**Model:** OpenAI `gpt-4o-mini-2024-07-18`
**Date:** 2026-06-18
**Auto-grade:** **100 / 100** — Schema 30 · Experiment 30 · Analysis 20 · Bonus 20

Báo cáo này tổng hợp **2 lần chạy thật** với LLM:
- **Dev Benchmark** — 120 câu HotpotQA (level: hard) → chi tiết: [`reports/dev_benchmark.md`](reports/dev_benchmark.md)
- **Golden Test Set** — 20 câu (bộ giảng viên phát) → chi tiết: [`reports/golden_test.md`](reports/golden_test.md)

---

## 1. Tóm tắt kết quả

### 1a. Dev Benchmark — `data/hotpot_100.json` (120 câu × 2 agent = 240 records)

| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| **Exact Match (EM)** | **74.17%** | **95.00%** | **+20.83pp** |
| Câu đúng | 89 / 120 | 114 / 120 | +25 |
| Avg. attempts / câu | 1.000 | 1.325 | +0.325 |
| Avg. tokens / câu | 2,007 | 2,822 | +815 (+41%) |
| Avg. latency / câu | 2,439 ms | 3,664 ms | +1,225 (+50%) |
| Chi phí (tổng) | $0.0387 | $0.0559 | **$0.0946** |

- Reflexion: **30** câu sai ở lần đầu → **24** câu được reflection cứu (**recovery rate 80%**); 6 câu khó còn sai sau 3 lần thử.
- Failure mode phổ biến nhất: `incomplete_multi_hop` (ReAct 17 → Reflexion 2), kế đến `wrong_final_answer` (10 → 3).

### 1b. Golden Test Set — `data/hotpot_golden.json` (20 câu × 2 agent = 40 records)

| Metric | ReAct | Reflexion |
|---|---:|---:|
| **Exact Match (EM)** | **100.00%** | **100.00%** |
| Câu đúng | 20 / 20 | 20 / 20 |
| Avg. tokens / câu | 733 | 794 |
| Chi phí (tổng) | $0.0026 | $0.0029 |

- Cả hai agent giải đúng **100%** trên bộ chưa từng thấy → agent **ổn định, không crash**, xử lý đúng nhiều dạng câu (yes/no, số liệu, danh sách).
- Reflexion kích hoạt reflection ở **1** câu và phục hồi thành công (vd `gold6`: gold "Dutch, French, and German" ← predicted "Dutch, French, German").

> **Tổng chi phí cả 2 run ≈ $0.10** với `gpt-4o-mini`.

---

## 2. Cách chạy lại (dùng `.venv`, không cài global)

```powershell
# Kiểm tra nhanh (mock, offline, miễn phí)
.\.venv\Scripts\python.exe run_benchmark.py --mode mock --dataset data\hotpot_mini.json --out-dir outputs\sample_run

# Dev benchmark thật (120 câu)
.\.venv\Scripts\python.exe run_benchmark.py --mode llm --dataset data\hotpot_100.json --out-dir outputs\llm_run

# Golden test set
.\.venv\Scripts\python.exe run_benchmark.py --mode llm --dataset data\hotpot_golden.json --out-dir outputs\golden_run

# Chấm điểm tự động
.\.venv\Scripts\python.exe autograde.py --report-path outputs\llm_run\report.json

# Sinh báo cáo chi tiết "đẹp" (overview / EM / cost / retry / failure modes) — không tốn API
.\.venv\Scripts\python.exe scripts\make_report_md.py --run-dir outputs\llm_run --student "Võ Huyền Khánh Mây" --mssv "2A202600858"
```

> Key OpenAI đọc tự động từ `.env` (`OPENAI_API_KEY`). Model có thể đổi qua biến `OPENAI_MODEL`.

---

## 3. Kiến trúc & luồng hoạt động

Mỗi câu hỏi đi qua vòng lặp `BaseAgent.run()`:

```
for attempt in 1..max_attempts:
    answer  = actor_answer(question, context, reflection_memory)   # LLM call
    judge   = evaluator(answer vs gold_answer)                     # LLM call -> JudgeResult (JSON)
    if judge.score == 1: break
    if reflexion and còn lượt:
        ref = reflector(question, wrong answer, lý do sai)         # LLM call -> ReflectionEntry (JSON)
        reflection_memory.append(ref)   # nạp bài học vào lần thử sau
```

- **ReAct** = `max_attempts = 1` (1 lượt, không phản chiếu).
- **Reflexion** = `max_attempts = 3` (phản chiếu + thử lại với reflection memory).
- 3 vai trò đều gọi `gpt-4o-mini`; Evaluator/Reflector ép JSON bằng `response_format={"type":"json_object"}`, parse có fallback an toàn.
- Token (input/output tách riêng) và latency đo **thật** từ API → dùng cho bảng chi phí.

---

## 4. Extensions đã triển khai (Bonus 20/20)

| Extension | Mô tả |
|---|---|
| `structured_evaluator` | Evaluator trả về `JudgeResult` có cấu trúc (JSON) thay vì text/regex |
| `reflection_memory` | Mỗi reflection gồm `failure_reason` / `lesson` / `next_strategy`, nạp vào Actor lần sau |
| `benchmark_report_json` | `report.json` đầy đủ 6 key theo schema |
| `mock_mode_for_autograding` | Switch `--mode mock/llm`: giữ mock runtime để autograde chạy offline, miễn phí |

---

## 5. Nhận xét chính

1. **Reflexion có cải thiện accuracy không?** Có — trên bộ khó (Dev), EM tăng **+20.83pp** (74.17% → 95.00%), cắt giảm **~80%** số lỗi. Trên bộ Golden (dễ hơn với model), baseline đã đạt 100% nên không còn chỗ cải thiện.
2. **Reflection memory có hữu ích không?** Có. Recovery rate **80%** (Dev) và **100%** (Golden, 1/1). Hiệu quả nhất với lỗi suy luận (thiếu hop, chọn nhầm đoạn distractor); ít tác dụng khi đáp án không có sẵn trong context.
3. **Trade-off chi phí.** Reflexion tốn thêm ~41% token và ~50% latency, nhưng chi phí tuyệt đối rất nhỏ (cả 2 run ≈ $0.10). Đáng đánh đổi khi cần accuracy cao.
4. **Giới hạn.** EM được chấm bởi **LLM-as-judge** (evaluator), nên độ khắt khe của judge ảnh hưởng tới con số của cả hai agent. Hướng cải tiến: `adaptive_max_attempts`, evidence-grounded evaluator, `memory_compression`.

---

## 6. Cấu trúc thư mục

| Đường dẫn | Mô tả |
|---|---|
| `src/reflexion_lab/prompts.py` | System prompt cho Actor / Evaluator / Reflector |
| `src/reflexion_lab/mock_runtime.py` | OpenAI runtime + mock runtime + switch mode |
| `src/reflexion_lab/agents.py` | Vòng lặp ReAct / Reflexion + đo token & latency thật |
| `src/reflexion_lab/reporting.py` | `report.json` + `report.md` cơ bản |
| `scripts/build_dataset.py` | Convert HotpotQA → `QAExample` (`data/hotpot_100.json`) |
| `scripts/make_report_md.py` | Sinh báo cáo chi tiết "đẹp" từ JSONL của một run |
| `reports/dev_benchmark.md` · `.json` | Báo cáo chi tiết Dev Benchmark (bản commit được) |
| `reports/golden_test.md` · `.json` | Báo cáo chi tiết Golden Test (bản commit được) |
| `outputs/` | Kết quả chạy raw (jsonl + report.json/md) của từng run |
