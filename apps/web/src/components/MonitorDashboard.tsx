import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useControlPlane } from "../hooks/useControlPlane";
import {
  type CommandStepRow,
  commandStepsForDisplay,
  isCommandLegal,
} from "../lib/playResolve";
import { buildTacticalPrompt } from "../lib/tacticalPrompt";
import type { ActionDTO, HeaderDTO, ViewModelDTO } from "../types/viewModel";

/** Best-effort description text from ingress / KB fields (aligned with projection enrich). */
function entityTooltip(obj: Record<string, unknown> | null | undefined): string {
  if (!obj) return "";
  const direct =
    obj.description ??
    obj.text ??
    obj.flavor ??
    obj.body_text ??
    obj.help;
  if (typeof direct === "string" && direct.trim()) return direct.trim();

  const kb = obj.kb;
  if (kb && typeof kb === "object" && !Array.isArray(kb)) {
    const k = kb as Record<string, unknown>;
    const cardRelicDesc =
      typeof k.description === "string" && k.description.trim()
        ? k.description.trim()
        : "";
    const effect =
      typeof k.effect === "string" && k.effect.trim() ? k.effect.trim() : "";
    const flavor =
      typeof k.flavor_text === "string" && k.flavor_text.trim()
        ? k.flavor_text.trim()
        : "";
    const rarity =
      typeof k.rarity === "string" && k.rarity.trim() ? k.rarity.trim() : "";

    const kbLines: string[] = [];
    if (cardRelicDesc) kbLines.push(cardRelicDesc);
    if (flavor) kbLines.push(flavor);
    if (effect) kbLines.push(effect);
    if (kbLines.length) {
      if (rarity) kbLines.push(`(${rarity})`);
      return kbLines.join("\n\n");
    }

    const parts: string[] = [];
    if (k.general) parts.push(String(k.general));
    if (k.notes) parts.push(String(k.notes));
    if (k.ai) parts.push(`AI: ${k.ai}`);
    if (k.hp_range) parts.push(`HP range: ${k.hp_range}`);
    if (Array.isArray(k.moves)) parts.push(`Moves: ${k.moves.join(", ")}`);
    if (parts.length) return parts.join("\n\n");
  }
  return "";
}

function labeledTooltip(name: string, obj: Record<string, unknown>): string {
  const t = entityTooltip(obj);
  if (t) return `${name}\n\n${t}`;
  return name.trim() ? name : "";
}

function monsterTooltip(m: Record<string, unknown>): string {
  const name = String(m.name ?? "?");
  const body = entityTooltip(m);
  if (body) return `${name}\n\n${body}`;
  const intent = m.intent_display ? String(m.intent_display) : "";
  const powers = (m.powers as Record<string, unknown>[] | undefined) ?? [];
  const pStr = powers.length
    ? powers
        .map((p) => {
          const pn = String(p.name ?? "");
          const stacks = p.stacks != null ? ` (${p.stacks})` : "";
          const d = entityTooltip(p);
          return d ? `${pn}${stacks} — ${d}` : `${pn}${stacks}`;
        })
        .join("\n")
    : "";
  return [name, intent, pStr].filter(Boolean).join("\n");
}

/** In-game card text / KB description for the hand & pile tables (no hover). */
function cardTableText(c: Record<string, unknown>): string {
  const raw = c.description;
  if (typeof raw === "string" && raw.trim()) return raw.trim();
  const kb = c.kb as Record<string, unknown> | undefined;
  const d =
    kb && typeof kb.description === "string" ? kb.description.trim() : "";
  if (d) return d;
  return "—";
}

type TipSide = "top" | "right" | "bottom";

function HoverTip({
  tip,
  children,
  className = "",
  side = "top",
}: {
  tip: string;
  children: ReactNode;
  className?: string;
  side?: TipSide;
}) {
  const text = tip.trim();
  if (!text) return <div className={className}>{children}</div>;
  const pos =
    side === "right"
      ? "left-full top-1/2 z-[200] ml-2 max-h-[min(70vh,24rem)] -translate-y-1/2 overflow-y-auto"
      : side === "bottom"
        ? "left-1/2 top-full z-[200] mt-2 max-h-[min(70vh,24rem)] -translate-x-1/2 overflow-y-auto"
        : "left-1/2 z-[200] mb-2 max-h-[min(70vh,24rem)] -translate-x-1/2 overflow-y-auto bottom-full";
  return (
    <div className={`group/tip relative min-w-0 cursor-help ${className}`}>
      {children}
      <div
        role="tooltip"
        className={`custom-scroll pointer-events-none absolute ${pos} w-max min-w-[8rem] max-w-[min(22rem,calc(100vw-2rem))] scale-95 rounded-md border border-slate-600 bg-slate-800 px-2.5 py-2 text-left font-telemetry text-xs font-normal leading-snug tracking-normal whitespace-pre-wrap text-slate-200 opacity-0 shadow-xl transition-all duration-150 group-hover/tip:scale-100 group-hover/tip:opacity-100`}
      >
        {text}
      </div>
    </div>
  );
}

/** Compact operator controls — dense enough for a narrow AI rail + full HD. */
const osdBtnBase =
  "font-console inline-flex h-6 shrink-0 items-center justify-center rounded border px-2 text-[10px] font-semibold uppercase tracking-[0.08em] transition duration-150 disabled:cursor-not-allowed disabled:opacity-35";

const osdBtnGhost =
  `${osdBtnBase} border-slate-600/90 bg-slate-800/80 text-slate-400 hover:border-slate-500 hover:bg-slate-700/75 hover:text-slate-200`;

/** Solid fill, same chrome family as Approve / CTA (no outline accent bar). */
const osdBtnRetry =
  `${osdBtnBase} border-amber-800/80 bg-amber-900/75 text-amber-50 hover:bg-amber-800/85`;

const osdBtnApprove =
  `${osdBtnBase} border-emerald-800/70 bg-emerald-950/70 text-emerald-100 hover:bg-emerald-900/80`;
