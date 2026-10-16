# Email (SMTP)

Email dùng cho báo cáo tuần, lời mời, cảnh báo gửi team (spec 04 §5).

## Chọn nhà cung cấp

Bất kỳ dịch vụ SMTP nào có STARTTLS cổng 587: Google Workspace (smtp-relay.gmail.com), Amazon SES, Mailgun, SendGrid, Brevo.

## Các bước (ví dụ Amazon SES, vùng `ap-southeast-1`)

1. **Verified identities → Create identity → Domain**: nhập tên miền gửi (ví dụ `dataxland.vn`), thêm các bản ghi DKIM vào DNS.
2. Thêm SPF `include:amazonses.com` và DMARC cho tên miền.
3. **Account dashboard → Request production access** để gửi cho người nhận chưa xác minh.
4. **SMTP settings → Create SMTP credentials** → lấy **SMTP username**, **SMTP password**.

## Biến môi trường

| Biến | Ví dụ |
|---|---|
| `SMTP_HOST` | `email-smtp.ap-southeast-1.amazonaws.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password (dev/prod: nạp từ Secret Manager vào biến môi trường của service) |
| `EMAIL_FROM` | `DataxLand <no-reply@dataxland.vn>` |
| `DX_TEAM_EMAIL` | Hộp thư nhận cảnh báo của team |

Ở `local`, `make up` bật **Mailpit**: `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, xem thư ở `http://localhost:8025`.

## Kiểm tra

Mời một thành viên thử trên cổng; thư mời đến hộp thư trong vài giây, không vào thư rác.
