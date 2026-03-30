/** Types and pure transforms for `run_metrics.ndjson` records (API `/api/runs/.../metrics`). */

import { fmtTruncIntEn } from "./formatDisplayNumber";

export type JsonRecord = Record<string, unknown>;

export type VmSummary = {
  screen_type?: string;
  floor?: number;
  act?: number;
  in_combat?: boolean;
  turn_key?: string;
  current_hp?: number | null;
  max_hp?: number | null;
  gold?: number | null;
  legal_action_count?: number | null;
  legal_commands_fingerprint?: string | null;
  monsters?: Array<{
    name?: string | null;
    current_hp?: number | null;
    max_hp?: number | null;
  }>;
  hand?: Array<{ name?: string | null }>;
};

export type StateRow = {
  event_index: number;
  timestamp: string;
  state_id: string;
  vm: VmSummary;
  monster_hp_sum: number | null;
  hand_size: number;
  monster_tooltip: string;
  hand_names_preview: string;
  /** Flattened vm scalars for Recharts string dataKey (stable props / perf). */
  line_current_hp: number | null;
  line_max_hp: number | null;
  line_gold: number | null;
  line_floor: number | null;
  line_legal_action_count: number | null;
};

export type AiRow = JsonRecord & {
  type?: string;
  event_index?: number | null;
  decision_id?: string;
  timestamp?: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  latency_ms?: number | null;
  status?: string;
  validation_error?: string | null;
  error?: string | null;
  llm_model_used?: string | null;
  llm_turn_model_key?: string | null;
};

