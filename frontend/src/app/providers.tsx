import { DirectionProvider } from "@radix-ui/react-direction";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { getDirection } from "@/i18n";
import { ThemeProvider } from "@/lib/theme";

function createDefaultQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
      },
    },
  });
}

export interface AppProvidersProps {
  children: ReactNode;
  queryClient?: QueryClient | undefined;
}

export function AppProviders({ children, queryClient }: AppProvidersProps) {
  const [defaultClient] = useState(createDefaultQueryClient);
  const { i18n } = useTranslation();
  const dir = getDirection(i18n.language);

  return (
    <QueryClientProvider client={queryClient ?? defaultClient}>
      <ThemeProvider>
        <DirectionProvider dir={dir}>
          <TooltipProvider>
            {children}
            <Toaster />
          </TooltipProvider>
        </DirectionProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
