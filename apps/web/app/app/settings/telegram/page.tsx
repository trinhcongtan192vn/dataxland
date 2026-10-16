"use client";

// Liên kết Telegram (spec 06 §9, spec 08 §3): mã cho chat riêng (mọi người) hoặc nhóm (owner, chọn phạm vi chỉ số),
// link `t.me/<bot>?start=<mã>`, đếm ngược 10 phút; danh sách liên kết và nút gỡ.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { MetricPicker } from "@/components/metric-picker";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatDateTime } from "@/lib/format";
import { can, useTenant } from "@/lib/tenant";

type Code = components["schemas"]["LinkCodeOut"];

function Countdown({ until, onExpire }: { until: string; onExpire: () => void }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const left = Math.max(0, Math.floor((Date.parse(until) - now) / 1000));
  useEffect(() => {
    if (left === 0) onExpire();
  }, [left, onExpire]);
  return (
    <span className="tabular-nums">
      {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}
    </span>
  );
}

export default function TelegramPage() {
  const { tenantId, tenant } = useTenant();
  const qc = useQueryClient();
  const [kind, setKind] = useState<"private" | "group">("private");
  const [scope, setScope] = useState<string[]>([]);
  const [code, setCode] = useState<Code | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const links = useQuery({
    queryKey: ["tg-links", tenantId],
    queryFn: () => unwrap(api.GET("/v1/telegram/links")),
    enabled: !!tenantId,
    refetchInterval: code ? 5000 : false,
  });
  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/v1/telegram/link-codes", {
          body: { kind, metric_scope: kind === "group" ? scope : null },
        }),
      ),
    onSuccess: (c) => {
      setErr(null);
      setCode(c);
    },
    onError: (e) => setErr(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/v1/telegram/links/{link_id}", { params: { path: { link_id: id } } })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["tg-links", tenantId] }),
  });
  const canGroup = can(tenant, "telegram.link_group");

  return (
    <div className="max-w-3xl">
      <PageHeader title="Telegram" subtitle="Nhận báo cáo tuần, cảnh báo và tra số nhanh qua Telegram" />
      <div className="card mb-4 space-y-4">
        <div className="flex gap-2">
          <button
            type="button"
            aria-pressed={kind === "private"}
            className={`rounded-full border px-3 py-1 text-sm ${kind === "private" ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300"}`}
            onClick={() => setKind("private")}
          >
            Chat riêng của tôi
          </button>
          {canGroup && (
            <button
              type="button"
              aria-pressed={kind === "group"}
              className={`rounded-full border px-3 py-1 text-sm ${kind === "group" ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300"}`}
              onClick={() => setKind("group")}
            >
              Nhóm Telegram
            </button>
          )}
        </div>
        {kind === "group" && (
          <div>
            <p className="mb-2 text-sm text-slate-600">
              Mọi thành viên trong nhóm sẽ thấy các chỉ số được chọn dưới đây; chỉ số khác hiện “—”.
            </p>
            <MetricPicker value={scope} onChange={setScope} />
          </div>
        )}
        <button
          type="button"
          className="btn-primary"
          disabled={create.isPending || (kind === "group" && scope.length === 0)}
          onClick={() => create.mutate()}
        >
          Tạo mã liên kết
        </button>
        {err && <p className="text-sm text-red-700">{err}</p>}
        {code && (
          <div className="rounded-lg border border-brand-100 bg-brand-50 p-4">
            <p className="text-sm">
              Mã: <code className="text-lg font-semibold tracking-widest">{code.code}</code> · còn{" "}
              <Countdown until={code.expires_at} onExpire={() => setCode(null)} />
            </p>
            <p className="mt-2 text-sm">
              {kind === "group" ? (
                <>
                  Bấm link để thêm bot vào nhóm:{" "}
                  <a
                    className="text-brand-600 underline"
                    href={code.deep_link}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {code.deep_link}
                  </a>
                  . Hoặc gửi <code>/start {code.code}</code> trong nhóm.
                </>
              ) : (
                <>
                  Bấm link để mở bot:{" "}
                  <a
                    className="text-brand-600 underline"
                    href={code.deep_link}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {code.deep_link}
                  </a>
                  , rồi bấm <strong>Start</strong>. Hoặc gửi <code>/start {code.code}</code> cho bot.
                </>
              )}
            </p>
          </div>
        )}
        <p className="text-xs text-slate-500">
          Tin nhắn qua Telegram được lưu trên máy chủ của Telegram. Báo cáo luôn được gửi cả qua email.
        </p>
      </div>

      <div className="card">
        <h2 className="mb-3 font-semibold">Liên kết đang hoạt động</h2>
        {links.isLoading ? (
          <Spinner />
        ) : links.error ? (
          <ErrorBox error={links.error} />
        ) : (links.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Chưa có liên kết nào.</p>
        ) : (
          <table className="table">
            <tbody>
              {links.data?.map((l) => (
                <tr key={l.id}>
                  <td>
                    {l.chat_type === "private" ? "Chat riêng" : `Nhóm ${l.chat_title ?? ""}`}{" "}
                    {l.mine && <Badge tone="blue">Của tôi</Badge>}
                  </td>
                  <td className="text-xs text-slate-500">Liên kết lúc {formatDateTime(l.linked_at)}</td>
                  <td className="text-right">
                    <button
                      type="button"
                      className="text-xs text-red-600 hover:underline"
                      onClick={() =>
                        confirm("Gỡ liên kết này? Chat sẽ không nhận báo cáo nữa.") && remove.mutate(l.id)
                      }
                    >
                      Gỡ
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
