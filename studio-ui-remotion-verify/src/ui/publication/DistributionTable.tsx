import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Lock, Unlock } from "lucide-react";
import { Badge } from "../components/badge";
import { DataTable } from "../components/data-table";
import type { ChannelRow, DistributionRow } from "./types";

const distributionReason = (reason: string) => ({
  auto: "Автораспределение",
  balanced: "Равномерно по заполнению квоты",
  longest_monetized: "Длинный ролик → монетизированный канал",
  ordered: "По порядку производственной партии",
  manual_locked: "Ручное назначение",
  confirmed_snapshot: "Уже подтверждено — защищено от перераспределения",
  quota_exhausted: "Нет свободной квоты у выбранных каналов",
  eligibility_mismatch: "Не подходит диапазон номера/длительности канала",
}[reason] || reason || "—");

export function DistributionTable({ rows, channels, onChange }: { rows: DistributionRow[]; channels: ChannelRow[]; onChange(id: string, patch: Partial<DistributionRow>): void }) {
  const columns = useMemo<ColumnDef<DistributionRow>[]>(() => [{ accessorKey: "title", header: "Ролик", cell: ({ row }) => <div><b>{row.original.title}</b><small>{row.original.duration}</small></div> }, { id: "channel", header: "Канал", cell: ({ row }) => <select aria-label={`Канал для ${row.original.title}`} value={row.original.channelId} onChange={(event) => onChange(row.original.productionItemId, { channelId: event.target.value, channelName: channels.find((channel) => channel.channelId === event.target.value)?.name || event.target.value, source: "manual", locked: true })}><option value="">Не назначен</option>{channels.filter((channel) => channel.enabled).map((channel) => <option value={channel.channelId} key={channel.channelId}>{channel.name}</option>)}</select> }, { id: "time", header: "Время выхода", cell: ({ row }) => <input aria-label={`Время ${row.original.title}`} type="datetime-local" step="900" value={row.original.publishAt ? row.original.publishAt.slice(0, 16) : ""} onChange={(event) => onChange(row.original.productionItemId, { publishAt: event.target.value ? `${event.target.value}:00` : "", source: "manual", locked: true })}/> }, { id: "reason", header: "Причина", cell: ({ row }) => <small>{distributionReason(row.original.reason)}</small> }, { id: "type", header: "Тип", cell: ({ row }) => <Badge tone={row.original.locked ? "warning" : "info"}>{row.original.locked ? <><Lock size={12}/>LOCKED</> : <><Unlock size={12}/>AUTO</>}</Badge> }, { id: "conflict", header: "Конфликт", cell: ({ row }) => row.original.warning ? <Badge tone="danger">{row.original.warning}</Badge> : <span className="nf-ok">—</span> }, { id: "suggestion", header: "Что сделать", cell: ({ row }) => row.original.suggestion ? <small className="nf-conflict-suggestion">{row.original.suggestion}</small> : <span className="nf-ok">—</span> }], [channels, onChange]);
  return <section className="nf-workspace-panel"><DataTable data={rows} columns={columns} preferenceKey="publication-distribution" ariaLabel="Распределение роликов" /></section>;
}
