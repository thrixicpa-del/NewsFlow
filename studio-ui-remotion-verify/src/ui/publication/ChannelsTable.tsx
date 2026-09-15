import type { ColumnDef } from "@tanstack/react-table";
import { MoreHorizontal } from "lucide-react";
import { Badge } from "../components/badge";
import { DataTable } from "../components/data-table";
import { UiButton } from "../components/button";
import type { ChannelRow } from "./types";

export function ChannelsTable({ rows, onEdit }: { rows: ChannelRow[]; onEdit(row: ChannelRow): void }) {
  const columns: ColumnDef<ChannelRow>[] = [{ accessorKey: "name", header: "Канал", cell: ({ row }) => <div><b>{row.original.name}</b><small>{row.original.subscribers} подписчиков</small></div> }, { id: "oauth", header: "OAuth", cell: ({ row }) => <Badge tone={row.original.oauthConnected ? "success" : "warning"}>{row.original.oauthConnected ? "Подключён" : "Нужен вход"}</Badge> }, { id: "monetized", header: "Монетизация", cell: ({ row }) => row.original.monetized ? "Да" : "Нет" }, { accessorKey: "quota", header: "Квота" }, { id: "first", header: "Первый выход", cell: ({ row }) => <small>{row.original.firstPublishAt || "Не задан"}</small> }, { id: "interval", header: "Интервал", cell: ({ row }) => `${row.original.intervalMinutes} мин` }, { accessorKey: "publishMode", header: "Режим", cell: ({ row }) => row.original.publishMode === "schedule" ? "Расписание" : "Сразу" }, { id: "action", header: "Действия", cell: ({ row }) => <UiButton variant="ghost" size="icon" aria-label={`Действия канала ${row.original.name}`} title="Настройки канала" onClick={() => onEdit(row.original)}><MoreHorizontal size={17}/></UiButton> }];
  return <section className="nf-workspace-panel"><DataTable data={rows} columns={columns} /></section>;
}
