// Link "Xem báo cáo" trong email và Telegram (spec 06 §4.6, FR-REP-06): API ghi nhận mở (không cần đăng nhập)
// rồi trả chuyển hướng tới báo cáo trên cổng; trang báo cáo vẫn yêu cầu đăng nhập.
import { NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: Request, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const fallback = new URL("/report-link-invalid", request.url);
  if (!/^[\w-]{16,128}$/.test(token)) return NextResponse.redirect(fallback);
  try {
    const r = await fetch(`${API}/r/${encodeURIComponent(token)}`, { redirect: "manual", cache: "no-store" });
    const loc = r.headers.get("location");
    if (loc) {
      const target = new URL(loc);
      return NextResponse.redirect(new URL(`${target.pathname}${target.search}`, request.url));
    }
  } catch {
    // API không trả lời: vẫn đưa người dùng tới trang chung
  }
  return NextResponse.redirect(fallback);
}
