"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { ReportView } from "@/components/report-view";
import { ErrorBox, Spinner, TextLink } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";
import { useTenant, useTenantHref } from "@/lib/tenant";

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const { tenantId } = useTenant();
  const href = useTenantHref();
  const q = useQuery({
    queryKey: ["report", tenantId, id],
    queryFn: () => unwrap(api.GET("/v1/reports/{report_id}", { params: { path: { report_id: id } } })),
    enabled: !!tenantId,
  });
  return (
    <div className="max-w-4xl">
      <div className="mb-3 text-sm">
        <TextLink href={href("/app/reports")}>← Báo cáo tuần</TextLink>
      </div>
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : q.data ? (
        <ReportView report={q.data} />
      ) : null}
    </div>
  );
}
