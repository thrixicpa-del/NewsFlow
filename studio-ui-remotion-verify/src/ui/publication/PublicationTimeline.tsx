import { stageLabel } from "./view-model";
import type { QueueRow } from "./types";

export function PublicationTimeline({ events }: { events: QueueRow["timeline"] }) {
  return <div className="nf-timeline"><small>ХОД ПУБЛИКАЦИИ</small>{events.length ? events.map((event, index) => <p key={`${event.at}-${index}`}><time>{event.at || "—"}</time>{event.detail || `${stageLabel(String(event.stage || ""))}: ${event.status || ""}`}</p>) : <p>События появятся после запуска.</p>}</div>;
}
