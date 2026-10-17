"use client";

// Khung màn hình vận hành (spec 06 §10): chỉ nhân viên DataxLand (`staff_role`).
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { RequireAuth, TopBar } from "@/components/app-shell";
import { ErrorBox, Spinner } from "@/components/ui";
import { useMe } from "@/lib/tenant";

const NAV = [
  { href: "/ops", label: "Tổng quan", exact: true },
  { href: "/ops/reports", label: "Báo cáo tuần" },
  { href: "/ops/health-checks", label: "Kiểm tra sức khỏe" },
  { href: "/ops/metric-requests", label: "Chỉ số được hỏi" },
  { href: "/ops/integrations", label: "Hướng dẫn tích hợp" },
  { href: "/ops/costs", label: "Chi phí" },
  { href: "/ops/fx-rates", label: "Tỷ giá" },
];

function Frame({ children }: { children: ReactNode }) {
  const me = useMe();
  const pathname = usePathname();
  if (me.isLoading) return <Spinner />;
  if (me.error) return <ErrorBox error={me.error} />;
  if (!me.data?.staff_role) {
    return (
      <div className="min-h-screen">
        <TopBar section="ops" />
        <div className="mx-auto max-w-3xl p-6">
          <ErrorBox error={new Error("Chỉ nhân viên DataxLand vào được màn hình vận hành")} />
        </div>
      </div>
    );
  }
  return (
    <div className="min-h-screen">
      <TopBar section="ops" />
      <div className="mx-auto max-w-7xl px-4 py-4">
        <nav className="mb-5 flex flex-wrap gap-2 text-sm">
          {NAV.map((n) => {
            const active = n.exact ? pathname === n.href : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={`rounded-lg px-3 py-1.5 ${active ? "bg-brand-600 text-white" : "bg-white text-slate-700 shadow-sm hover:bg-slate-100"}`}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
        {children}
      </div>
    </div>
  );
}

export function OpsShell({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <Frame>{children}</Frame>
    </RequireAuth>
  );
}
