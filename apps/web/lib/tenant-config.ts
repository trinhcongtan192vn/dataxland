"use client";

import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { useTenant } from "@/lib/tenant";

const SALES = ["shopee", "tiktok_shop", "lazada", "amazon_seller"];
const ADS = ["meta_ads", "tiktok_ads", "google_ads", "amazon_ads"];

type Source = { type: string; enabled?: boolean; account_id?: string | null; connector?: string };

/** Cấu hình đã đồng bộ của khách: nguồn đang bật, để dựng bộ lọc kênh và ẩn khối không áp dụng. */
export function useTenantSources() {
  const { tenantId } = useTenant();
  const q = useQuery({
    queryKey: ["tenant", tenantId],
    queryFn: () =>
      unwrap(api.GET("/v1/tenants/{tenant_id}", { params: { path: { tenant_id: tenantId ?? "" } } })),
    enabled: !!tenantId,
    staleTime: 5 * 60_000,
  });
  const sources = ((q.data?.config as { sources?: Source[] } | undefined)?.sources ?? []).filter(
    (s) => s.enabled !== false,
  );
  const types = [...new Set(sources.map((s) => s.type))];
  return {
    ...q,
    sources,
    salesPlatforms: types.filter((t) => SALES.includes(t)),
    adPlatforms: types.filter((t) => ADS.includes(t)),
    hasAmazon: types.includes("amazon_ads") || types.includes("amazon_seller"),
  };
}
