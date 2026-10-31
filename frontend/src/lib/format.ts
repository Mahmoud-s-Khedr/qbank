export function formatCostUsd(cost: number | null | undefined): string {
  const safeCost = typeof cost === "number" && Number.isFinite(cost) ? cost : 0;
  return `$${safeCost.toFixed(4)}`;
}

const TIME_DIVISIONS: readonly {
  amount: number;
  unit: Intl.RelativeTimeFormatUnit;
}[] = [
  { amount: 60, unit: "second" },
  { amount: 60, unit: "minute" },
  { amount: 24, unit: "hour" },
  { amount: 7, unit: "day" },
  { amount: 4.34524, unit: "week" },
  { amount: 12, unit: "month" },
  { amount: Number.POSITIVE_INFINITY, unit: "year" },
];

export function formatRelativeTime(
  isoDate: string,
  lang: string,
  nowMs: number = Date.now(),
): string {
  const timestamp = Date.parse(isoDate);
  if (Number.isNaN(timestamp)) {
    return isoDate;
  }

  let duration = (timestamp - nowMs) / 1000;
  const rtf = new Intl.RelativeTimeFormat(lang.startsWith("en") ? "en" : "ar", {
    numeric: "auto",
  });

  for (const division of TIME_DIVISIONS) {
    if (Math.abs(duration) < division.amount) {
      return rtf.format(Math.round(duration), division.unit);
    }
    duration /= division.amount;
  }

  return isoDate;
}

/**
 * Ensures the `next` redirect parameter is a safe, same-origin relative path.
 * Rejects external URLs, protocol-relative URLs (`//...`), backslash tricks (`/\...`),
 * and paths pointing back to `/login`.
 */
export function getSafeNextPath(
  next: string | null | undefined,
  fallback = "/sources",
): string {
  if (!next || typeof next !== "string") {
    return fallback;
  }
  const trimmed = next.trim();
  if (
    !trimmed.startsWith("/") ||
    trimmed.startsWith("//") ||
    trimmed.startsWith("/\\")
  ) {
    return fallback;
  }
  try {
    const baseOrigin =
      typeof window !== "undefined" && window.location.origin
        ? window.location.origin
        : "http://localhost";
    const resolved = new URL(trimmed, baseOrigin);
    if (resolved.origin !== baseOrigin) {
      return fallback;
    }
    if (resolved.pathname === "/login") {
      return fallback;
    }
    return `${resolved.pathname}${resolved.search}${resolved.hash}`;
  } catch {
    return fallback;
  }
}

export function stripFileExtension(filename: string): string {
  const trimmed = filename.trim();
  const withoutExt = trimmed.replace(/\.[^/.]+$/, "");
  return withoutExt.length > 0 ? withoutExt : trimmed;
}
