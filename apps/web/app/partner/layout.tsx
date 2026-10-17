"use client";

import { Suspense } from "react";
import { RequireAuth, TopBar } from "@/components/app-shell";
import { Spinner } from "@/components/ui";

export default function PartnerLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<Spinner />}>
      <RequireAuth>
        <div className="min-h-screen">
          <TopBar section="partner" />
          <div className="mx-auto max-w-7xl px-4 py-6">{children}</div>
        </div>
      </RequireAuth>
    </Suspense>
  );
}
