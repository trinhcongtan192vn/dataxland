"use client";

// Hỏi đáp AI (spec 09 §3, FR-AI-01): câu trả lời từ thư viện chỉ số, chân trang tự sinh (chỉ số, phiên bản, kỳ,
// thời điểm dữ liệu). Cùng bộ máy với Telegram nên cùng câu hỏi cho cùng câu trả lời khi dữ liệu chưa đổi.
import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Badge, PageHeader } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatAsOf, formatDate } from "@/lib/format";
import type { components } from "@/lib/api/schema";
import { useTenant } from "@/lib/tenant";

type AskOut = components["schemas"]["AskOut"];
type Citation = {
  metric: string;
  name_vi: string;
  version: string;
  time?: { from?: string; to?: string };
  data_as_of?: string | null;
};
type Turn = { q: string; a?: AskOut; error?: string; feedback?: "up" | "down" | null };

const SUGGEST: Record<string, string[]> = {
  seller: [
    "Tuần trước lãi bao nhiêu?",
    "Vì sao lãi tuần trước giảm?",
    "Sản phẩm nào đang lỗ tháng này?",
    "Phí sàn chiếm bao nhiêu phần trăm doanh thu tháng trước?",
  ],
  agency: [
    "ROAS thật tuần trước?",
    "Tháng này chi có vượt ngân sách không?",
    "Chiến dịch nào chi nhiều nhất tuần trước?",
    "Nền tảng báo cao hơn thực tế bao nhiêu?",
  ],
};

function period(c: Citation): string {
  if (!c.time?.from) return "";
  return c.time.from === c.time.to
    ? formatDate(c.time.from)
    : `${formatDate(c.time.from)} – ${formatDate(c.time.to ?? "")}`;
}

function Footer({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <ul className="mt-3 space-y-0.5 border-t border-slate-200 pt-2 text-xs text-slate-500">
      {citations.map((c) => (
        <li key={`${c.metric}-${c.time?.from}-${c.time?.to}`}>
          {c.name_vi} (v{c.version}){period(c) && <> · {period(c)}</>}
          {c.data_as_of && <> · cập nhật lúc {formatAsOf(c.data_as_of)}</>}
        </li>
      ))}
    </ul>
  );
}

export default function AskPage() {
  const { tenant } = useTenant();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversation, setConversation] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  const ask = useMutation({
    mutationFn: (question: string) =>
      unwrap(api.POST("/v1/ask", { body: { question, conversation_id: conversation } })),
    onSuccess: (a) => {
      setConversation(a.conversation_id);
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a } : x)));
    },
    onError: (e) =>
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, error: errorMessage(e) } : x))),
  });
  const feedback = useMutation({
    mutationFn: ({ id, value }: { id: string; value: "up" | "down" | null }) =>
      unwrap(
        api.POST("/v1/ask/{ask_id}/feedback", {
          params: { path: { ask_id: id } },
          body: { feedback: value },
        }),
      ),
  });

  useEffect(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), [turns]);

  const send = (text: string) => {
    const question = text.trim();
    if (!question || ask.isPending) return;
    setTurns((t) => [...t, { q: question }]);
    setQ("");
    ask.mutate(question);
  };
  const rate = (i: number, value: "up" | "down") => {
    const t = turns[i];
    if (!t?.a) return;
    const next = t.feedback === value ? null : value;
    setTurns((all) => all.map((x, j) => (j === i ? { ...x, feedback: next } : x)));
    feedback.mutate({ id: t.a.ask_id, value: next });
  };

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Hỏi đáp số liệu"
        subtitle="Hỏi bằng tiếng Việt về số của shop. Mọi số lấy từ thư viện chỉ số, kèm nguồn ở cuối câu trả lời."
        actions={
          turns.length > 0 ? (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setTurns([]);
                setConversation(null);
              }}
            >
              Cuộc hỏi mới
            </button>
          ) : undefined
        }
      />
      {turns.length === 0 && (
        <div className="card mb-4">
          <p className="mb-2 text-sm text-slate-600">Gợi ý:</p>
          <div className="flex flex-wrap gap-2">
            {(SUGGEST[tenant?.pack ?? "seller"] ?? []).map((s) => (
              <button key={s} type="button" className="btn-secondary text-sm" onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-500">
            AI không trả lời về từng người mua. Câu hỏi chưa có chỉ số sẽ được ghi nhận để đội ngũ bổ sung.
          </p>
        </div>
      )}
      <div className="space-y-4">
        {turns.map((t, i) => (
          <div key={i} className="space-y-2">
            <div className="ml-auto w-fit max-w-[85%] rounded-2xl bg-brand-600 px-4 py-2 text-white">
              {t.q}
            </div>
            <div className="card max-w-[95%]">
              {t.error ? (
                <p className="text-sm text-red-700">{t.error}</p>
              ) : !t.a ? (
                <p className="text-sm text-slate-500">Đang tra số…</p>
              ) : (
                <>
                  <div className="prose prose-sm max-w-none">
                    <ReactMarkdown>{t.a.answer_vi}</ReactMarkdown>
                  </div>
                  {t.a.missing_metric && <Badge tone="yellow">Đã ghi nhận chỉ số còn thiếu</Badge>}
                  <Footer citations={(t.a.citations ?? []) as Citation[]} />
                  {!t.a.refused_reason && (
                    <div className="mt-2 flex gap-2 text-xs">
                      <button
                        type="button"
                        aria-label="Câu trả lời hữu ích"
                        className={t.feedback === "up" ? "font-semibold text-green-700" : "text-slate-500"}
                        onClick={() => rate(i, "up")}
                      >
                        👍 Hữu ích
                      </button>
                      <button
                        type="button"
                        aria-label="Câu trả lời chưa đúng"
                        className={t.feedback === "down" ? "font-semibold text-red-700" : "text-slate-500"}
                        onClick={() => rate(i, "down")}
                      >
                        👎 Chưa đúng
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        <div ref={bottom} />
      </div>
      <form
        className="sticky bottom-0 mt-4 flex gap-2 bg-slate-50 py-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(q);
        }}
      >
        <input
          className="input flex-1"
          placeholder="Ví dụ: Doanh thu tuần này so với tuần trước?"
          value={q}
          maxLength={1000}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Câu hỏi"
        />
        <button type="submit" className="btn-primary" disabled={ask.isPending || !q.trim()}>
          Hỏi
        </button>
      </form>
    </div>
  );
}
