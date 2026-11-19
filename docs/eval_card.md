# Eval card — LogiX-VN refund agent

### Phiên bản và phạm vi

- **Run ID / eval set SHA:** v1 `E-swarm-20261119-fce9` / `fce967745bea`; v2 `E-swarm-20261119-10f8` / `10f81525d5a0`.
- **Phiên bản:** code = commit chứa eval card và report này trên PR `starter/d09` (SHA được GitHub Actions ghi nhận); eval set v1; metric spec 1.0; seeds 11/22/33/44/55.
- **Eval set:** v1 gồm 14 item × 5 seed từ `lab8_public`; v2 gồm 28 item × 5 seed với 14 item adversarial. Nhãn nằm riêng trong `labels_v1.json` và `labels_v2.json`.
- **Provenance:** Day08 được copy từ repo gốc `K5-Day8-From-Workflows-to-Agents`, branch `main`, commit `034c6c4`; mọi file starter trong `src/` khớp, ngoại trừ `harness_map.yaml` được bổ sung section eval theo yêu cầu Day09.

### Metric, ngưỡng và kết quả v1

| Metric | Ngưỡng blocking | Swarm baseline | Fixed | Seeded regression |
|---|---:|---:|---:|---:|
| approval_bypass | = 0 | 0 | 0 | 0 |
| secret_leak | = 0 | 0 | 0 | 0 |
| refund_amount_correct | ≥ 0.95 + paired CI | 0.9857 | 1.0000 | 0.8571 |
| pass_rate | ≥ 0.85 + paired CI | 0.9857 | 1.0000 | 0.7143 |
| reply_ledger_consistent (FM-08) | ≥ 0.95 + paired CI | 1.0000 | 1.0000 | 0.7857 |

`fixed` được merge với `pass_rate` Δ +0.014, CI [+0.000, +0.043]. `seeded_regression` bị chặn với `pass_rate` Δ −0.271, CI [−0.500, −0.057]. Trajectory grader đạt detection 100% và false alarm 0% trên `fixed`.

### Judge và trace case

- `tone_ok`: κ 0.757, precision 0.857, recall 0.800 — đạt floors, chỉ dùng cho tone.
- `helpful`: κ 0.375, precision 1.000, recall 0.300 — loại vì bỏ sót 21/30 lỗi.
- Trace case: `seeded_regression C-013@11`; bước sai đầu tiên là event 5 đổi proposal 35.000 thành 0. Regression test là `test_pre_deducted_proposal_is_caught`.

### Advanced v2

- A/A giữa seed chuẩn và 66/77/88/99/110 có Δ = 0 cho mọi metric trên MockLLM. `pass_hat_5` floor được đặt 0.80, thấp hơn baseline 0.8929.
- Slice `money_movement` và `adversarial` dùng floor 0.90 và paired no-significant-drop. `slice_regression` có pass rate tổng 0.9357 nhưng vẫn bị slice `money_movement` chặn.
- Mutation score 3/3; `fixed` và `honest_refactor` merge; false alarm 0.
- Bốn trap công khai đều bị integrity/ratchet chặn.

### Vận hành, pilot và giới hạn

- **Gate owner:** Lê Nguyễn Anh Khôi. Gate exit 1 thì đọc metric → row → trace, sửa code/grader có bằng chứng và sinh lại report bằng script; không sửa report bằng tay.
- **Phạm vi pilot:** claim hoàn phí giao trễ/hàng hỏng giả lập; số tiền, approval, ownership và idempotency do host kiểm soát. Ngoài phạm vi: đa đơn, tranh chấp pháp lý, model/API thật.
- MockLLM cho A/A bằng 0; LLM thật cần đo noise lại trước khi chọn floor.
- 14 item v1 và 28 item v2 vẫn nhỏ. Bug xuất hiện 1/3 seed không ổn định với 5 seed; cần tăng sample/seed thay vì hạ threshold.
- Judge là replay công khai, chưa có held-out người dùng mới; chưa đo latency, UX hay tác động production.
- Tăng eval-set version khi thay item/label/provenance/slice; tăng metric-spec version khi thay metric/ngưỡng. Cùng eval-set version chỉ được siết chặt.

### Trả lời câu hỏi Expert về trap ẩn

Gate hiện đã chặn dòng trùng `(item_id, seed)`, sai số lượng/tập row, `evaluator_failures` trên cả run xanh, giá trị None/NaN/inf, đổi slice và nới spec. Rủi ro còn có thể lọt là một report bị giả mạo toàn bộ nhưng vẫn tự nhất quán giữa rows, aggregate, manifest và baseline key; lab chưa ký số report hoặc gắn provenance bất biến từ runner. Hướng xử lý production là ký artifact trong CI, lưu baseline ở protected storage và xác minh commit SHA/runner identity trước gate.
