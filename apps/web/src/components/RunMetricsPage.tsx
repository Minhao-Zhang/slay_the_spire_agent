import { useCallback, useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useRunMetricsData } from "../hooks/useRunMetricsData";
import {
  fmtFiniteIntLikeEn,
  fmtIntEn,
  fmtNumEn,
  fmtUnknownNumericOrText,
  tickFmtIntEn,
  tickFmtNumberEn,
} from "../lib/formatDisplayNumber";
import {
  aiExecutedForSeries,
  binNumeric,
  deriveAiRows,
  deriveStateRows,
  screenTypeOrder,
  type BinnedNumeric,
  type MetricsSummary,
  type StateRow,
} from "../lib/runMetricsDerive";

const CHART_H = 220;
const SLATE_AXIS = { stroke: "#64748b", fontSize: 11 };
const GRID = { stroke: "#334155", strokeDasharray: "3 3" };

const X_AXIS_EVENT_INDEX = {
  ...SLATE_AXIS,
  tickFormatter: tickFmtIntEn,
};
const Y_AXIS_DEFAULT = { ...SLATE_AXIS, tickFormatter: tickFmtNumberEn };

/** Raw token count with digit grouping (e.g. 1,234,567). */
function fmtTokensCommas(n: number): string {
  return fmtIntEn(Math.round(n));
}

/** Y-axis tick when series values are already in thousands of tokens. */
function yAxisTickKTokens(value: number): string {
  const abs = Math.abs(value);
  const maxFrac = abs < 10 ? 2 : abs < 100 ? 1 : 0;
  return value.toLocaleString("en-US", {
    maximumFractionDigits: maxFrac,
    minimumFractionDigits: 0,
  });
}

function yAxisTickSeconds(value: number): string {
  return value.toLocaleString("en-US", {
    maximumFractionDigits: value >= 100 ? 0 : 2,
    minimumFractionDigits: 0,
  });
}

const PIE_COLORS = [
  "#38bdf8",
  "#a78bfa",
  "#f472b6",
  "#fbbf24",
  "#34d399",
  "#f87171",
  "#94a3b8",
];

const CHART_MARGIN_TIGHT = { top: 8, right: 8, left: 0, bottom: 0 };
const CHART_MARGIN_LEFT4 = { top: 8, right: 8, left: 4, bottom: 0 };
const CHART_MARGIN_SCATTER = { top: 8, right: 8, left: 8, bottom: 0 };
const CHART_MARGIN_PIE = { top: 8, right: 8, bottom: 8, left: 8 };
const CHART_MARGIN_BAR = { top: 8, right: 8, left: 0, bottom: 24 };

const Y_LABEL_K_TOKENS = {
  value: "k tokens",
  angle: -90,
  position: "insideLeft" as const,
  fill: "#64748b",
  fontSize: 10,
  dx: -4,
};

const Y_LABEL_LATENCY_S = {
  value: "s",
  angle: -90,
  position: "insideLeft" as const,
  fill: "#64748b",
  fontSize: 10,
  dx: -4,
};

const SCATTER_TOOLTIP_CURSOR = { strokeDasharray: "3 3" };

const X_AXIS_BAR_TICK = { fontSize: 9 };

type StateTooltipKeys = Array<
  "hp" | "gold" | "floor" | "legal" | "monsters" | "hand"
>;

const STATE_KEYS_HP: StateTooltipKeys = ["hp"];
const STATE_KEYS_GOLD: StateTooltipKeys = ["gold"];
const STATE_KEYS_FLOOR: StateTooltipKeys = ["floor"];
const STATE_KEYS_LEGAL: StateTooltipKeys = ["legal"];
const STATE_KEYS_MONSTERS: StateTooltipKeys = ["monsters"];
const STATE_KEYS_HAND: StateTooltipKeys = ["hand"];

type TooltipLite = {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: unknown }>;
};

type ScreenScatterPoint = {
  event_index: number;
  screen_y: number;
  screen_type: string;
  turn_key: string;
  in_combat: boolean;
  legal_action_count: unknown;
};

