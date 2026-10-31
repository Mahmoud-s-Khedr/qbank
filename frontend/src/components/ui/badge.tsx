import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
        success:
          "border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
        warning:
          "border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-300",
        info: "border-blue-500/30 bg-blue-500/15 text-blue-700 dark:text-blue-300",
        destructive:
          "border-red-500/30 bg-red-500/15 text-red-700 dark:text-red-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export type BadgeProps = ComponentProps<"span"> &
  VariantProps<typeof badgeVariants>;

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span
      data-slot="badge"
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}
