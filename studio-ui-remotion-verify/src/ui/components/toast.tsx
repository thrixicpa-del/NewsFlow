export type ToastTone = "info" | "success" | "warning" | "danger";
export function Toast({ message, tone = "info", onDismiss }: { message: string; tone?: ToastTone; onDismiss?(): void }) {
  return <div className={`nf-toast nf-toast-${tone}`} role="status" aria-live="polite"><span>{message}</span>{onDismiss ? <button aria-label="Закрыть уведомление" onClick={onDismiss}>×</button> : null}</div>;
}
