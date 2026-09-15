import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

const variants = cva("nf-button", {
  variants: { variant: { primary: "nf-button-primary", secondary: "nf-button-secondary", success: "nf-button-success", ghost: "nf-button-ghost", destructive: "nf-button-destructive" }, size: { sm: "nf-button-sm", md: "", icon: "nf-button-icon" } },
  defaultVariants: { variant: "secondary", size: "md" },
});

export function Button({ className, variant, size, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof variants> & { children: ReactNode }) {
  return <button className={cn(variants({ variant, size }), className)} {...props}>{children}</button>;
}

// Kept as a compatibility alias while screens move off their legacy controls.
export const UiButton = Button;
