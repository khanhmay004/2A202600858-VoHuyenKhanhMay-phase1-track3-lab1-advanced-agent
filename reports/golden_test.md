# Lab 16 — Reflexion Agent: Benchmark Report

**Dataset:** Golden Test Set (HotpotQA) — 20 mẫu (lấy 20 câu đầu, deterministic)  
**Model:** gpt-4o-mini-2024-07-18  
**Date:** 2026-06-18  
**Student:** Võ Huyền Khánh Mây — 2A202600858

---

## 1. Bảng so sánh tổng quan: ReAct vs Reflexion Agent

| Tiêu chí | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| Số mẫu | 20 | 20 | — |
| Câu đúng | 20 | 20 | +0 |
| Câu sai | 0 | 0 | 0 |
| **Exact Match (EM)** | **100.00%** | **100.00%** | **+0.00pp** |
| Avg. số lần thử / mẫu | 1.000 | 1.050 | +0.050 |
| Avg. token / mẫu | 733 | 794 | +62 (+8%) |
| Avg. latency / mẫu (ms) | 2,789 | 2,278 | -510 (-18%) |
| Max attempts | 1 | 2 | — |

**Ghi chú:**  
- ReAct chỉ có 1 lần thử duy nhất per sample; không có bước phản chiếu (reflection).  
- Reflexion dùng tối đa 2 lần thử: trong 1 mẫu sai ở lần 1, 1 mẫu đã tự sửa thành công (tỷ lệ phục hồi **100%**).  
- Cả hai agent trả lời đúng 100% trên bộ này; reflection chỉ cần kích hoạt ở số ít mẫu khó.

---

## 2. Bảng so sánh EM / Accuracy

### 2a. Kết quả tổng thể

| Agent | Tổng mẫu | Đúng | Sai | EM (%) | Accuracy (%) |
|---|---:|---:|---:|---:|---:|
| ReAct | 20 | 20 | 0 | 100.00 | 100.00 |
| Reflexion | 20 | 20 | 0 | 100.00 | 100.00 |

> EM và Accuracy bằng nhau vì đây là bài toán QA — không có partial credit.

### 2b. Phân tích theo failure mode

| Failure Mode | ReAct (count) | Reflexion (count) | Reflexion cải thiện? |
|---|---:|---:|---|
| Không lỗi (correct) | 20 | 20 | +0 mẫu được phục hồi |

### 2c. Phân tích theo số lần thử (Reflexion)

| Số lần thử | Số mẫu | Đúng | Sai | EM (%) |
|---:|---:|---:|---:|---:|
| 1 | 19 | 19 | 0 | 100.00 |
| 2 | 1 | 1 | 0 | 100.00 |
| **Tổng** | **20** | **20** | **0** | **100.00** |

---

## 3. Bảng ước tính chi phí (Cost Estimation)

### Giá model: gpt-4o-mini-2024-07-18

| Loại token | Đơn giá |
|---|---|
| Input tokens | $0.150 / 1M tokens |
| Output tokens | $0.600 / 1M tokens |

> Chi phí dưới đây tính **chính xác** từ số input/output token thật do API trả về (không phải ước lượng blended).

### 3a. Chi phí per sample

| Agent | Avg input tok | Avg output tok | Avg token / mẫu | Chi phí / mẫu (USD) |
|---|---:|---:|---:|---:|
| ReAct | 686 | 46 | 733 | $0.000131 |
| Reflexion | 742 | 53 | 794 | $0.000143 |
| Delta | +55 | +6 | +62 | +$0.000012 |

### 3b. Chi phí toàn bộ benchmark (20 mẫu)

| Agent | Tổng token | Chi phí (USD) | Running time (đo thực tế) |
|---|---:|---:|---|
| ReAct | 14,658 | **$0.0026** | ~0.9 phút |
| Reflexion | 15,889 | **$0.0029** | ~0.8 phút |
| **Tổng benchmark** | **30,547** | **$0.0055** | **~1.7 phút** |

> Running time = tổng latency đo được (chạy tuần tự, không thêm delay nhân tạo).

### 3c. Ước tính chi phí theo scale

| Quy mô | ReAct cost | Reflexion cost | Chênh lệch |
|---|---:|---:|---:|
| 20 mẫu (lab) | $0.0026 | $0.0029 | $0.0002 |
| 1,000 mẫu | $0.1308 | $0.1429 | $0.0121 |
| 10,000 mẫu | $1.3084 | $1.4295 | $0.1211 |
| 100,000 mẫu | $13.0838 | $14.2950 | $1.2112 |

