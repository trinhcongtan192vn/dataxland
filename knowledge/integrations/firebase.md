# Firebase Authentication

Cổng đăng nhập bằng Firebase Auth (email + mật khẩu có xác minh email, và Google). API xác minh ID token bằng `firebase-admin` (spec 05 §3.1).

## 1. Tạo project

1. **console.firebase.google.com → Add project**, dùng chính GCP project của môi trường (`GCP_PROJECT_ID`) để dùng chung service account.
2. **Authentication → Sign-in method**: bật **Email/Password** và **Google**.
3. **Authentication → Settings → Authorized domains**: thêm tên miền của cổng (ví dụ `app.dataxland.vn`).
4. **Templates → Email address verification**: đổi ngôn ngữ sang tiếng Việt.

## 2. Cấu hình web (cổng)

**Project settings → General → Your apps → Add app → Web**. Firebase hiện đoạn `firebaseConfig`; chép vào biến của web:

| Trường | Biến |
|---|---|
| `apiKey` | `NEXT_PUBLIC_FIREBASE_API_KEY` |
| `authDomain` | `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` |
| `projectId` | `NEXT_PUBLIC_FIREBASE_PROJECT_ID` |

Các giá trị này công khai theo thiết kế của Firebase, không phải bí mật.

## 3. Cấu hình API

- `FIREBASE_PROJECT_ID`: project ID ở trên.
- Trên GCP, service account của API cần vai trò **Firebase Authentication Admin** (để đặt custom claims và thu hồi phiên).
- Ở `local` dùng emulator: `FIREBASE_AUTH_EMULATOR_HOST=localhost:9099`, không cần khóa.

## 4. Kiểm tra

Đăng nhập cổng bằng tài khoản Google của bạn; `GET /v1/me` trả thông tin người dùng.
