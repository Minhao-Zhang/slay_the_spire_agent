/** en-US digit grouping (e.g. 1,234) for dashboard readouts. */
const EN = "en-US" as const;

export function fmtIntEn(n: number): string {
  return Math.round(n).toLocaleString(EN);
}

/** Like fmtIntEn but truncates toward zero (histogram bin edges). */
export function fmtTruncIntEn(n: number): string {
  return Math.trunc(n).toLocaleString(EN);
}

export function fmtNumEn(
  n: number | null | undefined,
  fracDigits = 0,
): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString(EN, {
    maximumFractionDigits: fracDigits,
    minimumFractionDigits: fracDigits,
  });
}

export function tickFmtIntEn(v: number | string): string {
  const n = typeof v === "number" ? v : Number(String(v).replace(/,/g, ""));
  if (!Number.isFinite(n)) return String(v);
  return Math.round(n).toLocaleString(EN);
}

export function tickFmtNumberEn(v: number | string): string {
  const n = typeof v === "number" ? v : Number(String(v).replace(/,/g, ""));
  if (!Number.isFinite(n)) return String(v);
  return n.toLocaleString(EN, { maximumFractionDigits: 6 });
}

/**
 * Format game/header stats: plain integers, x/y pairs, or pass-through for
 * non-numeric strings (e.g. class name).
 */
export function fmtGameStatDisplay(s: unknown): string {
  if (s === null || s === undefined) return "—";
  if (typeof s === "number" && Number.isFinite(s)) {
    return Number.isInteger(s) ? fmtIntEn(s) : fmtNumEn(s, 4);
  }
  const str = String(s).trim();
  if (!str || str === "—") return str || "—";
  const parts = str.split("/");
  if (parts.length === 1) {
    const raw = str.replace(/,/g, "");
    if (!/^-?[\d.]+$/.test(raw)) return str;
    const n = Number(raw);
    if (!Number.isFinite(n)) return str;
    return Number.isInteger(n)
      ? fmtIntEn(n)
      : n.toLocaleString(EN, { maximumFractionDigits: 4 });
  }
  return parts
    .map((p) => {
      const t = p.trim().replace(/,/g, "");
      if (!/^-?[\d.]+$/.test(t)) return p.trim();
      const n = Number(t);
      if (!Number.isFinite(n)) return p.trim();
      return Number.isInteger(n)
        ? fmtIntEn(n)
        : n.toLocaleString(EN, { maximumFractionDigits: 4 });
    })
    .join("/");
}

export function fmtUnknownNumericOrText(s: unknown, fallback = "—"): string {
  if (s === null || s === undefined) return fallback;
  if (typeof s === "number" && Number.isFinite(s)) {
    return Number.isInteger(s) ? fmtIntEn(s) : fmtNumEn(s, 4);
  }
  const str = String(s).trim();
  if (!str) return fallback;
  return fmtGameStatDisplay(str);
}

/** Integer-like fields from JSON (event_index, counts, …). */
export function fmtFiniteIntLikeEn(v: unknown): string {
  if (typeof v === "number" && Number.isFinite(v)) return fmtIntEn(v);
  const n = Number(v);
  if (Number.isFinite(n)) return fmtIntEn(Math.round(n));
  return String(v ?? "—");
}
