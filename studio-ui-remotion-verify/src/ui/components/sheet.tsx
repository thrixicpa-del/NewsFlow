import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

export function Sheet({ open, onOpenChange, title, description, children }: { open: boolean; onOpenChange(open: boolean): void; title: string; description?: string; children: ReactNode }) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="nf-sheet-overlay" /><Dialog.Content className="nf-sheet-content">
    <header className="nf-sheet-header"><div><Dialog.Title>{title}</Dialog.Title>{description ? <Dialog.Description>{description}</Dialog.Description> : null}</div><Dialog.Close className="nf-icon-button" aria-label="Закрыть"><X size={18} /></Dialog.Close></header>
    <div className="nf-sheet-body">{children}</div>
  </Dialog.Content></Dialog.Portal></Dialog.Root>;
}
