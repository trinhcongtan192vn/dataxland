import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-6 px-6">
      <h1 className="text-3xl font-semibold">DataxLand</h1>
      <p className="text-slate-600">
        Số liệu đã chuẩn hóa từ mọi kênh bán và quảng cáo, báo cáo một trang mỗi tuần, dashboard và sổ tay chỉ
        số.
      </p>
      <div className="flex flex-wrap gap-3">
        <Link className="btn-primary" href="/login">
          Đăng nhập
        </Link>
        <Link className="btn-secondary" href="/health-check">
          Kiểm tra sức khỏe dữ liệu miễn phí
        </Link>
      </div>
    </main>
  );
}