const osdBtnReject =
  `${osdBtnBase} border-slate-600/90 bg-slate-800/90 text-slate-300 hover:bg-slate-700/85`;
const osdBtnCta =
  `${osdBtnBase} border-indigo-700/85 bg-indigo-800 text-indigo-50 hover:bg-indigo-700`;

const osdPanelStrip =
  "flex shrink-0 items-center justify-between gap-2 border-b border-slate-700/85 bg-slate-800/95 px-2 py-1 font-console text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-300";

const osdSectionLabel =
  "font-console text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500";

const osdStatCaption =
  "font-console text-[9px] font-semibold uppercase tracking-[0.18em] text-slate-500";

function actionBtnClass(style: string): string {
  const map: Record<string, string> = {
    danger:
      "border-red-800/90 bg-red-950/75 text-red-100 hover:bg-red-900/90",
    primary:
      "border-sky-800/85 bg-sky-950/60 text-sky-100 hover:bg-sky-900/75",
    success:
      "border-emerald-800/85 bg-emerald-950/60 text-emerald-100 hover:bg-emerald-900/75",
    secondary:
      "border-slate-600/90 bg-slate-800/80 text-slate-200 hover:bg-slate-700/90",
  };
  return `font-console rounded border py-0.5 px-2 text-[10px] font-semibold uppercase tracking-wide transition ${map[style] ?? map.secondary}`;
}

type PileKind = "draw" | "discard" | "exhaust";

/** Single chassis: three deck zones — industrial readout, not three chunky tiles */
function PileTelemetryBar({
  draw: drawN,
  discard: discN,
  exhaust: exhN,
  onInspect,
}: {
  draw: number;
  discard: number;
  exhaust: number;
  onInspect: (k: PileKind) => void;
}) {
  const segments: {
    kind: PileKind;
    abbr: string;
    title: string;
    n: number;
    tint: string;
    glow: string;
  }[] = [
    {
      kind: "draw",
      abbr: "DRW",
      title: "Draw pile — click to inspect",
      n: drawN,
      tint: "text-cyan-200/95",
      glow: "group-hover:text-cyan-100",
    },
    {
      kind: "discard",
      abbr: "DIS",
      title: "Discard pile — click to inspect",
      n: discN,
      tint: "text-amber-200/90",
      glow: "group-hover:text-amber-100",
    },
    {
      kind: "exhaust",
      abbr: "EXH",
      title: "Exhaust pile — click to inspect",
      n: exhN,
      tint: "text-rose-200/85",
      glow: "group-hover:text-rose-100",
    },
  ];

  return (
    <div
      className="deck-telemetry flex shrink-0 overflow-hidden rounded-md border border-slate-700/90"
      role="group"
      aria-label="Deck piles — click a zone to inspect"
    >
      {segments.map((s, i) => (
        <button
          key={s.kind}
          type="button"
          onClick={() => onInspect(s.kind)}
          title={s.title}
          className={
            "group relative flex min-h-[1.75rem] min-w-[3.75rem] flex-1 items-center justify-between gap-1.5 px-1.5 py-0.5 text-left transition-[background-color,box-shadow] duration-150 " +
            "hover:bg-slate-800/40 active:bg-slate-800/65 " +
            "focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-400/45 " +
            (i > 0 ? "border-l border-slate-700/55 " : "")
          }
        >
          <span className="font-console text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500 transition-colors group-hover:text-slate-400">
            {s.abbr}
          </span>
          <span
            className={`font-telemetry text-[13px] font-semibold leading-none tabular-nums tracking-tight transition-colors ${s.tint} ${s.glow}`}
          >
            {s.n}
          </span>
        </button>
      ))}
    </div>
  );
}

function cardHash(uuid: unknown): string {
  const s = typeof uuid === "string" ? uuid : "";
  return s.length >= 6 ? s.slice(0, 6) : s || "—";
}

function headerClass(h: HeaderDTO | null | undefined): string {
  return h?.["class"] ?? "?";
}

/** Enemy block: header row (name, HP, intent) + powers row — layout per IDE mock. */
function EnemyCard({ m }: { m: Record<string, unknown> }) {
  const name = String(m.name ?? "?");
  const hp = String(m.hp_display ?? "");
  const intent = String(m.intent_display ?? "");
  const powers = (m.powers as Record<string, unknown>[] | undefined) ?? [];
  const tip = monsterTooltip(m);

  return (
    <div
      className="flex cursor-help flex-col overflow-hidden rounded border border-slate-700 bg-slate-800/30"
      title={tip || undefined}
    >
        <div className="flex items-center justify-between border-b border-slate-700/50 bg-slate-800/50 px-3 py-1.5">
          <div className="flex items-baseline gap-2">
            <span className="font-console text-xs font-bold text-red-400">
              {name}
            </span>
            <span className={osdStatCaption}>HP</span>
            <span className="font-telemetry text-xs font-medium text-slate-200">
              {hp || "—"}
            </span>
          </div>
          <div className="font-console text-[10px] font-semibold uppercase tracking-wide text-red-400">
            {intent || "—"}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 px-3 py-2">
          {powers.length === 0 ? (
            <span className="text-[10px] text-slate-600">—</span>
          ) : (
            powers.map((p, i) => {
              const pDesc = entityTooltip(p);
              return (
                <span
                  key={i}
                  title={pDesc || undefined}
                  className="inline-flex rounded border border-purple-700/50 bg-purple-900/40 px-1.5 py-0.5 text-[10px] text-purple-300"
                >
                  {String(p.name ?? "?")}
                  {p.stacks != null ? ` (${String(p.stacks)})` : ""}
                </span>
              );
            })
          )}
        </div>
      </div>
  );
}

function cardNameClass(type: unknown): string {
  const t = String(type ?? "").toUpperCase();
  if (t === "ATTACK") return "font-bold text-red-400";
  if (t === "SKILL") return "font-bold text-blue-400";
  if (t === "POWER") return "font-bold text-purple-400";
  return "font-bold text-slate-300";
}

