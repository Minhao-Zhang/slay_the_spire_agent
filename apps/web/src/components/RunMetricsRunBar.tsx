import { Link } from "react-router-dom";

import { fmtIntEn } from "../lib/formatDisplayNumber";

export type RunMetricsRunBarProps = {
  runs: string[];
  run: string;
  onRunChange: (run: string) => void;
  loading: boolean;
  frameCount: number | null;
  recordsLength?: number;
  /** When metrics fetch failed, e.g. `no_metrics_file`. */
  metricsReason?: string | null;
  variant: "metrics" | "debug" | "map";
  mapLoading?: boolean;
  mapError?: string | null;
};

function metricsReasonLabel(reason: string): string {
  if (reason === "no_metrics_file") {
    return "No run_metrics.ndjson for this run.";
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

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-slate-700/90 bg-slate-900/80 px-4 py-3 backdrop-blur-sm">
      <Link
        to="/"
        className="font-console text-xs font-semibold uppercase tracking-wide text-sky-400 hover:text-sky-300"
      >
        ← Monitor
      </Link>

      {variant === "metrics" ? (
        <>
          <span className="font-console text-sm font-bold tracking-[0.12em] text-slate-100">
            RUN METRICS
          </span>
          <Link
            to={`/metrics/debug${runQ}`}
            className="font-console text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-300"
          >
            Debug
          </Link>
          <Link
            to={`/metrics/map${runQ}`}
            className="font-console text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-300"
          >
            Run map
          </Link>
        </>
      ) : null}

      {variant === "debug" ? (
        <>
          <Link
            to={run ? `/metrics${runQ}` : "/metrics"}
            className="font-console text-xs font-semibold uppercase tracking-wide text-sky-400 hover:text-sky-300"
          >
            ← Run metrics
          </Link>
          <span className="font-console text-sm font-bold tracking-[0.12em] text-slate-100">
            METRICS DEBUG
          </span>
          <Link
            to={`/metrics/map${runQ}`}
            className="font-console text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-300"
          >
            Run map
          </Link>
        </>
      ) : null}

      {variant === "map" ? (
        <>
          <Link
            to={run ? `/metrics${runQ}` : "/metrics"}
            className="font-console text-xs font-semibold uppercase tracking-wide text-sky-400 hover:text-sky-300"
          >
            ← Run metrics
          </Link>
          <span className="font-console text-sm font-bold tracking-[0.12em] text-slate-100">
            RUN MAP
          </span>
          <Link
            to={`/metrics/debug${runQ}`}
            className="font-console text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-300"
          >
            Debug
          </Link>
        </>
      ) : null}

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