function pieStatusLabel(props: {
  name?: string;
  percent?: number;
}): string {
  return `${props.name ?? ""} ${fmtIntEn(
    Math.round((props.percent ?? 0) * 100),
  )}%`;
}

function TooltipScreenScatter(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const p = tp.payload[0].payload as ScreenScatterPoint;
  return (
    <div className="rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="font-mono text-slate-200">
        event_index: {fmtIntEn(p.event_index)}
      </div>
      <div>screen_type: {p.screen_type}</div>
      <div>turn_key: {p.turn_key}</div>
      <div>in_combat: {String(p.in_combat)}</div>
      <div>
        legal_action_count: {fmtUnknownNumericOrText(p.legal_action_count)}
      </div>
    </div>
  );
}

function HistogramTooltipInput(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const p = tp.payload[0].payload as BinnedNumeric;
  return (
    <div className="rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="tabular-nums">count: {fmtIntEn(p.count)}</div>
      <div>
        range: {fmtNumEn(p.lo, 2)}–{fmtNumEn(p.hi, 2)} tokens
      </div>
    </div>
  );
}

function HistogramTooltipLatency(tp: TooltipLite) {
  if (!tp.active || !tp.payload?.[0]) return null;
  const p = tp.payload[0].payload as BinnedNumeric;
  return (
    <div className="rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="tabular-nums">count: {fmtIntEn(p.count)}</div>
      <div>
        range: {fmtNumEn(p.lo, 1)}–{fmtNumEn(p.hi, 1)} ms
      </div>
    </div>
  );
}

