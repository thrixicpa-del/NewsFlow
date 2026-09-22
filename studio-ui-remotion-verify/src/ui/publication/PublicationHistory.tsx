import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { ExternalLink } from "lucide-react";
import { Badge } from "../components/badge";
import { DataTable } from "../components/data-table";
import { Sheet } from "../components/sheet";
import type { ReceiptRow } from "./types";

function adHistoryLabel(row: ReceiptRow) {
  const mode = String(row.ads?.mode || "").toUpperCase();
  const status = String(row.ads?.status || "").toUpperCase();
  if (mode === "AUTO+MANUAL") return { label: "AUTO + MANUAL 39s", tone: status === "SUCCESS" ? "success" as const : "warning" as const };
  if (mode === "AUTO_ONLY") return { label: "AUTO ONLY", tone: "info" as const };
  if (mode === "NONE" || status === "NOT_REQUIRED" || status === "SKIPPED") return { label: "NONE", tone: "neutral" as const };
  if (status === "FAILED") return { label: "ОШИБКА", tone: "danger" as const };
  return { label: "ОЖИДАЕТ", tone: "warning" as const };
}

export function PublicationHistory({ rows }: { rows: ReceiptRow[] }) {
  const [selected, setSelected] = useState<ReceiptRow | null>(null);
  const columns: ColumnDef<ReceiptRow>[] = [{ accessorKey: "title", header: "Ролик", cell: ({ row }) => <button className="nf-history-title" onClick={() => setSelected(row.original)}>{row.original.title}</button> }, { accessorKey: "channelName", header: "Канал" }, { id: "youtube", header: "YouTube", cell: ({ row }) => row.original.youtubeVideoUrl ? <a href={row.original.youtubeVideoUrl} target="_blank" rel="noreferrer">Открыть <ExternalLink size={13}/></a> : "—" }, { accessorKey: "requestedPublishAt", header: "Запланирован" }, { id: "ads", header: "Реклама", cell: ({ row }) => { const value = adHistoryLabel(row.original); return <Badge tone={value.tone}>{value.label}</Badge>; } }, { accessorKey: "completion", header: "Оформление" }, { accessorKey: "finalStatus", header: "Итог", cell: ({ row }) => <Badge tone={row.original.finalStatus === "DONE" ? "success" : "warning"}>{row.original.finalStatus}</Badge> }, { accessorKey: "duration", header: "Duration" }];
  return <section className="nf-workspace-panel">{rows.length ? <DataTable data={rows} columns={columns}/> : <div className="nf-empty-small"><b>История пока пуста</b><span>Receipt появится после подтверждённого выполнения публикации.</span></div>}<ReceiptSheet receipt={selected} onClose={() => setSelected(null)}/></section>;
}

function ReceiptSheet({ receipt, onClose }: { receipt: ReceiptRow | null; onClose(): void }) { if (!receipt) return null; return <Sheet open={Boolean(receipt)} onOpenChange={(open) => !open && onClose()} title={receipt.title} description={`Итог: ${receipt.finalStatus}`}><div className="nf-receipt-meta"><p>Snapshot ID <b>{receipt.snapshotId || "Не получен"}</b></p><p>ProductionItem ID <b>{receipt.productionItemId || "Не получен из текущего snapshot"}</b></p><p>YouTube ID <b>{receipt.youtubeVideoId || "—"}</b></p><p>Канал <b>{receipt.channelName || "Не сообщён текущим snapshot"}</b></p><p>Запрошенное время <b>{receipt.requestedPublishAt || "—"}</b></p><p>Подтверждённое время <b>{receipt.confirmedPublishAt || "UNVERIFIED"}</b></p><p>Длительность <b>{receipt.duration || "Не получена"}</b></p><p>Реклама <b>{adHistoryLabel(receipt).label}</b></p><p>Ручные рекламные слоты <b>{receipt.ads?.confirmedManualSlotsSeconds?.length || 0}/{receipt.ads?.manualSlotsSeconds?.length || 0}</b></p><p>Актуальность <b>Текущий snapshot не сообщает признак устаревания</b></p></div><div className="nf-stage-list">{Object.entries(receipt.stages).map(([stage, state]) => <div key={stage}><span>{stage}</span><Badge tone={state === "SUCCESS" ? "success" : state === "UNVERIFIED" ? "warning" : "neutral"}>{state}</Badge></div>)}</div></Sheet>; }
