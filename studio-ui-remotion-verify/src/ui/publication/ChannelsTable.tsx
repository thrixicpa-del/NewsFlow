import type { ColumnDef } from "@tanstack/react-table";
import { MoreHorizontal } from "lucide-react";
import { Badge } from "../components/badge";
import { DataTable } from "../components/data-table";
import { UiButton } from "../components/button";
import type { ChannelRow } from "./types";

export function ChannelsTable({ rows, onEdit }: { rows: ChannelRow[]; onEdit(row: ChannelRow): void }) {
  const columns: ColumnDef<ChannelRow>[] = [
    { id: "number", header: "№", cell: ({ row }) => <span className="nf-number">Канал {row.original.number}</span> },
    { accessorKey: "name", header: "Канал", cell: ({ row }) => <div><b>{row.original.name}</b><small>{row.original.subscribers} подписчиков</small></div> },
    { id: "oauth", header: "OAuth", cell: ({ row }) => <Badge tone={row.original.oauthConnected ? "success" : "warning"}>{row.original.oauthConnected ? "Подключён" : "Нужен вход"}</Badge> },
    { id: "monetized", header: "Монетизация", cell: ({ row }) => <Badge tone={row.original.monetized ? "success" : "neutral"}>{row.original.monetized ? "Вкл" : "Нет"}</Badge> },
    { accessorKey: "quota", header: "Квота" },
    { accessorKey: "channelPriority", header: "Приоритет" },
    { id: "range", header: "Диапазон", cell: ({ row }) => <small>{row.original.orderStart || row.original.orderEnd ? `${row.original.orderStart || 1}–${row.original.orderEnd || "∞"}` : "Все"}</small> },
    { id: "duration", header: "Длительность", cell: ({ row }) => <small>{row.original.minDurationSeconds || row.original.maxDurationSeconds ? `${row.original.minDurationSeconds || 0}–${row.original.maxDurationSeconds || "∞"} сек` : "Любая"}</small> },
    { id: "first", header: "Первый выход", cell: ({ row }) => <small>{row.original.firstPublishAt || "Не задан"}</small> },
    { id: "interval", header: "Интервал", cell: ({ row }) => `${row.original.intervalMinutes} мин` },
    { id: "ads", header: "Реклама", cell: ({ row }) => <Badge tone={row.original.monetized && row.original.automation.ads ? "info" : "neutral"}>{row.original.monetized && row.original.automation.ads ? "AUTO + 39s" : "Нет"}</Badge> },
    { accessorKey: "publishMode", header: "Режим", cell: ({ row }) => row.original.publishMode === "schedule" ? "Расписание" : "Сразу" },
    { id: "action", header: "Действия", cell: ({ row }) => <UiButton variant="ghost" size="icon" aria-label={`Действия канала ${row.original.name}`} title="Настройки канала" onClick={() => onEdit(row.original)}><MoreHorizontal size={17}/></UiButton> },
  ];
  return <section className="nf-workspace-panel"><DataTable data={rows} columns={columns} preferenceKey="publication-channels" ariaLabel="Каналы публикации" /></section>;
}