function CardTable({ cards }: { cards: Record<string, unknown>[] }) {
  return (
    <table className="w-full text-left whitespace-nowrap [&_td:last-child]:whitespace-normal">
      <thead className="sticky top-0 z-10 bg-slate-900 font-console text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        <tr>
          <th className="w-8 border-b border-slate-800 py-2 px-3 font-semibold">
            #
          </th>
          <th className="w-24 border-b border-slate-800 py-2 px-3 font-semibold">
            Hash
          </th>
          <th className="w-8 border-b border-slate-800 py-2 px-3 text-center font-semibold">
            $
          </th>
          <th className="w-32 border-b border-slate-800 py-2 px-3 font-semibold">
            Name
          </th>
          <th className="w-24 border-b border-slate-800 py-2 px-3 font-semibold">
            Type
          </th>
          <th className="w-full border-b border-slate-800 py-2 px-3 font-semibold">
            Text
          </th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-800 font-telemetry text-[10px] text-slate-400">
        {cards.map((c, idx) => (
            <tr key={idx} className="hover:bg-slate-800/50">
              <td className="py-2 px-3">{idx + 1}</td>
              <td className="py-2 px-3 text-slate-500">{cardHash(c.uuid)}</td>
              <td className="py-2 px-3 text-center">
                <span className="font-bold text-cyan-400">
                  {String(c.cost ?? "—")}
                </span>
              </td>
              <td className={`py-2 px-3 ${cardNameClass(c.type)}`}>
                {String(c.name ?? "?")}
              </td>
              <td className="py-2 px-3 text-[11px] text-slate-500">
                {String(c.type ?? "—")}
              </td>
              <td className="max-w-md py-2 px-3 break-words text-slate-300">
                {cardTableText(c)}
              </td>
            </tr>
          ))}
      </tbody>
    </table>
  );
}

function PileInspectModal({
  title,
  cards,
  onClose,
}: {
  title: string;
  cards: Record<string, unknown>[];
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="presentation"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label={title}
        className="custom-scroll flex max-h-[85vh] max-w-4xl flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-900 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={osdPanelStrip}>
          <div className="flex min-w-0 items-baseline gap-3 normal-case tracking-normal">
            <span className="truncate font-console text-xs font-bold text-slate-100">
              {title}
            </span>
            <span className="shrink-0 font-telemetry text-[10px] text-slate-500">
              {cards.length} cards
            </span>
          </div>
          <button type="button" onClick={onClose} className={osdBtnGhost}>
            Close
          </button>
        </div>
        <div className="custom-scroll min-h-0 flex-1 overflow-auto p-3">
          {cards.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">Empty pile</p>
          ) : (
            <CardTable cards={cards} />
          )}
        </div>
      </div>
    </div>
  );
}