export function RunMetricsPage() {
  const {
    runs,
    archived,
    run,
    setRun,
    loading,
    payload,
    frameCount,
    records,
    parseErrors,
  } = useRunMetricsData();

  const stateRows = useMemo(() => deriveStateRows(records), [records]);
  const aiRows = useMemo(() => deriveAiRows(records), [records]);
  const aiExec = useMemo(() => aiExecutedForSeries(aiRows), [aiRows]);
  const screenOrder = useMemo(() => screenTypeOrder(stateRows), [stateRows]);

  const screenScatter = useMemo(() => {
    const m = new Map(screenOrder.map((s, i) => [s, i]));
    return stateRows.map((s) => ({
      event_index: s.event_index,
      screen_y: m.get(s.vm.screen_type?.trim() || "unknown") ?? 0,
      screen_type: s.vm.screen_type || "unknown",
      turn_key: s.vm.turn_key ?? "—",
      in_combat: s.vm.in_combat ?? false,
      legal_action_count: s.vm.legal_action_count ?? "—",
    }));
  }, [stateRows, screenOrder]);

  const tokenSeries = useMemo(
    () =>
      aiExec
        .filter((r) => typeof r.event_index === "number")
        .map((r) => {
          const input = numOrZero(r.input_tokens);
          const output = numOrZero(r.output_tokens);
          const total = numOrZero(r.total_tokens);
          const latMs = numOrZero(r.latency_ms);
          return {
            event_index: r.event_index as number,
            total_tokens: total,
            input_tokens: input,
            output_tokens: output,
            input_k: input / 1000,
            output_k: output / 1000,
            total_k: total / 1000,
            latency_ms: latMs,
            latency_s: latMs / 1000,
            decision_id: String(r.decision_id ?? "—"),
            status: String(r.status ?? "—"),
            llm_model_used: String(r.llm_model_used ?? "—"),
            llm_turn_model_key: String(r.llm_turn_model_key ?? "—"),
            timestamp: String(r.timestamp ?? "—"),
          };
        })
        .sort((a, b) => a.event_index - b.event_index),
    [aiExec],
  );

  /** Run-cumulative sums (raw tokens); *_k fields are thousands for charts. */
  const cumulativeTokenSeries = useMemo(() => {
    let cumIn = 0;
    let cumOut = 0;
    let cumTotal = 0;
    return tokenSeries.map((p) => {
      cumIn += p.input_tokens;
      cumOut += p.output_tokens;
      cumTotal += p.total_tokens;
      return {
        ...p,
        cumulative_total: cumTotal,
        cumulative_input: cumIn,
        cumulative_output: cumOut,
        cumulative_total_k: cumTotal / 1000,
        cumulative_input_k: cumIn / 1000,
        cumulative_output_k: cumOut / 1000,
      };
    });
  }, [tokenSeries]);

  const inputTokBins = useMemo(() => {
    const vals = aiExec
      .map((r) =>
        typeof r.input_tokens === "number" ? r.input_tokens : null,
      )
      .filter((x): x is number => x !== null && x >= 0);
    return binNumeric(vals, 12);
  }, [aiExec]);

  const latencyBins = useMemo(() => {
    const vals = aiExec
      .map((r) =>
        typeof r.latency_ms === "number" ? r.latency_ms : null,
      )
      .filter((x): x is number => x !== null && x >= 0);
    return binNumeric(vals, 12);
  }, [aiExec]);

  const statusPie = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of aiRows) {
      const k = String(r.status ?? "unknown");
      counts[k] = (counts[k] ?? 0) + 1;
    }
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [aiRows]);

  const screenOrderTicks = useMemo(
    () => (screenOrder.length ? screenOrder.map((_, i) => i) : [0]),
    [screenOrder],
  );

  const screenScatterYDomain = useMemo(
    (): [number, number] => [0, Math.max(0, screenOrder.length - 1)],
    [screenOrder.length],
  );

  const screenTickFormatter = useCallback(
    (i: number | string) =>
      screenOrder[typeof i === "number" ? i : 0] ?? "",
    [screenOrder],
  );

  const aiRowCount = aiRows.length;
  const statusPieTooltipContent = useCallback(
    (tp: TooltipLite) => {
      if (!tp.active || !tp.payload?.[0]) return null;
      const d = tp.payload[0].payload as { name: string; value: number };
      const pct =
        aiRowCount > 0
          ? fmtNumEn((d.value / aiRowCount) * 100, 1)
          : fmtNumEn(0, 1);
      return (
        <div className="rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
          <div className="font-medium text-slate-200">{d.name}</div>
          <div className="tabular-nums">
            count: {fmtIntEn(d.value)} ({pct}%)
          </div>
        </div>
      );
    },
    [aiRowCount],
  );

  const summary = payload?.ok === true ? payload.summary : undefined;

  const executedInOutTokens = useMemo(() => {
    const sIn = summary?.input_tokens_executed;
    const sOut = summary?.output_tokens_executed;
    if (typeof sIn === "number" && typeof sOut === "number") {
      return { input: sIn, output: sOut };
    }
    let input = 0;
    let output = 0;
    for (const r of aiExec) {
      const ti = r.input_tokens;
      const to = r.output_tokens;
      if (typeof ti === "number" && Number.isFinite(ti)) input += ti;
      if (typeof to === "number" && Number.isFinite(to)) output += to;
    }
    return { input, output };
  }, [summary, aiExec]);

  const debugSearch = run
    ? `?run=${encodeURIComponent(run)}`
    : "";

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-[#0a0d11] to-[#06080a] text-sm text-slate-300">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-slate-700/90 bg-slate-900/80 px-4 py-3 backdrop-blur-sm">
        <Link
          to="/"
          className="font-console text-xs font-semibold uppercase tracking-wide text-sky-400 hover:text-sky-300"
        >
          ← Monitor
        </Link>
        <span className="font-console text-sm font-bold tracking-[0.12em] text-slate-100">
          RUN METRICS
        </span>
        <Link
          to={`/metrics/debug${debugSearch}`}
          className="font-console text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-300"
        >
          Debug / forensics
        </Link>
        <label className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-slate-500">
            Run
          </span>
          <select
            value={run}
            onChange={(e) => setRun(e.target.value)}
            className="font-console h-8 max-w-[18rem] rounded border border-slate-700 bg-slate-950/80 px-2 text-xs text-slate-200 outline-none"
            aria-label="Log run"
          >
            <option value="">Select run…</option>
            {runs.map((r) => (
              <option key={r} value={r}>
                {r}
                {archived[r] ? " · zip" : ""}
              </option>
            ))}
          </select>
        </label>
        {loading ? (
          <span className="text-xs text-slate-500">Loading…</span>
        ) : null}
        {payload && !payload.ok ? (
          <span className="text-xs text-amber-400" title={payload.reason}>
            {payload.reason === "no_metrics_file"
              ? "No run_metrics.ndjson for this run."
              : `Metrics: ${payload.reason}`}
          </span>
        ) : null}
        {payload?.ok && frameCount !== null ? (
          <span className="font-telemetry text-xs tabular-nums text-slate-500">
            Frames: {fmtIntEn(frameCount)} · Rows: {fmtIntEn(records.length)}
          </span>
        ) : null}
        {payload?.ok && frameCount === null && run.endsWith(".zip") ? (
          <span className="text-xs text-slate-500">Archived zip (metrics only)</span>
        ) : null}
      </header>

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

        {summary ? (
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi
              label="State rows"
              value={fmtNumEn(summary.state_row_count)}
            />
            <Kpi
              label="Tokens (executed)"
              value={`in ${fmtNumEn(executedInOutTokens.input)} · out ${fmtNumEn(executedInOutTokens.output)}`}
              title="Total input and output tokens summed over executed AI decisions."
            />
            <Kpi
              label="Latency mean / median (s)"
              value={latencyMeanMedianSecondsKpi(summary)}
              title="Wall time per executed AI call (mean and median)."
            />
            <Kpi
              label="Levels reached"
              value={levelsReachedKpi(summary)}
              title="Highest act and floor observed in any state snapshot (vm_summary)."
            />
          </section>
        ) : null}

        {payload?.ok && records.length > 0 ? (
          <>
            <section>
              <h2 className="mb-3 font-console text-xs font-semibold uppercase tracking-wide text-slate-400">
                Progression (state rows)
              </h2>
              <div className="grid gap-6 lg:grid-cols-2">
                <ChartCard title="HP & max HP">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateHp}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="line_current_hp"
                        name="current_hp"
                        stroke="#f87171"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="line_max_hp"
                        name="max_hp"
                        stroke="#94a3b8"
                        dot={false}
                        strokeWidth={1.5}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Gold">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateGold}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="line_gold"
                        name="gold"
                        stroke="#fbbf24"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Floor (step)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateFloor}
                        isAnimationActive={false}
                      />
                      <Line
                        type="stepAfter"
                        dataKey="line_floor"
                        name="floor"
                        stroke="#38bdf8"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Legal action count">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateLegal}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="line_legal_action_count"
                        name="legal_action_count"
                        stroke="#a78bfa"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Combat: enemy HP sum">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateMonsters}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="monster_hp_sum"
                        name="enemy_hp_sum"
                        stroke="#f472b6"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Hand size">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={stateRows} margin={CHART_MARGIN_TIGHT}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={TooltipStateHand}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="hand_size"
                        name="hand_size"
                        stroke="#34d399"
                        dot={false}
                        strokeWidth={2}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Screen type (scatter)" className="lg:col-span-2">
                  <p className="mb-1 text-[11px] text-slate-500">
                    Y = category index ({fmtIntEn(screenOrder.length)} types).
                    Hover for turn_key and flags.
                  </p>
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <ScatterChart margin={CHART_MARGIN_SCATTER}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" name="event_index" {...X_AXIS_EVENT_INDEX} />
                      <YAxis
                        dataKey="screen_y"
                        type="number"
                        domain={screenScatterYDomain}
                        ticks={screenOrderTicks}
                        tickFormatter={screenTickFormatter}
                        width={120}
                        {...SLATE_AXIS}
                      />
                      <Tooltip
                        cursor={SCATTER_TOOLTIP_CURSOR}
                        content={TooltipScreenScatter}
                        isAnimationActive={false}
                      />
                      <Scatter
                        data={screenScatter}
                        fill="#38bdf8"
                        isAnimationActive={false}
                      />
                    </ScatterChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
            </section>

            <section>
              <h2 className="mb-3 font-console text-xs font-semibold uppercase tracking-wide text-slate-400">
                AI decisions
              </h2>
              <p className="mb-4 max-w-4xl text-[11px] leading-relaxed text-slate-500">
                Executed rows only. Token charts use{" "}
                <span className="text-slate-400">thousands of tokens</span>{" "}
                (divide raw values by 1000). Source rows in{" "}
                <span className="font-mono">run_metrics.ndjson</span> are still
                full tokens per decision; cumulative sums those rows in{" "}
                <span className="font-mono">event_index</span> order. Latency is
                wall time in <span className="text-slate-400">seconds</span>{" "}
                (milliseconds ÷ 1000).
              </p>
              <div className="grid gap-6 lg:grid-cols-2">
                <ChartCard title="Input tokens per call (k tokens)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={tokenSeries} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis
                        {...Y_AXIS_DEFAULT}
                        tickFormatter={yAxisTickKTokens}
                        width={52}
                        label={Y_LABEL_K_TOKENS}
                      />
                      <Tooltip
                        content={TooltipAiToken}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="input_k"
                        name="input_k"
                        stroke="#818cf8"
                        dot={false}
                        strokeWidth={2}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Output tokens per call (k tokens)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={tokenSeries} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis
                        {...Y_AXIS_DEFAULT}
                        tickFormatter={yAxisTickKTokens}
                        width={52}
                        label={Y_LABEL_K_TOKENS}
                      />
                      <Tooltip
                        content={TooltipAiToken}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="output_k"
                        name="output_k"
                        stroke="#c084fc"
                        dot={false}
                        strokeWidth={2}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Cumulative total tokens (k tokens)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <AreaChart data={cumulativeTokenSeries} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis
                        {...Y_AXIS_DEFAULT}
                        tickFormatter={yAxisTickKTokens}
                        width={56}
                        label={Y_LABEL_K_TOKENS}
                      />
                      <Tooltip
                        content={TooltipCumulativeToken}
                        isAnimationActive={false}
                      />
                      <Area
                        type="monotone"
                        dataKey="cumulative_total_k"
                        name="cumulative_total_k"
                        stroke="#22d3ee"
                        fill="#22d3ee33"
                        strokeWidth={2}
                        isAnimationActive={false}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Latency (seconds)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <LineChart data={tokenSeries} margin={CHART_MARGIN_LEFT4}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="event_index" type="number" {...X_AXIS_EVENT_INDEX} />
                      <YAxis
                        {...Y_AXIS_DEFAULT}
                        tickFormatter={yAxisTickSeconds}
                        width={48}
                        label={Y_LABEL_LATENCY_S}
                      />
                      <Tooltip
                        content={TooltipLatencySeconds}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="latency_s"
                        name="latency_s"
                        stroke="#fbbf24"
                        dot={false}
                        strokeWidth={2}
                        connectNulls
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
            </section>

            <section>
              <h2 className="mb-3 font-console text-xs font-semibold uppercase tracking-wide text-slate-400">
                Distributions
              </h2>
              <div className="grid gap-6 lg:grid-cols-3">
                <ChartCard title="AI status (all rows)">
                  {statusPie.length === 0 ? (
                    <p className="py-8 text-center text-xs text-slate-500">
                      No AI decision rows.
                    </p>
                  ) : (
                    <ResponsiveContainer width="100%" height={CHART_H}>
                      <PieChart margin={CHART_MARGIN_PIE}>
                        <Pie
                          data={statusPie}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          outerRadius={72}
                          label={pieStatusLabel}
                          isAnimationActive={false}
                        >
                          {statusPie.map((_, i) => (
                            <Cell
                              key={i}
                              fill={PIE_COLORS[i % PIE_COLORS.length]}
                            />
                          ))}
                        </Pie>
                        <Tooltip
                          content={statusPieTooltipContent}
                          isAnimationActive={false}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  )}
                </ChartCard>
                <ChartCard title="Input tokens (histogram, executed)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <BarChart data={inputTokBins} margin={CHART_MARGIN_BAR}>
                      <CartesianGrid {...GRID} />
                      <XAxis
                        dataKey="label"
                        {...SLATE_AXIS}
                        angle={-25}
                        textAnchor="end"
                        height={48}
                        interval={0}
                        tick={X_AXIS_BAR_TICK}
                      />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={HistogramTooltipInput}
                        isAnimationActive={false}
                      />
                      <Bar
                        dataKey="count"
                        fill="#818cf8"
                        radius={[4, 4, 0, 0]}
                        isAnimationActive={false}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Latency ms (histogram, executed)">
                  <ResponsiveContainer width="100%" height={CHART_H}>
                    <BarChart data={latencyBins} margin={CHART_MARGIN_BAR}>
                      <CartesianGrid {...GRID} />
                      <XAxis
                        dataKey="label"
                        {...SLATE_AXIS}
                        angle={-25}
                        textAnchor="end"
                        height={48}
                        interval={0}
                        tick={X_AXIS_BAR_TICK}
                      />
                      <YAxis {...Y_AXIS_DEFAULT} />
                      <Tooltip
                        content={HistogramTooltipLatency}
                        isAnimationActive={false}
                      />
                      <Bar
                        dataKey="count"
                        fill="#f472b6"
                        radius={[4, 4, 0, 0]}
                        isAnimationActive={false}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}

