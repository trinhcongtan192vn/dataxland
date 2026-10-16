"use client";

// Dashboard gói Seller (spec 06 §3.1, FR-DSH-01..05). Mỗi khối gọi `POST /v1/metrics/query` một lần.
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Block } from "@/components/block";
import { BarChartView, LineChartView } from "@/components/charts/charts";
import { DataStatus } from "@/components/data-status";
import { FilterBar } from "@/components/filter-bar";
import { KeyNumbersCards } from "@/components/key-numbers";
import { MetricLabel } from "@/components/metric-label";
import { StatCards } from "@/components/stat-cards";
import { DataTable } from "@/components/tables/data-table";
import { Badge, PageHeader } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";
import { formatPercent } from "@/lib/format";
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
import { useTenant, useUrlState } from "@/lib/tenant";
import { useTenantSources } from "@/lib/tenant-config";

const OVERVIEW = ["gmv", "contribution_margin", "net_margin_pct", "order_count", "aov"];
const FEES = ["platform_fees", "payment_fees", "shipping_cost", "allocated_ad_spend", "return_cost", "cogs"];

function grainFor(time: Record<string, string>): "day" | "week" {
  if (time.preset === "last_90_days") return "week";
  if (time.from && time.to) {
    const days = (Date.parse(time.to) - Date.parse(time.from)) / 86400000;
    return days > 62 ? "week" : "day";
  }
  return "day";
}

function name(q: QueryOut | undefined, m: string): string {
  return q?.metrics?.[m]?.name_vi ?? m;
}

