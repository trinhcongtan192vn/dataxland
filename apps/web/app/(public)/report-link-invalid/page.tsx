import Link from "next/link";

export default function ReportLinkInvalid() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-6">
      <h1 className="text-xl font-semibold">Link không còn dùng được</h1>
      <p className="text-sm text-slate-600">
        Link báo cáo không đúng hoặc đã được thay. Đăng nhập cổng để xem các báo cáo tuần của bạn.
      </p>
      <Link className="btn-primary" href="/app">
        Mở cổng DataxLand
      </Link>
    </main>
  );
}
