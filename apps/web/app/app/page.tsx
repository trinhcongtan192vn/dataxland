"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Spinner } from "@/components/ui";
import { useTenant } from "@/lib/tenant";

/** Mở dashboard theo gói của khách đang chọn. */
export default function AppHome() {
  const { tenant } = useTenant();
  const router = useRouter();
  useEffect(() => {
    if (tenant) router.replace(`/app/dashboards/${tenant.pack}?t=${tenant.tenant_id}`);
  }, [tenant, router]);
  return <Spinner />;
}
