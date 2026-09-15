import type { ReactNode } from "react";

export function StatCard({ label, value, tone = "neutral", icon }: { label: string; value: ReactNode; tone?: "neutral" | "success" | "warning" | "danger" | "info"; icon?: ReactNode }) {
  return <article className={`nf-stat-card nf-stat-${tone}`}>{icon ? <span aria-hidden="true">{icon}</span> : null}<div><b>{value}</b><small>{label}</small></div></article>;
}
