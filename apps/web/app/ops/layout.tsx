import { Suspense } from "react";
import { OpsShell } from "@/components/ops-shell";
import { Spinner } from "@/components/ui";

export default function OpsLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<Spinner />}>
      <OpsShell>{children}</OpsShell>
    </Suspense>
  );
}
