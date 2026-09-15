import { cn } from "./cn";

export type TabItem<T extends string> = { id: T; label: string; count?: number };
export function Tabs<T extends string>({ items, value, onChange }: { items: TabItem<T>[]; value: T; onChange(value: T): void }) {
  return <div className="nf-tabs" role="tablist">{items.map((item) => <button key={item.id} role="tab" aria-label={item.label} aria-selected={value === item.id} className={cn("nf-tab", value === item.id && "active")} onClick={() => onChange(item.id)}>{item.label}{item.count !== undefined ? <span aria-hidden="true">{item.count}</span> : null}</button>)}</div>;
}
