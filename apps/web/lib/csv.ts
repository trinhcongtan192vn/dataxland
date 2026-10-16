// Xuất CSV phía client (FR-DSH-05, spec 06 §3.3): tiêu đề là `name_vi`, tiền là số nguyên không định dạng,
// UTF-8 có BOM để Excel đọc đúng tiếng Việt.

export type CsvColumn = { key: string; label: string; unit?: string };

function escapeCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  let s: string;
  if (typeof v === "number") {
    s = Number.isInteger(v) ? v.toString() : v.toString();
  } else {
    s = String(v);
  }
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function toCsv(columns: CsvColumn[], rows: Record<string, unknown>[]): string {
  const header = columns.map((c) => escapeCell(c.label)).join(",");
  const lines = rows.map((r) =>
    columns
      .map((c) => {
        const v = r[c.key];
        if (c.unit === "VND" && typeof v === "number") return escapeCell(Math.round(v));
        return escapeCell(v);
      })
      .join(","),
  );
  return "﻿" + [header, ...lines].join("\r\n") + "\r\n";
}

export function csvFilename(block: string, from: string, to: string): string {
  return `${block}_${from}_${to}.csv`;
}

export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
