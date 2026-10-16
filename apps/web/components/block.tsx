"use client";

import type { ReactNode } from "react";
import { ErrorBox, Spinner } from "@/components/ui";
import { type CsvColumn, csvFilename, downloadCsv, toCsv } from "@/lib/csv";

export type CsvSpec = {
  block: string;
  from?: string;
  to?: string;
  columns: CsvColumn[];
  rows: Record<string, unknown>[];
};

/**
 * Khung một khối dashboard (spec 06 §3.3): mỗi khối tải và lỗi riêng, có nút xuất CSV từ đúng dữ liệu đang hiển thị.
 */
export function Block({
  title,
  loading,
  error,
  onRetry,
  csv,
  actions,
  children,
  className = "",
}: {
  title: ReactNode;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  csv?: CsvSpec | null;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">{title}</h2>
        <div className="flex items-center gap-2">
          {actions}
          {csv && csv.rows.length > 0 && (
            <button
              type="button"
              className="btn-secondary px-2 py-1 text-xs"
              onClick={() =>
                downloadCsv(
                  csvFilename(csv.block, csv.from ?? "", csv.to ?? ""),
                  toCsv(csv.columns, csv.rows),
                )
              }
            >
              Xuất CSV
            </button>
          )}
        </div>
      </div>
      {loading ? <Spinner /> : error ? <ErrorBox error={error} onRetry={onRetry} /> : children}
    </section>
  );
}
