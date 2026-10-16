"use client";

import Link from "next/link";
import { useState } from "react";
import { Drawer } from "@/components/ui";
import { useHandbook } from "@/lib/metrics";
import { useTenantHref } from "@/lib/tenant";

/** Tên chỉ số `name_vi`; bấm mở định nghĩa từ sổ tay (FR-DSH-03). */
export function MetricLabel({ metric, fallback }: { metric: string; fallback?: string }) {
  const [open, setOpen] = useState(false);
  const { data } = useHandbook();
  const href = useTenantHref();
  const m = data?.byName[metric];
  const name = m?.name_vi ?? fallback ?? metric;
  return (
    <>
      <button
        type="button"
        className="text-left decoration-dotted underline-offset-4 hover:underline"
        onClick={() => setOpen(true)}
        title="Xem định nghĩa"
      >
        {name}
      </button>
      <Drawer open={open} onClose={() => setOpen(false)} title={name}>
        {m ? (
          <div className="space-y-3 text-sm">
            <p>{m.description_vi}</p>
            {m.formula_vi && (
              <div>
                <div className="font-medium text-slate-600">Cách tính</div>
                <p>{m.formula_vi}</p>
              </div>
            )}
            {m.source_note_vi && (
              <div>
                <div className="font-medium text-slate-600">Nguồn</div>
                <p>{m.source_note_vi}</p>
              </div>
            )}
            <p className="text-xs text-slate-500">Phiên bản {m.version}</p>
            <Link className="btn-secondary" href={href(`/app/metrics/${metric}`)}>
              Mở trong sổ tay chỉ số
            </Link>
          </div>
        ) : (
          <p className="text-sm text-slate-500">Bạn không có quyền xem định nghĩa chỉ số này.</p>
        )}
      </Drawer>
    </>
  );
}
