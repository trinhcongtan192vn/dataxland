"use client";

// Dashboard gói Agency của một shop (spec 06 §8) với `X-Tenant-Id` của shop đó; shop thu quyền thì API trả 403.
import Link from "next/link";
import { AgencyDashboard } from "@/components/agency-dashboard";
import { ErrorBox } from "@/components/ui";
import { useTenant } from "@/lib/tenant";

export default function PartnerTenant() {
  const { tenant, me } = useTenant();
  if (me && !tenant)
    return <ErrorBox error={new Error("Shop đã thu quyền hoặc bạn không có quyền xem shop này")} />;
  return (
    <div>
      <div className="mb-2 text-sm">
        <Link className="text-brand-600 hover:underline" href="/partner">
          ← Các shop
        </Link>
      </div>
      <AgencyDashboard title={tenant?.name ?? "Dashboard"} />
    </div>
  );
}
