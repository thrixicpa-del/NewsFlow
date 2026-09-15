import type { ReactNode } from "react";

function State({ tone, title, description, action }: { tone: string; title: string; description: string; action?: ReactNode }) {
  return <section className={`nf-state nf-state-${tone}`}><div><b>{title}</b><p>{description}</p></div>{action}</section>;
}
export function EmptyState(props: { title: string; description: string; action?: ReactNode }) { return <State tone="empty" {...props} />; }
export function ErrorState(props: { title: string; description: string; action?: ReactNode }) { return <State tone="error" {...props} />; }
export function LoadingState({ label = "Загрузка" }: { label?: string }) { return <div className="nf-loading" role="status" aria-label={label}><i aria-hidden="true" />{label}…</div>; }
