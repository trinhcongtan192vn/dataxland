"use client";

// Khung chung (spec 06 §2): bắt buộc đăng nhập, chọn khách, menu theo vai trò từ `GET /v1/me`.
// Menu chỉ để hiển thị; backend vẫn là nơi chặn quyền.
import { signOut } from "firebase/auth";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect } from "react";
import { ErrorBox, Spinner } from "@/components/ui";
import { firebaseAuth, useAuthUser } from "@/lib/auth/firebase";
import { can, type TenantRole, useMe, useTenant } from "@/lib/tenant";

type NavItem = { href: string; label: string; show: (t: TenantRole | null) => boolean };

const APP_NAV: NavItem[] = [
  {
    href: "/app/dashboards/seller",
    label: "Dashboard",
    show: (t) => t?.pack === "seller" && can(t, "metrics.read"),
  },
  {
    href: "/app/dashboards/agency",
    label: "Dashboard",
    show: (t) => t?.pack === "agency" && can(t, "metrics.read"),
  },
  { href: "/app/reports", label: "Báo cáo tuần", show: (t) => can(t, "reports.read") },
  { href: "/app/metrics", label: "Sổ tay chỉ số", show: (t) => can(t, "metrics.read") },
  {
    href: "/app/inputs/costs",
    label: "Giá vốn",
    show: (t) => t?.pack === "seller" && t.role !== "partner" && can(t, "inputs.read"),
  },
  { href: "/app/inputs/budgets", label: "Ngân sách", show: (t) => can(t, "inputs.read") },
  { href: "/app/decisions", label: "Quyết định", show: (t) => can(t, "decisions.read") },
  { href: "/app/settings/members", label: "Thành viên", show: (t) => can(t, "users.manage") },
  { href: "/app/settings/partners", label: "Agency", show: (t) => can(t, "partners.manage") },
  { href: "/app/settings/telegram", label: "Telegram", show: (t) => can(t, "telegram.link_self") },
];

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuthUser();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  useEffect(() => {
    if (!loading && !user) {
      const next = `${pathname}${params.toString() ? `?${params.toString()}` : ""}`;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [loading, user, router, pathname, params]);
  if (loading || !user) return <Spinner label="Đang kiểm tra đăng nhập…" />;
  if (!user.emailVerified && user.providerData.some((p) => p.providerId === "password")) {
    return (
      <div className="mx-auto max-w-md p-8 text-sm">
        <p className="mb-3">
          Bạn cần xác minh email trước khi dùng cổng. Kiểm tra hộp thư {user.email} rồi tải lại trang.
        </p>
        <button type="button" className="btn-secondary" onClick={() => signOut(firebaseAuth())}>
          Đăng xuất
        </button>
      </div>
    );
  }
  return <>{children}</>;
}

function TenantPicker() {
  const { tenantId, me } = useTenant();
  const router = useRouter();
  const pathname = usePathname();
  const tenants = me?.tenants ?? [];
  if (tenants.length <= 1) return <span className="text-sm font-medium">{tenants[0]?.name}</span>;
  return (
    <select
      aria-label="Chọn khách"
      className="input w-auto py-1"
      value={tenantId ?? ""}
      onChange={(e) => {
        const t = tenants.find((x) => x.tenant_id === e.target.value);
        const base = pathname.startsWith("/app/dashboards") && t ? `/app/dashboards/${t.pack}` : pathname;
        router.push(`${base}?t=${e.target.value}`);
      }}
    >
      <option value="" disabled>
        Chọn khách…
      </option>
      {tenants.map((t) => (
        <option key={t.tenant_id} value={t.tenant_id}>
          {t.name}
        </option>
      ))}
    </select>
  );
}

export function TopBar({ section }: { section: "app" | "ops" | "partner" }) {
  const { data: me } = useMe();
  const { tenantId } = useTenant();
  const router = useRouter();
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
        <Link
          href={tenantId ? `/app?t=${tenantId}` : "/app"}
          className="text-lg font-semibold text-brand-700"
        >
          DataxLand
        </Link>
        {section === "app" && <TenantPicker />}
        <nav className="ml-auto flex items-center gap-3 text-sm">
          {me?.staff_role && (
            <Link className={section === "ops" ? "font-semibold" : "text-slate-600"} href="/ops">
              Vận hành
            </Link>
          )}
          {me?.partner_id && (
            <Link className={section === "partner" ? "font-semibold" : "text-slate-600"} href="/partner">
              Agency
            </Link>
          )}
          {(me?.tenants?.length ?? 0) > 0 && section !== "app" && (
            <Link className="text-slate-600" href="/app">
              Cổng khách
            </Link>
          )}
          <span className="hidden text-slate-500 sm:inline">{me?.display_name ?? me?.email}</span>
          <button
            type="button"
            className="btn-secondary px-2 py-1"
            onClick={async () => {
              await signOut(firebaseAuth());
              router.replace("/login");
            }}
          >
            Đăng xuất
          </button>
        </nav>
      </div>
    </header>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AppFrame>{children}</AppFrame>
    </RequireAuth>
  );
}

function AppFrame({ children }: { children: ReactNode }) {
  const { tenant, tenantId, me } = useTenant();
  const meQuery = useMe();
  const pathname = usePathname();
  if (meQuery.isLoading) return <Spinner />;
  if (meQuery.error) return <ErrorBox error={meQuery.error} onRetry={() => meQuery.refetch()} />;
  const items = APP_NAV.filter((i) => i.show(tenant));
  return (
    <div className="min-h-screen">
      <TopBar section="app" />
      <div className="mx-auto flex max-w-7xl gap-6 px-4 py-6">
        <aside className="hidden w-48 shrink-0 md:block">
          <nav className="flex flex-col gap-1 text-sm">
            {items.map((i) => (
              <Link
                key={i.href}
                href={`${i.href}?t=${tenantId ?? ""}`}
                className={`rounded-lg px-3 py-2 ${pathname.startsWith(i.href) ? "bg-brand-50 font-medium text-brand-700" : "text-slate-700 hover:bg-slate-100"}`}
              >
                {i.label}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="min-w-0 flex-1">
          <nav className="mb-4 flex gap-2 overflow-x-auto text-sm md:hidden">
            {items.map((i) => (
              <Link
                key={i.href}
                href={`${i.href}?t=${tenantId ?? ""}`}
                className="whitespace-nowrap rounded-lg bg-white px-3 py-1.5 shadow-sm"
              >
                {i.label}
              </Link>
            ))}
          </nav>
          {!tenantId ? (
            <div className="card">
              {(me?.tenants?.length ?? 0) === 0 ? (
                <p className="text-sm">
                  Tài khoản chưa thuộc khách nào. Nhờ chủ shop gửi lời mời, hoặc liên hệ DataxLand.
                  {me?.staff_role && (
                    <>
                      {" "}
                      Bạn là nhân viên DataxLand: vào{" "}
                      <Link className="text-brand-600 underline" href="/ops">
                        màn hình vận hành
                      </Link>
                      .
                    </>
                  )}
                </p>
              ) : (
                <p className="text-sm">Chọn khách ở thanh trên để bắt đầu.</p>
              )}
            </div>
          ) : !tenant ? (
            <ErrorBox error={new Error("Bạn không có quyền với khách này")} />
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}
