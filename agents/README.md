# agents – agent nội bộ (spec 09 §8)

Mỗi agent là một skill Claude Code trong `agents/<tên>/SKILL.md`. Agent chỉ đọc mặc định; mọi thay đổi đi qua PR hoặc
bản nháp có người duyệt.

| Agent | Kích hoạt | Nơi chạy | Đầu ra |
|---|---|---|---|
| [weekly-insight](weekly-insight/SKILL.md) | Báo cáo tuần vừa dựng | Worker của API (`app/ask/agents.py`) | Bản nháp nhận định, việc cần làm |
| [incident-triage](incident-triage/SKILL.md) | Lần chạy lỗi hoặc bị chặn | Worker của API (`app/ask/agents.py`) | `pipeline_runs.triage_md` |
| [new-adapter](new-adapter/SKILL.md) | Engineer chạy tay | Claude Code | PR connector mới |
| [review-change](review-change/SKILL.md) | Mỗi PR | GitHub Action `review-change.yml` | Bình luận trên PR |
| [onboarding-draft](onboarding-draft/SKILL.md) | Data lead chạy tay | Claude Code | PR `tenants/<id>.yml` |

Chạy agent tay trong Claude Code: mở repo rồi nhắc "dùng agents/new-adapter" (hoặc tên agent khác).