> Với gpt-4o-mini-2024-07-18, để có thêm 0 câu đúng trên 20 mẫu, Reflexion chỉ tốn thêm ~$0.0002. Chi phí ở quy mô thực tế rất thấp so với mức tăng EM +0.00pp.

---

## 4. Phân tích Retry — Reflexion Agent

### 4a. Phân bố số lần thử

| Số lần thử | Số mẫu | Đúng | Sai | EM (%) |
|---:|---:|---:|---:|---:|
| 1 | 19 | 19 | 0 | 100.00 |
| 2 | 1 | 1 | 0 | 100.00 |
| **Tổng** | **20** | **20** | **0** | **100.00** |

**Nhận xét:**
- 19/20 mẫu (95%) đúng ngay lần đầu — reflection không cần thiết với câu hỏi rõ ràng.
- 1/1 mẫu sai lần 1 được reflection cứu lại → recovery rate **100%**.
- 0 mẫu vẫn sai sau 2 lần thử: nhóm khó nhất, context thường không đủ thông tin để sửa.

### 4b. Chi tiết 1 mẫu có retry (attempts ≥ 2)

| qid (rút gọn) | Attempts | Đúng? | Gold answer | Predicted |
|---|---:|---|---|---|
| gold6… | 2 | True | Dutch, French, and German | Dutch, French, German |

### 4c. Tổng kết khả năng phục hồi

| Nhóm | Số mẫu | Tỷ lệ |
|---|---:|---:|
| Tổng mẫu có retry (≥2 lần) | 1 | 5.0% tổng dataset |
| Phục hồi thành công | 1 | 100.0% của nhóm retry |
| Vẫn sai sau max attempts | 0 | 0.0% của nhóm retry |

---

## 5. Phân tích Failure Modes

_Cả hai agent không mắc lỗi nào trên bộ này (100% đúng) — không có failure mode để phân tích._

---

## 6. Extensions được triển khai

| Extension | Mô tả |
|---|---|
| `structured_evaluator` | Evaluator parse Pydantic `JudgeResult` từ JSON response (response_format=json_object) thay vì regex |
| `reflection_memory` | Mỗi entry gồm `failure_reason`, `lesson`, `next_strategy`; truyền vào Actor ở lần thử sau |
| `benchmark_report_json` | `report.json` đầy đủ 6 key theo schema yêu cầu |
| `mock_mode_for_autograding` | Giữ song song mock runtime + switch `--mode mock/llm` để autograde chạy offline, miễn phí |

---

## 7. Discussion

Trên bộ 20 mẫu này, cả ReAct và Reflexion đều đạt EM **100.00%** — baseline đã giải đúng gần hết nên Reflexion không có chỗ để cải thiện thêm; cơ chế phản chiếu chỉ tốn thêm **+8%** token và **-18%** latency (kích hoạt ở số ít mẫu). Toàn bộ benchmark tốn **$0.0055** với gpt-4o-mini-2024-07-18.

**Reflection memory có hữu ích không?** Có. Trong 1 mẫu sai ở lần đầu, reflection cứu được 1 mẫu (recovery rate **100%**). Reflection hiệu quả nhất khi lỗi nằm ở suy luận (thiếu hop, chọn nhầm đoạn distractor): reflector chỉ ra hop còn thiếu để actor hoàn thành ở lần sau. Nó ít hữu ích khi đáp án vốn không có trong context — 0 mẫu còn lại không cứu được, thử thêm chỉ tốn chi phí.

**Failure modes:** cả hai agent không mắc lỗi nào trên bộ này (100% đúng). Lưu ý EM do **LLM-as-judge** (evaluator) chấm — độ khắt khe của judge ảnh hưởng trực tiếp tới con số của cả hai agent.

**Hướng cải tiến tiếp theo:** (1) `adaptive_max_attempts` — dừng sớm nếu reflection notes không đổi giữa các lần; (2) evidence-grounded evaluator — đối chiếu trực tiếp câu trả lời với context thay vì chỉ so khớp ngữ nghĩa; (3) `memory_compression` — tóm tắt reflection history khi vượt quá vài entry để tránh prompt quá dài.
