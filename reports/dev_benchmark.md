# Lab 16 — Reflexion Agent: Benchmark Report

**Dataset:** HotpotQA Dev (Distractor) — 120 mẫu (lấy 120 câu đầu, deterministic)  
**Model:** gpt-4o-mini-2024-07-18  
**Date:** 2026-06-18  
**Student:** Võ Huyền Khánh Mây — 2A202600858

---

## 1. Bảng so sánh tổng quan: ReAct vs Reflexion Agent

| Tiêu chí | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| Số mẫu | 120 | 120 | — |
| Câu đúng | 89 | 114 | +25 |
| Câu sai | 31 | 6 | -25 |
| **Exact Match (EM)** | **74.17%** | **95.00%** | **+20.83pp** |
| Avg. số lần thử / mẫu | 1.000 | 1.325 | +0.325 |
| Avg. token / mẫu | 2,007 | 2,822 | +815 (+41%) |
| Avg. latency / mẫu (ms) | 2,439 | 3,664 | +1,225 (+50%) |
| Max attempts | 1 | 3 | — |

**Ghi chú:**  
- ReAct chỉ có 1 lần thử duy nhất per sample; không có bước phản chiếu (reflection).  
- Reflexion dùng tối đa 3 lần thử: trong 30 mẫu sai ở lần 1, 24 mẫu đã tự sửa thành công (tỷ lệ phục hồi **80%**).  
- 6 mẫu vẫn sai sau khi hết số lần thử — phần lớn do context không chứa đủ thông tin để phán đoán.

---

## 2. Bảng so sánh EM / Accuracy

### 2a. Kết quả tổng thể

| Agent | Tổng mẫu | Đúng | Sai | EM (%) | Accuracy (%) |
|---|---:|---:|---:|---:|---:|
| ReAct | 120 | 89 | 31 | 74.17 | 74.17 |
| Reflexion | 120 | 114 | 6 | 95.00 | 95.00 |

> EM và Accuracy bằng nhau vì đây là bài toán QA — không có partial credit.

### 2b. Phân tích theo failure mode

| Failure Mode | ReAct (count) | Reflexion (count) | Reflexion cải thiện? |
|---|---:|---:|---|
| Không lỗi (correct) | 89 | 114 | +25 mẫu được phục hồi |
| incomplete_multi_hop | 17 | 2 | giảm (17 → 2) |
| wrong_final_answer | 10 | 3 | giảm (10 → 3) |
| entity_drift | 4 | 1 | giảm (4 → 1) |

### 2c. Phân tích theo số lần thử (Reflexion)

| Số lần thử | Số mẫu | Đúng | Sai | EM (%) |
|---:|---:|---:|---:|---:|
| 1 | 90 | 90 | 0 | 100.00 |
| 2 | 21 | 21 | 0 | 100.00 |
| 3 | 9 | 3 | 6 | 33.33 |
| **Tổng** | **120** | **114** | **6** | **95.00** |

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
| ReAct | 1,959 | 48 | 2,007 | $0.000323 |
| Reflexion | 2,729 | 93 | 2,822 | $0.000465 |
| Delta | +770 | +45 | +815 | +$0.000143 |

### 3b. Chi phí toàn bộ benchmark (120 mẫu)

| Agent | Tổng token | Chi phí (USD) | Running time (đo thực tế) |
|---|---:|---:|---|
| ReAct | 240,862 | **$0.0387** | ~4.9 phút |
| Reflexion | 338,681 | **$0.0559** | ~7.3 phút |
| **Tổng benchmark** | **579,543** | **$0.0946** | **~12.2 phút** |

> Running time = tổng latency đo được (chạy tuần tự, không thêm delay nhân tạo).

### 3c. Ước tính chi phí theo scale

| Quy mô | ReAct cost | Reflexion cost | Chênh lệch |
|---|---:|---:|---:|
| 120 mẫu (lab) | $0.0387 | $0.0559 | $0.0171 |
| 1,000 mẫu | $0.3228 | $0.4654 | $0.1426 |
| 10,000 mẫu | $3.2283 | $4.6542 | $1.4259 |
| 100,000 mẫu | $32.2831 | $46.5423 | $14.2591 |

> Với gpt-4o-mini-2024-07-18, để có thêm 25 câu đúng trên 120 mẫu, Reflexion chỉ tốn thêm ~$0.0171. Chi phí ở quy mô thực tế rất thấp so với mức tăng EM +20.83pp.

---

## 4. Phân tích Retry — Reflexion Agent

### 4a. Phân bố số lần thử

| Số lần thử | Số mẫu | Đúng | Sai | EM (%) |
|---:|---:|---:|---:|---:|
| 1 | 90 | 90 | 0 | 100.00 |
| 2 | 21 | 21 | 0 | 100.00 |
| 3 | 9 | 3 | 6 | 33.33 |
| **Tổng** | **120** | **114** | **6** | **95.00** |

**Nhận xét:**
- 90/120 mẫu (75%) đúng ngay lần đầu — reflection không cần thiết với câu hỏi rõ ràng.
- 24/30 mẫu sai lần 1 được reflection cứu lại → recovery rate **80%**.
- 6 mẫu vẫn sai sau 3 lần thử: nhóm khó nhất, context thường không đủ thông tin để sửa.

### 4b. Chi tiết 30 mẫu có retry (attempts ≥ 2)

