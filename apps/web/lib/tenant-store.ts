// Khách đang chọn cho client API. Nguồn sự thật là URL `?t=<tenant_id>` (spec 06 §2); `TenantSync` ghi lại ở đây
// để middleware của client gắn `X-Tenant-Id`.
let tenant: string | null = null;

export function currentTenant(): string | null {
  return tenant;
}

export function setCurrentTenant(t: string | null): void {
  tenant = t;
}
