import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { CSSProperties, ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useControlPlane } from "../hooks/useControlPlane";
import { GameScreenPanel } from "./gameScreen/GameScreenPanel";
import {
  fmtGameStatDisplay,
  fmtIntEn,
} from "../lib/formatDisplayNumber";
import {
  labeledTooltip,
  monsterTooltip,
} from "../lib/entityKb";
import { cardNameClass } from "../lib/cardTypeStyle";
import {
  formatOrbChipTooltip,
  orbMechanics,
  orbStripHelpText,
} from "../lib/orbMechanics";
import type {
  ActionDTO,
  AgentSnapshotDTO,
  HeaderDTO,
  PendingApprovalDTO,
  ProposalDTO,
  ViewModelDTO,
} from "../types/viewModel";

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

/** Renders in `document.body` with fixed position so parent `overflow-auto` never clips tooltips. */
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
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<CSSProperties>({});

  const computePos = useCallback(() => {
    const el = wrapRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const margin = 8;
    const maxW = Math.min(22 * 16, window.innerWidth - 2 * margin);
    const maxH = Math.min(window.innerHeight * 0.7, 24 * 16);
    const base: CSSProperties = {
      position: "fixed",
      zIndex: 99999,
      maxWidth: maxW,
      maxHeight: maxH,
      overflowY: "auto",
    };
    if (side === "right") {
      let left = r.right + margin;
      const top = r.top + r.height / 2;
      const transformDefault = "translateY(-50%)";
      if (left + 120 > window.innerWidth - margin) {
        left = r.left - margin;
        setPos({
          ...base,
          left,
          top,
          transform: "translate(-100%, -50%)",
        });
      } else {
        setPos({
          ...base,
          left,
          top,
          transform: transformDefault,
        });
      }
      return;
    }
    if (side === "bottom") {
      setPos({
        ...base,
        left: r.left + r.width / 2,
        top: r.bottom + margin,
        transform: "translateX(-50%)",
      });
      return;
    }
    setPos({
      ...base,
      left: r.left + r.width / 2,
      top: r.top - margin,
      transform: "translate(-50%, -100%)",
    });
  }, [side]);

  useLayoutEffect(() => {
    if (!open) return;
    computePos();
  }, [open, computePos, text]);

  useEffect(() => {
    if (!open) return;
    const onScrollOrResize = () => computePos();
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [open, computePos]);

  if (!text) return <div className={className}>{children}</div>;

  return (
    <>
      <div
        ref={wrapRef}
        className={`min-w-0 cursor-help ${className}`}
        onMouseEnter={() => {
          computePos();
          setOpen(true);
        }}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => {
          computePos();
          setOpen(true);
        }}
        onBlur={() => setOpen(false)}
      >
        {children}
      </div>
      {open &&
        createPortal(
          <div
            role="tooltip"
            style={pos}
            className="custom-scroll pointer-events-none rounded-md border border-slate-600 bg-slate-800 px-2.5 py-2 text-left font-telemetry text-sm font-normal leading-snug tracking-normal whitespace-pre-wrap text-slate-200 shadow-xl"
          >
            {text}
          </div>,
          document.body,
        )}
    </>
  );
}

/** Operator controls — sized for the AI rail + legible type. */
const osdBtnBase =
  "font-console inline-flex h-8 shrink-0 items-center justify-center rounded border px-3 text-sm font-semibold uppercase tracking-[0.08em] transition duration-150 disabled:cursor-not-allowed disabled:opacity-35";

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
  "flex shrink-0 items-center justify-between gap-2 border-b border-slate-700/85 bg-slate-800/95 px-3 py-2 font-console text-sm font-semibold uppercase tracking-[0.12em] text-slate-300";

const osdSectionLabel =
  "font-console text-sm font-semibold uppercase tracking-[0.12em] text-slate-500";

const osdStatCaption =
  "font-console text-sm font-semibold uppercase tracking-[0.18em] text-slate-500";

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
  return `font-console rounded border py-1 px-2.5 text-sm font-semibold uppercase tracking-wide transition ${map[style] ?? map.secondary}`;
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
          <span className="font-console text-xs font-semibold uppercase tracking-[0.22em] text-slate-500 transition-colors group-hover:text-slate-400">
            {s.abbr}
          </span>
          <span
            className={`font-telemetry text-base font-semibold leading-none tabular-nums tracking-tight transition-colors ${s.tint} ${s.glow}`}
          >
            {fmtIntEn(s.n)}
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
    <HoverTip
      tip={tip}
      side="bottom"
      className="flex flex-col overflow-hidden rounded border border-slate-700 bg-slate-800/30"
    >
        <div className="flex items-center justify-between border-b border-slate-700/50 bg-slate-800/50 px-3 py-1.5">
          <div className="flex items-baseline gap-2">
            <span className="font-console text-sm font-bold text-red-400">
              {name}
            </span>
            <span className={osdStatCaption}>HP</span>
            <span className="font-telemetry text-sm font-medium text-slate-200">
              {hp ? fmtGameStatDisplay(hp) : "—"}
            </span>
          </div>
          <div className="font-console text-xs font-semibold uppercase tracking-wide text-red-400">
            {intent || "—"}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 px-3 py-2">
          {powers.length === 0 ? (
            <span className="text-xs text-slate-600">—</span>
          ) : (
            powers.map((p, i) => (
              <HoverTip
                key={i}
                tip={labeledTooltip(
                  `${String(p.name ?? "?")}${
                    p.stacks != null
                      ? ` (${typeof p.stacks === "number" ? fmtIntEn(p.stacks) : String(p.stacks)})`
                      : ""
                  }`,
                  p,
                )}
                side="bottom"
                className="inline-flex"
              >
                <span className="inline-flex cursor-help rounded border border-purple-700/50 bg-purple-900/40 px-1.5 py-0.5 text-xs text-purple-300">
                  {String(p.name ?? "?")}
                  {p.stacks != null
                    ? ` (${
                        typeof p.stacks === "number"
                          ? fmtIntEn(p.stacks)
                          : String(p.stacks)
                      })`
                    : ""}
                </span>
              </HoverTip>
            ))
          )}
        </div>
    </HoverTip>
  );
}

