import type { ReactNode } from "react";

export function PageHeader({ eyebrow, title, description, actions, meta }: { eyebrow?: string; title: ReactNode; description?: string; actions?: ReactNode; meta?: ReactNode }) {
  return <header className="nf-page-header"><div>{eyebrow ? <span className="nf-eyebrow">{eyebrow}</span> : null}<h1>{title}</h1>{description ? <p>{description}</p> : null}</div>{actions ? <div className="nf-page-header-actions">{actions}</div> : null}{meta ? <div className="nf-page-header-meta">{meta}</div> : null}</header>;
}