export function MonitorDashboard() {
  const {
    snapshot,
    connected,
    logLines,
    postIngress,
    loadSample,
    queueManualCommand,
    resumeAgent,
    retryAgent,
    pushLog,
    historyThreads,
    historyEvents,
    historyCheckpoints,
    historyThreadFilter,
    setHistoryThreadFilter,
    refreshHistoryThreads,
    loadHistoryEvents,
    loadHistoryCheckpoints,
  } = useControlPlane();

  const copyClipboard = useCallback(
    async (text: string, label: string) => {
      if (text === "") {
        pushLog("SYSTEM", `Nothing to copy (${label})`);
        return;
      }
      try {
        await navigator.clipboard.writeText(text);
        pushLog("SYSTEM", `Copied ${label} to clipboard`);
      } catch (e) {
        pushLog("ERROR", `Copy failed: ${String(e)}`);
      }
    },
    [pushLog],
  );

  const [paste, setPaste] = useState("");
  const [editCmd, setEditCmd] = useState("");
  const [pileInspect, setPileInspect] = useState<PileKind | null>(null);

  const hitlQueuedSteps = useMemo(() => {
    const intr = snapshot?.agent?.pending_approval?.interrupt;
    if (!intr) return [];
    const head = intr.command != null ? String(intr.command).trim() : "";
    const tail = Array.isArray(intr.command_queue)
      ? intr.command_queue.map((s) => String(s).trim()).filter(Boolean)
      : [];
    if (head) return [head, ...tail];
    return tail;
  }, [snapshot?.agent?.pending_approval?.interrupt]);

  const vm: ViewModelDTO | null = snapshot?.view_model ?? null;
  const stateId = snapshot?.state_id ?? null;
  const combat = vm?.combat as Record<string, unknown> | null | undefined;
  const inventory = vm?.inventory as Record<string, unknown> | null | undefined;
  const header = vm?.header;

  const hand = (combat?.hand as Record<string, unknown>[] | undefined) ?? [];
  const monsters =
    (combat?.monsters as Record<string, unknown>[] | undefined) ?? [];
  const playerPowers =
    (combat?.player_powers as Record<string, unknown>[] | undefined) ?? [];
  const drawPile =
    (combat?.draw_pile as Record<string, unknown>[] | undefined) ?? [];
  const discardPile =
    (combat?.discard_pile as Record<string, unknown>[] | undefined) ?? [];
  const exhaustPile =
    (combat?.exhaust_pile as Record<string, unknown>[] | undefined) ?? [];
  const draw = drawPile.length;
  const disc = discardPile.length;
  const exhaust = exhaustPile.length;

  const pileModal =
    pileInspect === "draw"
      ? { title: "Draw pile", cards: drawPile }
      : pileInspect === "discard"
        ? { title: "Discard pile", cards: discardPile }
        : pileInspect === "exhaust"
          ? { title: "Exhaust pile", cards: exhaustPile }
          : null;

  const relics = (inventory?.relics as Record<string, unknown>[] | undefined) ?? [];
  const potions =
    (inventory?.potions as Record<string, unknown>[] | undefined) ?? [];

  const potionSlots = useMemo(() => {
    const slots: (Record<string, unknown> | null)[] = [null, null, null];
    potions.forEach((p, i) => {
      if (i < 3) slots[i] = p;
    });
    return slots;
  }, [potions]);

  const applyPaste = () => {
    try {
      const body = JSON.parse(paste) as Record<string, unknown>;
      void postIngress(body);
      pushLog("SYSTEM", "Applied JSON from paste buffer");
    } catch (e) {
      pushLog("ERROR", `Invalid JSON: ${String(e)}`);
    }
  };

  const actions: ActionDTO[] = vm?.actions ?? [];
  const { user: tacticalUser } = useMemo(() => buildTacticalPrompt(vm), [vm]);

  const proposal = snapshot?.agent?.proposal as Record<string, unknown> | undefined;
  const proposalRationale =
    proposal?.rationale != null && String(proposal.rationale).trim() !== ""
      ? String(proposal.rationale)
      : null;

  const llmRaw =
    proposal?.llm_raw != null ? String(proposal.llm_raw) : "";

  const parsedModelBlock = useMemo(() => {
    if (!proposal) return null;
    const status = proposal.status != null ? String(proposal.status) : null;
    const command =
      proposal.command != null && String(proposal.command).trim() !== ""
        ? String(proposal.command)
        : null;
    const rationale =
      proposal.rationale != null && String(proposal.rationale).trim() !== ""
        ? String(proposal.rationale)
        : null;
    const errorReason =
      proposal.error_reason != null &&
      String(proposal.error_reason).trim() !== ""
        ? String(proposal.error_reason)
        : null;
    const resolveTag =
      proposal.resolve_tag != null &&
      String(proposal.resolve_tag).trim() !== ""
        ? String(proposal.resolve_tag)
        : null;
    const parsedModel = proposal.parsed_model as Record<string, unknown> | null | undefined;
    let parsedJson: string | null = null;
    if (parsedModel != null && typeof parsedModel === "object") {
      try {
        parsedJson = JSON.stringify(parsedModel, null, 2);
      } catch {
        parsedJson = String(parsedModel);
      }
    }
    if (
      !status &&
      !command &&
      !rationale &&
      !errorReason &&
      !resolveTag &&
      !parsedJson
    ) {
      return null;
    }
    return {
      status,
      command,
      rationale,
      resolveTag,
      errorReason,
      parsedJson,
    };
  }, [proposal]);

  const proposalCmdNotLegalNow = useMemo(() => {
    const c = parsedModelBlock?.command;
    if (!c || !actions.length) return false;
    return !isCommandLegal(actions, c);
  }, [parsedModelBlock?.command, actions]);

  const resolvedCommandSteps = useMemo((): CommandStepRow[] => {
    if (!vm?.actions?.length || !proposal) return [];
    const pm = proposal.parsed_model as Record<string, unknown> | null | undefined;
    const apiSteps = pm?.command_steps;
    if (Array.isArray(apiSteps) && apiSteps.length > 0) {
      return apiSteps as CommandStepRow[];
    }
    const cmds = pm?.commands;
    if (Array.isArray(cmds) && cmds.length > 0) {
      return commandStepsForDisplay(vm.actions, cmds.map(String));
    }
    const single = pm?.command;
    if (single != null && String(single).trim() !== "") {
      return commandStepsForDisplay(vm.actions, [String(single).trim()]);
    }
    const pc = proposal.command;
    if (pc != null && String(pc).trim() !== "") {
      return commandStepsForDisplay(vm.actions, [String(pc).trim()]);
    }
    return [];
  }, [proposal, vm]);

  const parsedCopyText = useMemo(() => {
    if (!parsedModelBlock) return "";
    const b = parsedModelBlock;
    const lines: string[] = [];
    if (b.status) lines.push(`status: ${b.status}`);
    if (b.command) lines.push(`command: ${b.command}`);
    if (b.errorReason) lines.push(`error: ${b.errorReason}`);
    if (b.resolveTag && b.resolveTag !== b.rationale) {
      lines.push(`resolve_tag: ${b.resolveTag}`);
    }
    if (b.rationale && b.rationale !== b.errorReason) {
      lines.push(`rationale: ${b.rationale}`);
    }
    if (b.parsedJson) lines.push(b.parsedJson);
    if (resolvedCommandSteps.length) {
      lines.push(
        "resolved_steps:",
        ...resolvedCommandSteps.map(
          (r) =>
            `  ${r.model} => ${r.canonical ?? "—"} (${r.resolve_tag})`,
        ),
      );
    }
    return lines.join("\n");
  }, [parsedModelBlock, resolvedCommandSteps]);

  const tacticalPromptText = !vm?.actions?.length
    ? "— Load ingress —"
    : tacticalUser;

  const explorerHref =
    snapshot?.agent?.thread_id != null && snapshot.agent.thread_id !== ""
      ? `/explorer?thread_id=${encodeURIComponent(snapshot.agent.thread_id)}`
      : "/explorer";
  const envLine = `${snapshot?.agent?.agent_mode ?? "—"} · ${snapshot?.agent?.proposer ?? "legacy"}/${snapshot?.agent?.llm_backend ?? "off"} · tid ${snapshot?.agent?.thread_id ?? "n/a"} · seed ${snapshot?.agent?.run_seed ?? "n/a"} · ${stateId ?? "—"}`;
  const agentErrorText = snapshot?.agent?.agent_error;

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gradient-to-b from-slate-900 via-[#0a0d11] to-[#06080a] text-xs text-slate-300 select-none">
      {/* Top bar — game / session controls only; combat readouts live in the stats strip */}
      <header className="flex shrink-0 items-center border-b border-slate-700/90 bg-slate-900/80 px-3 py-2 backdrop-blur-sm">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
          <span className="font-console text-xs font-bold tracking-[0.14em] text-slate-100">
            SPIRE AGENT
            <span className="ml-1.5 font-medium tracking-normal text-slate-500">
              · operator
            </span>
          </span>
          <Link
            to={explorerHref}
            title="History explorer (no LangGraph threads in legacy mode; page opens for future log-backed views)"
            className="rounded border border-sky-800/60 bg-sky-950/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-sky-300 hover:bg-sky-900/50"
          >
            History
          </Link>
          <div
            className={`font-console flex h-6 items-center gap-1.5 rounded border px-2 text-[10px] font-semibold uppercase tracking-wide ${
              connected
                ? "border-emerald-700/50 bg-emerald-950/35 text-emerald-400"
                : "border-red-800/55 bg-red-950/30 text-red-400"
            }`}
          >
            <span className="relative flex h-1.5 w-1.5">
              {connected ? (
                <>
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                </>
              ) : (
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-red-500" />
              )}
            </span>
            {connected ? "Live" : "Offline"}
          </div>

          <div className="flex flex-wrap items-center gap-1.5 border-l border-slate-600/70 pl-4">
            <span className={osdStatCaption}>Replay</span>
            <select
              disabled
              className="font-console h-6 rounded border border-slate-700 bg-slate-950/80 px-2 text-[10px] font-medium text-slate-500 outline-none"
            >
              <option>Select run…</option>
            </select>
            <button type="button" disabled className={osdBtnGhost}>
              Load
            </button>
            <button type="button" onClick={() => loadSample()} className={osdBtnCta}>
              Load sample
            </button>
          </div>
        </div>
      </header>

      {/* Stats + potions — left-aligned run readout */}
      <div className="flex min-h-0 shrink-0 flex-wrap items-end gap-x-6 gap-y-1.5 border-b border-slate-700/85 bg-slate-800/75 px-3 py-2">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-1.5">
          <div className="flex flex-col gap-px">
            <span className={osdStatCaption}>Turn</span>
            <span className="font-telemetry text-sm font-semibold tabular-nums leading-none text-slate-50">
              {header?.turn ?? "—"}
            </span>
          </div>
          {(
            [
              ["Class", headerClass(header), "text-orange-300"],
              ["Floor", header?.floor ?? "—", "text-slate-200"],
              ["HP", header?.hp_display ?? "—", "text-red-400"],
              ["Gold", header?.gold ?? "—", "text-amber-400"],
              ["Energy", header?.energy ?? "—", "text-cyan-400"],
            ] as const
          ).map(([label, val, col]) => (
            <div key={label} className="flex flex-col gap-px">
              <span className={osdStatCaption}>{label}</span>
              <span
                className={`font-telemetry text-sm font-semibold tabular-nums leading-none ${col}`}
              >
                {val}
              </span>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-1.5 border-l border-slate-600/55 pl-5">
            <span className={`${osdStatCaption} mr-0.5`}>Potions</span>
            {potionSlots.map((p, i) =>
              p ? (
                <HoverTip
                  key={i}
                  tip={labeledTooltip(String(p.name ?? "Potion"), p)}
                  side="bottom"
                  className="w-auto shrink-0"
                >
                  <div className="font-console max-w-[7.5rem] truncate rounded border border-slate-600/90 bg-slate-800/80 px-1.5 py-0.5 text-[10px] font-medium text-slate-200">
                    {String(p.name ?? "Potion")}
                  </div>
                </HoverTip>
              ) : (
                <div
                  key={i}
                  className="font-console rounded border border-dashed border-slate-600/70 px-1.5 py-0.5 text-[10px] text-slate-600"
                >
                  —
                </div>
              ),
            )}
          </div>
        </div>
      </div>

      {/* IDE workspace */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Col 1 — relics / powers */}
        <aside className="flex w-36 shrink-0 flex-col border-r border-slate-700 bg-slate-900">
          <div className="flex min-h-0 flex-1 flex-col border-b border-slate-700">
            <div className={osdPanelStrip}>Relics · {relics.length}</div>
            <div className="custom-scroll flex-1 space-y-1 overflow-y-auto p-2">
              {relics.length === 0 ? (
                <div className="px-1 font-console text-[10px] italic text-slate-600">
                  None
                </div>
              ) : (
                relics.map((r, i) => (
                  <div
                    key={i}
                    title={
                      labeledTooltip(String(r.name ?? "?"), r) || undefined
                    }
                    className="cursor-help rounded border border-slate-700 bg-slate-800/50 px-1.5 py-1 text-[10px] text-slate-300"
                  >
                    {String(r.name ?? "?")}
                  </div>
                ))
              )}
            </div>
          </div>
          <div className="flex min-h-0 flex-1 flex-col">
            <div className={osdPanelStrip}>Powers</div>
            <div className="custom-scroll flex-1 overflow-y-auto p-2">
              {playerPowers.length === 0 ? (
                <div className="px-1 font-console text-[10px] italic text-slate-600">
                  None
                </div>
              ) : (
                <div className="space-y-1">
                  {playerPowers.map((p, i) => (
                    <div
                      key={i}
                      title={
                        labeledTooltip(String(p.name ?? "?"), p) || undefined
                      }
                      className="cursor-help rounded border border-slate-700 bg-slate-800/50 px-1.5 py-0.5 text-[10px]"
                    >
                      {String(p.name ?? "?")}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </aside>

        {/* Col 2–3 — main */}
        <main className="flex min-h-0 min-w-0 flex-1 flex-col border-r border-slate-700">
          {/* Top: enemies | hand */}
          <div className="flex min-h-0 flex-1 border-b border-slate-700">
            <div className="flex min-h-0 min-w-0 flex-[1.05] flex-col border-r border-slate-700">
              <div className={`sticky top-0 z-10 ${osdPanelStrip}`}>
                Enemies · {monsters.length}
              </div>
              <div className="custom-scroll flex-1 space-y-3 overflow-y-auto p-3">
                {monsters.length === 0 ? (
                  <div className="py-6 text-center text-slate-600">
                    No combat / no enemies
                  </div>
                ) : (
                  monsters.map((m, i) => <EnemyCard key={i} m={m} />)
                )}
              </div>
            </div>

            <div className="flex min-h-0 min-w-0 flex-[0.95] flex-col bg-slate-900">
              <div
                className={`sticky top-0 z-10 flex shrink-0 items-center justify-between gap-2 ${osdPanelStrip}`}
              >
                <span className="min-w-0 shrink-0 truncate">
                  Hand · {hand.length}
                </span>
                <PileTelemetryBar
                  draw={draw}
                  discard={disc}
                  exhaust={exhaust}
                  onInspect={setPileInspect}
                />
              </div>
              <div className="custom-scroll min-h-0 flex-1 overflow-y-auto">
                <CardTable cards={hand} />
              </div>
            </div>
          </div>

          {/* Valid actions — full width under enemies + hand */}
          <div className="flex h-[5.5rem] max-h-[26vh] shrink-0 flex-col border-b border-slate-700 bg-slate-900/50">
            <div
              className={`shrink-0 border-b border-slate-700/85 bg-slate-800/80 px-2 py-1 ${osdSectionLabel}`}
            >
              Valid actions
            </div>
            <div className="custom-scroll flex flex-1 flex-wrap content-start gap-1 overflow-y-auto px-2 py-1">
              {actions.length === 0 ? (
                <span className="font-console text-[10px] text-slate-600">
                  No actions
                </span>
              ) : (
                actions.map((a, i) => (
                  <button
                    key={`${a.command}-${i}`}
                    type="button"
                    className={actionBtnClass(a.style)}
                    title={a.command}
                    onClick={() => void queueManualCommand(a.command)}
                  >
                    {a.label}
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Bottom: LLM prompt | session log */}
          <div className="flex h-[min(38vh,30rem)] min-h-[20rem] shrink-0 border-t border-slate-700">
            <div className="flex min-h-0 min-w-0 flex-1 flex-col border-r border-slate-700 bg-slate-950">
              <div className={osdPanelStrip}>
                <span className="min-w-0 shrink truncate">LLM user prompt</span>
                <div className="flex min-w-0 shrink-0 items-center gap-2">
                  <button
                    type="button"
                    className={osdBtnGhost}
                    onClick={() =>
                      void copyClipboard(tacticalPromptText, "LLM user prompt")
                    }
                  >
                    Copy
                  </button>
                  <span className="max-w-[11rem] truncate font-console text-[10px] font-normal normal-case tracking-normal text-slate-500 md:max-w-md">
                    {snapshot?.agent?.proposer === "legacy"
                      ? "Debug summary — legacy prompt_builder may differ."
                      : "Proposer status from server."}
                  </span>
                </div>
              </div>
              {proposalRationale ? (
                <div className="flex shrink-0 items-start gap-2 border-b border-emerald-900/35 bg-emerald-950/25 px-2 py-1">
                  <span className="shrink-0 font-console text-[9px] font-semibold uppercase tracking-wide text-emerald-500">
                    Rationale
                  </span>
                  <span className="font-telemetry text-[10px] leading-snug text-emerald-200">
                    {proposalRationale}
                  </span>
                </div>
              ) : null}
              <pre className="font-telemetry custom-scroll flex-1 overflow-auto p-2 text-[10px] leading-relaxed whitespace-pre text-slate-400">
                {!vm?.actions?.length
                  ? "— Load ingress —"
                  : tacticalUser}
              </pre>
            </div>

            <div className="flex w-[min(24vw,19rem)] min-w-[14rem] max-w-[20rem] shrink-0 flex-col bg-slate-950">
              <div className={osdPanelStrip}>
                <span>Session log</span>
                <span className="font-telemetry text-[10px] tabular-nums text-slate-500">
                  {logLines.length}
                </span>
              </div>
              <div className="custom-scroll flex-1 space-y-1 overflow-y-auto p-2 font-telemetry text-[10px] leading-snug">
                {logLines.map((line, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="shrink-0 whitespace-nowrap text-slate-500">
                      [{line.t}]
                    </span>
                    <span
                      className={`w-12 shrink-0 font-semibold ${
                        line.kind === "ERROR"
                          ? "text-red-400"
                          : line.kind === "STATE"
                            ? "text-blue-400"
                            : line.kind === "SYSTEM"
                              ? "text-yellow-500"
                              : "text-slate-500"
                      }`}
                    >
                      {line.kind}
                    </span>
                    <span className="text-slate-300">{line.msg}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </main>

        {/* Col 4 — AI operator rail (compact; boxed headers avoid overlap with scroll areas) */}
        <aside className="z-20 flex w-[22.5rem] min-w-[19rem] shrink-0 flex-col border-l border-emerald-950/30 bg-[#07090c] shadow-[-8px_0_24px_rgba(0,0,0,0.4)]">
          <div className={osdPanelStrip}>
            <span className="min-w-0 truncate">AI control</span>
            <button
              type="button"
              disabled={
                snapshot?.ingress == null ||
                typeof snapshot.ingress !== "object"
              }
              title="Legacy: clears a pending approval if any; a new AI proposal requires the next game update (CommunicationMod), not a server graph replay."
              className={osdBtnRetry}
              onClick={() => void retryAgent()}
            >
              Retry AI
            </button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2 custom-scroll">
            <div
              className="font-telemetry shrink-0 cursor-default truncate rounded border border-slate-700/80 bg-slate-950/80 px-2 py-1 text-[10px] leading-snug text-slate-500"
              title={envLine}
            >
              {envLine}
            </div>

            <div className="shrink-0 space-y-1.5 rounded border border-indigo-900/40 bg-slate-950/50 p-2">
              <div className="flex items-center justify-between gap-1">
                <span className={osdSectionLabel}>History</span>
                <button
                  type="button"
                  className={osdBtnGhost}
                  onClick={() => void refreshHistoryThreads()}
                >
                  Threads
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                <select
                  value={historyThreadFilter}
                  onChange={(e) => {
                    const v = e.target.value;
                    setHistoryThreadFilter(v);
                    if (v) {
                      void loadHistoryEvents(v);
                      void loadHistoryCheckpoints(v);
                    }
                  }}
                  className="font-telemetry h-6 max-w-full flex-1 rounded border border-slate-700 bg-slate-950 px-1 text-[10px] text-slate-200 outline-none"
                >
                  <option value="">Thread…</option>
                  {historyThreads.map((t) => (
                    <option key={t.thread_id} value={t.thread_id}>
                      {t.thread_id} ({t.event_count})
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className={osdBtnGhost}
                  onClick={() => {
                    const tid =
                      historyThreadFilter ||
                      snapshot?.agent?.thread_id ||
                      "default";
                    setHistoryThreadFilter(tid);
                    void loadHistoryEvents(tid);
                    void loadHistoryCheckpoints(tid);
                  }}
                >
                  Load
                </button>
              </div>
              <div className="custom-scroll max-h-24 space-y-0.5 overflow-y-auto font-telemetry text-[9px] leading-tight text-slate-400">
                {historyEvents.length === 0 ? (
                  <div className="text-slate-600">No events loaded</div>
                ) : (
                  historyEvents.map((e, i) => (
                    <div
                      key={i}
                      className="truncate border-b border-slate-800/50 border-b-transparent py-0.5"
                      title={JSON.stringify(e)}
                    >
                      <span className="text-indigo-400">
                        {String(e.step_kind ?? "?")}
                      </span>{" "}
                      · seq {String(e.step_seq ?? "—")} ·{" "}
                      <span className="text-slate-500">
                        {String(e.state_id ?? "—")}
                      </span>
                    </div>
                  ))
                )}
              </div>
              <div className="custom-scroll max-h-20 space-y-0.5 overflow-y-auto font-console text-[9px] text-slate-500">
                {historyCheckpoints.length === 0 ? null : (
                  <>
                    <div className="font-semibold text-slate-400">
                      Checkpoints
                    </div>
                    {historyCheckpoints.slice(0, 8).map((c, i) => (
                      <div key={i} className="truncate">
                        {c.checkpoint_id?.slice(0, 8) ?? "?"} ·{" "}
                        {c.state_id != null ? String(c.state_id) : "—"}
                      </div>
                    ))}
                  </>
                )}
              </div>
            </div>

            {snapshot?.agent?.pending_approval ? (
              <div className="flex shrink-0 flex-col gap-2 rounded border border-amber-900/35 bg-slate-800/35 p-2">
                <span className="font-console text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-400">
                  Awaiting approval
                </span>
                <div className="space-y-1 rounded border border-slate-700/90 bg-slate-950 px-2 py-1.5 font-telemetry text-[11px] text-slate-200">
                  {hitlQueuedSteps.length === 0 ? (
                    <div className="text-xs font-semibold text-white">—</div>
                  ) : (
                    hitlQueuedSteps.map((line, i) => (
                      <div
                        key={`${i}-${line}`}
                        className="flex gap-2 leading-snug"
                      >
                        <span className="w-5 shrink-0 text-right font-mono text-[10px] text-slate-500">
                          {i + 1}.
                        </span>
                        <span className="min-w-0 flex-1 font-semibold tracking-wide text-white">
                          {line}
                        </span>
                      </div>
                    ))
                  )}
                </div>
                <p className="font-telemetry text-[9px] leading-snug text-slate-500">
                  Approve runs the first command and leaves further steps to the game
                  process queue when the model proposed a sequence. Reject cancels
                  this proposal.
                </p>
                <div className="flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    className={osdBtnApprove}
                    onClick={() => void resumeAgent("approve")}
                  >
                    Approve all
                  </button>
                  <button
                    type="button"
                    className={osdBtnReject}
                    onClick={() => void resumeAgent("reject")}
                  >
                    Reject all
                  </button>
                </div>
                <div className="flex items-center gap-1.5">
                  <input
                    value={editCmd}
                    onChange={(e) => setEditCmd(e.target.value)}
                    placeholder="Edit command…"
                    className="font-telemetry h-6 min-h-6 min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-0.5 text-[11px] leading-tight text-slate-100 outline-none focus-visible:border-indigo-500 focus-visible:ring-1 focus-visible:ring-indigo-500/25"
                  />
                  <button
                    type="button"
                    className={osdBtnCta}
                    onClick={() => void resumeAgent("edit", editCmd)}
                  >
                    Apply
                  </button>
                </div>
              </div>
            ) : null}

            {agentErrorText ? (
              <div className="custom-scroll max-h-32 shrink-0 space-y-1 overflow-y-auto rounded border border-red-900/55 bg-red-950/25 p-2 font-telemetry text-[10px] text-red-200">
                <div className="flex justify-end">
                  <button
                    type="button"
                    className={osdBtnGhost}
                    onClick={() =>
                      void copyClipboard(String(agentErrorText), "agent error")
                    }
                  >
                    Copy error
                  </button>
                </div>
                <div className="whitespace-pre-wrap break-words leading-snug">
                  {agentErrorText}
                </div>
              </div>
            ) : null}

            <div className="flex min-h-0 flex-1 flex-col gap-2">
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded border border-slate-800/90 bg-slate-950/30">
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-800 bg-slate-900/95 px-2 py-1">
                  <span className={osdSectionLabel}>Model output</span>
                  <button
                    type="button"
                    className={osdBtnGhost}
                    disabled={llmRaw === ""}
                    onClick={() => void copyClipboard(llmRaw, "model output")}
                  >
                    Copy
                  </button>
                </div>
                <textarea
                  readOnly
                  value={llmRaw}
                  className="font-telemetry custom-scroll min-h-0 flex-1 resize-none border-0 bg-transparent p-2 text-[10px] leading-relaxed text-slate-400 outline-none"
                  placeholder={
                    snapshot?.agent?.llm_backend === "off" ||
                    snapshot?.agent?.llm_backend === ""
                      ? "AI disabled or no API — enable LLM in legacy config for raw output here."
                      : "Raw model output from legacy trace when available."
                  }
                  spellCheck={false}
                />
              </div>

              <div className="flex shrink-0 flex-col overflow-hidden rounded border border-slate-800/90 bg-slate-950/30">
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-800 bg-slate-900/95 px-2 py-1">
                  <span className={osdSectionLabel}>Parsed</span>
                  <button
                    type="button"
                    className={osdBtnGhost}
                    disabled={parsedCopyText === ""}
                    onClick={() =>
                      void copyClipboard(parsedCopyText, "parsed proposal")
                    }
                  >
                    Copy
                  </button>
                </div>
                {parsedModelBlock ? (
                  <div className="custom-scroll max-h-28 overflow-y-auto p-2 font-telemetry text-[10px] leading-snug text-slate-400">
                    {parsedModelBlock.status ? (
                      <div className="mb-1 flex flex-wrap gap-x-2 gap-y-0.5">
                        <span className="shrink-0 font-console text-[9px] font-medium uppercase tracking-wide text-slate-500">
                          status
                        </span>
                        <span className="min-w-0 text-slate-200">
                          {parsedModelBlock.status}
                        </span>
                      </div>
                    ) : null}
                    {parsedModelBlock.command ? (
                      <div className="mb-1 flex flex-wrap gap-x-2 gap-y-0.5">
                        <span className="shrink-0 font-console text-[9px] font-medium uppercase tracking-wide text-slate-500">
                          command
                        </span>
                        <span className="min-w-0 text-indigo-300">
                          {parsedModelBlock.command}
                        </span>
                      </div>
                    ) : null}
                    {proposalCmdNotLegalNow ? (
                      <div className="mb-1 text-amber-400/90">
                        Command is not in the current legal action list (stale
                        proposal or state mismatch). Send a fresh ingress or use
                        Retry AI.
                      </div>
                    ) : null}
                    {parsedModelBlock.errorReason ? (
                      <div className="mb-1 flex flex-wrap gap-x-2 text-red-300/90">
                        <span className="shrink-0 font-console text-[9px] font-medium uppercase tracking-wide text-slate-500">
                          error
                        </span>
                        <span className="min-w-0">{parsedModelBlock.errorReason}</span>
                      </div>
                    ) : null}
                    {resolvedCommandSteps.length ? (
                      <div className="mb-1.5 space-y-1 border-b border-slate-800/80 pb-1.5">
                        <span className="font-console text-[9px] font-medium uppercase tracking-wide text-slate-500">
                          Resolved (token → mod index)
                        </span>
                        <ul className="mt-1 space-y-0.5 pl-2">
                          {resolvedCommandSteps.map((row, i) => (
                            <li
                              key={`${row.model}-${i}`}
                              className="font-telemetry break-all text-[10px] leading-snug text-slate-400"
                            >
                              <span className="text-slate-300">{row.model}</span>
                              {row.canonical != null && row.canonical !== row.model ? (
                                <>
                                  <span className="text-slate-600"> → </span>
                                  <span className="text-emerald-300/90">
                                    {row.canonical}
                                  </span>
                                </>
                              ) : row.canonical != null ? (
                                <span className="text-slate-600"> (mod)</span>
                              ) : (
                                <span className="text-amber-400/80"> → ?</span>
                              )}
                              <span className="ml-1.5 text-[9px] text-slate-600">
                                {row.resolve_tag}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {parsedModelBlock.resolveTag &&
                    parsedModelBlock.resolveTag !== parsedModelBlock.rationale ? (
                      <div className="mb-1 flex flex-wrap gap-x-2 text-slate-400">
                        <span className="shrink-0 font-console text-[9px] font-medium uppercase tracking-wide text-slate-500">
                          resolver
                        </span>
                        <span className="min-w-0 font-telemetry text-slate-400">
                          {parsedModelBlock.resolveTag}
                        </span>
                      </div>
                    ) : null}
                    {parsedModelBlock.rationale &&
                    parsedModelBlock.rationale !== parsedModelBlock.errorReason ? (
                      <div className="mb-1 flex flex-wrap gap-x-2 text-slate-300">
                        <span className="shrink-0 font-console text-[9px] font-medium uppercase tracking-wide text-slate-500">
                          rationale
                        </span>
                        <span className="min-w-0 leading-snug">
                          {parsedModelBlock.rationale}
                        </span>
                      </div>
                    ) : null}
                    {parsedModelBlock.parsedJson ? (
                      <pre className="mt-1.5 whitespace-pre-wrap break-all border-t border-slate-800/80 pt-1.5 text-[10px] leading-relaxed text-slate-500">
                        {parsedModelBlock.parsedJson}
                      </pre>
                    ) : null}
                  </div>
                ) : (
                  <div className="px-2 py-3 text-center font-console text-[10px] text-slate-600">
                    No proposal fields yet
                  </div>
                )}
              </div>

              <div className="shrink-0 space-y-1.5 border-t border-slate-800/80 pt-2">
                <div className="flex items-center justify-between gap-2">
                  <span className={`${osdStatCaption} text-slate-500`}>
                    Paste ingress · debug
                  </span>
                  <button
                    type="button"
                    className={osdBtnGhost}
                    disabled={paste === ""}
                    onClick={() =>
                      void copyClipboard(paste, "ingress JSON buffer")
                    }
                  >
                    Copy
                  </button>
                </div>
                <textarea
                  value={paste}
                  onChange={(e) => setPaste(e.target.value)}
                  className="font-telemetry custom-scroll h-16 w-full resize-none rounded border border-slate-800 bg-slate-950 p-2 text-[10px] text-slate-400 outline-none focus-visible:border-indigo-500 focus-visible:ring-1 focus-visible:ring-indigo-500/25"
                  placeholder='{"in_game": true, ...}'
                />
                <button
                  type="button"
                  onClick={applyPaste}
                  className={`${osdBtnCta} w-full`}
                >
                  Apply projection
                </button>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {pileModal ? (
        <PileInspectModal
          title={pileModal.title}
          cards={pileModal.cards}
          onClose={() => setPileInspect(null)}
        />
      ) : null}
    </div>
  );
}
