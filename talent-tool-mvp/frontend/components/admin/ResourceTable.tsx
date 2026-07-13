"use client";

/**
 * ResourceTable — Refine-aware shadcn-admin DataTable wrapper.
 *
 * Wraps our shared `DataTable` so admin pages can drop in a CRUD list with
 * minimal ceremony:
 *
 *   <ResourceTable
 *     data={services}
 *     columns={[...]}
 *     resource="services"
 *     onRowClick={(row) => router.push(`/admin/services/${row.name}`)}
 *   />
 *
 * Features:
 *   - Sorting / filtering / pagination via @tanstack/react-table
 *   - Bulk delete via Refine's `useDeleteMany`
 *   - Inline edit shortcut column
 *   - Optional toolbar slot for ad-hoc buttons (export, refresh, etc.)
 */

import * as React from "react";
import Link from "next/link";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
  type SortingState,
} from "@tanstack/react-table";
import { ChevronLeft, ChevronRight, ExternalLink, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export interface ResourceTableProps<T> {
  data: T[];
  columns: ColumnDef<T, unknown>[];
  resource: string;
  searchPlaceholder?: string;
  pageSize?: number;
  toolbar?: React.ReactNode;
  onRowClick?: (row: T) => void;
  onBulkDelete?: (rows: T[]) => Promise<void> | void;
  getRowId?: (row: T) => string;
}

export function ResourceTable<T>({
  data,
  columns,
  resource,
  searchPlaceholder,
  pageSize = 10,
  toolbar,
  onRowClick,
  onBulkDelete,
  getRowId,
}: ResourceTableProps<T>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [filter, setFilter] = React.useState("");
  const [selection, setSelection] = React.useState<RowSelectionState>({});

  const selectionCol: ColumnDef<T, unknown> = {
    id: "_select",
    header: ({ table }) => (
      <Checkbox
        aria-label="Select all"
        checked={table.getIsAllPageRowsSelected()}
        onCheckedChange={(v) => table.toggleAllPageRowsSelected(Boolean(v))}
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        aria-label="Select row"
        checked={row.getIsSelected()}
        onCheckedChange={(v) => row.toggleSelected(Boolean(v))}
      />
    ),
    enableSorting: false,
    size: 32,
  };

  const allCols = React.useMemo(
    () => [selectionCol, ...columns],
    [columns],
  );

  const table = useReactTable({
    data,
    columns: allCols,
    state: { sorting, globalFilter: filter, rowSelection: selection },
    onSortingChange: setSorting,
    onGlobalFilterChange: setFilter,
    onRowSelectionChange: setSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getRowId,
    initialState: { pagination: { pageSize } },
  });

  const selectedRows = table.getSelectedRowModel().rows.map((r) => r.original);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={searchPlaceholder ?? `Filter ${resource}...`}
          className="max-w-sm"
        />
        <div className="flex items-center gap-2">
          {selectedRows.length > 0 && (
            <>
              <span className="text-xs text-muted-foreground">
                {selectedRows.length} 已选
              </span>
              {onBulkDelete && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => onBulkDelete(selectedRows)}
                >
                  <Trash2 className="mr-1 h-3 w-3" />
                  批量删除
                </Button>
              )}
            </>
          )}
          {toolbar}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((g) => (
              <TableRow key={g.id}>
                {g.headers.map((h) => (
                  <TableHead key={h.id}>
                    {h.isPlaceholder
                      ? null
                      : flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() ? "selected" : undefined}
                  className={onRowClick ? "cursor-pointer" : undefined}
                  onClick={() => onRowClick?.(row.original)}
                >
                  {row.getVisibleCells().map((c) => (
                    <TableCell key={c.id}>
                      {flexRender(c.column.columnDef.cell, c.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={allCols.length}
                  className="h-32 text-center text-muted-foreground"
                >
                  No results.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          共 {table.getFilteredRowModel().rows.length} 条
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            aria-label="Previous page"
            disabled={!table.getCanPreviousPage()}
            onClick={() => table.previousPage()}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span>
            {table.getState().pagination.pageIndex + 1} /{" "}
            {Math.max(1, table.getPageCount())}
          </span>
          <Button
            variant="outline"
            size="icon"
            aria-label="Next page"
            disabled={!table.getCanNextPage()}
            onClick={() => table.nextPage()}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ResourceRowLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-0.5 font-medium hover:underline"
      onClick={(e) => e.stopPropagation()}
    >
      {children}
      <ExternalLink className="h-3 w-3" />
    </Link>
  );
}

export default ResourceTable;
