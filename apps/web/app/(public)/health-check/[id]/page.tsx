"use client";

// Trang kết quả công khai (spec 07 §6.1): không cần đăng nhập, chỉ hiển thị từ `result` đã duyệt, có lời mời tư vấn,
// ngày xóa dữ liệu và ô đồng ý chuyển dữ liệu sang dịch vụ chính thức (spec 07 §8).
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { HcResultView } from "@/components/hc-result";
import { ErrorBox, Spinner } from "@/components/ui";
import { API_URL, ApiError, errorMessage } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

type Pub = {
  check_id: string;
  shop_name: string | null;
  result: Record<string, unknown> | null;
  reviewer_notes_md: string | null;
  expires_at: string;
  consent_convert_at: string | null;
};

function Result() {
  const { id } = useParams<{ id: string }>();
  const k = useSearchParams().get("k") ?? "";
  const [converted, setConverted] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["hc-result", id, k],
    queryFn: async () => {
      const r = await fetch(`${API_URL}/v1/health-checks/${id}/result?k=${encodeURIComponent(k)}`);
      const body = await r.json();
      if (!r.ok) throw new ApiError(r.status, body.code, body.detail);
      return body as Pub;
    },
    retry: false,
  });
  const consent = useMutation({
    mutationFn: async () => {
      const r = await fetch(`${API_URL}/v1/health-checks/${id}/consent-convert?k=${encodeURIComponent(k)}`, {
        method: "POST",
      });
      const body = await r.json();
      if (!r.ok) throw new ApiError(r.status, body.code, body.detail);
      return body as { consent_convert_at: string };
    },
    onSuccess: (d) => setConverted(d.consent_convert_at),
  });
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <ErrorBox error={q.error ?? new Error("Không tìm thấy kết quả")} />;
  const d = q.data;
  const agreed = converted ?? d.consent_convert_at;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">
        Kết quả kiểm tra sức khỏe dữ liệu{d.shop_name ? ` – ${d.shop_name}` : ""}
      </h1>
      {d.result && <HcResultView result={d.result} notes={d.reviewer_notes_md} />}
      <div className="card space-y-3">
        <h2 className="font-semibold">Muốn có số này mỗi tuần?</h2>
        <p className="text-sm text-slate-600">
          DataxLand kết nối trực tiếp với sàn và tài khoản quảng cáo, gửi báo cáo một trang mỗi tuần kèm nhận
          định. Đặt lịch tư vấn miễn phí 30 phút với đội ngũ của chúng tôi.
        </p>
        <a
          className="btn-primary"
          href="mailto:hello@dataxland.vn?subject=Đặt lịch tư vấn sau kiểm tra sức khỏe dữ liệu"
        >
          Đặt lịch tư vấn
        </a>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            disabled={!!agreed || consent.isPending}
            checked={!!agreed}
            onChange={() => consent.mutate()}
          />
          <span>
            Tôi đồng ý chuyển dữ liệu đã tải lên sang dịch vụ chính thức khi trở thành khách hàng (để có thêm
            lịch sử), thay vì xóa sau 14 ngày.
          </span>
        </label>
        {consent.error && <p className="text-sm text-red-700">{errorMessage(consent.error)}</p>}
      </div>
      <p className="text-xs text-slate-500">
        {agreed
          ? "Bạn đã đồng ý chuyển dữ liệu sang dịch vụ chính thức."
          : `Dữ liệu của bạn sẽ tự xóa vào ngày ${formatDate(d.expires_at.slice(0, 10))}.`}
      </p>
    </div>
  );
}

export default function HcResultPage() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <Suspense fallback={<Spinner />}>
        <Result />
      </Suspense>
    </main>
  );
}
