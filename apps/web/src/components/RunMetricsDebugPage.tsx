import { useMemo, type ReactNode } from "react";
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useRunMetricsData } from "../hooks/useRunMetricsData";
import { fmtIntEn, tickFmtIntEn } from "../lib/formatDisplayNumber";
import { deriveAiRows } from "../lib/runMetricsDerive";
import { RunMetricsRunBar } from "./RunMetricsRunBar";

const CHART_H = 220;
const SLATE_AXIS = { stroke: "#64748b", fontSize: 11 };
const GRID = { stroke: "#334155", strokeDasharray: "3 3" };
const X_AXIS_EVENT_INDEX = {
  ...SLATE_AXIS,
  tickFormatter: tickFmtIntEn,
};

const CHART_MARGIN_SCATTER = { top: 8, right: 8, left: 0, bottom: 0 };
const DEBUG_SCATTER_Y_DOMAIN: [number, number] = [0, 2];

type TooltipLite = {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: unknown }>;
};

type FailureScatterPoint = {
  event_index: number;
  y: number;
  status: string;
  decision_id: string;
  validation_error: string;
  error: string;
};

function TooltipFailureScatter(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const p = tp.payload[0].payload as FailureScatterPoint;
  return (
    <div className="max-w-xs rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="font-mono">Event {fmtIntEn(p.event_index)}</div>
      <div>Status: {p.status}</div>
      <div>Decision: {p.decision_id}</div>
      {p.validation_error !== "—" ? (
        <div className="mt-1 text-amber-200/90">validation: {p.validation_error}</div>
      ) : null}
      {p.error !== "—" ? (
        <div className="mt-1 text-red-300/90">error: {p.error}</div>
      ) : null}
    </div>
  );
}

export function RunMetricsDebugPage() {
  const {
    runs,
    run,
    setRun,
    loading,
    payload,
    frameCount,
    records,
    parseErrors,
  } = useRunMetricsData();

  const aiRows = useMemo(() => deriveAiRows(records), [records]);

  const failureScatter = useMemo(() => {
    return aiRows
      .filter((r) => r.status !== "executed")
      .filter((r) => typeof r.event_index === "number")
      .map((r) => ({
        event_index: r.event_index as number,
        y: 1,
        status: String(r.status ?? "—"),
        decision_id: String(r.decision_id ?? "—"),
        validation_error: String(r.validation_error ?? "—"),
        error: String(r.error ?? "—"),
      }));
  }, [aiRows]);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-[#0a0d11] to-[#06080a] text-sm text-slate-300">
      <RunMetricsRunBar
        runs={runs}
        run={run}
        onRunChange={setRun}
        loading={loading}
        frameCount={frameCount}
        recordsLength={records.length}
        metricsReason={
          payload && !payload.ok ? payload.reason : null
        }
        variant="debug"
      />

      <main className="space-y-6 px-4 py-5">
        {parseErrors.length > 0 ? (
          <div
            className="rounded border border-amber-800/60 bg-amber-950/40 px-3 py-2 text-xs text-amber-100"
            role="alert"
          >
            <span className="font-semibold">Parse warnings: </span>
            {parseErrors.slice(0, 5).join(" · ")}
            {parseErrors.length > 5
              ? ` (+${fmtIntEn(parseErrors.length - 5)} more)`
              : ""}
          </div>
        ) : null}

        {!run ? (
          <p className="text-sm text-slate-500">Select a run to inspect rows.</p>
        ) : null}

        {payload?.ok && records.length > 0 ? (
          <>
            <section>
              <h2 className="mb-3 font-console text-xs font-semibold uppercase tracking-wide text-slate-400">
                Failures (non-executed)
              </h2>
              <ChartCard title="Failures">
                <ResponsiveContainer width="100%" height={CHART_H}>
                  <ScatterChart margin={CHART_MARGIN_SCATTER}>
                    <CartesianGrid {...GRID} />
                    <XAxis
                      dataKey="event_index"
                      type="number"
                      {...X_AXIS_EVENT_INDEX}
                    />
                    <YAxis dataKey="y" hide domain={DEBUG_SCATTER_Y_DOMAIN} />
                    <Tooltip
                      content={TooltipFailureScatter}
                      isAnimationActive={false}
                    />
                    <Scatter
                      data={failureScatter}
                      fill="#f87171"
                      isAnimationActive={false}
                    />
                  </ScatterChart>
                </ResponsiveContainer>
              </ChartCard>

              <div className="mt-4 overflow-x-auto rounded border border-slate-700/80 bg-slate-950/50">
                <table className="w-full min-w-[640px] border-collapse text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-700 text-slate-500">
                      <th className="p-2 font-medium">Event</th>
                      <th className="p-2 font-medium">Status</th>
                      <th className="p-2 font-medium">Decision</th>
                      <th className="p-2 font-medium">Validation</th>
                      <th className="p-2 font-medium">Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {failureScatter.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="p-3 text-slate-500">
                          No non-executed AI rows.
                        </td>
                      </tr>
                    ) : (
                      failureScatter.map((row, i) => (
                        <tr
                          key={`${row.event_index}-${row.decision_id}-${i}`}
                          className="border-b border-slate-800/80"
                        >
                          <td className="p-2 font-mono tabular-nums">
                            {fmtIntEn(row.event_index)}
                          </td>
                          <td className="p-2">{row.status}</td>
                          <td
                            className="max-w-[12rem] truncate p-2 font-mono"
                            title={row.decision_id}
                          >
                            {row.decision_id}
                          </td>
                          <td
                            className="max-w-[18rem] truncate p-2"
                            title={row.validation_error}
                          >
                            {row.validation_error}
                          </td>
                          <td
                            className="max-w-[18rem] truncate p-2"
                            title={row.error}
                          >
                            {row.error}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2 className="mb-3 font-console text-xs font-semibold uppercase tracking-wide text-slate-400">
                Raw records
              </h2>
              <pre className="max-h-[min(70vh,48rem)] overflow-auto rounded border border-slate-700/80 bg-black/40 p-3 text-[10px] leading-relaxed text-slate-400">
                {JSON.stringify(records, null, 2)}
              </pre>
            </section>
          </>
        ) : null}

        {run && payload && !payload.ok ? (
          <p className="text-sm text-amber-400/90">
            {payload.reason === "no_metrics_file"
              ? "No run_metrics.ndjson for this run."
              : `Metrics: ${payload.reason}`}
          </p>
        ) : null}
      </main>
    </div>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded border border-slate-700/80 bg-slate-950/40 p-3">
      <h3 className="mb-2 font-console text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </h3>
      {children}
    </div>
  );
}
