"use client";

// Xác nhận email của lượt kiểm tra sức khỏe (spec 07 §1): gọi API, API phát `healthcheck.submitted`.
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ErrorBox, Spinner } from "@/components/ui";
import { API_URL, ApiError } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

function Verify() {
  const token = useSearchParams().get("token") ?? "";
  const q = useQuery({
    queryKey: ["hc-verify", token],
    queryFn: async () => {
      const r = await fetch(`${API_URL}/v1/health-checks/verify?token=${encodeURIComponent(token)}`);
      const body = await r.json();
      if (!r.ok) throw new ApiError(r.status, body.code, body.detail);
      return body as { check_id: string; status: string; expires_at: string };
    },
    enabled: !!token,
    retry: false,
  });
  if (q.isLoading) return <Spinner label="Đang xác nhận…" />;
  if (q.error || !q.data) return <ErrorBox error={q.error ?? new Error("Thiếu mã xác nhận")} />;
  return (
    <div>
      <h1 className="mb-3 text-2xl font-semibold">Đã xác nhận email</h1>
      <p className="text-slate-700">
        DataxLand đang xử lý file của bạn. Kết quả sẽ được gửi qua email trong 1–2 ngày làm việc.
      </p>
      <p className="mt-3 text-sm text-slate-500">
        Dữ liệu sẽ tự xóa lúc {formatDateTime(q.data.expires_at)}.
      </p>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <main className="mx-auto max-w-xl px-6 py-16">
      <Suspense fallback={<Spinner />}>
        <Verify />
      </Suspense>
    </main>
  );
}