export default function SellerDashboard() {
  const [params] = useUrlState();
  const { tenantId } = useTenant();
  const { salesPlatforms } = useTenantSources();
  const handbook = useHandbook();
  const time = timeFromParams(params);
  const filters = platformFilter(params);
  const grain = grainFor(time);
  const base = { time, filters } as Pick<QueryIn, "time" | "filters">;

  const overview = useMetricQuery("seller-overview", {
    ...base,
    metrics: OVERVIEW,
    compare: "previous_period",
  } as QueryIn);
  const trend = useMetricQuery("seller-trend", {
    ...base,
    metrics: ["net_revenue", "net_profit_after_fees"],
    grain,
  } as QueryIn);
  const byChannel = useMetricQuery("seller-channel", {
    ...base,
    metrics: ["net_revenue", "contribution_margin", "net_profit_after_fees"],
    dimensions: ["platform"],
  } as QueryIn);
  const fees = useMetricQuery("seller-fees", {
    ...base,
    metrics: [...FEES, "net_revenue"],
    dimensions: ["platform"],
  } as QueryIn);
  const skus = useMetricQuery("seller-sku", {
    ...base,
    metrics: ["sku_profit", "net_revenue", "order_count"],
    dimensions: ["product", "product_name", "sku"],
    order: [{ metric: "sku_profit", dir: "asc" }],
    limit: 500,
  } as QueryIn);
  const returnsTrend = useMetricQuery("seller-returns", {
    ...base,
    metrics: ["return_rate", "cancel_rate"],
    grain,
  } as QueryIn);
  const returnCost = useMetricQuery("seller-return-cost", {
    ...base,
    metrics: ["return_cost"],
    dimensions: ["platform"],
  } as QueryIn);
  const missing = useQuery({
    queryKey: ["missing-costs", tenantId],
    queryFn: () => unwrap(api.GET("/v1/inputs/product-costs/missing")),
    enabled: !!tenantId,
  });
  const missingSkus = useMemo(
    () => new Set((missing.data?.items ?? []).map((i) => i.seller_sku)),
    [missing.data],
  );

  const warnings: Warning[] = [overview, trend, skus].flatMap((q) => (q.data?.warnings ?? []) as Warning[]);
  const t = overview.data?.time as { from?: string; to?: string } | undefined;
  const range = { from: t?.from, to: t?.to };

  const channelRows = (byChannel.data?.rows ?? []).map((r): Record<string, unknown> => ({
    ...r,
    platform_name: platformLabel(r.platform),
  }));
  const feeRows = (fees.data?.rows ?? []).map((r): Record<string, unknown> => ({
    ...r,
    platform_name: platformLabel(r.platform),
  }));
  const feeTotals = FEES.map((m) => ({
    metric: m,
    amount: feeRows.reduce((s, r) => s + Number(r[m] ?? 0), 0),
  }));
  const revenueTotal = feeRows.reduce((s, r) => s + Number(r.net_revenue ?? 0), 0);
  const returnsCostRows = (returnCost.data?.rows ?? []).map((r): Record<string, unknown> => ({
    ...r,
    platform_name: platformLabel(r.platform),
  }));

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Doanh thu, chi phí và lãi theo kênh, theo SKU" />
      <FilterBar platforms={salesPlatforms} />
      <div className="mb-4">
        <DataStatus asOf={overview.data?.data_as_of} warnings={warnings} />
      </div>
      <div className="grid gap-4">
        <Block
          title="Tổng quan"
          loading={overview.isLoading}
          error={overview.error}
          onRetry={() => overview.refetch()}
          csv={
            overview.data && {
              block: "tong-quan",
              ...range,
              columns: OVERVIEW.map((m) => ({
                key: m,
                label: name(overview.data, m),
                unit: overview.data?.metrics?.[m]?.unit,
              })),
              rows: overview.data.rows as Record<string, unknown>[],
            }
          }
        >
          <div className="space-y-4">
            <KeyNumbersCards preset={params.get("preset")} />
            <StatCards data={overview.data} metrics={OVERVIEW} handbook={handbook.data?.byName} />
          </div>
        </Block>

        <Block
          title="Lãi lỗ theo thời gian"
          loading={trend.isLoading}
          error={trend.error}
          onRetry={() => trend.refetch()}
          csv={
            trend.data && {
              block: "lai-lo-theo-thoi-gian",
              ...range,
              columns: [
                { key: "date", label: "Ngày" },
                { key: "net_revenue", label: name(trend.data, "net_revenue"), unit: "VND" },
                {
                  key: "net_profit_after_fees",
                  label: name(trend.data, "net_profit_after_fees"),
                  unit: "VND",
                },
              ],
              rows: trend.data.rows as Record<string, unknown>[],
            }
          }
        >
          <LineChartView
            data={(trend.data?.rows ?? []) as Record<string, unknown>[]}
            x="date"
            series={[
              { key: "net_revenue", label: name(trend.data, "net_revenue"), unit: "VND" },
              { key: "net_profit_after_fees", label: name(trend.data, "net_profit_after_fees"), unit: "VND" },
            ]}
          />
        </Block>

        <div className="grid gap-4 lg:grid-cols-2">
          <Block
            title="Lãi theo kênh"
            loading={byChannel.isLoading}
            error={byChannel.error}
            onRetry={() => byChannel.refetch()}
            csv={
              byChannel.data && {
                block: "lai-theo-kenh",
                ...range,
                columns: [
                  { key: "platform_name", label: "Kênh" },
                  ...["net_revenue", "contribution_margin", "net_profit_after_fees"].map((m) => ({
                    key: m,
                    label: name(byChannel.data, m),
                    unit: "VND",
                  })),
                ],
                rows: channelRows,
              }
            }
          >
            <BarChartView
              data={channelRows}
              x="platform_name"
              xLabel={(v) => String(v)}
              series={["net_revenue", "contribution_margin", "net_profit_after_fees"].map((m) => ({
                key: m,
                label: name(byChannel.data, m),
                unit: "VND",
              }))}
            />
          </Block>

          <Block
            title="Phí theo loại"
            loading={fees.isLoading}
            error={fees.error}
            onRetry={() => fees.refetch()}
            csv={
              fees.data && {
                block: "phi-theo-loai",
                ...range,
                columns: [
                  { key: "platform_name", label: "Kênh" },
                  ...[...FEES, "net_revenue"].map((m) => ({
                    key: m,
                    label: name(fees.data, m),
                    unit: "VND",
                  })),
                ],
                rows: feeRows,
              }
            }
          >
            <BarChartView
              data={feeRows}
              x="platform_name"
              xLabel={(v) => String(v)}
              series={FEES.map((m) => ({ key: m, label: name(fees.data, m), unit: "VND", stack: "fees" }))}
            />
            <table className="table mt-3">
              <thead>
                <tr>
                  <th>Loại phí</th>
                  <th className="text-right">Tỷ lệ trên doanh thu thực nhận</th>
                </tr>
              </thead>
              <tbody>
                {feeTotals.map((f) => (
                  <tr key={f.metric}>
                    <td>
                      <MetricLabel metric={f.metric} fallback={name(fees.data, f.metric)} />
                    </td>
                    <td className="text-right tabular-nums">
                      {revenueTotal ? formatPercent(f.amount / revenueTotal) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Block>
        </div>

        <Block
          title="Lãi theo SKU"
          loading={skus.isLoading}
          error={skus.error}
          onRetry={() => skus.refetch()}
          csv={
            skus.data && {
              block: "lai-theo-sku",
              ...range,
              columns: [
                { key: "sku", label: "SKU" },
                { key: "product_name", label: "Sản phẩm" },
                { key: "sku_profit", label: name(skus.data, "sku_profit"), unit: "VND" },
                { key: "net_revenue", label: name(skus.data, "net_revenue"), unit: "VND" },
                { key: "order_count", label: name(skus.data, "order_count"), unit: "count" },
              ],
              rows: skus.data.rows as Record<string, unknown>[],
            }
          }
        >
          <DataTable
            rows={(skus.data?.rows ?? []) as Record<string, unknown>[]}
            maxRows={50}
            initialSort={[{ id: "sku_profit", desc: false }]}
            rowClassName={(r) => (missingSkus.has(String(r.sku)) ? "bg-amber-50" : "")}
            columns={[
              {
                key: "product_name",
                header: "Sản phẩm",
                render: (r) => (
                  <span>
                    {String(r.product_name ?? r.sku ?? "—")}
                    <span className="ml-2 text-xs text-slate-400">{String(r.sku ?? "")}</span>
                    {missingSkus.has(String(r.sku)) && (
                      <span className="ml-2">
                        <Badge tone="yellow">Thiếu giá vốn</Badge>
                      </span>
                    )}
                  </span>
                ),
              },
              { key: "sku_profit", header: <MetricLabel metric="sku_profit" />, unit: "VND" },
              { key: "net_revenue", header: <MetricLabel metric="net_revenue" />, unit: "VND" },
              { key: "order_count", header: <MetricLabel metric="order_count" />, unit: "count" },
            ]}
          />
        </Block>

        <div className="grid gap-4 lg:grid-cols-2">
          <Block
            title="Hoàn hàng và hủy đơn"
            loading={returnsTrend.isLoading}
            error={returnsTrend.error}
            onRetry={() => returnsTrend.refetch()}
            csv={
              returnsTrend.data && {
                block: "hoan-huy",
                ...range,
                columns: [
                  { key: "date", label: "Ngày" },
                  { key: "return_rate", label: name(returnsTrend.data, "return_rate"), unit: "percent" },
                  { key: "cancel_rate", label: name(returnsTrend.data, "cancel_rate"), unit: "percent" },
                ],
                rows: returnsTrend.data.rows as Record<string, unknown>[],
              }
            }
          >
            <LineChartView
              data={(returnsTrend.data?.rows ?? []) as Record<string, unknown>[]}
              x="date"
              series={[
                { key: "return_rate", label: name(returnsTrend.data, "return_rate"), unit: "percent" },
                { key: "cancel_rate", label: name(returnsTrend.data, "cancel_rate"), unit: "percent" },
              ]}
            />
          </Block>
          <Block
            title="Chi phí hoàn hàng theo kênh"
            loading={returnCost.isLoading}
            error={returnCost.error}
            onRetry={() => returnCost.refetch()}
            csv={
              returnCost.data && {
                block: "chi-phi-hoan-hang",
                ...range,
                columns: [
                  { key: "platform_name", label: "Kênh" },
                  { key: "return_cost", label: name(returnCost.data, "return_cost"), unit: "VND" },
                ],
                rows: returnsCostRows,
              }
            }
          >
            <BarChartView
              data={returnsCostRows}
              x="platform_name"
              xLabel={(v) => String(v)}
              series={[{ key: "return_cost", label: name(returnCost.data, "return_cost"), unit: "VND" }]}
            />
          </Block>
        </div>
      </div>
    </div>
  );
}
