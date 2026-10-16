"use client";

// Dashboard gói Agency (spec 06 §3.2). Dùng cho `/app/dashboards/agency` và `/partner/[tenant]` (spec 06 §8).
import { Block } from "@/components/block";
import { BarChartView, pivot } from "@/components/charts/charts";
import { DataStatus } from "@/components/data-status";
import { FilterBar } from "@/components/filter-bar";
import { FlagList } from "@/components/flags";
import { KeyNumbersCards } from "@/components/key-numbers";
import { Value } from "@/components/money";
import { MetricLabel } from "@/components/metric-label";
import { StatCards } from "@/components/stat-cards";
import { DataTable } from "@/components/tables/data-table";
import { PageHeader } from "@/components/ui";
import {
  type QueryIn,
  type QueryOut,
  type Warning,
  platformFilter,
  platformLabel,
  timeFromParams,
  useHandbook,
  useMetricQuery,
} from "@/lib/metrics";
import { useUrlState } from "@/lib/tenant";
import { useTenantSources } from "@/lib/tenant-config";

const DELIVERY = [
  "ad_spend",
  "impressions",
  "clicks",
  "ctr",
  "cpc",
  "cpm",
  "conversions",
  "cpa",
  "roas_platform",
];

function name(q: QueryOut | undefined, m: string): string {
  return q?.metrics?.[m]?.name_vi ?? m;
}

function PacingBar({ row }: { row: Record<string, unknown> }) {
  const used = Number(row.budget_used_pct ?? 0);
  const pacing = Number(row.budget_pacing ?? 0);
  // Vạch "đúng tiến độ" = phần ngân sách đáng lẽ đã dùng tới hôm qua (budget_used_pct / budget_pacing).
  const expected = pacing > 0 ? used / pacing : null;
  const over = pacing > 1;
  return (
    <div className="space-y-1">
      <div className="relative h-3 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full ${over ? "bg-red-500" : "bg-brand-500"}`}
          style={{ width: `${Math.min(used, 1) * 100}%` }}
        />
        {expected !== null && (
          <div
            className="absolute top-0 h-full w-0.5 bg-slate-800"
            style={{ left: `${Math.min(expected, 1) * 100}%` }}
            title="Đúng tiến độ"
          />
        )}
      </div>
    </div>
  );
}

