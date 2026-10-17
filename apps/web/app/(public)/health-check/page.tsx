"use client";

// Trang công khai kiểm tra sức khỏe dữ liệu (spec 07 §2, FR-HC-01): email, tên shop, file và loại file, đồng ý.
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { ErrorBox, Spinner } from "@/components/ui";
import { API_URL, ApiError, errorMessage } from "@/lib/api/client";
import { HC_GUIDES } from "@/lib/hc-guides";

type ConsentInfo = {
  version: string;
  text_md: string;
  kinds: Record<string, string>;
  max_files: number;
  max_mb: number;
  retention_days: number;
};
type Picked = { file: File; kind: string };

export default function HealthCheckPage() {
  const startedAt = useRef(Date.now());
  const info = useQuery({
    queryKey: ["hc-consent"],
    queryFn: async () => (await (await fetch(`${API_URL}/v1/health-checks/consent`)).json()) as ConsentInfo,
  });
  const [email, setEmail] = useState("");
  const [shop, setShop] = useState("");
  const [website, setWebsite] = useState("");
  const [agree, setAgree] = useState(false);
  const [files, setFiles] = useState<Picked[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<{ expires_at: string } | null>(null);
  const [guide, setGuide] = useState<string | null>(null);

  if (info.isLoading) return <Spinner />;
  if (info.error || !info.data) return <ErrorBox error={info.error ?? new Error("Không tải được trang")} />;
  const c = info.data;
  const maxBytes = c.max_mb * 1024 * 1024;

  const add = (list: FileList | null) => {
    if (!list) return;
    const next = [...files];
    for (const f of Array.from(list)) {
      if (!/\.(xlsx|csv)$/i.test(f.name)) {
        setErr(`${f.name}: chỉ nhận file .xlsx hoặc .csv`);
        continue;
      }
      if (f.size > maxBytes) {
        setErr(`${f.name}: vượt ${c.max_mb} MB`);
        continue;
      }
      if (next.length >= c.max_files) {
        setErr(`Tối đa ${c.max_files} file`);
        break;
      }
      next.push({ file: f, kind: "" });
    }
    setFiles(next);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (files.some((f) => !f.kind)) return setErr("Chọn loại cho từng file");
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("email", email);
      if (shop) fd.append("shop_name", shop);
      fd.append("consent_version", c.version);
      fd.append("started_at", String(startedAt.current));
      if (website) fd.append("website", website);
      for (const f of files) {
        fd.append("files", f.file);
        fd.append("kinds", f.kind);
      }
      const r = await fetch(`${API_URL}/v1/health-checks`, { method: "POST", body: fd });
      const body = await r.json();
      if (!r.ok) throw new ApiError(r.status, body.code ?? "ERROR", body.detail ?? "Không gửi được");
      setDone(body);
    } catch (e2) {
      setErr(errorMessage(e2));
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <main className="mx-auto max-w-xl px-6 py-16">
        <h1 className="mb-3 text-2xl font-semibold">Đã nhận file</h1>
        <p className="text-slate-700">
          Kiểm tra email để xác nhận. Kết quả sẽ được gửi trong 1–2 ngày làm việc.
        </p>
        <p className="mt-3 text-sm text-slate-500">
          Dữ liệu sẽ tự xóa vào ngày {new Date(done.expires_at).toLocaleDateString("vi-VN")} (
          {c.retention_days} ngày sau khi tải lên).
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="mb-2 text-2xl font-semibold">Kiểm tra sức khỏe dữ liệu miễn phí</h1>
      <p className="mb-6 text-slate-600">
        Tải file xuất từ Shopee, TikTok Shop, Lazada và tài khoản quảng cáo. DataxLand tính phí ăn vào lãi,
        SKU lỗ sau phí, hoàn hàng và chênh lệch số liệu giữa các nguồn, rồi gửi kết quả cho bạn.
      </p>
      <form onSubmit={submit} className="card space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="label">Email nhận kết quả *</span>
            <input
              className="input"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="label">Tên shop</span>
            <input className="input" value={shop} onChange={(e) => setShop(e.target.value)} maxLength={120} />
          </label>
        </div>
        <label className="hidden" aria-hidden="true">
          Website
          <input
            tabIndex={-1}
            autoComplete="off"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
          />
        </label>

        <div>
          <span className="label">
            File (tối đa {c.max_files} file, mỗi file ≤ {c.max_mb} MB, .xlsx hoặc .csv)
          </span>
          <input
            type="file"
            multiple
            accept=".xlsx,.csv"
            className="block text-sm"
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
          {files.length > 0 && (
            <table className="table mt-3">
              <tbody>
                {files.map((f, i) => (
                  <tr key={`${f.file.name}-${i}`}>
                    <td className="text-sm">
                      {f.file.name}{" "}
                      <span className="text-xs text-slate-400">
                        ({(f.file.size / 1024 / 1024).toFixed(1)} MB)
                      </span>
                    </td>
                    <td>
                      <select
                        className="input"
                        required
                        value={f.kind}
                        onChange={(e) =>
                          setFiles(files.map((x, j) => (j === i ? { ...x, kind: e.target.value } : x)))
                        }
                      >
                        <option value="">Chọn loại file…</option>
                        {Object.entries(c.kinds).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="text-xs text-red-600"
                        onClick={() => setFiles(files.filter((_, j) => j !== i))}
                      >
                        Bỏ
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <details className="rounded-lg border border-slate-200 p-3 text-sm">
          <summary className="cursor-pointer font-medium">Xuất các file này ở đâu?</summary>
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(HC_GUIDES).map(([k, g]) => (
              <button
                key={k}
                type="button"
                onClick={() => setGuide(guide === k ? null : k)}
                className={`rounded-full border px-3 py-1 ${guide === k ? "border-brand-600 bg-brand-50" : "border-slate-300"}`}
              >
                {g.title}
              </button>
            ))}
          </div>
          {guide && (
            <div className="mt-3">
              <ol className="list-decimal space-y-1 pl-5">
                {HC_GUIDES[guide]?.steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
              {HC_GUIDES[guide]?.note && <p className="mt-2 text-slate-500">{HC_GUIDES[guide]?.note}</p>}
              {guide === "product_costs" && (
                <a className="btn-secondary mt-2" href="/hc-guides/gia-von-mau.xlsx" download>
                  Tải file mẫu giá vốn
                </a>
              )}
            </div>
          )}
        </details>

        <div className="rounded-lg bg-slate-50 p-3 text-sm">
          <div className="prose-dx">
            <ReactMarkdown>{c.text_md}</ReactMarkdown>
          </div>
          <label className="mt-2 flex items-start gap-2">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} required />
            <span>Tôi đã đọc và đồng ý với các điều kiện trên.</span>
          </label>
        </div>

        {err && (
          <p className="text-sm text-red-700" role="alert">
            {err}
          </p>
        )}
        <button type="submit" className="btn-primary" disabled={busy || !agree || files.length === 0}>
          {busy ? "Đang tải lên…" : "Gửi file"}
        </button>
      </form>
    </main>
  );
}
