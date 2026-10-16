"use client";

// Bảng có sắp xếp (TanStack Table). Ô số định dạng theo đơn vị của chỉ số.
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { type ReactNode, useState } from "react";
import { formatByUnit } from "@/lib/format";

export type Col = {
  key: string;
  header: ReactNode;
  unit?: string;
  render?: (row: Record<string, unknown>) => ReactNode;
  align?: "left" | "right";
};

export function DataTable({
  rows,
  columns,
  initialSort,
  rowClassName,
  maxRows,
}: {
  rows: Record<string, unknown>[];
  columns: Col[];
  initialSort?: SortingState;
  rowClassName?: (row: Record<string, unknown>) => string;
  maxRows?: number;
}) {
  const [sorting, setSorting] = useState<SortingState>(initialSort ?? []);
  const defs: ColumnDef<Record<string, unknown>>[] = columns.map((c) => ({
    id: c.key,
    accessorFn: (r) => r[c.key] as unknown,
    header: () => c.header,
    sortingFn: c.unit ? "basic" : "alphanumeric",
    sortUndefined: "last",
    cell: (info) => {
      if (c.render) return c.render(info.row.original);
      const v = info.getValue();
      return c.unit ? formatByUnit(v as number | null, c.unit) : String(v ?? "—");
    },
  }));
  const table = useReactTable({
    data: rows,
    columns: defs,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const all = table.getRowModel().rows;
  const shown = maxRows ? all.slice(0, maxRows) : all;
  return (
    <div className="overflow-x-auto">
      <table className="table">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h, i) => {
                const c = columns[i];
                const right = c?.align === "right" || (c?.unit && c.align !== "left");
                const dir = h.column.getIsSorted();
                return (
                  <th key={h.id} className={right ? "text-right" : ""}>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1"
                      onClick={h.column.getToggleSortingHandler()}
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      <span className="text-xs text-slate-400">
                        {dir === "asc" ? "▲" : dir === "desc" ? "▼" : ""}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.id} className={rowClassName?.(r.original) ?? ""}>
              {r.getVisibleCells().map((cell, i) => {
                const c = columns[i];
                const right = c?.align === "right" || (c?.unit && c.align !== "left");
                return (
                  <td key={cell.id} className={right ? "text-right tabular-nums" : ""}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {maxRows && all.length > maxRows && (
        <p className="mt-2 text-xs text-slate-500">
          Hiện {maxRows}/{all.length} dòng. Xuất CSV để xem đủ.
        </p>
      )}
    </div>
  );
}
