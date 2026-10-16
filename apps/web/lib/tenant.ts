"use client";

// Khách đang chọn (spec 06 §2): lưu trong `?t=<tenant_id>`, gửi qua `X-Tenant-Id`.
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { setCurrentTenant } from "@/lib/tenant-store";
import { useAuthUser } from "@/lib/auth/firebase";

export type Me = components["schemas"]["MeOut"];
export type TenantRole = components["schemas"]["TenantRole"];

export function useMe() {
  const { user } = useAuthUser();
  return useQuery({
    queryKey: ["me", user?.uid],
    queryFn: () => unwrap(api.GET("/v1/me")),
    enabled: !!user,
    staleTime: 60_000,
  });
}

/** Khách trong URL; nếu chưa có và người dùng chỉ có một khách thì dùng khách đó. */
export function useTenant(): { tenantId: string | null; tenant: TenantRole | null; me: Me | undefined } {
  const params = useSearchParams();
  const { data: me } = useMe();
  const fromUrl = params.get("t");
  const tenants = me?.tenants ?? [];
  const tenantId = fromUrl ?? (tenants.length === 1 ? (tenants[0]?.tenant_id ?? null) : null);
  setCurrentTenant(tenantId);
  const tenant = tenants.find((t) => t.tenant_id === tenantId) ?? null;
  return { tenantId, tenant, me };
}

/** Thêm `?t=` vào đường dẫn nội bộ để giữ khách đang chọn. */
export function useTenantHref(): (href: string) => string {
  const { tenantId } = useTenant();
  return useCallback(
    (href: string) => {
      if (!tenantId) return href;
      const [path, query = ""] = href.split("?");
      const q = new URLSearchParams(query);
      q.set("t", tenantId);
      return `${path}?${q.toString()}`;
    },
    [tenantId],
  );
}

/** Đọc và ghi tham số trong URL (bộ lọc chia sẻ được, spec 06 §3). */
export function useUrlState(): [URLSearchParams, (patch: Record<string, string | null>) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const current = useMemo(() => new URLSearchParams(params.toString()), [params]);
  const set = useCallback(
    (patch: Record<string, string | null>) => {
      const q = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === "") q.delete(k);
        else q.set(k, v);
      }
      router.replace(`${pathname}?${q.toString()}`, { scroll: false });
    },
    [params, router, pathname],
  );
  return [current, set];
}

export function can(tenant: TenantRole | null, permission: string): boolean {
  return !!tenant?.permissions?.includes(permission);
}
