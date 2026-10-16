"use client";

// Gọi lớp chỉ số qua API (spec 03 §4). Web không tính chỉ số; chỉ định dạng giá trị trả về.
import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useTenant } from "@/lib/tenant";

type ApiQueryIn = components["schemas"]["QueryIn"];
/** Thân `POST /v1/metrics/query`; `grain`, `limit` có giá trị mặc định ở API. */
export type QueryIn = Omit<ApiQueryIn, "grain" | "limit"> & { grain?: ApiQueryIn["grain"]; limit?: number };
export type QueryOut = Omit<components["schemas"]["QueryOut"], "rows"> & { rows: Row[] };
export type MetricInfo = components["schemas"]["MetricInfo"];
export type Row = Record<string, unknown> & { compare?: Record<string, number | null> };

export const PRESETS: { value: string; label: string }[] = [
  { value: "yesterday", label: "Hôm qua" },
  { value: "this_week", label: "Tuần này" },
  { value: "last_week", label: "Tuần trước" },
  { value: "last_7_days", label: "7 ngày qua" },
  { value: "this_month", label: "Tháng này" },
  { value: "last_month", label: "Tháng trước" },
  { value: "last_30_days", label: "30 ngày qua" },
  { value: "last_90_days", label: "90 ngày qua" },
];

export const PLATFORM_LABEL: Record<string, string> = {
  shopee: "Shopee",
  tiktok_shop: "TikTok Shop",
  lazada: "Lazada",
  amazon_seller: "Amazon",
  meta_ads: "Meta Ads",
  tiktok_ads: "TikTok Ads",
  google_ads: "Google Ads",
  amazon_ads: "Amazon Ads",
};

export function platformLabel(p: unknown): string {
  const s = String(p ?? "");
  return PLATFORM_LABEL[s] ?? s;
}

/** Khoảng thời gian từ URL: `preset` hoặc `from`/`to`. */
export function timeFromParams(params: URLSearchParams, fallback = "last_30_days"): Record<string, string> {
  const from = params.get("from");
  const to = params.get("to");
  if (from && to) return { from, to };
  return { preset: params.get("preset") ?? fallback };
}

export function platformFilter(params: URLSearchParams): QueryIn["filters"] {
  const p = params.get("platform");
  if (!p) return [];
  return [{ dimension: "platform", op: "in", values: p.split(",") }];
}

export function useMetricQuery(key: string, body: QueryIn | null) {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["metrics", tenantId, key, body],
    queryFn: async () => {
      const full: ApiQueryIn = { grain: "none", limit: 1000, ...(body as QueryIn) };
      return (await unwrap(api.POST("/v1/metrics/query", { body: full }))) as QueryOut;
    },
    enabled: !!tenantId && !!body,
  });
}

export function useHandbook() {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["handbook", tenantId],
    queryFn: () => unwrap(api.GET("/v1/metrics")),
    enabled: !!tenantId,
    staleTime: 10 * 60_000,
    select: (list) => ({
      list,
      byName: Object.fromEntries(list.map((m) => [m.metric, m])) as Record<string, MetricInfo>,
    }),
  });
}

export type KeyNumber = {
  key: string;
  metric: string;
  label_vi: string;
  value: number | null;
  unit: string;
  version: string;
  change_pct?: number | null;
  note_vi?: string;
  month?: string;
};

export type KeyNumbers = {
  pack: string;
  period: { preset: string; from: string; to: string };
  previous: { from: string; to: string };
  numbers: KeyNumber[];
  data_as_of: string | null;
  warnings: Warning[];
};

export type Warning = { code: string; detail_vi: string; metrics?: string[]; action_url?: string };

export function useKeyNumbers(period: string) {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["key-numbers", tenantId, period],
    queryFn: async () =>
      (await unwrap(
        api.GET("/v1/metrics/key-numbers", { params: { query: { period } } }),
      )) as unknown as KeyNumbers,
    enabled: !!tenantId,
  });
}

export type Flag = {
  code: string;
  platform?: string;
  value: number;
  threshold: number;
  baseline?: number;
  message_vi: string;
};

export function useFlags(enabled = true) {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["flags", tenantId],
    queryFn: async () => (await unwrap(api.GET("/v1/metrics/flags"))) as unknown as Flag[],
    enabled: !!tenantId && enabled,
  });
}