| qid (rút gọn) | Attempts | Đúng? | Gold answer | Predicted |
|---|---:|---|---|---|
| 5a8e3ea9… | 3 | False | Greenwich Village, New York City | Greenwich Village |
| 5a722b86… | 3 | False | Barton Lee Hazlewood | Lee Hazlewood, Jim Shoulders |
| 5ae03611… | 3 | False | Charles Eugène | Charles Nungesser |
| 5add61d6… | 3 | False | Organizations could come together to addr… | peace forum |
| 5ac2acff… | 3 | False | Bill Murray | Nick Lachey |
| 5a713ea9… | 3 | False | Apalachees | Ais |
| 5a7bbb64… | 3 | True | Terry Richardson | Terry Richardson |
| 5a7be259… | 3 | True | Adeline Virginia Woolf | Adeline Virginia Woolf |
| 5ae53b54… | 3 | True | Las Vegas Strip in Paradise | Las Vegas Strip in Paradise |
| 5a8c7595… | 2 | True | Chief of Protocol | Chief of Protocol |
| 5ab56e32… | 2 | True | no | no |
| 5ae6050f… | 2 | True | Sonic | Sonic |
| 5adddccd… | 2 | True | keyboard function keys | keyboard function keys |
| 5ae4a326… | 2 | True | Fujioka, Gunma | Fujioka, Gunma |
| 5a7d5416… | 2 | True | Yellowcraig | Yellowcraigs |
| 5ae32e12… | 2 | True | 35,124 | 35,124 |
| 5adc53f7… | 2 | True | no | no |
| 5a8b2033… | 2 | True | shortest player ever to play in the Natio… | shortest player in NBA history |
| 5a8f4c8d… | 2 | True | more than 70 countries | more than 70 |
| 5ae5aba0… | 2 | True | Teen Titans Go! | Teen Titans Go! |
| 5ae1f4cb… | 2 | True | 276,170 inhabitants | 276170 |
| 5a886589… | 2 | True | Conscription | conscription |
| 5a7759fc… | 2 | True | Canary Islands, Spain | Canary Islands, Spain (Tenerife and La Go… |
| 5a835478… | 2 | True | 250 million | 250 million |
| 5ae2b770… | 2 | True | March and April | March and April |
| 5adccd79… | 2 | True | Beijing | Beijing |
| 5ac32b56… | 2 | True | North Avenue at Techwood Drive | North Avenue at Techwood Drive |
| 5a8b8b31… | 2 | True | business | business |
| 5ae63dad… | 2 | True | 7 January 1936 | 7 January 1936 |
| 5a879adb… | 2 | True | United States Senator | U.S. Senator |

### 4c. Tổng kết khả năng phục hồi

| Nhóm | Số mẫu | Tỷ lệ |
|---|---:|---:|
| Tổng mẫu có retry (≥2 lần) | 30 | 25.0% tổng dataset |
| Phục hồi thành công | 24 | 80.0% của nhóm retry |
| Vẫn sai sau max attempts | 6 | 20.0% của nhóm retry |

---

## 5. Phân tích Failure Modes

### Failure Mode 1: `incomplete_multi_hop`

**Mô tả:** Agent trả lời sau hop 1 mà không hoàn thành chuỗi reasoning multi-hop.  
**Ví dụ:** `qid=5a8c7595…` — Gold: "Chief of Protocol", Predicted: "diplomat"  
**ReAct:** 17 mẫu | **Reflexion:** 2 mẫu  

### Failure Mode 2: `wrong_final_answer`

**Mô tả:** Agent chọn đáp án sai ở bước cuối cùng — thường do nhầm entity ở hop thứ 2.  
**Ví dụ:** `qid=5a7bbb64…` — Gold: "Terry Richardson", Predicted: "Annie Morton"  
**ReAct:** 10 mẫu | **Reflexion:** 3 mẫu  

### Failure Mode 3: `entity_drift`

**Mô tả:** Agent trôi sang một entity khác trong context (thường là đoạn distractor).  
**Ví dụ:** `qid=5a722b86…` — Gold: "Barton Lee Hazlewood", Predicted: "Lee Hazlewood, Jim Shoulders"  
**ReAct:** 4 mẫu | **Reflexion:** 1 mẫu  

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

Reflexion cải thiện EM từ **74.17% → 95.00%** (**+20.83pp**, tương đối **+28.1%**, cắt giảm **80.6%** số lỗi) so với ReAct baseline trên 120 mẫu HotpotQA, với chi phí token tăng **+41%** và latency tăng **+50%**. Toàn bộ benchmark chỉ tốn **$0.0946** với gpt-4o-mini-2024-07-18 — trade-off rất đáng giá.

**Reflection memory có hữu ích không?** Có. Trong 30 mẫu sai ở lần đầu, reflection cứu được 24 mẫu (recovery rate **80%**). Reflection hiệu quả nhất khi lỗi nằm ở suy luận (thiếu hop, chọn nhầm đoạn distractor): reflector chỉ ra hop còn thiếu để actor hoàn thành ở lần sau. Nó ít hữu ích khi đáp án vốn không có trong context — 6 mẫu còn lại không cứu được, thử thêm chỉ tốn chi phí.

**Failure mode phổ biến nhất** là `incomplete_multi_hop`. Reflexion giảm rõ rệt các lỗi suy luận nhưng vẫn còn sót lại ở nhóm câu khó nhất (cần ≥3 hop hoặc context thiếu bằng chứng trực tiếp). Một giới hạn cần lưu ý: toàn bộ EM ở đây do **LLM-as-judge** (evaluator) chấm, nên độ khắt khe của judge ảnh hưởng trực tiếp tới con số của cả hai agent.

**Hướng cải tiến tiếp theo:** (1) `adaptive_max_attempts` — dừng sớm nếu reflection notes không đổi giữa các lần; (2) evidence-grounded evaluator — đối chiếu trực tiếp câu trả lời với context thay vì chỉ so khớp ngữ nghĩa; (3) `memory_compression` — tóm tắt reflection history khi vượt quá vài entry để tránh prompt quá dài.
