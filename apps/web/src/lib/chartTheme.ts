/**
 * Chart stroke/fill strings for Recharts — must match semantic `--chart-*` tokens
 * on `:root` in `index.css` (light parchment + **jewel** chart accents: ruby / cobalt / emerald).
 */
export const chartColors = {
  axis: "var(--chart-axis)",
  grid: "var(--chart-grid)",
  refLine: "var(--chart-ref-line)",
  hp: "var(--chart-hp)",
  maxHp: "var(--chart-max-hp)",
  gold: "var(--chart-gold)",
  floor: "var(--chart-floor)",
  legal: "var(--chart-legal)",
  enemy: "var(--chart-enemy)",
  hand: "var(--chart-hand)",
  deck: "var(--chart-deck)",
  relic: "var(--chart-relic)",
  aiInput: "var(--chart-ai-input)",
  aiOutput: "var(--chart-ai-output)",
  throughput: "var(--chart-throughput)",
  latency: "var(--chart-latency)",
  cumulativeStroke: "var(--chart-cumulative)",
  cumulativeFill: "var(--chart-cumulative-fill)",
  histInput: "var(--chart-hist-input)",
  histLatency: "var(--chart-hist-latency)",
} as const;

/** AI status pie — ordered gold / cobalt / emerald / ruby (+ neutrals). */
export const PIE_COLORS = [
  "var(--chart-pie-1)",
  "var(--chart-pie-2)",
  "var(--chart-pie-3)",
  "var(--chart-pie-4)",
  "var(--chart-pie-5)",
  "var(--chart-pie-6)",
  "var(--chart-pie-7)",
] as const;
