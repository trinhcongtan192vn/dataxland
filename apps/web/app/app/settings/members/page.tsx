"use client";

// Thành viên (spec 06 §9, spec 05 §5.1): owner mời, gỡ, chọn chỉ số cho member.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { MetricPicker } from "@/components/metric-picker";
import { Badge, ErrorBox, Field, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatDateTime } from "@/lib/format";
import { useHandbook } from "@/lib/metrics";
import { useMe, useTenant } from "@/lib/tenant";

type Member = components["schemas"]["MemberOut"];

function MemberRow({ m, onChanged, isSelf }: { m: Member; onChanged: () => void; isSelf: boolean }) {
  const [editing, setEditing] = useState(false);
  const [allow, setAllow] = useState<string[]>(m.metric_allowlist ?? []);
  const [err, setErr] = useState<string | null>(null);
  const { data: hb } = useHandbook();
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PUT("/v1/members/{user_id}", {
          params: { path: { user_id: m.user_id } },
          body: { metric_allowlist: allow },
        }),
      ),
    onSuccess: () => {
      setEditing(false);
      onChanged();
    },
    onError: (e) => setErr(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: () =>
      unwrap(api.DELETE("/v1/members/{user_id}", { params: { path: { user_id: m.user_id } } })),
    onSuccess: onChanged,
    onError: (e) => setErr(errorMessage(e)),
  });
  const names = (m.metric_allowlist ?? []).map((x) => hb?.byName[x]?.name_vi ?? x);
  return (
    <tr>
      <td>
        <div>{m.display_name ?? m.email}</div>
        <div className="text-xs text-slate-500">{m.email}</div>
      </td>
      <td>{m.role === "owner" ? <Badge tone="blue">Chủ shop</Badge> : <Badge>Thành viên</Badge>}</td>
      <td className="text-sm">
        {m.role === "owner" ? (
          "Mọi chỉ số"
        ) : editing ? (
          <div className="space-y-2">
            <MetricPicker value={allow} onChange={setAllow} />
            <button
              type="button"
              className="btn-primary px-2 py-1 text-xs"
              disabled={!allow.length || save.isPending}
              onClick={() => save.mutate()}
            >
              Lưu
            </button>
            <button type="button" className="ml-2 text-xs" onClick={() => setEditing(false)}>
              Hủy
            </button>
          </div>
        ) : (
          <span>
            {names.join(", ") || "—"}{" "}
            <button
              type="button"
              className="text-xs text-brand-600 hover:underline"
              onClick={() => setEditing(true)}
            >
              Sửa
            </button>
          </span>
        )}
        {err && <div className="text-xs text-red-700">{err}</div>}
      </td>
      <td className="text-right">
        {!isSelf && (
          <button
            type="button"
            className="text-xs text-red-600 hover:underline"
            onClick={() =>
              confirm(`Gỡ ${m.email} khỏi khách này? Quyền mất ngay lập tức.`) && remove.mutate()
            }
          >
            Gỡ
          </button>
        )}
      </td>
    </tr>
  );
}

export default function MembersPage() {
  const { tenantId, tenant } = useTenant();
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"member" | "owner">("member");
  const [allow, setAllow] = useState<string[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const list = useQuery({
    queryKey: ["members", tenantId],
    queryFn: () => unwrap(api.GET("/v1/members")),
    enabled: !!tenantId,
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["members", tenantId] });
  const invite = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/v1/members/invitations", {
          body: { email, role, metric_allowlist: role === "member" ? allow : null },
        }),
      ),
    onSuccess: (inv) => {
      setMsg({
        ok: true,
        text: inv.email_sent
          ? `Đã gửi lời mời tới ${inv.email}.`
          : `Đã tạo lời mời. Gửi link này cho ${inv.email}: ${inv.invite_url ?? ""}`,
      });
      setEmail("");
      setAllow([]);
      refresh();
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });
  const revoke = useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/v1/members/invitations/{invitation_id}", { params: { path: { invitation_id: id } } }),
      ),
    onSuccess: refresh,
  });

  return (
    <div>
      <PageHeader
        title="Thành viên"
        subtitle="Mời người cùng xem số liệu; thành viên chỉ thấy các chỉ số được chọn"
      />
      <form
        className="card mb-4 space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setMsg(null);
          invite.mutate();
        }}
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Email">
            <input
              className="input"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Field label="Vai trò">
            <select
              className="input"
              value={role}
              onChange={(e) => setRole(e.target.value as "member" | "owner")}
            >
              <option value="member">Thành viên</option>
              {tenant?.role === "data_lead" && <option value="owner">Chủ shop</option>}
            </select>
          </Field>
        </div>
        {role === "member" && (
          <div>
            <span className="label">Chỉ số được xem</span>
            <MetricPicker value={allow} onChange={setAllow} />
          </div>
        )}
        {msg && (
          <p className={`break-all text-sm ${msg.ok ? "text-green-700" : "text-red-700"}`}>{msg.text}</p>
        )}
        <button
          type="submit"
          className="btn-primary"
          disabled={invite.isPending || (role === "member" && allow.length === 0)}
        >
          Gửi lời mời
        </button>
      </form>

      <div className="card">
        {list.isLoading ? (
          <Spinner />
        ) : list.error ? (
          <ErrorBox error={list.error} onRetry={() => list.refetch()} />
        ) : (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>Người dùng</th>
                  <th>Vai trò</th>
                  <th>Chỉ số</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.data?.members.map((m) => (
                  <MemberRow key={m.user_id} m={m} onChanged={refresh} isSelf={m.user_id === me?.user_id} />
                ))}
              </tbody>
            </table>
            {(list.data?.invitations.length ?? 0) > 0 && (
              <>
                <h2 className="mb-2 mt-6 font-semibold">Lời mời đang chờ</h2>
                <table className="table">
                  <tbody>
                    {list.data?.invitations.map((i) => (
                      <tr key={i.id}>
                        <td>{i.email}</td>
                        <td>{i.role === "owner" ? "Chủ shop" : "Thành viên"}</td>
                        <td className="text-xs text-slate-500">Hết hạn {formatDateTime(i.expires_at)}</td>
                        <td className="text-right">
                          <button
                            type="button"
                            className="text-xs text-red-600 hover:underline"
                            onClick={() => revoke.mutate(i.id)}
                          >
                            Thu hồi
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