function CardTable({ cards }: { cards: Record<string, unknown>[] }) {
  return (
    <table className="w-full text-left whitespace-nowrap [&_td:last-child]:whitespace-normal">
      <thead className="sticky top-0 z-10 bg-slate-900 font-console text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">
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
          <th className="w-36 border-b border-slate-800 py-2 px-3 font-semibold">
            Name
          </th>
          <th className="w-full border-b border-slate-800 py-2 px-3 font-semibold">
            Text
          </th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-800 font-telemetry text-sm text-slate-400">
        {cards.map((c, idx) => (
            <tr key={idx} className="hover:bg-slate-800/50">
              <td className="py-2 px-3">{fmtIntEn(idx + 1)}</td>
              <td className="py-2 px-3 text-slate-500">{cardHash(c.uuid)}</td>
              <td className="py-2 px-3 text-center">
                <span className="font-bold text-cyan-400">
                  {fmtGameStatDisplay(c.cost ?? "—")}
                </span>
              </td>
              <td
                className={`py-2 px-3 ${cardNameClass(c.type)}`}
                title={
                  String(c.type ?? "").trim()
                    ? `Type: ${String(c.type)}`
                    : undefined
                }
              >
                {String(c.name ?? "?")}
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
            <span className="shrink-0 font-telemetry text-xs text-slate-500">
              {fmtIntEn(cards.length)} cards
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

/** Derived status for the AI operator rail (always prefer a visible state over “blank”). */
type LlmRailStatus =
  | { kind: "error"; title: string; message: string }
  | {
      kind: "pending";
      title: string;
      message: string;
      hint?: string;
      /** When false, omit the pulsing dot (idle / informational). */
      pulse?: boolean;
    };

const AGENT_MODES_UI = ["manual", "propose", "auto"] as const;

function normalizeAgentMode(
  raw: string | undefined,
): (typeof AGENT_MODES_UI)[number] {
  const s = String(raw ?? "manual").toLowerCase();
  return AGENT_MODES_UI.includes(s as (typeof AGENT_MODES_UI)[number])
    ? (s as (typeof AGENT_MODES_UI)[number])
    : "manual";
}

function AgentModeBar({
  modeRaw,
  onSelect,
  disabled,
}: {
  modeRaw: string | undefined;
  onSelect: (m: "manual" | "propose" | "auto") => void;
  disabled?: boolean;
}) {
  const current = normalizeAgentMode(modeRaw);
  return (
    <div
      className="flex w-full shrink-0 overflow-hidden rounded border border-slate-600/90 font-console text-[11px] font-semibold uppercase tracking-[0.12em]"
      role="group"
      aria-label="Agent mode"
    >
      {AGENT_MODES_UI.map((m) => (
        <button
          key={m}
          type="button"
          disabled={disabled}
          title={
            m === "manual"
              ? "Operator only — AI does not run."
              : m === "propose"
                ? "AI proposes; approve before execution."
                : "AI runs without approval when allowed."
          }
          className={
            "min-w-0 flex-1 border-r border-slate-700/80 px-1 py-1.5 last:border-r-0 transition " +
            (current === m
              ? "bg-sky-900/85 text-sky-100"
              : "bg-slate-950/90 text-slate-500 hover:bg-slate-800/90 hover:text-slate-300")
          }
          onClick={() => onSelect(m)}
        >
          {m}
        </button>
      ))}
    </div>
  );
}

export function MonitorDashboard() {
  const {
    snapshot,
    connected,
    logLines,
    queueManualCommand,
    setAgentMode,
    resumeAgent,
    retryAgent,
    pushLog,
    replayRuns,
    replayArchived,
    replayPickerRun,
    setReplayPickerRun,
    replayFiles,
    replayIndex,
    replayBusy,
    replayRunName,
    replayAiSidecar,
    loadReplayRun,
    replaySeek,
    clearReplaySelection,
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

  const [editCmd, setEditCmd] = useState("");
  const [pileInspect, setPileInspect] = useState<PileKind | null>(null);

  const vm: ViewModelDTO | null = snapshot?.view_model ?? null;
  const showScreenPanel = Boolean(vm?.screen);
  const stateId = snapshot?.state_id ?? null;
  /** Recent CommunicationMod / bridge feed — not merely WebSocket connected to the dashboard. */
  const gameFeedLive = snapshot?.live_ingress === true;

  const agentForRail = useMemo((): AgentSnapshotDTO | undefined => {
    const base = snapshot?.agent;
    const inReplay = replayRunName !== "" && replayFiles.length > 0;
    if (!inReplay) return base ?? undefined;
    if (replayAiSidecar?.kind === "loading") {
      return {
        ...base,
        ai_enabled: true,
        llm_backend: "replay",
        ai_system_status: "ok",
        ai_system_message: "",
        proposal_in_flight: true,
        proposal_for_state_id: null,
        agent_error: undefined,
        proposal: undefined,
        pending_approval: undefined,
      };
    }
    if (replayAiSidecar?.kind === "missing") {
      return {
        ...base,
        ai_enabled: true,
        llm_backend: "replay",
        ai_system_status: "ok",
        ai_system_message: "",
        proposal_in_flight: false,
        proposal_for_state_id: null,
        agent_error: undefined,
        proposal: undefined,
        pending_approval: undefined,
      };
    }
    if (replayAiSidecar?.kind === "ok") {
      return {
        ...base,
        ai_enabled: true,
        llm_backend: "replay",
        ai_system_status: "ok",
        ai_system_message: "",
        proposal_in_flight: false,
        proposal_for_state_id: null,
        agent_error: undefined,
        proposal: (replayAiSidecar.proposal ?? undefined) as
          | ProposalDTO
          | undefined,
        pending_approval: (replayAiSidecar.pending_approval ??
          undefined) as PendingApprovalDTO | undefined,
      };
    }
    return base ?? undefined;
  }, [snapshot?.agent, replayAiSidecar, replayFiles.length, replayRunName]);

  const hitlReadOnly =
    String(agentForRail?.llm_backend ?? "").toLowerCase() === "replay";

  const hitlQueuedSteps = useMemo(() => {
    const intr = agentForRail?.pending_approval?.interrupt;
    if (!intr) return [];
    const head = intr.command != null ? String(intr.command).trim() : "";
    const tail = Array.isArray(intr.command_queue)
      ? intr.command_queue.map((s) => String(s).trim()).filter(Boolean)
      : [];
    if (head) return [head, ...tail];
    return tail;
  }, [agentForRail?.pending_approval?.interrupt]);
  const combat = vm?.combat as Record<string, unknown> | null | undefined;
  const inventory = vm?.inventory as Record<string, unknown> | null | undefined;
  const header = vm?.header;
  const screenVm = vm?.screen as Record<string, unknown> | undefined;
  const screenType =
    screenVm && typeof screenVm.type === "string"
      ? String(screenVm.type).trim()
      : "";

  const nonCombatBoardHint = useMemo(() => {
    if (combat) return null;
    if (!vm?.in_game) return null;
    const st = screenType || "NONE";
    const namedScreens = new Set([
      "COMBAT_REWARD",
      "REST",
      "SHOP",
      "MAP",
      "EVENT",
      "CARD_REWARD",
      "GRID",
      "HAND_SELECT",
      "TREASURE",
      "SMITH",
    ]);
    if (namedScreens.has(st)) {
      return `Screen ${st.replace(/_/g, " ")} — not a combat tick, so the mod omits combat_state (no hand or enemy rows). Step replay to a frame with Energy and Turn filled in; those frames include hand and monsters.`;
    }
    if (st === "NONE") {
      return "Screen NONE and no combat_state on this frame. If you expected combat, advance replay until the prompt shows HAND / MONSTERS sections.";
    }
    return "No combat_state in this snapshot — hand and enemies only exist while combat is active.";
  }, [combat, screenType, vm?.in_game]);

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

  const playerClass =
    header && typeof header["class"] === "string"
      ? header["class"].trim()
      : "";
  const playerOrbs =
    (combat?.player_orbs as Record<string, unknown>[] | undefined) ?? [];
  const showOrbStrip =
    playerClass.toUpperCase() === "DEFECT" &&
    Boolean(combat) &&
    playerOrbs.length > 0;

  const actions: ActionDTO[] = vm?.actions ?? [];

  const proposal = agentForRail?.proposal as Record<string, unknown> | undefined;

  const llmUserPromptLive = useMemo(() => {
    const fromProposal = String(proposal?.user_prompt ?? "").trim();
    const fromAgent = String(agentForRail?.llm_user_prompt ?? "").trim();
    return fromProposal || fromAgent;
  }, [proposal?.user_prompt, agentForRail?.llm_user_prompt]);

  const llmRaw =
    proposal?.llm_raw != null ? String(proposal.llm_raw) : "";

  const proposalStatus =
    proposal?.status != null ? String(proposal.status).trim().toLowerCase() : "";
  const proposalErrorReason =
    proposal?.error_reason != null && String(proposal.error_reason).trim() !== ""
      ? String(proposal.error_reason).trim()
      : "";

  const llmRunStatus = useMemo((): LlmRailStatus => {
    if (
      replayRunName !== "" &&
      replayFiles.length > 0 &&
      replayAiSidecar?.kind === "loading"
    ) {
      return {
        kind: "pending",
        pulse: true,
        title: "Replay",
        message: "Loading logged model output for this frame…",
      };
    }
    if (
      replayRunName !== "" &&
      replayFiles.length > 0 &&
      replayAiSidecar?.kind === "missing"
    ) {
      return {
        kind: "pending",
        pulse: false,
        title: "Replay",
        message:
          "No .ai.json sidecar for this frame — the model trace was not logged next to this state file.",
      };
    }

    const agent = agentForRail;
    const sysStatus = String(agent?.ai_system_status ?? "").trim().toLowerCase();
    const sysMsg = String(agent?.ai_system_message ?? "").trim();
    const aiEnabled = agent?.ai_enabled === true;
    const llmBackend = String(agent?.llm_backend ?? "").trim().toLowerCase();
    const llmOff = llmBackend === "" || llmBackend === "off";
    const proposalInFlight = agent?.proposal_in_flight === true;
    const mode = String(agent?.agent_mode ?? "").trim().toLowerCase();
    const srvProposalSid = String(agent?.proposal_for_state_id ?? "").trim();

    const traceForSid = String(proposal?.for_state_id ?? "").trim();
    const curSid = String(stateId ?? "").trim();
    const stateMismatch =
      traceForSid !== "" &&
      curSid !== "" &&
      traceForSid !== curSid &&
      proposalStatus !== "stale";

    if (sysStatus === "checking") {
      return {
        kind: "pending",
        pulse: true,
        title: "AI starting",
        message:
          sysMsg ||
          "The game process is checking LLM configuration (see session log).",
      };
    }

    if (stateMismatch) {
      return {
        kind: "error",
        title: "State mismatch",
        message: `Trace is for state ${traceForSid}; dashboard state is ${curSid}. Wait for a fresh trace or use Retry AI to clear the monitor.`,
      };
    }

    if (!aiEnabled || llmOff || sysStatus === "disabled") {
      return {
        kind: "error",
        title: "AI unavailable",
        message:
          sysMsg ||
          (llmOff
            ? "LLM backend is off or not configured for this run."
            : "AI is disabled for this run."),
      };
    }

    const backendErr =
      agent?.agent_error != null &&
      String(agent.agent_error).trim() !== ""
        ? String(agent.agent_error).trim()
        : "";
    if (backendErr) {
      return {
        kind: "error",
        title: "LLM / agent error",
        message: backendErr,
      };
    }
    if (proposalStatus === "error" || proposalStatus === "disabled") {
      return {
        kind: "error",
        title:
          proposalStatus === "disabled" ? "AI disabled" : "LLM request failed",
        message:
          proposalErrorReason ||
          (proposalStatus === "disabled"
            ? "LLM is not available for this run."
            : "The model or tool loop reported an error."),
      };
    }
    if (proposalStatus === "invalid") {
      return {
        kind: "error",
        title: "Invalid proposal",
        message:
          proposalErrorReason ||
          "The model output did not include a valid final decision.",
      };
    }
    if (proposalStatus === "building_prompt") {
      return {
        kind: "pending",
        pulse: true,
        title: "Preparing prompt",
        message:
          "Building the user prompt and context before calling the model…",
        hint:
          proposal?.command != null ? String(proposal.command) : undefined,
      };
    }
    if (proposalStatus === "running") {
      return {
        kind: "pending",
        pulse: true,
        title: "Awaiting model response",
        message:
          "The model is generating a reply (including after tool calls). This can take a while.",
        hint:
          proposal?.command != null ? String(proposal.command) : undefined,
      };
    }
    if (proposalStatus === "awaiting_approval") {
      return {
        kind: "pending",
        pulse: false,
        title: "Proposal ready",
        message:
          "The model returned a legal command. Use Awaiting approval below or switch to auto mode.",
        hint:
          proposal?.command != null ? String(proposal.command) : undefined,
      };
    }
    if (proposalStatus === "stale") {
      return {
        kind: "pending",
        pulse: false,
        title: "Superseded",
        message:
          "This run was for an earlier room. Wait for the game process to post a new trace, or use Retry AI to clear the monitor.",
      };
    }
    if (proposalStatus === "rejected") {
      return {
        kind: "pending",
        pulse: false,
        title: "Proposal rejected",
        message:
          "The last proposal was rejected. The next game tick or state change should start a new run if auto/propose mode allows it.",
      };
    }
    if (proposalStatus === "approved") {
      return {
        kind: "pending",
        pulse: true,
        title: "Approved",
        message:
          "Waiting for the game loop to pick up the approved action from the dashboard.",
      };
    }
    if (proposalStatus === "executed") {
      return {
        kind: "pending",
        pulse: false,
        title: "Idle",
        message:
          "Last proposal was executed. Waiting for the next decision point from the game.",
      };
    }

    if (proposalInFlight) {
      const sidHint =
        srvProposalSid && curSid && srvProposalSid !== curSid
          ? ` (worker state ${srvProposalSid} vs dashboard ${curSid})`
          : "";
      return {
        kind: "pending",
        pulse: true,
        title: "Awaiting model response",
        message: `The game process has an LLM call in flight${sidHint}. Streamed trace updates will appear when the worker posts them.`,
      };
    }

    if (mode === "manual") {
      return {
        kind: "pending",
        pulse: false,
        title: "Manual mode",
        message:
          "AI is enabled but mode is manual — no automatic proposals. Use legal actions or queue a command.",
      };
    }

    if (actions.length > 0 && !proposal && (mode === "auto" || mode === "propose")) {
      const ingressReady = snapshot?.ingress_ready_for_command;
      const readyHint =
        ingressReady === true
          ? " Game ingress: ready_for_command=true (decision room is ready); the agent should attach a proposal on the next state packet."
          : ingressReady === false
            ? " Game ingress: ready_for_command=false on the last frame."
            : "";
      return {
        kind: "pending",
        pulse: true,
        title: "Waiting for AI",
        message: `No trace for this state yet.${readyHint}`,
      };
    }

    if (vm && actions.length > 0) {
      return {
        kind: "pending",
        pulse: false,
        title: "Watching",
        message:
          "Connected with legal actions; no AI activity flag for this frame.",
      };
    }

    return {
      kind: "pending",
      pulse: false,
      title: "No game state",
      message: !connected
        ? "WebSocket offline — reconnect to see live status."
        : snapshot?.live_ingress === false
          ? "No live game feed (game stopped or last state is stale). Start the bridge or use Replay."
          : "Load ingress or run CommunicationMod so the dashboard receives state.",
    };
  }, [
    actions.length,
    connected,
    snapshot?.live_ingress,
    proposal,
    proposal?.command,
    proposal?.for_state_id,
    proposalErrorReason,
    proposalStatus,
    agentForRail?.agent_error,
    agentForRail?.agent_mode,
    agentForRail?.ai_enabled,
    agentForRail?.ai_system_message,
    agentForRail?.ai_system_status,
    agentForRail?.llm_backend,
    agentForRail?.proposal_for_state_id,
    agentForRail?.proposal_in_flight,
    replayAiSidecar,
    replayFiles.length,
    replayRunName,
    snapshot?.ingress_ready_for_command,
    stateId,
    vm,
  ]);

  const tacticalPromptText = !vm?.actions?.length
    ? "— Load ingress —"
    : llmUserPromptLive ||
      "— User prompt not available (wait for agent trace or check dashboard logs). —";

  const aiRailTitle =
    "LLM / replay backend for this row. Legacy dashboard snapshot does not populate thread_id; state is the current frame id. Run seed comes from game_state.seed on the current ingress frame.";
  const runSeedDisplay =
    snapshot?.agent?.run_seed != null &&
    String(snapshot.agent.run_seed).trim() !== ""
      ? fmtGameStatDisplay(snapshot.agent.run_seed)
      : "n/a";

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gradient-to-b from-slate-900 via-[#0a0d11] to-[#06080a] text-sm text-slate-300 select-none">
      {/* Top bar — game / session controls only; combat readouts live in the stats strip */}
      <header className="flex shrink-0 items-center border-b border-slate-700/90 bg-slate-900/80 px-3 py-2 backdrop-blur-sm">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
          <span className="font-console text-sm font-bold tracking-[0.14em] text-slate-100">
            SPIRE AGENT
            <span className="ml-1.5 font-medium tracking-normal text-slate-500">
              · operator
            </span>
          </span>
          <Link
            to="/metrics"
            className="font-console text-xs font-semibold uppercase tracking-wide text-sky-400 hover:text-sky-300"
          >
            Run metrics
          </Link>
          <div
            className={`font-console flex h-7 items-center gap-1.5 rounded border px-2.5 text-xs font-semibold uppercase tracking-wide ${
              gameFeedLive
                ? "border-emerald-700/50 bg-emerald-950/35 text-emerald-400"
                : "border-red-800/55 bg-red-950/30 text-red-400"
            }`}
            title={
              gameFeedLive
                ? "Live: the game bridge has sent state recently (CommunicationMod + main.py)."
                : !connected
                  ? "WebSocket to the dashboard is disconnected."
                  : "Offline: dashboard is connected but there is no fresh game feed (stop the game, or wait past DASHBOARD_INGRESS_MAX_AGE_SECONDS)."
            }
          >
            <span className="relative flex h-1.5 w-1.5">
              {gameFeedLive ? (
                <>
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                </>
              ) : (
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-red-500" />
              )}
            </span>
            {gameFeedLive ? "Live" : "Offline"}
          </div>

          <div
            className="flex flex-wrap items-center gap-x-3 gap-y-1 border-l border-slate-600/70 pl-4"
            title="Choosing a run loads its first frame automatically. Prev/Next POST each JSON to /api/debug/ingress. While a run is selected, WebSocket snapshots are ignored so replay is not overwritten. Clear the run to resume live updates."
          >
            <div
              className="flex min-w-0 items-center gap-1.5"
              title="Run seed from agent snapshot (reproducibility). Shows n/a when the backend does not set it."
            >
              <span className={osdStatCaption}>Seed</span>
              <span className="font-telemetry max-w-[12rem] truncate text-xs tabular-nums text-slate-400">
                {runSeedDisplay}
              </span>
            </div>
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              <span className={osdStatCaption}>Replay</span>
              <select
                value={replayPickerRun}
                onChange={(e) => {
                  const v = e.target.value;
                  setReplayPickerRun(v);
                  if (v) void loadReplayRun(v);
                  else clearReplaySelection();
                }}
                disabled={replayBusy}
                className="font-console h-7 max-w-[14rem] rounded border border-slate-700 bg-slate-950/80 px-2 text-xs font-medium text-slate-200 outline-none"
                aria-label="Log run directory under logs/"
              >
                <option value="">Select run…</option>
                {replayRuns.map((run) => (
                  <option key={run} value={run}>
                    {run}
                    {replayArchived[run] ? " · zip" : ""}
                  </option>
                ))}
              </select>
              {replayFiles.length > 0 ? (
                <>
                  <button
                    type="button"
                    disabled={replayBusy || replayIndex <= 0}
                    className={osdBtnGhost}
                    onClick={() => replaySeek(-10)}
                    title="Back 10 frames"
                  >
                    −10
                  </button>
                  <button
                    type="button"
                    disabled={replayBusy || replayIndex <= 0}
                    className={osdBtnGhost}
                    onClick={() => replaySeek(-1)}
                  >
                    Prev
                  </button>
                  <span className="font-telemetry min-w-[4.5rem] text-center text-xs tabular-nums text-slate-400">
                    {fmtIntEn(replayIndex + 1)}/{fmtIntEn(replayFiles.length)}
                  </span>
                  <button
                    type="button"
                    disabled={
                      replayBusy || replayIndex >= replayFiles.length - 1
                    }
                    className={osdBtnGhost}
                    onClick={() => replaySeek(1)}
                  >
                    Next
                  </button>
                  <button
                    type="button"
                    disabled={
                      replayBusy || replayIndex >= replayFiles.length - 1
                    }
                    className={osdBtnGhost}
                    onClick={() => replaySeek(10)}
                    title="Forward 10 frames"
                  >
                    +10
                  </button>
                </>
              ) : null}
            </div>
          </div>
        </div>
      </header>

      {snapshot?.live_ingress === false ? (
        <div
          className="shrink-0 border-b border-amber-900/50 bg-amber-950/40 px-3 py-2 text-sm text-amber-100/95"
          role="status"
        >
          <span className="font-console font-semibold uppercase tracking-wide text-amber-300">
            No live game feed
          </span>
          <span className="text-amber-100/85">
            {" "}
            — the monitor hides stale snapshots when CommunicationMod has not sent a
            state for a while. Start the game +{" "}
            <code className="rounded bg-black/25 px-1">src.main</code>, or choose a
            run under <span className="font-medium">Replay</span>.
            {typeof snapshot.ingress_age_seconds === "number" ? (
              <span className="text-amber-200/80">
                {" "}
                Last packet was ~{fmtIntEn(Math.round(snapshot.ingress_age_seconds))}
                s ago.
              </span>
            ) : null}
          </span>
        </div>
      ) : null}

      {/* Stats + potions — left-aligned run readout */}
      <div className="flex min-h-0 shrink-0 flex-wrap items-end gap-x-6 gap-y-1.5 border-b border-slate-700/85 bg-slate-800/75 px-3 py-2">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-1.5">
          <div className="flex flex-col gap-px">
            <span className={osdStatCaption}>Turn</span>
            <span className="font-telemetry text-base font-semibold tabular-nums leading-none text-slate-50">
              {fmtGameStatDisplay(header?.turn ?? "—")}
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
                className={`font-telemetry text-base font-semibold tabular-nums leading-none ${col}`}
              >
                {fmtGameStatDisplay(val)}
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
                  <div className="font-console max-w-[7.5rem] truncate rounded border border-slate-600/90 bg-slate-800/80 px-1.5 py-0.5 text-xs font-medium text-slate-200">
                    {String(p.name ?? "Potion")}
                  </div>
                </HoverTip>
              ) : (
                <div
                  key={i}
                  className="font-console rounded border border-dashed border-slate-600/70 px-1.5 py-0.5 text-xs text-slate-600"
                >
                  —
                </div>
              ),
            )}
          </div>
          {showOrbStrip ? (
            <div className="flex flex-wrap items-center gap-1.5 border-l border-slate-600/55 pl-5">
              <HoverTip
                tip={orbStripHelpText()}
                side="bottom"
                className="shrink-0"
              >
                <span
                  className={`${osdStatCaption} mr-0.5 cursor-help border-b border-dotted border-slate-500/80`}
                >
                  {orbMechanics.ui?.strip_label ?? "Orbs"}
                </span>
              </HoverTip>
              <div className="flex max-w-[16rem] flex-row-reverse flex-wrap items-center gap-1">
                {playerOrbs.map((orb, i) => {
                  const name = String(orb.name ?? "").trim();
                  const empty = name === "Orb Slot";
                  return (
                    <HoverTip
                      key={i}
                      tip={formatOrbChipTooltip(orb)}
                      side="bottom"
                      className="w-auto shrink-0"
                    >
                      {empty ? (
                        <div className="font-console rounded border border-dashed border-slate-600/70 px-1.5 py-0.5 text-xs text-slate-600">
                          {orbMechanics.ui?.empty_chip ?? "—"}
                        </div>
                      ) : (
                        <div className="font-console max-w-[6.5rem] truncate rounded border border-violet-600/75 bg-violet-950/40 px-1.5 py-0.5 text-xs font-medium text-violet-100">
                          {name || "?"}
                        </div>
                      )}
                    </HoverTip>
                  );
                })}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* IDE workspace */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Col 1 — relics / powers */}
        <aside className="flex w-36 shrink-0 flex-col border-r border-slate-700 bg-slate-900">
          <div className="flex min-h-0 flex-1 flex-col border-b border-slate-700">
            <div className={osdPanelStrip}>
              Relics · {fmtIntEn(relics.length)}
            </div>
            <div className="custom-scroll flex-1 space-y-1 overflow-y-auto p-2">
              {relics.length === 0 ? (
                <div className="px-1 font-console text-sm italic text-slate-600">
                  None
                </div>
              ) : (
                relics.map((r, i) => (
                  <HoverTip
                    key={i}
                    tip={labeledTooltip(String(r.name ?? "?"), r)}
                    side="right"
                    className="w-full min-w-0"
                  >
                    <div className="cursor-help truncate rounded border border-slate-700 bg-slate-800/50 px-1.5 py-1 text-sm text-slate-300">
                      {String(r.name ?? "?")}
                    </div>
                  </HoverTip>
                ))
              )}
            </div>
          </div>
          <div className="flex min-h-0 flex-1 flex-col">
            <div className={osdPanelStrip}>Powers</div>
            <div className="custom-scroll flex-1 overflow-y-auto p-2">
              {playerPowers.length === 0 ? (
                <div className="px-1 font-console text-sm italic text-slate-600">
                  None
                </div>
              ) : (
                <div className="space-y-1">
                  {playerPowers.map((p, i) => (
                    <HoverTip
                      key={i}
                      tip={labeledTooltip(String(p.name ?? "?"), p)}
                      side="right"
                      className="w-full min-w-0"
                    >
                      <div className="cursor-help truncate rounded border border-slate-700 bg-slate-800/50 px-1.5 py-0.5 text-sm">
                        {String(p.name ?? "?")}
                      </div>
                    </HoverTip>
                  ))}
                </div>
              )}
            </div>
          </div>
        </aside>

        {/* Col 2–3 — main */}
        <main className="flex min-h-0 min-w-0 flex-1 flex-col border-r border-slate-700">
          {/* Top: non-combat screen (from vm.screen) OR enemies | hand */}
          {showScreenPanel && vm ? (
            <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden border-b border-slate-700">
              <GameScreenPanel
                vm={vm}
                onChoose={(cmd) => void queueManualCommand(cmd)}
              />
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 border-b border-slate-700">
              <div className="flex min-h-0 min-w-0 flex-[0.68] flex-col border-r border-slate-700">
                <div className={`sticky top-0 z-10 ${osdPanelStrip}`}>
                  Enemies · {fmtIntEn(monsters.length)}
                </div>
                <div className="custom-scroll flex-1 space-y-3 overflow-y-auto p-3">
                  {monsters.length === 0 ? (
                    <div className="space-y-2 px-2 py-6 text-center text-sm text-slate-500">
                      <p className="font-medium text-slate-400">No enemies</p>
                      {nonCombatBoardHint ? (
                        <p className="text-xs leading-relaxed text-slate-600">
                          {nonCombatBoardHint}
                        </p>
                      ) : (
                        <p className="text-xs text-slate-600">
                          In combat but no living foes, or snapshot incomplete.
                        </p>
                      )}
                    </div>
                  ) : (
                    monsters.map((m, i) => <EnemyCard key={i} m={m} />)
                  )}
                </div>
              </div>

              <div className="flex min-h-0 min-w-0 flex-[1.32] flex-col bg-slate-900">
                <div
                  className={`sticky top-0 z-10 flex shrink-0 items-center justify-between gap-2 ${osdPanelStrip}`}
                >
                  <span className="min-w-0 shrink-0 truncate">
                    Hand · {fmtIntEn(hand.length)}
                  </span>
                  <PileTelemetryBar
                    draw={draw}
                    discard={disc}
                    exhaust={exhaust}
                    onInspect={setPileInspect}
                  />
                </div>
                <div className="custom-scroll min-h-0 flex-1 overflow-y-auto">
                  {hand.length === 0 ? (
                    <div className="space-y-2 px-3 py-8 text-center text-sm text-slate-500">
                      <p className="font-medium text-slate-400">
                        No cards in hand
                      </p>
                      {nonCombatBoardHint ? (
                        <p className="text-xs leading-relaxed text-slate-600">
                          {nonCombatBoardHint}
                        </p>
                      ) : (
                        <p className="text-xs text-slate-600">
                          Empty hand this turn, or combat not loaded.
                        </p>
                      )}
                    </div>
                  ) : (
                    <CardTable cards={hand} />
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Valid actions — full width under enemies + hand (z-index keeps it above scrolling map) */}
          <div className="relative z-10 flex h-[6.25rem] max-h-[28vh] shrink-0 flex-col border-b border-t border-slate-700/90 bg-slate-900/95 shadow-[0_-6px_20px_rgba(0,0,0,0.35)]">
            <div
              className={`shrink-0 border-b border-slate-700/85 bg-slate-800/80 px-2 py-1 ${osdSectionLabel}`}
            >
              Valid actions
            </div>
            <div className="custom-scroll flex flex-1 flex-wrap content-start gap-1 overflow-y-auto px-2 py-1">
              {actions.length === 0 ? (
                <span className="font-console text-xs text-slate-600">
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
              <div
                className={osdPanelStrip}
                title="Same tactical user message as build_user_prompt in Python: from the live trace when state matches, otherwise a server preview (strategy memory may appear only after the agent builds the turn)."
              >
                <span className="min-w-0 shrink truncate">LLM user prompt</span>
                <button
                  type="button"
                  className={osdBtnGhost}
                  onClick={() =>
                    void copyClipboard(tacticalPromptText, "LLM user prompt")
                  }
                >
                  Copy
                </button>
              </div>
              <pre className="font-telemetry custom-scroll flex-1 overflow-auto p-2 text-sm leading-relaxed whitespace-pre text-slate-400">
                {tacticalPromptText}
              </pre>
            </div>

            <div className="flex w-[min(26vw,22rem)] min-w-[15rem] max-w-[24rem] shrink-0 flex-col bg-slate-950">
              <div className={osdPanelStrip}>
                <span>Session log</span>
                <span className="font-telemetry text-xs tabular-nums text-slate-500">
                  {fmtIntEn(logLines.length)}
                </span>
              </div>
              <div className="custom-scroll flex-1 space-y-1 overflow-y-auto p-2 font-telemetry text-sm leading-snug">
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
                              : line.kind === "REPLAY"
                                ? "text-violet-400"
                                : "text-slate-500"
                      }`}
                    >
                      {line.kind}
                    </span>
                    <span className="text-slate-300">
                      {line.msg}
                      {(line.repeat ?? 1) > 1 ? (
                        <span className="whitespace-nowrap text-slate-500">
                          {" "}
                          x{fmtIntEn(line.repeat ?? 1)}
                        </span>
                      ) : null}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </main>

        {/* Col 4 — AI operator rail (compact; boxed headers avoid overlap with scroll areas) */}
        <aside className="z-20 flex w-[min(32rem,40vw)] min-w-[26rem] shrink-0 flex-col border-l border-emerald-950/30 bg-[#07090c] shadow-[-8px_0_24px_rgba(0,0,0,0.4)]">
          <div className={osdPanelStrip}>
            <span className="min-w-0 truncate">AI control</span>
            <button
              type="button"
              disabled={
                snapshot == null ||
                String(snapshot?.agent?.agent_mode ?? "")
                  .toLowerCase()
                  .trim() === "manual"
              }
              title="Propose/auto: clears the stuck trace, cancels any in-flight LLM proposal for this state, and allows the game loop to start a fresh proposal on the next tick. Disabled in manual mode (server no-op)."
              className={osdBtnRetry}
              onClick={() => void retryAgent()}
            >
              Retry AI
            </button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2 custom-scroll">
            <div
              className="shrink-0 rounded border border-slate-700/80 bg-slate-950/80 px-2 py-2"
              title={aiRailTitle}
            >
              <AgentModeBar
                modeRaw={agentForRail?.agent_mode}
                disabled={snapshot == null}
                onSelect={(m) => void setAgentMode(m)}
              />
              <div className="mt-2 truncate font-mono text-[10px] leading-tight text-slate-500">
                <span className="text-slate-600">llm</span>{" "}
                {agentForRail?.llm_backend ?? "—"}{" "}
                <span className="text-slate-700">·</span>{" "}
                <span className="text-slate-600">state</span>{" "}
                <span className="font-telemetry text-slate-400">
                  {stateId ?? "—"}
                </span>
              </div>
            </div>

            {llmRunStatus.kind === "error" ? (
              <div className="shrink-0 rounded border border-red-800/65 bg-red-950/35 p-2 shadow-[inset_0_0_0_1px_rgba(248,113,113,0.12)]">
                <div className="mb-1 flex items-start justify-between gap-2">
                  <span className="font-console text-xs font-bold uppercase tracking-[0.1em] text-red-300">
                    {llmRunStatus.title}
                  </span>
                  <button
                    type="button"
                    className={osdBtnGhost}
                    onClick={() =>
                      void copyClipboard(llmRunStatus.message, "LLM error")
                    }
                  >
                    Copy
                  </button>
                </div>
                <p className="font-telemetry text-sm leading-snug text-red-100/95 whitespace-pre-wrap break-words">
                  {llmRunStatus.message}
                </p>
              </div>
            ) : (
              <div className="shrink-0 rounded border border-sky-800/55 bg-sky-950/30 p-2 shadow-[inset_0_0_0_1px_rgba(56,189,248,0.12)]">
                <div className="mb-1 flex items-center gap-2">
                  {llmRunStatus.pulse !== false ? (
                    <span
                      className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-sky-400 shadow-[0_0_10px_rgba(56,189,248,0.7)]"
                      aria-hidden
                    />
                  ) : null}
                  <span className="font-console text-xs font-bold uppercase tracking-[0.1em] text-sky-200">
                    {llmRunStatus.title}
                  </span>
                </div>
                <p className="font-telemetry text-sm leading-snug text-sky-100/90">
                  {llmRunStatus.message}
                </p>
                {llmRunStatus.hint ? (
                  <p className="mt-1.5 font-telemetry text-sm leading-snug text-slate-400">
                    Latest trace:{" "}
                    <span className="font-medium text-slate-300">
                      {llmRunStatus.hint}
                    </span>
                  </p>
                ) : null}
              </div>
            )}

            {agentForRail?.pending_approval ? (
              <div className="flex shrink-0 flex-col gap-2 rounded border border-amber-900/35 bg-slate-800/35 p-2">
                <span className="font-console text-xs font-semibold uppercase tracking-[0.12em] text-amber-400">
                  Awaiting approval
                </span>
                <div className="space-y-1 rounded border border-slate-700/90 bg-slate-950 px-2 py-1.5 font-telemetry text-sm text-slate-200">
                  {hitlQueuedSteps.length === 0 ? (
                    <div className="text-xs font-semibold text-white">—</div>
                  ) : (
                    hitlQueuedSteps.map((line, i) => (
                      <div
                        key={`${i}-${line}`}
                        className="flex gap-2 leading-snug"
                      >
                        <span className="w-5 shrink-0 text-right font-mono text-xs text-slate-500">
                          {fmtIntEn(i + 1)}.
                        </span>
                        <span className="min-w-0 flex-1 font-semibold tracking-wide text-white">
                          {line}
                        </span>
                      </div>
                    ))
                  )}
                </div>
                <p className="font-telemetry text-xs leading-snug text-slate-500">
                  {hitlReadOnly
                    ? "Replay: logged proposal only — approve/reject/edit do not apply."
                    : "Approve runs the first command and leaves further steps to the game process queue when the model proposed a sequence. Reject cancels this proposal."}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    className={osdBtnApprove}
                    disabled={hitlReadOnly}
                    title={
                      hitlReadOnly
                        ? "Replay: not connected to live agent"
                        : undefined
                    }
                    onClick={() => void resumeAgent("approve")}
                  >
                    Approve all
                  </button>
                  <button
                    type="button"
                    className={osdBtnReject}
                    disabled={hitlReadOnly}
                    title={
                      hitlReadOnly
                        ? "Replay: not connected to live agent"
                        : undefined
                    }
                    onClick={() => void resumeAgent("reject")}
                  >
                    Reject all
                  </button>
                </div>
                <div className="flex items-center gap-1.5">
                  <input
                    value={editCmd}
                    onChange={(e) => setEditCmd(e.target.value)}
                    disabled={hitlReadOnly}
                    placeholder="Edit command…"
                    className="font-telemetry h-7 min-h-7 min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm leading-tight text-slate-100 outline-none focus-visible:border-indigo-500 focus-visible:ring-1 focus-visible:ring-indigo-500/25 disabled:cursor-not-allowed disabled:opacity-50"
                  />
                  <button
                    type="button"
                    className={osdBtnCta}
                    disabled={hitlReadOnly}
                    onClick={() => void resumeAgent("edit", editCmd)}
                  >
                    Apply
                  </button>
                </div>
              </div>
            ) : null}

            <div className="flex min-h-0 flex-1 flex-col">
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
                  className="font-telemetry custom-scroll min-h-0 flex-1 resize-none border-0 bg-transparent p-2 text-sm leading-relaxed text-slate-400 outline-none"
                  placeholder={(() => {
                    const b = String(agentForRail?.llm_backend ?? "")
                      .trim()
                      .toLowerCase();
                    if (b === "replay") {
                      return replayAiSidecar?.kind === "missing"
                        ? "No .ai.json for this replay frame."
                        : "Raw output from the logged *.ai.json sidecar.";
                    }
                    if (b === "off" || b === "") {
                      return "AI disabled or no API — enable LLM in legacy config for raw output here.";
                    }
                    return "Raw model output from legacy trace when available.";
                  })()}
                  spellCheck={false}
                />
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