function num(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function asVmSummary(raw: unknown): VmSummary {
  if (!raw || typeof raw !== "object") return {};
  const o = raw as Record<string, unknown>;
  return {
    screen_type:
      typeof o.screen_type === "string" ? o.screen_type : undefined,
    floor: num(o.floor) ?? undefined,
    act: num(o.act) ?? undefined,
    in_combat: typeof o.in_combat === "boolean" ? o.in_combat : undefined,
    turn_key: typeof o.turn_key === "string" ? o.turn_key : undefined,
    current_hp: num(o.current_hp),
    max_hp: num(o.max_hp),
    gold: num(o.gold),
    legal_action_count: num(o.legal_action_count),
    legal_commands_fingerprint:
      typeof o.legal_commands_fingerprint === "string"
        ? o.legal_commands_fingerprint
        : undefined,
    monsters: Array.isArray(o.monsters) ? (o.monsters as VmSummary["monsters"]) : undefined,
    hand: Array.isArray(o.hand) ? (o.hand as VmSummary["hand"]) : undefined,
  };
}

export function deriveStateRows(records: JsonRecord[]): StateRow[] {
  const out: StateRow[] = [];
  for (const r of records) {
    if (r.type !== "state") continue;
    const ei = num(r.event_index);
    if (ei === null) continue;
    const vm = asVmSummary(r.vm_summary);
    let monster_hp_sum: number | null = null;
    let monster_tooltip = "";
    if (vm.monsters?.length) {
      const parts: string[] = [];
      let sum = 0;
      for (const m of vm.monsters) {
        const hp = num(m?.current_hp);
        const name = (m?.name && String(m.name)) || "?";
        if (hp !== null) sum += hp;
        parts.push(`${name}: ${hp ?? "—"}/${num(m?.max_hp) ?? "—"}`);
      }
      monster_hp_sum = sum;
      monster_tooltip = parts.join("\n");
    }
    const hand = vm.hand ?? [];
    const hand_size = hand.length;
    const names = hand
      .map((c) => (c?.name ? String(c.name) : ""))
      .filter(Boolean)
      .slice(0, 12);
    const hand_names_preview =
      names.length === 0
        ? "—"
        : names.join(", ") + (hand_size > names.length ? "…" : "");

    out.push({
      event_index: ei,
      timestamp: typeof r.timestamp === "string" ? r.timestamp : "",
      state_id: typeof r.state_id === "string" ? r.state_id : "",
      vm,
      monster_hp_sum,
      hand_size,
      monster_tooltip,
      hand_names_preview,
      line_current_hp: vm.current_hp ?? null,
      line_max_hp: vm.max_hp ?? null,
      line_gold: vm.gold ?? null,
      line_floor: vm.floor ?? null,
      line_legal_action_count: vm.legal_action_count ?? null,
    });
  }
  out.sort((a, b) => a.event_index - b.event_index);
  return out;
}

export function deriveAiRows(records: JsonRecord[]): AiRow[] {
  return records.filter((r) => r.type === "ai_decision") as AiRow[];
}

export function aiExecutedForSeries(rows: AiRow[]): AiRow[] {
  return rows.filter((r) => r.status === "executed");
}

/** Stable bucket id for grouping state + AI rows by act+floor. */
export type FloorBucketMeta = {
  floor_key: string;
  floor_label: string;
  act: number | null;
  floor: number | null;
  /** Minimum event_index in this bucket (run order). */
  first_event_index: number;
};

export function floorBucketForStateRow(row: StateRow): FloorBucketMeta {
  const act = row.vm.act ?? null;
  const floor = row.vm.floor ?? null;
  const hasAct = typeof act === "number" && Number.isFinite(act);
  const hasFloor = typeof floor === "number" && Number.isFinite(floor);
  const floor_key =
    hasAct || hasFloor
      ? `${hasAct ? act : "?"}\u200f:\u200f${hasFloor ? floor : "?"}`
      : "__unknown__";
  const floor_label =
    hasAct && hasFloor
      ? `A${act}·F${floor}`
      : hasFloor
        ? `F${floor}`
        : hasAct
          ? `A${act}`
          : "—";
  return {
    floor_key,
    floor_label,
    act: hasAct ? act : null,
    floor: hasFloor ? floor : null,
    first_event_index: row.event_index,
  };
}

/** Sort floor buckets for charts: by map level (`floor`), unknown/missing floor last. */
export function sortFloorBucketsByLevel<
  T extends FloorBucketMeta & { first_event_index: number },
>(rows: T[]): void {
  rows.sort((a, b) => {
    const unkA = a.floor_key === "__unknown__" || a.floor == null;
    const unkB = b.floor_key === "__unknown__" || b.floor == null;
    if (unkA !== unkB) return unkA ? 1 : -1;
    if (unkA && unkB) return a.first_event_index - b.first_event_index;
    return (a.floor! - b.floor!) || a.first_event_index - b.first_event_index;
  });
}

/**
 * X positions (midpoints between floor levels) where `act` changes — for vertical
 * reference lines on floor-level charts.
 */
export function actTransitionMidXs(
  rows: ReadonlyArray<{ act: number | null; floor: number | null }>,
): number[] {
  const xs: number[] = [];
  const withFloor = rows.filter(
    (r): r is { act: number | null; floor: number } =>
      typeof r.floor === "number" && Number.isFinite(r.floor),
  );
  for (let i = 1; i < withFloor.length; i++) {
    const p = withFloor[i - 1];
    const c = withFloor[i];
    if (p.act != null && c.act != null && p.act !== c.act) {
      xs.push((p.floor + c.floor) / 2);
    }
  }
  return xs;
}

function mean(nums: number[]): number {
  if (nums.length === 0) return NaN;
  return nums.reduce((s, x) => s + x, 0) / nums.length;
}

/** One row per floor bucket: mean of state snapshots in that bucket (floor mode). */
export type FloorStateAggRow = FloorBucketMeta & {
  mean_current_hp: number | null;
  mean_max_hp: number | null;
  mean_gold: number | null;
  mean_legal: number | null;
  mean_monster_hp_sum: number | null;
  mean_hand_size: number | null;
  x_rank: number;
};

export function deriveFloorStateAggRows(stateRows: StateRow[]): FloorStateAggRow[] {
  const groups = new Map<
    string,
    { meta: FloorBucketMeta; rows: StateRow[] }
  >();
  for (const row of stateRows) {
    const meta = floorBucketForStateRow(row);
    const prev = groups.get(meta.floor_key);
    if (!prev) {
      groups.set(meta.floor_key, {
        meta: { ...meta, first_event_index: row.event_index },
        rows: [row],
      });
    } else {
      prev.rows.push(row);
      if (row.event_index < prev.meta.first_event_index) {
        prev.meta.first_event_index = row.event_index;
      }
    }
  }
  const out: FloorStateAggRow[] = [];
  for (const { meta, rows } of groups.values()) {
    const hp = rows
      .map((r) => r.line_current_hp)
      .filter((x): x is number => x !== null && Number.isFinite(x));
    const mxhp = rows
      .map((r) => r.line_max_hp)
      .filter((x): x is number => x !== null && Number.isFinite(x));
    const gold = rows
      .map((r) => r.line_gold)
      .filter((x): x is number => x !== null && Number.isFinite(x));
    const legal = rows
      .map((r) => r.line_legal_action_count)
      .filter((x): x is number => x !== null && Number.isFinite(x));
    const msum = rows
      .map((r) => r.monster_hp_sum)
      .filter((x): x is number => x !== null && Number.isFinite(x));
    const hand = rows.map((r) => r.hand_size).filter((x) => Number.isFinite(x));
    const avgOrNull = (arr: number[]) => (arr.length === 0 ? null : mean(arr));
    out.push({
      ...meta,
      mean_current_hp: avgOrNull(hp),
      mean_max_hp: avgOrNull(mxhp),
      mean_gold: avgOrNull(gold),
      mean_legal: avgOrNull(legal),
      mean_monster_hp_sum: avgOrNull(msum),
      mean_hand_size: avgOrNull(hand),
      x_rank: 0,
    });
  }
  sortFloorBucketsByLevel(out);
  out.forEach((r, i) => {
    r.x_rank = i;
  });
  return out;
}

/** event_index -> floor_key for joining AI rows to floor buckets. */
export function buildEventIndexToFloorKey(stateRows: StateRow[]): Map<number, string> {
  const m = new Map<number, string>();
  for (const row of stateRows) {
    m.set(row.event_index, floorBucketForStateRow(row).floor_key);
  }
  return m;
}

export type FloorAiAggRow = FloorBucketMeta & {
  x_rank: number;
  decision_count: number;
  sum_input_tokens: number;
  sum_output_tokens: number;
  sum_total_tokens: number;
  mean_latency_ms: number | null;
};

export function deriveFloorAiAggRows(
  aiExec: AiRow[],
  eventToFloorKey: Map<number, string>,
  floorOrder: FloorStateAggRow[],
): FloorAiAggRow[] {
  const keyToMeta = new Map<string, FloorBucketMeta>();
  const unknownMeta: FloorBucketMeta = {
    floor_key: "__unknown__",
    floor_label: "—",
    act: null,
    floor: null,
    first_event_index: 1e15,
  };
  keyToMeta.set("__unknown__", { ...unknownMeta });
  for (const f of floorOrder) {
    keyToMeta.set(f.floor_key, {
      floor_key: f.floor_key,
      floor_label: f.floor_label,
      act: f.act,
      floor: f.floor,
      first_event_index: f.first_event_index,
    });
  }
  const fkMinEi = new Map<string, number>();
  const groups = new Map<
    string,
    {
      inputs: number[];
      outputs: number[];
      totals: number[];
      lats: number[];
    }
  >();
  for (const r of aiExec) {
    const ei = r.event_index;
    if (typeof ei !== "number" || !Number.isFinite(ei)) continue;
    const fk = eventToFloorKey.get(ei) ?? "__unknown__";
    const prevMin = fkMinEi.get(fk);
    if (prevMin === undefined || ei < prevMin) fkMinEi.set(fk, ei);
    if (!keyToMeta.has(fk)) {
      keyToMeta.set(fk, {
        ...unknownMeta,
        floor_key: fk,
        floor_label: fk,
        first_event_index: ei,
      });
    }
    let g = groups.get(fk);
    if (!g) {
      g = { inputs: [], outputs: [], totals: [], lats: [] };
      groups.set(fk, g);
    }
    const ti = r.input_tokens;
    const to = r.output_tokens;
    const tt = r.total_tokens;
    const lat = r.latency_ms;
    if (typeof ti === "number" && Number.isFinite(ti)) g.inputs.push(ti);
    if (typeof to === "number" && Number.isFinite(to)) g.outputs.push(to);
    if (typeof tt === "number" && Number.isFinite(tt)) g.totals.push(tt);
    if (typeof lat === "number" && Number.isFinite(lat)) g.lats.push(lat);
  }
  const rows: FloorAiAggRow[] = [];
  for (const [fk, g] of groups) {
    const base = keyToMeta.get(fk);
    if (!base) continue;
    const meta: FloorBucketMeta = {
      ...base,
      first_event_index: Math.min(
        base.first_event_index,
        fkMinEi.get(fk) ?? base.first_event_index,
      ),
    };
    rows.push({
      ...meta,
      x_rank: 0,
      decision_count: g.totals.length || g.inputs.length,
      sum_input_tokens: g.inputs.reduce((s, x) => s + x, 0),
      sum_output_tokens: g.outputs.reduce((s, x) => s + x, 0),
      sum_total_tokens: g.totals.reduce((s, x) => s + x, 0),
      mean_latency_ms: g.lats.length ? mean(g.lats) : null,
    });
  }
  sortFloorBucketsByLevel(rows);
  rows.forEach((r, i) => {
    r.x_rank = i;
  });
  return rows;
}

/** Cumulative tokens by floor order (sum of totals up through each bucket). */
export function deriveFloorCumulativeTokens(floorAi: FloorAiAggRow[]): Array<
  FloorAiAggRow & {
    cumulative_total: number;
    cumulative_total_k: number;
  }
> {
  let cum = 0;
  return floorAi.map((row) => {
    cum += row.sum_total_tokens;
    return {
      ...row,
      cumulative_total: cum,
      cumulative_total_k: cum / 1000,
    };
  });
}

export type BinnedNumeric = {
  label: string;
  lo: number;
  hi: number;
  count: number;
};

export function binNumeric(values: number[], binCount: number): BinnedNumeric[] {
  if (values.length === 0) return [];
  const vmin = Math.min(...values);
  const vmax = Math.max(...values);
  if (vmin === vmax) {
    return [
      {
        label: fmtTruncIntEn(vmin),
        lo: vmin,
        hi: vmax,
        count: values.length,
      },
    ];
  }
  const n = Math.max(2, Math.min(binCount, 24));
  const step = (vmax - vmin) / n;
  const bins = Array.from({ length: n }, (_, i) => ({
    lo: vmin + i * step,
    hi: vmin + (i + 1) * step,
    count: 0,
  }));
  for (const v of values) {
    let i = Math.floor((v - vmin) / step);
    if (i >= n) i = n - 1;
    if (i < 0) i = 0;
    bins[i].count += 1;
  }
  return bins.map((b) => ({
    ...b,
    label: `${fmtTruncIntEn(b.lo)}–${fmtTruncIntEn(b.hi)}`,
  }));
}

export type MetricsSummary = {
  state_row_count: number;
  ai_row_count: number;
  ai_executed_row_count: number;
  status_counts: Record<string, number>;
  total_tokens_executed: number;
  /** Sum over executed AI rows; may be absent on older API responses. */
  input_tokens_executed?: number;
  output_tokens_executed?: number;
  latency_ms_mean: number | null;
  latency_ms_median: number | null;
  event_index_min: number | null;
  event_index_max: number | null;
  /** Deepest map floor / act from state `vm_summary` (omitted on older logs). */
  max_floor_reached?: number | null;
  max_act_reached?: number | null;
};