function numOrZero(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  return 0;
}

function latencyMeanMedianSecondsKpi(summary: MetricsSummary): string {
  const m = summary.latency_ms_mean;
  const med = summary.latency_ms_median;
  const meanS =
    typeof m === "number" && Number.isFinite(m) ? m / 1000 : null;
  const medS =
    typeof med === "number" && Number.isFinite(med) ? med / 1000 : null;
  return `${fmtNumEn(meanS, 2)} / ${fmtNumEn(medS, 2)}`;
}

function levelsReachedKpi(summary: {
  max_floor_reached?: number | null;
  max_act_reached?: number | null;
}): string {
  const f = summary.max_floor_reached;
  const a = summary.max_act_reached;
  const fOk = typeof f === "number" && Number.isFinite(f);
  const aOk = typeof a === "number" && Number.isFinite(a);
  if (aOk && fOk) return `Act ${fmtIntEn(a)} · floor ${fmtIntEn(f)}`;
  if (fOk) return `Floor ${fmtIntEn(f)}`;
  if (aOk) return `Act ${fmtIntEn(a)}`;
  return "—";
}

function Kpi({
  label,
  value,
  title,
}: {
  label: string;
  value: string;
  title?: string;
}) {
  return (
    <div
      className="rounded border border-slate-700/80 bg-slate-950/50 px-3 py-2"
      title={title}
    >
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="font-telemetry mt-0.5 text-lg tabular-nums text-slate-100">
        {value}
      </div>
    </div>
  );
}

