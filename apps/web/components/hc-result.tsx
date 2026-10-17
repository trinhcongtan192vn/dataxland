"use client";

// Kết quả kiểm tra sức khỏe (spec 07 §6): hiển thị từ `result`, không tính lại.
import ReactMarkdown from "react-markdown";
import { Value } from "@/components/money";
import { Badge } from "@/components/ui";
import { formatDate, formatPercent, formatVnd } from "@/lib/format";
import { platformLabel } from "@/lib/metrics";

type Row = Record<string, unknown>;
type Result = Record<string, unknown> & {
  metrics?: Record<string, { name_vi: string; version: string; unit: string }>;
};

function n(r: Result, m: string): string {
  return r.metrics?.[m]?.name_vi ?? m;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-slate-100 pt-4">
      <h2 className="mb-3 font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function HcResultView({
  result,
  notes,
  staff = false,
}: {
  result: Result;
  notes?: string | null;
  staff?: boolean;
}) {
  const period = result.period as { from: string; to: string } | undefined;
  const ov = result.overview as { profit_metric: string; values: Row } | undefined;
  const fees = result.fees as { by_platform: Row[]; totals: Row } | undefined;
  const loss = result.loss_skus as { before_cogs: boolean; rows: Row[] } | undefined;
  const ret = result.returns as { by_platform: Row[]; by_product: Row[] } | undefined;
  const gaps = result.source_gaps as
    { unsettled_completed?: Row[]; ads?: Row & { by_platform?: Row[] } } | undefined;
  const fq = result.file_quality as { files: Row[]; mapping_issues: string[] } | undefined;
  const feeMetrics = ["platform_fees", "payment_fees", "shipping_cost", "return_cost", "allocated_ad_spend"];
  const totals = fees?.totals ?? {};
  const rev = Number(totals.net_revenue ?? 0);
  const platformPayment = Number(totals.platform_fees ?? 0) + Number(totals.payment_fees ?? 0);
  const versions = Object.entries(result.metrics ?? {})
    .map(([k, v]) => `${k} ${v.version}`)
    .join(", ");

  return (
    <article className="card space-y-5">
      {period && (
        <p className="text-sm text-slate-500">
          Số liệu từ {formatDate(period.from)} đến {formatDate(period.to)} theo các file đã gửi.
        </p>
      )}
      {notes && (
        <div className="rounded-lg border border-brand-100 bg-brand-50 p-4 text-sm">
          <div className="mb-1 font-semibold">Nhận xét của DataxLand</div>
          <div className="prose-dx">
            <ReactMarkdown>{notes}</ReactMarkdown>
          </div>
        </div>
      )}
      {ov && (
        <Section title="Tổng quan">
          <div className="grid gap-3 sm:grid-cols-4">
            {["gmv", "net_revenue", "order_count", ov.profit_metric].map((m) => (
              <div key={m} className="rounded-lg border border-slate-200 p-3">
                <div className="text-sm text-slate-600">{n(result, m)}</div>
                <div className="text-lg font-semibold">
                  <Value value={ov.values[m] as number} unit={result.metrics?.[m]?.unit ?? "VND"} />
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}
      {fees && (
        <Section title="Phí ăn vào lãi">
          {rev > 0 && (
            <p className="mb-3 text-sm">
              Phí sàn và thanh toán đã lấy <strong>{formatVnd(platformPayment)}</strong>, bằng{" "}
              <strong>{formatPercent(platformPayment / rev)}</strong> doanh thu thực nhận.
            </p>
          )}
          <table className="table">
            <thead>
              <tr>
                <th>Kênh</th>
                {feeMetrics.map((m) => (
                  <th key={m} className="text-right">
                    {n(result, m)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fees.by_platform.map((r) => (
                <tr key={String(r.platform)}>
                  <td>{platformLabel(r.platform)}</td>
                  {feeMetrics.map((m) => (
                    <td key={m} className="text-right">
                      <Value value={r[m] as number} unit="VND" />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}
      {loss && (
        <Section title="SKU lỗ sau phí">
          {loss.before_cogs && (
            <p className="mb-2 text-sm text-amber-800">Chưa có giá vốn: đây là lãi trước giá vốn.</p>
          )}
          {loss.rows.length === 0 ? (
            <p className="text-sm text-green-700">Không có SKU nào lỗ trong kỳ.</p>
          ) : (
            <table className="table">
              <tbody>
                {loss.rows.map((r) => (
                  <tr key={String(r.product)}>
                    <td>
                      {String(r.product_name ?? r.sku)}{" "}
                      <span className="text-xs text-slate-400">{String(r.sku ?? "")}</span>
                    </td>
                    <td className="text-right text-red-700">
                      <Value value={r.sku_profit as number} unit="VND" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
      )}
      {ret && (
        <Section title="Hoàn hàng">
          <div className="grid gap-4 lg:grid-cols-2">
            <table className="table">
              <thead>
                <tr>
                  <th>Kênh</th>
                  <th className="text-right">{n(result, "return_rate")}</th>
                  <th className="text-right">{n(result, "return_cost")}</th>
                </tr>
              </thead>
              <tbody>
                {ret.by_platform.map((r) => (
                  <tr key={String(r.platform)}>
                    <td>{platformLabel(r.platform)}</td>
                    <td className="text-right">
                      <Value value={r.return_rate as number} unit="percent" />
                    </td>
                    <td className="text-right">
                      <Value value={r.return_cost as number} unit="VND" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <table className="table">
              <thead>
                <tr>
                  <th>Sản phẩm hoàn nhiều nhất</th>
                  <th className="text-right">{n(result, "return_cost")}</th>
                </tr>
              </thead>
              <tbody>
                {ret.by_product.map((r) => (
                  <tr key={String(r.product)}>
                    <td>{String(r.product_name ?? r.sku)}</td>
                    <td className="text-right">
                      <Value value={r.return_cost as number} unit="VND" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
      {gaps && (
        <Section title="Chênh lệch giữa các nguồn">
          {(gaps.unsettled_completed ?? []).length > 0 && (
            <ul className="mb-2 list-disc pl-5 text-sm">
              {(gaps.unsettled_completed ?? []).map((r) => (
                <li key={String(r.platform)}>
                  {platformLabel(r.platform)}: {String(r.order_count)} đơn đã hoàn thành chưa có trong file
                  quyết toán ({formatVnd(r.net_revenue as number)})
                </li>
              ))}
            </ul>
          )}
          {gaps.ads && (
            <p className="text-sm">
              {n(result, "platform_vs_actual_gap")}:{" "}
              <Value value={gaps.ads.platform_vs_actual_gap as number} unit="percent" /> ·{" "}
              {n(result, "roas_blended")}: <Value value={gaps.ads.roas_blended as number} unit="ratio" />
            </p>
          )}
        </Section>
      )}
      {staff && fq && (
        <Section title="Chất lượng file (chỉ nhân viên thấy)">
          <table className="table">
            <tbody>
              {fq.files.map((f) => (
                <tr key={String(f.id)}>
                  <td>{String(f.filename)}</td>
                  <td>
                    <Badge tone={f.status === "loaded" ? "green" : "red"}>{String(f.status)}</Badge>
                  </td>
                  <td className="text-xs">
                    {f.error_message_vi
                      ? String(f.error_message_vi)
                      : `${formatDate(f.date_from as string)}–${formatDate(f.date_to as string)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {fq.mapping_issues.length > 0 && (
            <p className="mt-2 text-sm text-amber-800">
              Trạng thái hoặc phí chưa ánh xạ: {fq.mapping_issues.join(", ")}
            </p>
          )}
        </Section>
      )}
      <footer className="border-t border-slate-100 pt-3 text-xs text-slate-500">
        Phiên bản chỉ số: {versions}.
      </footer>
    </article>
  );
}
