import * as DialogPrimitive from "@radix-ui/react-dialog";
import type { ReactNode } from "react";
import { IconButton } from "./icon-button";

export function Dialog({ open, onOpenChange, title, description, children }: { open: boolean; onOpenChange(open: boolean): void; title: string; description?: string; children: ReactNode }) {
  return <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}><DialogPrimitive.Portal><DialogPrimitive.Overlay className="nf-dialog-overlay" /><DialogPrimitive.Content className="nf-dialog-content"><header><div><DialogPrimitive.Title>{title}</DialogPrimitive.Title>{description ? <DialogPrimitive.Description>{description}</DialogPrimitive.Description> : null}</div><DialogPrimitive.Close asChild><IconButton label="Закрыть">×</IconButton></DialogPrimitive.Close></header><div className="nf-dialog-body">{children}</div></DialogPrimitive.Content></DialogPrimitive.Portal></DialogPrimitive.Root>;
}
