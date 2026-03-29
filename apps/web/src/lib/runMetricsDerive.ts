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

export function screenTypeOrder(states: StateRow[]): string[] {
  const seen = new Set<string>();
  const order: string[] = [];
  for (const s of states) {
    const k = s.vm.screen_type?.trim() || "unknown";
    if (!seen.has(k)) {
      seen.add(k);
      order.push(k);
    }
  }
  return order;
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
