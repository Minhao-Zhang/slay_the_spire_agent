import { fmtIntEn } from "../lib/formatDisplayNumber";
import { SpireAgentNav } from "./SpireAgentNav";

export type RunMetricsRunBarProps = {
  runs: string[];
  run: string;
  onRunChange: (run: string) => void;
  loading: boolean;
  frameCount: number | null;
  recordsLength?: number;
  /** When metrics fetch failed, e.g. `no_metrics_file`. */
  metricsReason?: string | null;
  variant: "metrics" | "map";
  mapLoading?: boolean;
  mapError?: string | null;
};

function metricsReasonLabel(reason: string): string {
  if (reason === "no_metrics_file") {
    return "No run_metrics.ndjson for this run.";
  }
  if (reason === "internal_error") {
    return "Metrics server error; check API logs.";
  }
  if (reason.startsWith("http_")) {
    const code = reason.slice("http_".length);
    return `Metrics request failed (HTTP ${code}). Is the dashboard API running on the Vite proxy target?`;
  }
  if (reason === "invalid_response") {
    return "Metrics response was not in the expected shape.";
  }
  return `Metrics: ${reason}`;
}

export function RunMetricsRunBar({
  runs,
  run,
  onRunChange,
  loading,
  frameCount,
  recordsLength,
  metricsReason,
  variant,
  mapLoading,
  mapError,
}: RunMetricsRunBarProps) {
  const runQ = run ? `?run=${encodeURIComponent(run)}` : "";
  const showFrameRow =
    variant !== "map" &&
    typeof recordsLength === "number" &&
    frameCount !== null;

  const spirePage = variant === "map" ? "map" : "metrics";

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-slate-700/90 bg-slate-900/80 px-4 py-3 backdrop-blur-sm">
      <SpireAgentNav page={spirePage} runQuery={runQ} />

      <label className="flex items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-slate-500">
          Run
        </span>
        <select
          value={run}
          onChange={(e) => onRunChange(e.target.value)}
          className="font-console h-8 max-w-[18rem] rounded border border-slate-700 bg-slate-950/80 px-2 text-xs text-slate-200 outline-none"
          aria-label="Log run"
        >
          <option value="">Select run…</option>
          {runs.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>

      {variant !== "map" && loading ? (
        <span className="text-xs text-slate-500">Loading…</span>
      ) : null}
      {variant === "map" && mapLoading ? (
        <span className="text-xs text-slate-500">Loading map…</span>
      ) : null}

      {variant !== "map" && metricsReason ? (
        <span className="text-xs text-amber-400" title={metricsReason}>
          {metricsReasonLabel(metricsReason)}
        </span>
      ) : null}

      {variant === "map" && mapError ? (
        <span className="text-xs text-amber-400" title={mapError}>
          {mapError}
        </span>
      ) : null}

      {showFrameRow ? (
        <span className="font-telemetry text-xs tabular-nums text-slate-500">
          Frames: {fmtIntEn(frameCount)} · Rows: {fmtIntEn(recordsLength)}
        </span>
      ) : null}

      {variant === "map" && run && frameCount !== null ? (
        <span className="font-telemetry text-xs tabular-nums text-slate-500">
          Frames: {fmtIntEn(frameCount)}
        </span>
      ) : null}
    </header>
  );
}
