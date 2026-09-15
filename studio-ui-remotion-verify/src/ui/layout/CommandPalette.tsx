import { useMemo, useState } from "react";
import { Dialog } from "../components/dialog";
import { Input } from "../components/input";
import type { WorkspaceSearchItem } from "./workspace-search";

export function CommandPalette({ open, onOpenChange, onNavigate, items }: { open: boolean; onOpenChange(open: boolean): void; onNavigate(page: WorkspaceSearchItem["page"]): void; items: WorkspaceSearchItem[] }) {
  const [query, setQuery] = useState("");
  const visible = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return (normalized ? items.filter((item) => `${item.kind} ${item.title}`.toLocaleLowerCase().includes(normalized)) : items).slice(0, 12);
  }, [items, query]);
  const navigate = (item: WorkspaceSearchItem) => {
    onNavigate(item.page);
    onOpenChange(false);
    setQuery("");
  };
  return <Dialog open={open} onOpenChange={onOpenChange} title="Перейти в NewsFlow" description="Поиск по текущему snapshot. Команды запуска задач здесь не выполняются.">
    <div className="nf-command-palette">
      <Input label="Поиск по NewsFlow" value={query} onChange={(event) => setQuery(event.target.value)} autoFocus placeholder="Topic, Script, MP3, Cover, Montage, receipt…" />
      <div role="listbox" aria-label="Результаты поиска">
        {visible.length ? visible.map((item) => <button key={item.id} type="button" role="option" onClick={() => navigate(item)}><span>{item.kind}</span><b>{item.title}</b></button>) : <p>Ничего не найдено в текущем состоянии.</p>}
      </div>
    </div>
  </Dialog>;
}
