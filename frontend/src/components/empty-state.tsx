import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  children?: ReactNode | undefined;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  children,
}: EmptyStateProps) {
  return (
    <Card className="border-dashed">
      <CardHeader className="items-center text-center">
        <div className="bg-muted text-muted-foreground mb-2 flex size-12 items-center justify-center rounded-full">
          <Icon className="size-6" aria-hidden="true" />
        </div>
        <CardTitle className="text-lg">{title}</CardTitle>
        <CardDescription className="font-content max-w-md text-base">
          {description}
        </CardDescription>
      </CardHeader>
      {children ? (
        <CardContent className="flex justify-center">{children}</CardContent>
      ) : null}
    </Card>
  );
}
