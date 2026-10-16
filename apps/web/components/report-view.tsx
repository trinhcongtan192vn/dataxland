"use client";

// Hiển thị báo cáo tuần từ `snapshot` (spec 06 §4.3, §4.7): không gọi lại bộ máy chỉ số (FR-REP-07).
import ReactMarkdown from "react-markdown";
import { FlagList } from "@/components/flags";
import { Change, Value, changeOf } from "@/components/money";
import { Badge } from "@/components/ui";
import { formatAsOf, formatPercent, formatWeekLabel } from "@/lib/format";
import { type Flag, platformLabel } from "@/lib/metrics";

type Meta = { name_vi: string; version: string; unit: string };
type Snap = Record<string, unknown> & {
  metrics?: Record<string, Meta>;
  warnings?: { code: string; detail_vi: string }[];
  data_as_of?: string | null;
};
type KN = {
  key: string;
  metric: string;
  label_vi: string;
  value: number | null;
  unit: string;
  change_pct?: number | null;
  note_vi?: string;
};
type Row = Record<string, unknown> & { compare?: Record<string, number | null> };

export type ReportLike = {
  pack: string;
  period_start: string;
  tenant_name: string;
  snapshot: Record<string, unknown>;
  insight_md: string | null;
  actions: string[];
  data_stale: boolean;
};

function name(snap: Snap, m: string): string {
  return snap.metrics?.[m]?.name_vi ?? m;
}
function unit(snap: Snap, m: string): string {
  return snap.metrics?.[m]?.unit ?? "VND";
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-slate-100 pt-4">
      <h2 className="mb-3 font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function CompareTable({ snap, row, metrics }: { snap: Snap; row: Row; metrics: string[] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Chỉ số</th>
          <th className="text-right">Tuần này</th>
          <th className="text-right">Tuần trước</th>
          <th className="text-right">Thay đổi</th>
        </tr>
      </thead>
      <tbody>
        {metrics
          .filter((m) => m in row)
          .map((m) => (
            <tr key={m}>
              <td>{name(snap, m)}</td>
              <td className="text-right">
                <Value value={row[m] as number | null} unit={unit(snap, m)} />
              </td>
              <td className="text-right">
                <Value value={row.compare?.[m] ?? null} unit={unit(snap, m)} />
              </td>
              <td className="text-right">
                {unit(snap, m) === "percent" ? "" : <Change value={changeOf(row[m], row.compare?.[m])} />}
              </td>
            </tr>
          ))}
      </tbody>
    </table>
  );
}