export function AgencyDashboard({ title = "Dashboard" }: { title?: string }) {
  const [params] = useUrlState();
  const { adPlatforms, hasAmazon } = useTenantSources();
  const handbook = useHandbook();
  const time = timeFromParams(params);
  const filters = platformFilter(params);
  const base = { time, filters } as Pick<QueryIn, "time" | "filters">;
  const grain = time.preset === "last_90_days" ? "week" : "day";

  const overview = useMetricQuery("agency-overview", {
    time,
    metrics: ["mer", "roas_blended", "ad_spend"],
    compare: "previous_period",
  } as QueryIn);
  const platformRoas = useMetricQuery("agency-roas-platform", {
    ...base,
    metrics: ["roas_platform"],
    dimensions: ["platform"],
  } as QueryIn);
  const spendDaily = useMetricQuery("agency-spend", {
    ...base,
    metrics: ["ad_spend"],
    dimensions: ["platform"],
    grain,
  } as QueryIn);
  const budget = useMetricQuery("agency-budget", {
    time: { preset: "this_month" },
    filters,
    metrics: ["budget", "spend_mtd", "budget_used_pct", "budget_pacing"],
    dimensions: ["platform"],
  } as QueryIn);
  const gap = useMetricQuery("agency-gap", {
    time,
    metrics: ["roas_blended", "platform_vs_actual_gap"],
  } as QueryIn);
  const delivery = useMetricQuery("agency-delivery", {
    ...base,
    metrics: DELIVERY,
    dimensions: ["platform"],
  } as QueryIn);
  const campaigns = useMetricQuery("agency-campaigns", {
    ...base,
    metrics: DELIVERY,
    dimensions: ["platform", "campaign", "campaign_name"],
    order: [{ metric: "ad_spend", dir: "desc" }],
    limit: 500,
  } as QueryIn);
  const amazonAcos = useMetricQuery(
    "agency-acos",
    hasAmazon
      ? ({
          time,
          metrics: ["acos"],
          filters: [{ dimension: "platform", op: "eq", value: "amazon_ads" }],
        } as QueryIn)
      : null,
  );
  const amazonTacos = useMetricQuery(
    "agency-tacos",
    hasAmazon ? ({ time, metrics: ["tacos"] } as QueryIn) : null,
  );

  const warnings: Warning[] = [overview, spendDaily].flatMap((q) => (q.data?.warnings ?? []) as Warning[]);
  const t = overview.data?.time as { from?: string; to?: string } | undefined;
  const range = { from: t?.from, to: t?.to };
  const withName = (rows: unknown[] | undefined) =>
    ((rows ?? []) as Record<string, unknown>[]).map((r): Record<string, unknown> => ({
      ...r,
      platform_name: platformLabel(r.platform),
    }));
  const spend = pivot(withName(spendDaily.data?.rows), "date", "platform_name", "ad_spend");
  const blended = gap.data?.rows?.[0]?.roas_blended as number | undefined;
  const roasRows = [
    ...withName(platformRoas.data?.rows),
    ...(blended !== undefined ? [{ platform_name: "ROAS thật (mọi kênh)", roas_platform: blended }] : []),
  ];

  return (
    <div>
      <PageHeader title={title} subtitle="Chi tiêu, ngân sách và hiệu quả quảng cáo" />
      <FilterBar platforms={adPlatforms} />
      <div className="mb-4">
        <DataStatus asOf={overview.data?.data_as_of} warnings={warnings} />
      </div>
      <div className="grid gap-4">
        <Block
          title="Tổng quan"
          loading={overview.isLoading}
          error={overview.error}
          onRetry={() => overview.refetch()}
        >
          <div className="space-y-4">
            <KeyNumbersCards preset={params.get("preset")} />
            <StatCards
              data={overview.data}
              metrics={["mer", "roas_blended", "ad_spend"]}
              handbook={handbook.data?.byName}
            />
            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-600">Cờ cần chú ý</h3>
              <FlagList />
            </div>
          </div>
        </Block>

        <Block
          title="Chi tiêu theo nền tảng"
          loading={spendDaily.isLoading}
          error={spendDaily.error}
          onRetry={() => spendDaily.refetch()}
          csv={
            spendDaily.data && {
              block: "chi-tieu-theo-nen-tang",
              ...range,
              columns: [
                { key: "date", label: "Ngày" },
                { key: "platform_name", label: "Nền tảng" },
                { key: "ad_spend", label: name(spendDaily.data, "ad_spend"), unit: "VND" },
              ],
              rows: withName(spendDaily.data.rows),
            }
          }
        >
          <BarChartView
            data={spend.data}
            x="date"
            series={spend.keys.map((k) => ({ key: k, label: k, unit: "VND", stack: "s" }))}
          />
        </Block>

        <div className="grid gap-4 lg:grid-cols-2">
          <Block
            title="Tiến độ ngân sách tháng này"
            loading={budget.isLoading}
            error={budget.error}
            onRetry={() => budget.refetch()}
            csv={
              budget.data && {
                block: "tien-do-ngan-sach",
                from: (budget.data.time as { from?: string }).from,
                to: (budget.data.time as { to?: string }).to,
                columns: [
                  { key: "platform_name", label: "Nền tảng" },
                  { key: "budget", label: name(budget.data, "budget"), unit: "VND" },
                  { key: "spend_mtd", label: name(budget.data, "spend_mtd"), unit: "VND" },
                  { key: "budget_used_pct", label: name(budget.data, "budget_used_pct"), unit: "percent" },
                  { key: "budget_pacing", label: name(budget.data, "budget_pacing"), unit: "ratio" },
                ],
                rows: withName(budget.data.rows),
              }
            }
          >
            {(budget.data?.rows ?? []).length === 0 ? (
              <p className="text-sm text-slate-500">Chưa có ngân sách tháng này. Nhập ở mục Ngân sách.</p>
            ) : (
              <div className="space-y-4">
                {withName(budget.data?.rows).map((r) => (
                  <div key={String(r.platform)}>
                    <div className="mb-1 flex flex-wrap justify-between gap-2 text-sm">
                      <span className="font-medium">{String(r.platform_name)}</span>
                      <span className="text-slate-600">
                        <Value value={r.spend_mtd as number} unit="VND" /> /{" "}
                        <Value value={r.budget as number} unit="VND" /> ·{" "}
                        <MetricLabel metric="budget_pacing" />:{" "}
                        <Value value={r.budget_pacing as number} unit="ratio" />
                      </span>
                    </div>
                    <PacingBar row={r} />
                  </div>
                ))}
                <p className="text-xs text-slate-500">
                  Vạch đen là mức đáng lẽ đã chi tới hôm qua nếu đúng tiến độ.
                </p>
              </div>
            )}
          </Block>

          <Block
            title="ROAS nền tảng và ROAS thật"
            loading={platformRoas.isLoading}
            error={platformRoas.error}
            onRetry={() => platformRoas.refetch()}
            csv={
              platformRoas.data && {
                block: "roas",
                ...range,
                columns: [
                  { key: "platform_name", label: "Nền tảng" },
                  { key: "roas_platform", label: name(platformRoas.data, "roas_platform"), unit: "ratio" },
                ],
                rows: roasRows,
              }
            }
          >
            <BarChartView
              data={roasRows}
              x="platform_name"
              xLabel={(v) => String(v)}
              series={[
                { key: "roas_platform", label: name(platformRoas.data, "roas_platform"), unit: "ratio" },
              ]}
            />
            <p className="mt-2 text-sm text-slate-600">
              <MetricLabel metric="platform_vs_actual_gap" />:{" "}
              <Value
                value={gap.data?.rows?.[0]?.platform_vs_actual_gap as number | undefined}
                unit="percent"
              />
            </p>
          </Block>
        </div>

        <Block
          title="Phân phối theo nền tảng"
          loading={delivery.isLoading}
          error={delivery.error}
          onRetry={() => delivery.refetch()}
          csv={
            delivery.data && {
              block: "phan-phoi",
              ...range,
              columns: [
                { key: "platform_name", label: "Nền tảng" },
                ...DELIVERY.map((m) => ({
                  key: m,
                  label: name(delivery.data, m),
                  unit: delivery.data?.metrics?.[m]?.unit,
                })),
              ],
              rows: withName(delivery.data.rows),
            }
          }
        >
          <DataTable
            rows={withName(delivery.data?.rows)}
            columns={[
              { key: "platform_name", header: "Nền tảng" },
              ...DELIVERY.map((m) => ({
                key: m,
                header: <MetricLabel metric={m} />,
                unit: delivery.data?.metrics?.[m]?.unit ?? "count",
              })),
            ]}
          />
        </Block>

        <Block
          title="Chiến dịch"
          loading={campaigns.isLoading}
          error={campaigns.error}
          onRetry={() => campaigns.refetch()}
          csv={
            campaigns.data && {
              block: "chien-dich",
              ...range,
              columns: [
                { key: "platform_name", label: "Nền tảng" },
                { key: "campaign_name", label: "Chiến dịch" },
                ...DELIVERY.map((m) => ({
                  key: m,
                  label: name(campaigns.data, m),
                  unit: campaigns.data?.metrics?.[m]?.unit,
                })),
              ],
              rows: withName(campaigns.data.rows),
            }
          }
        >
          <DataTable
            rows={withName(campaigns.data?.rows)}
            maxRows={50}
            initialSort={[{ id: "ad_spend", desc: true }]}
            columns={[
              { key: "platform_name", header: "Nền tảng" },
              { key: "campaign_name", header: "Chiến dịch" },
              ...DELIVERY.map((m) => ({
                key: m,
                header: <MetricLabel metric={m} />,
                unit: campaigns.data?.metrics?.[m]?.unit ?? "count",
              })),
            ]}
          />
        </Block>

        {hasAmazon && (
          <Block
            title="Amazon"
            loading={amazonAcos.isLoading || amazonTacos.isLoading}
            error={amazonAcos.error ?? amazonTacos.error}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="text-sm text-slate-600">
                  <MetricLabel metric="acos" />
                </div>
                <div className="text-lg font-semibold">
                  <Value value={amazonAcos.data?.rows?.[0]?.acos as number | undefined} unit="percent" />
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="text-sm text-slate-600">
                  <MetricLabel metric="tacos" />
                </div>
                <div className="text-lg font-semibold">
                  <Value value={amazonTacos.data?.rows?.[0]?.tacos as number | undefined} unit="percent" />
                </div>
              </div>
            </div>
          </Block>
        )}
      </div>
    </div>
  );
}
