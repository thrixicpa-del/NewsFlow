import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Button } from "./button";

export function AlertDialog({ open, onOpenChange, title, description, confirmLabel, onConfirm }: { open: boolean; onOpenChange(open: boolean): void; title: string; description: string; confirmLabel: string; onConfirm(): void }) {
  return <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}><DialogPrimitive.Portal><DialogPrimitive.Overlay className="nf-dialog-overlay" /><DialogPrimitive.Content role="alertdialog" className="nf-alert-dialog"><DialogPrimitive.Title>{title}</DialogPrimitive.Title><DialogPrimitive.Description>{description}</DialogPrimitive.Description><footer><DialogPrimitive.Close asChild><Button variant="secondary">Отмена</Button></DialogPrimitive.Close><Button variant="destructive" onClick={onConfirm}>{confirmLabel}</Button></footer></DialogPrimitive.Content></DialogPrimitive.Portal></DialogPrimitive.Root>;
}