function SkuTable({ snap, rows }: { snap: Snap; rows: Row[] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Sản phẩm</th>
          <th className="text-right">{name(snap, "sku_profit")}</th>
          <th className="text-right">{name(snap, "net_revenue")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td>
              {String(r.product_name ?? r.sku ?? "—")}{" "}
              <span className="text-xs text-slate-400">{String(r.sku ?? "")}</span>
            </td>
            <td className="text-right">
              <Value value={r.sku_profit as number} unit="VND" />
            </td>
            <td className="text-right">
              <Value value={r.net_revenue as number} unit="VND" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const SELLER_PNL = [
  "net_revenue",
  "cogs",
  "platform_fees",
  "payment_fees",
  "shipping_cost",
  "return_cost",
  "allocated_ad_spend",
  "other_costs",
  "contribution_margin",
  "net_profit_after_fees",
  "net_margin_pct",
];

export function ReportView({ report }: { report: ReportLike }) {
  const snap = report.snapshot as Snap;
  const kn = ((snap.key_numbers as { numbers?: KN[] } | undefined)?.numbers ?? []) as KN[];
  const versions = Object.entries(snap.metrics ?? {})
    .map(([k, v]) => `${k} ${v.version}`)
    .join(", ");
  return (
    <article className="card space-y-5">
      <header>
        <h1 className="text-xl font-semibold">
          Báo cáo {formatWeekLabel(report.period_start)} – {report.tenant_name}
        </h1>
        {report.data_stale && (
          <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            Dữ liệu tuần này chưa cập nhật đủ lúc dựng báo cáo; số có thể thay đổi nhẹ.
          </p>
        )}
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        {kn.map((n) => (
          <div key={n.key} className="rounded-lg border border-brand-100 bg-brand-50 p-3">
            <div className="text-sm text-slate-600">{n.label_vi}</div>
            <div className="mt-1 text-2xl font-semibold">
              {n.value === null ? (
                <span className="text-base font-normal text-slate-500">{n.note_vi ?? "—"}</span>
              ) : n.key === "net_profit_change_pct" ? (
                <Change value={n.value} />
              ) : (
                <Value value={n.value} unit={n.unit} />
              )}
            </div>
            {n.change_pct !== undefined && n.key !== "net_profit_change_pct" && (
              <div className="text-xs">
                <Change value={n.change_pct} />
              </div>
            )}
          </div>
        ))}
      </div>

      {report.pack === "seller" ? (
        <>
          <Section title="Lãi lỗ tuần">
            <CompareTable snap={snap} row={(snap.pnl ?? {}) as Row} metrics={SELLER_PNL} />
          </Section>
          <Section title="SKU lãi nhất và lỗ nhất">
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h3 className="mb-2 text-sm font-medium text-green-700">Top 5 lãi nhất</h3>
                <SkuTable snap={snap} rows={(snap.top_skus ?? []) as Row[]} />
              </div>
              <div>
                <h3 className="mb-2 text-sm font-medium text-red-700">Top 5 lỗ nhất</h3>
                <SkuTable snap={snap} rows={(snap.bottom_skus ?? []) as Row[]} />
              </div>
            </div>
          </Section>
          <Section title="Hoàn hàng và hủy đơn">
            <CompareTable
              snap={snap}
              row={(snap.rates ?? {}) as Row}
              metrics={["return_rate", "cancel_rate"]}
            />
          </Section>
        </>
      ) : (
        <>
          <Section title="Chi tiêu theo nền tảng">
            <table className="table">
              <thead>
                <tr>
                  <th>Nền tảng</th>
                  <th className="text-right">Tuần này</th>
                  <th className="text-right">Tuần trước</th>
                  <th className="text-right">Thay đổi</th>
                </tr>
              </thead>
              <tbody>
                {((snap.spend_by_platform ?? []) as Row[]).map((r) => (
                  <tr key={String(r.platform)}>
                    <td>{platformLabel(r.platform)}</td>
                    <td className="text-right">
                      <Value value={r.ad_spend as number} unit="VND" />
                    </td>
                    <td className="text-right">
                      <Value value={r.compare?.ad_spend ?? null} unit="VND" />
                    </td>
                    <td className="text-right">
                      <Change value={changeOf(r.ad_spend, r.compare?.ad_spend)} goodDirection="neutral" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
          <Section
            title={`Tiến độ ngân sách tháng ${String((snap.budget as { month?: string })?.month ?? "").slice(5)}`}
          >
            <table className="table">
              <thead>
                <tr>
                  <th>Nền tảng</th>
                  <th className="text-right">{name(snap, "budget")}</th>
                  <th className="text-right">{name(snap, "spend_mtd")}</th>
                  <th className="text-right">{name(snap, "budget_used_pct")}</th>
                  <th className="text-right">{name(snap, "budget_pacing")}</th>
                </tr>
              </thead>
              <tbody>
                {(((snap.budget as { rows?: Row[] })?.rows ?? []) as Row[]).map((r) => (
                  <tr key={String(r.platform)}>
                    <td>{platformLabel(r.platform)}</td>
                    <td className="text-right">
                      <Value value={r.budget as number} unit="VND" />
                    </td>
                    <td className="text-right">
                      <Value value={r.spend_mtd as number} unit="VND" />
                    </td>
                    <td className="text-right">
                      <Value value={r.budget_used_pct as number} unit="percent" />
                    </td>
                    <td className="text-right">
                      <Value value={r.budget_pacing as number} unit="ratio" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
          <Section title="ROAS nền tảng so với ROAS thật">
            <ul className="space-y-1 text-sm">
              {(((snap.roas as { platforms?: Row[] })?.platforms ?? []) as Row[]).map((r) => (
                <li key={String(r.platform)}>
                  {platformLabel(r.platform)}: <Value value={r.roas_platform as number} unit="ratio" />
                </li>
              ))}
              <li className="font-medium">
                ROAS thật (mọi kênh):{" "}
                <Value value={(snap.roas as { blended?: number })?.blended} unit="ratio" />
              </li>
            </ul>
          </Section>
          {"amazon" in snap && (
            <Section title="Amazon">
              <p className="text-sm">
                ACOS: <Value value={(snap.amazon as { acos?: number }).acos} unit="percent" /> · TACOS:{" "}
                <Value value={(snap.amazon as { tacos?: number }).tacos} unit="percent" />
              </p>
            </Section>
          )}
          <Section title="Cần chú ý">
            <FlagList flags={(snap.flags ?? []) as Flag[]} />
            {((snap.campaigns_attention ?? []) as Row[]).length > 0 && (
              <ul className="mt-3 space-y-1 text-sm">
                {((snap.campaigns_attention ?? []) as Row[]).map((c) => (
                  <li key={String(c.campaign)}>
                    <Badge tone="yellow">ROAS chiến dịch giảm</Badge> {platformLabel(c.platform)} ·{" "}
                    {String(c.campaign_name)}: <Value value={c.roas_platform as number} unit="ratio" /> (trung
                    bình 4 tuần <Value value={c.baseline as number} unit="ratio" />, giảm{" "}
                    {formatPercent(c.drop_pct as number)})
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </>
      )}

      {(snap.warnings ?? []).length > 0 && (
        <Section title="Cảnh báo dữ liệu">
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {(snap.warnings ?? []).map((w) => (
              <li key={w.code}>{w.detail_vi}</li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Nhận định và việc cần làm">
        {report.insight_md ? (
          <div className="prose-dx text-sm">
            <ReactMarkdown>{report.insight_md}</ReactMarkdown>
          </div>
        ) : (
          <p className="text-sm text-slate-400">Chưa có nhận định.</p>
        )}
        {report.actions.length > 0 && (
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
            {report.actions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ol>
        )}
      </Section>

      <footer className="border-t border-slate-100 pt-3 text-xs text-slate-500">
        Số liệu tại thời điểm {formatAsOf(snap.data_as_of ?? null)}. Phiên bản chỉ số: {versions}.
      </footer>
    </article>
  );
}
