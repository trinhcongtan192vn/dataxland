import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { Spinner } from "@/components/ui";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<Spinner />}>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
