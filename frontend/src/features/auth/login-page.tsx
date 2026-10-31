import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
import { z } from "zod";
import { ApiError } from "@/api/client";
import { type LoginIn, useLogin } from "@/api/hooks/auth";
import { LanguageSwitch } from "@/app/language-switch";
import { ThemeToggle } from "@/app/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getSafeNextPath } from "@/lib/format";

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const loginMutation = useLogin();
  const [serverErrorKey, setServerErrorKey] = useState<
    "invalidCredentials" | "generic" | null
  >(null);

  const schema = useMemo(
    () =>
      z.object({
        email: z
          .string()
          .trim()
          .min(1, { error: t("auth.login.errors.emailRequired") })
          .pipe(z.email({ error: t("auth.login.errors.emailInvalid") })),
        password: z
          .string()
          .min(1, { error: t("auth.login.errors.passwordRequired") }),
      }),
    [t],
  );

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginIn>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  const isLoading = isSubmitting || loginMutation.isPending;

  const onSubmit = async (values: LoginIn) => {
    setServerErrorKey(null);
    try {
      await loginMutation.mutateAsync(values);
      const destination = getSafeNextPath(searchParams.get("next"), "/sources");
      await navigate(destination, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "invalid_credentials") {
        setServerErrorKey("invalidCredentials");
      } else {
        setServerErrorKey("generic");
      }
    }
  };

  return (
    <div className="bg-background text-foreground flex min-h-screen flex-col">
      <header className="border-border bg-card flex h-14 items-center justify-between border-b px-4">
        <span className="text-base font-semibold tracking-tight">
          {t("app.brand")}
        </span>
        <div className="flex items-center gap-2">
          <LanguageSwitch />
          <ThemeToggle />
        </div>
      </header>

      <main
        id="main-content"
        className="flex flex-1 items-center justify-center p-4"
      >
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-xl font-bold">
              <h1>{t("auth.login.title")}</h1>
            </CardTitle>
            <CardDescription>{t("auth.login.subtitle")}</CardDescription>
          </CardHeader>

          <CardContent>
            <form
              noValidate
              onSubmit={(event) => {
                void handleSubmit(onSubmit)(event);
              }}
              className="flex flex-col gap-4"
            >
              {serverErrorKey ? (
                <div
                  role="alert"
                  aria-live="assertive"
                  data-testid="login-error"
                  className="border-destructive/30 bg-destructive/10 text-destructive flex items-center gap-2 rounded-md border px-3 py-2 text-sm"
                >
                  <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
                  <span>{t(`auth.login.errors.${serverErrorKey}`)}</span>
                </div>
              ) : null}

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="login-email">
                  {t("auth.login.emailLabel")}
                </Label>
                <Input
                  id="login-email"
                  type="email"
                  dir="ltr"
                  autoComplete="email"
                  placeholder={t("auth.login.emailPlaceholder")}
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={
                    errors.email ? "login-email-error" : undefined
                  }
                  disabled={isLoading}
                  {...register("email")}
                />
                {errors.email?.message ? (
                  <p
                    id="login-email-error"
                    role="alert"
                    className="text-destructive text-xs"
                  >
                    {errors.email.message}
                  </p>
                ) : null}
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="login-password">
                  {t("auth.login.passwordLabel")}
                </Label>
                <Input
                  id="login-password"
                  type="password"
                  dir="ltr"
                  autoComplete="current-password"
                  placeholder={t("auth.login.passwordPlaceholder")}
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={
                    errors.password ? "login-password-error" : undefined
                  }
                  disabled={isLoading}
                  {...register("password")}
                />
                {errors.password?.message ? (
                  <p
                    id="login-password-error"
                    role="alert"
                    className="text-destructive text-xs"
                  >
                    {errors.password.message}
                  </p>
                ) : null}
              </div>

              <Button
                type="submit"
                disabled={isLoading}
                className="mt-2 w-full"
              >
                {isLoading
                  ? t("auth.login.submitting")
                  : t("auth.login.submit")}
              </Button>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