function ChartCard({
  title,
  children,
  className = "",
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded border border-slate-700/80 bg-slate-950/40 p-3 ${className}`}>
      <h3 className="mb-2 font-console text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </h3>
      {children}
    </div>
  );
}

function StateTooltip({
  active,
  payload,
  keys,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: unknown }> | undefined;
  keys: Array<"hp" | "gold" | "floor" | "legal" | "monsters" | "hand">;
}) {
  if (!active || !payload?.[0]) return null;
  const row = payload[0].payload as StateRow | undefined;
  if (!row || typeof row.event_index !== "number") return null;
  const sid =
    row.state_id.length > 28
      ? `${row.state_id.slice(0, 28)}…`
      : row.state_id;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="font-mono text-slate-200">
        event_index: {fmtIntEn(row.event_index)}
      </div>
      <div className="text-slate-400">{row.timestamp}</div>
      <div className="truncate text-slate-500" title={row.state_id}>
        state_id: {sid}
      </div>
      {keys.includes("hp") ? (
        <>
          <div>current_hp: {fmtNumEn(row.vm.current_hp)}</div>
          <div>max_hp: {fmtNumEn(row.vm.max_hp)}</div>
          <div>floor: {fmtNumEn(row.vm.floor)} · act: {fmtNumEn(row.vm.act)}</div>
          <div>screen_type: {row.vm.screen_type ?? "—"}</div>
        </>
      ) : null}
      {keys.includes("gold") ? (
        <>
          <div>gold: {fmtNumEn(row.vm.gold)}</div>
          <div>floor: {fmtNumEn(row.vm.floor)}</div>
          <div>screen_type: {row.vm.screen_type ?? "—"}</div>
        </>
      ) : null}
      {keys.includes("floor") ? (
        <>
          <div>floor: {fmtNumEn(row.vm.floor)}</div>
          <div>act: {fmtNumEn(row.vm.act)}</div>
          <div>screen_type: {row.vm.screen_type ?? "—"}</div>
        </>
      ) : null}
      {keys.includes("legal") ? (
        <>
          <div>legal_action_count: {fmtNumEn(row.vm.legal_action_count)}</div>
          <div className="break-all font-mono text-[10px] text-slate-500">
            fp: {row.vm.legal_commands_fingerprint ?? "—"}
          </div>
        </>
      ) : null}
      {keys.includes("monsters") ? (
        <>
          <div>enemy_hp_sum: {fmtNumEn(row.monster_hp_sum)}</div>
          {row.monster_tooltip ? (
            <pre className="mt-1 whitespace-pre-wrap text-[10px] text-slate-400">
              {row.monster_tooltip}
            </pre>
          ) : (
            <div className="text-slate-500">No monsters in vm_summary</div>
          )}
        </>
      ) : null}
      {keys.includes("hand") ? (
        <>
          <div>
            hand_size:{" "}
            {typeof row.hand_size === "number"
              ? fmtIntEn(row.hand_size)
              : String(row.hand_size)}
          </div>
          <div className="text-[10px] text-slate-400">{row.hand_names_preview}</div>
        </>
      ) : null}
    </div>
  );
}

function AiTokenTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: Record<string, unknown> }> | undefined;
}) {
  if (!active || !payload?.[0]) return null;
  const p = payload[0].payload;
  if (!p) return null;
  const rawIn = Number(p.input_tokens) || 0;
  const rawOut = Number(p.output_tokens) || 0;
  const rawTot = Number(p.total_tokens) || 0;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="font-mono">
        event_index: {fmtFiniteIntLikeEn(p.event_index)}
      </div>
      <div>decision_id: {String(p.decision_id)}</div>
      <div className="mt-1 text-slate-400">This call (tokens)</div>
      <div className="tabular-nums text-slate-100">
        input: {fmtTokensCommas(rawIn)} tokens
      </div>
      <div className="tabular-nums text-slate-100">
        output: {fmtTokensCommas(rawOut)} tokens
      </div>
      <div className="tabular-nums text-slate-100">
        total: {fmtTokensCommas(rawTot)} tokens
      </div>
      <div className="mt-1 border-t border-slate-700 pt-1 text-slate-400">Latency</div>
      <div className="tabular-nums text-slate-100">
        {fmtTokensCommas(Number(p.latency_ms) || 0)} ms
      </div>
      <div>status: {String(p.status)}</div>
      <div className="truncate" title={String(p.llm_model_used)}>
        model: {String(p.llm_model_used)}
      </div>
      <div className="truncate text-[10px] text-slate-500" title={String(p.llm_turn_model_key)}>
        key: {String(p.llm_turn_model_key)}
      </div>
      <div className="text-[10px] text-slate-500">{String(p.timestamp)}</div>
    </div>
  );
}

function LatencySecondsTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: Record<string, unknown> }> | undefined;
}) {
  if (!active || !payload?.[0]) return null;
  const p = payload[0].payload;
  if (!p) return null;
  const ms = Number(p.latency_ms) || 0;
  return (
    <div className="max-w-sm rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="font-mono">
        event_index: {fmtFiniteIntLikeEn(p.event_index)}
      </div>
      <div>decision_id: {String(p.decision_id)}</div>
      <div className="mt-1 text-slate-400">Latency</div>
      <div className="tabular-nums text-slate-100">{fmtTokensCommas(ms)} ms</div>
      <div>status: {String(p.status)}</div>
      <div className="truncate text-[10px] text-slate-500" title={String(p.llm_model_used)}>
        {String(p.llm_model_used)}
      </div>
    </div>
  );
}

function CumulativeTokenTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: Record<string, unknown> }> | undefined;
}) {
  if (!active || !payload?.[0]) return null;
  const p = payload[0].payload;
  if (!p) return null;
  const cin = Number(p.cumulative_input);
  const cout = Number(p.cumulative_output);
  const ctot = Number(p.cumulative_total);
  const safeIn = Number.isFinite(cin) ? cin : 0;
  const safeOut = Number.isFinite(cout) ? cout : 0;
  const safeTot = Number.isFinite(ctot) ? ctot : 0;
  return (
    <div className="max-w-xs rounded border border-slate-600 bg-slate-950/95 px-2 py-1.5 text-[11px] shadow-lg">
      <div className="font-mono text-slate-200">
        event_index: {fmtFiniteIntLikeEn(p.event_index)}
      </div>
      <div className="mt-1 border-t border-slate-700 pt-1 text-slate-400">
        This decision (step, tokens)
      </div>
      <div className="tabular-nums text-slate-100">
        in / out / total: {fmtTokensCommas(Number(p.input_tokens) || 0)} /{" "}
        {fmtTokensCommas(Number(p.output_tokens) || 0)} /{" "}
        {fmtTokensCommas(Number(p.total_tokens) || 0)}
      </div>
      <div className="mt-1 border-t border-slate-700 pt-1 text-slate-400">
        Run cumulative (tokens)
      </div>
      <div className="tabular-nums text-slate-100">
        total: {fmtTokensCommas(safeTot)} tokens
      </div>
      <div className="tabular-nums text-slate-100">
        input: {fmtTokensCommas(safeIn)} tokens
      </div>
      <div className="tabular-nums text-slate-100">
        output: {fmtTokensCommas(safeOut)} tokens
      </div>
      <div className="mt-1 truncate text-[10px] text-slate-500" title={String(p.decision_id)}>
        {String(p.decision_id)}
      </div>
    </div>
  );
}

function TooltipStateHp(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_HP} />
  );
}

function TooltipStateGold(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_GOLD} />
  );
}

function TooltipStateFloor(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_FLOOR} />
  );
}

function TooltipStateLegal(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_LEGAL} />
  );
}

function TooltipStateMonsters(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_MONSTERS} />
  );
}

function TooltipStateHand(tp: TooltipLite) {
  return (
    <StateTooltip active={tp.active} payload={tp.payload} keys={STATE_KEYS_HAND} />
  );
}

function TooltipAiToken(tp: TooltipLite) {
  return (
    <AiTokenTooltip
      active={tp.active}
      payload={
        tp.payload as ReadonlyArray<{
          payload?: Record<string, unknown>;
        }>
      }
    />
  );
}

function TooltipCumulativeToken(tp: TooltipLite) {
  return (
    <CumulativeTokenTooltip
      active={tp.active}
      payload={
        tp.payload as ReadonlyArray<{
          payload?: Record<string, unknown>;
        }>
      }
    />
  );
}

function TooltipLatencySeconds(tp: TooltipLite) {
  return (
    <LatencySecondsTooltip
      active={tp.active}
      payload={
        tp.payload as ReadonlyArray<{
          payload?: Record<string, unknown>;
        }>
      }
    />
  );
}
