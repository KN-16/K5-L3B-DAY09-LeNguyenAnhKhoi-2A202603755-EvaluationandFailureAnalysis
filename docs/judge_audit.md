# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7) ?  | Quyết định |
|---|---:|---:|---:|---:|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Có | dùng có giám sát; không dùng cho tiền/approval |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không (κ và recall thấp) | loại khỏi gate |

### Audit thủ công các bất đồng

| # | Case | Judge nói | Người nói | Ai đúng? | Hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 | PASS | FAIL | Người | Nêu rõ đại từ và yêu cầu kiểm tra; “em/anh… check giúp em” quá thân mật. |
| 2 | H-017 | PASS | FAIL | Người | Thêm ví dụ biên âm tính cho “bạn ơi… nha”. |
| 3 | H-029 | PASS | FAIL | Người | Thêm tiêu chí không xua đuổi khách bằng câu “không cần nhắn thêm”. |
| 4 | H-042 | FAIL | PASS | Người | Cho phép câu ngắn nếu vẫn đủ xác nhận, số tiền và ETA. |
| 5 | H-051 | FAIL | PASS | Người | Không tự động phạt thuật ngữ song ngữ phổ biến như “refund”. |
| 6 | H-063 | PASS | FAIL | Người | Không cho phép hứa hành động/tài chính chưa được host xác nhận. |

### Kết luận của bài làm

- `tone_ok` đạt floors với `tp=24, fp=4, fn=6, tn=66`; chỉ dùng như tín hiệu chất lượng ngôn ngữ.
- `helpful` bị loại với `tp=9, fp=0, fn=21, tn=70`; 21/30 lỗi bị bỏ sót làm recall chỉ 0.300.
- Judge chỉ là replay công khai; cần nhãn người mới và held-out riêng trước khi dùng ngoài lab.
