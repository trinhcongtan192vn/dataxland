"use client";

// Nhận lời mời (ADR 0002 #17): yêu cầu đăng nhập đúng email được mời, gọi `POST /v1/invitations/accept`.
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorBox, Spinner } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";
import { useAuthUser } from "@/lib/auth/firebase";

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const { user, loading } = useAuthUser();
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <Spinner />;
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-6">
      <h1 className="text-2xl font-semibold">Lời mời tham gia DataxLand</h1>
      {!user ? (
        <>
          <p className="text-sm text-slate-600">
            Đăng nhập (hoặc tạo tài khoản) bằng đúng email nhận lời mời để tiếp tục.
          </p>
          <Link className="btn-primary" href={`/login?next=${encodeURIComponent(`/invite/${token}`)}`}>
            Đăng nhập để nhận lời mời
          </Link>
        </>
      ) : (
        <>
          <p className="text-sm text-slate-600">
            Bạn đang đăng nhập bằng <strong>{user.email}</strong>.
          </p>
          {error ? <ErrorBox error={error} /> : null}
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await unwrap(api.POST("/v1/invitations/accept", { body: { token } }));
                router.replace("/app");
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            Nhận lời mời
          </button>
        </>
      )}
    </main>
  );
}
