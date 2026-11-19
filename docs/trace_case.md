# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case `C-013@11`

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-013@11`, report `E-seeded_regression-20261118-fce9` |
| Triệu chứng | `TrialPass` fail với `proposal_mismatch`: ledger 0 và status denied đều đúng, nhưng proposal bị đổi từ 35.000 xuống 0 trước host. |
| Bước sai đầu tiên | Event 5 `proposal {"amount_vnd": 0}`. |
| Vì sao là bước *đầu tiên* | Event 2 đọc đúng O-505; event 3 quote đúng 35.000; event 4 chỉ đọc lịch sử refund 35.000. Sai xuất hiện khi lịch sử bị trừ vào proposal ở event 5. |
| Failure mode | FM-05 `pre_deducted`. |
| Đối chứng | `fixed C-013@11` giữ quote 35.000, không có event `proposal`; host tự xét lịch sử và trả denied. Trial đối chứng PASS. |
| Regression test | `test_pre_deducted_proposal_is_caught` dùng `ProposalAmountCorrect`: fail với proposal 0/label 35.000; report `fixed` đạt 1.0 và `seeded_regression` chỉ 0.7857. |
| Chưa chắc chắn | Trace chứng minh phép trừ sai, nhưng không chứng minh nguyên nhân nội tại của model; causal attribution chỉ đến bước orchestration tạo proposal. |
