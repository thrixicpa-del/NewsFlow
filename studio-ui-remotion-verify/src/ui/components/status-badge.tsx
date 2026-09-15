import { Badge, type BadgeTone } from "./badge";

export type UiJobStatus = "QUEUED" | "PREPARING" | "RUNNING" | "WAITING" | "PAUSED" | "RETRYING" | "READY" | "FAILED" | "CANCELLED";

const labels: Record<UiJobStatus, string> = {
  QUEUED: "В очереди", PREPARING: "Подготовка", RUNNING: "В работе", WAITING: "Ожидает провайдера", PAUSED: "Пауза", RETRYING: "Повтор",
  READY: "Готово", FAILED: "Ошибка", CANCELLED: "Остановлено",
};
const tones: Record<UiJobStatus, BadgeTone> = {
  QUEUED: "neutral", PREPARING: "info", RUNNING: "info", WAITING: "warning", PAUSED: "warning", RETRYING: "warning",
  READY: "success", FAILED: "danger", CANCELLED: "neutral",
};

export function StatusBadge({ status }: { status: UiJobStatus }) {
  return <Badge tone={tones[status]}>{labels[status]}</Badge>;
}
