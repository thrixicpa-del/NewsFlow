import { Fragment, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { flexRender, getCoreRowModel, getFilteredRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState } from "@tanstack/react-table";
import { cn } from "./cn";
import "./data-table.css";

const TABLE_PREFERENCES_STORAGE_KEY = "newsflow.ui-table-preferences.v1";

type TablePreference = { filter: string; sort: SortingState; columns: Record<string, boolean> };
type TablePreferences = Record<string, TablePreference>;

function loadTablePreference(key?: string): TablePreference {
  if (!key) return { filter: "", sort: [], columns: {} };
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(TABLE_PREFERENCES_STORAGE_KEY) || "{}");
    const preference = parsed && typeof parsed === "object" ? (parsed as TablePreferences)[key] : undefined;
    if (!preference || typeof preference.filter !== "string" || !Array.isArray(preference.sort) || !preference.columns || typeof preference.columns !== "object") return { filter: "", sort: [], columns: {} };
    return preference;
  } catch {
    return { filter: "", sort: [], columns: {} };
  }
}

export function DataTable<T>({ data, columns, getRowClassName, expanded, ariaLabel, onRowActivate, preferenceKey }: { data: T[]; columns: ColumnDef<T>[]; getRowClassName?: (row: T) => string | undefined; expanded?: (row: T) => ReactNode; ariaLabel?: string; onRowActivate?: (row: T) => void; preferenceKey?: string }) {
  const initialPreference = useRef(loadTablePreference(preferenceKey)).current;
  const [globalFilter, setGlobalFilter] = useState(initialPreference.filter);
  const [sorting, setSorting] = useState<SortingState>(initialPreference.sort);
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>(initialPreference.columns);
  useEffect(() => {
    if (!preferenceKey) return;
    try {
      const stored: unknown = JSON.parse(localStorage.getItem(TABLE_PREFERENCES_STORAGE_KEY) || "{}");
      const preferences = stored && typeof stored === "object" ? stored as TablePreferences : {};
      localStorage.setItem(TABLE_PREFERENCES_STORAGE_KEY, JSON.stringify({ ...preferences, [preferenceKey]: { filter: globalFilter, sort: sorting, columns: columnVisibility } }));
    } catch {
      // A blocked or malformed local layout preference must never affect business state.
    }
  }, [columnVisibility, globalFilter, preferenceKey, sorting]);
  const table = useReactTable({ data, columns, state: preferenceKey ? { globalFilter, sorting, columnVisibility } : undefined, onGlobalFilterChange: setGlobalFilter, onSortingChange: setSorting, onColumnVisibilityChange: setColumnVisibility, getCoreRowModel: getCoreRowModel(), getFilteredRowModel: getFilteredRowModel(), getSortedRowModel: getSortedRowModel() });
  const rootRef = useRef<HTMLTableElement>(null);
  const onRowKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, rowIndex: number, row: T) => {
    if (event.key === "Enter") {
      event.preventDefault();
      onRowActivate?.(row);
      return;
    }
    if (event.key === "Delete") {
      event.preventDefault();
      return;
    }
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const nextIndex = Math.min(Math.max(rowIndex + (event.key === "ArrowDown" ? 1 : -1), 0), table.getRowModel().rows.length - 1);
    rootRef.current?.querySelector<HTMLTableRowElement>(`tr[data-nf-row-index="${nextIndex}"]`)?.focus();
  };
  return <div className="nf-table-scroll">{preferenceKey ? <div className="nf-table-preferences" aria-label={`Настройки таблицы: ${ariaLabel || preferenceKey}`}><label>Фильтр: {ariaLabel || preferenceKey}<input aria-label={`Фильтр: ${ariaLabel || preferenceKey}`} value={globalFilter} onChange={(event) => setGlobalFilter(event.target.value)} placeholder="Поиск по таблице" /></label><details><summary>Колонки</summary>{table.getAllLeafColumns().map((column) => <label key={column.id}><input type="checkbox" checked={column.getIsVisible()} onChange={column.getToggleVisibilityHandler()} />{String(column.columnDef.header || column.id)}</label>)}</details></div> : null}<table ref={rootRef} className="nf-table" aria-label={ariaLabel}><thead>{table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.map((header) => <th key={header.id}>{header.isPlaceholder ? null : preferenceKey && header.column.getCanSort() ? <button type="button" onClick={header.column.getToggleSortingHandler()}>{flexRender(header.column.columnDef.header, header.getContext())}</button> : flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}</thead><tbody>{table.getRowModel().rows.map((row, rowIndex) => <Fragment key={row.id}>
    <tr key={row.id} className={cn(getRowClassName?.(row.original))} data-nf-row-index={rowIndex} tabIndex={onRowActivate ? 0 : undefined} onKeyDown={onRowActivate ? (event) => onRowKeyDown(event, rowIndex, row.original) : undefined}>{row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>
    {expanded ? <tr key={`${row.id}-detail`} className="nf-expanded-row"><td colSpan={row.getVisibleCells().length}>{expanded(row.original)}</td></tr> : null}
  </Fragment>)}</tbody></table></div>;
}
