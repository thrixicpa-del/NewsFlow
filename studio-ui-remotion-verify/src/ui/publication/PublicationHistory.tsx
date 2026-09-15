import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { ExternalLink } from "lucide-react";
import { Badge } from "../components/badge";
import { DataTable } from "../components/data-table";
import { Sheet } from "../components/sheet";
import type { ReceiptRow } from "./types";

export function PublicationHistory({ rows }: { rows: ReceiptRow[] }) {
  const [selected, setSelected] = useState<ReceiptRow | null>(null);
  const columns: ColumnDef<ReceiptRow>[] = [{ accessorKey: "title", header: "Ролик", cell: ({ row }) => <button className="nf-history-title" onClick={() => setSelected(row.original)}>{row.original.title}</button> }, { accessorKey: "channelName", header: "Канал" }, { id: "youtube", header: "YouTube", cell: ({ row }) => row.original.youtubeVideoUrl ? <a href={row.original.youtubeVideoUrl} target="_blank" rel="noreferrer">Открыть <ExternalLink size={13}/></a> : "—" }, { accessorKey: "requestedPublishAt", header: "Запланирован" }, { accessorKey: "completion", header: "Оформление" }, { accessorKey: "finalStatus", header: "Итог", cell: ({ row }) => <Badge tone={row.original.finalStatus === "DONE" ? "success" : "warning"}>{row.original.finalStatus}</Badge> }, { accessorKey: "duration", header: "Duration" }];
  return <section className="nf-workspace-panel">{rows.length ? <DataTable data={rows} columns={columns}/> : <div className="nf-empty-small"><b>История пока пуста</b><span>Receipt появится после подтверждённого выполнения публикации.</span></div>}<ReceiptSheet receipt={selected} onClose={() => setSelected(null)}/></section>;
}

function ReceiptSheet({ receipt, onClose }: { receipt: ReceiptRow | null; onClose(): void }) { if (!receipt) return null; return <Sheet open={Boolean(receipt)} onOpenChange={(open) => !open && onClose()} title={receipt.title} description={`Итог: ${receipt.finalStatus}`}><div className="nf-receipt-meta"><p>Snapshot ID <b>{receipt.snapshotId || "Не получен"}</b></p><p>ProductionItem ID <b>{receipt.productionItemId || "Не получен из текущего snapshot"}</b></p><p>YouTube ID <b>{receipt.youtubeVideoId || "—"}</b></p><p>Канал <b>{receipt.channelName || "Не сообщён текущим snapshot"}</b></p><p>Запрошенное время <b>{receipt.requestedPublishAt || "—"}</b></p><p>Подтверждённое время <b>{receipt.confirmedPublishAt || "UNVERIFIED"}</b></p><p>Длительность <b>{receipt.duration || "Не получена"}</b></p><p>Актуальность <b>Текущий snapshot не сообщает признак устаревания</b></p></div><div className="nf-stage-list">{Object.entries(receipt.stages).map(([stage, state]) => <div key={stage}><span>{stage}</span><Badge tone={state === "SUCCESS" ? "success" : state === "UNVERIFIED" ? "warning" : "neutral"}>{state}</Badge></div>)}</div></Sheet>; }
