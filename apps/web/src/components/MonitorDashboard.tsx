import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { CSSProperties, MouseEvent as ReactMouseEvent, ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useControlPlane } from "../hooks/useControlPlane";
import { GameScreenPanel } from "./gameScreen/GameScreenPanel";
import { SpireAgentNav } from "./SpireAgentNav";
import {
  displayPlayerClassName,
  fmtGameStatDisplay,
  fmtIntEn,
} from "../lib/formatDisplayNumber";
import {
  labeledTooltip,
  monsterTooltip,
  powerChipLabel,
} from "../lib/entityKb";
import { cardNameClass } from "../lib/cardTypeStyle";
import { renderPromptMarkdown } from "../lib/renderPromptMarkdown";
import { validActionVariant } from "../lib/validActionVariant";
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

/** Game state uses a row with this name/id for an empty potion slot (e.g. with Potion Belt). */
function isPotionSlotPlaceholder(p: Record<string, unknown>): boolean {
  const id = String(p.id ?? "").trim();
  const name = String(p.name ?? "").trim();
  return id === "Potion Slot" || name === "Potion Slot";
}

type TipSide = "top" | "right" | "bottom";

/** Keep a horizontally centered tooltip (translateX(-50%)) inside the viewport. */
function clampTooltipCenterX(
  anchorCenterX: number,
  maxTooltipWidth: number,
  vw: number,
  margin: number,
): number {
  const half = maxTooltipWidth / 2;
  const minC = margin + half;
  const maxC = vw - margin - half;
  if (minC <= maxC) {
    return Math.min(Math.max(anchorCenterX, minC), maxC);
  }
  return vw / 2;
}

function clampTooltipCenterY(
  anchorCenterY: number,
  maxTooltipHeight: number,
  vh: number,
  margin: number,
): number {
  const half = maxTooltipHeight / 2;
  const minC = margin + half;
  const maxC = vh - margin - half;
  if (minC <= maxC) {
    return Math.min(Math.max(anchorCenterY, minC), maxC);
  }
  return vh / 2;
}

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
  const tooltipRef = useRef<HTMLDivElement>(null);
  const clampPassRef = useRef(0);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<CSSProperties>({});

  const computePos = useCallback(() => {
    const el = wrapRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const margin = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const maxW = Math.min(22 * 16, vw - 2 * margin);
    const maxH = Math.min(vh * 0.7, 24 * 16);
    const base: CSSProperties = {
      position: "fixed",
      zIndex: 99999,
      maxWidth: maxW,
      maxHeight: maxH,
      overflowY: "auto",
    };
    if (side === "right") {
      let left = r.right + margin;
      const top = clampTooltipCenterY(
        r.top + r.height / 2,
        maxH,
        vh,
        margin,
      );
      if (left + maxW > vw - margin) {
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
          transform: "translateY(-50%)",
        });
      }
      return;
    }
    if (side === "bottom") {
      const anchorCx = r.left + r.width / 2;
      const left = clampTooltipCenterX(anchorCx, maxW, vw, margin);
      setPos({
        ...base,
        left,
        top: r.bottom + margin,
        transform: "translateX(-50%)",
      });
      return;
    }
    const anchorCx = r.left + r.width / 2;
    const left = clampTooltipCenterX(anchorCx, maxW, vw, margin);
    setPos({
      ...base,
      left,
      top: r.top - margin,
      transform: "translate(-50%, -100%)",
    });
  }, [side]);

  useLayoutEffect(() => {
    if (!open) return;
    computePos();
  }, [open, computePos, text]);

  /** Nudge tooltip after layout so flipped / wide content cannot clip off-screen. */
  useLayoutEffect(() => {
    if (!open) {
      clampPassRef.current = 0;
      return;
    }
    if (clampPassRef.current >= 4) return;
    const tipEl = tooltipRef.current;
    if (!tipEl || Object.keys(pos).length === 0) return;
    const rect = tipEl.getBoundingClientRect();
    const m = 8;
    let dx = 0;
    let dy = 0;
    if (rect.left < m) dx = m - rect.left;
    else if (rect.right > window.innerWidth - m) {
      dx = window.innerWidth - m - rect.right;
    }
    if (rect.top < m) dy = m - rect.top;
    else if (rect.bottom > window.innerHeight - m) {
      dy = window.innerHeight - m - rect.bottom;
    }
    if (dx !== 0 || dy !== 0) {
      clampPassRef.current += 1;
      setPos((p) => ({
        ...p,
        left: (typeof p.left === "number" ? p.left : 0) + dx,
        top: (typeof p.top === "number" ? p.top : 0) + dy,
      }));
    }
  }, [open, pos]);

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
            ref={tooltipRef}
            role="tooltip"
            style={pos}
            className="custom-scroll pointer-events-none rounded-md border border-spire-border-strong bg-spire-panel px-2.5 py-2 text-left font-telemetry text-sm font-normal leading-snug tracking-normal whitespace-pre-wrap text-spire-primary shadow-xl"
          >
            {text}
          </div>,
          document.body,
        )}
    </>
  );
}

/** Operator controls — stronger borders + weight for parchment contrast. */
const osdBtnBase =
  "font-console inline-flex h-9 shrink-0 items-center justify-center rounded-md border-2 px-3 text-sm font-bold uppercase tracking-[0.06em] shadow-sm transition duration-150 disabled:cursor-not-allowed disabled:opacity-35";

const osdBtnGhost =
  `${osdBtnBase} border-spire-border-strong bg-spire-canvas text-spire-primary hover:bg-spire-panel-raised hover:border-spire-border-strong`;

/** Replay toolbar — matches `h-7` replay `<select>` height. */
const osdReplayBtn =
  "font-console inline-flex h-8 shrink-0 items-center justify-center rounded-md border-2 border-spire-border-strong bg-spire-canvas px-2.5 text-xs font-bold uppercase tracking-[0.08em] text-spire-primary shadow-sm transition duration-150 hover:bg-spire-panel-raised disabled:cursor-not-allowed disabled:opacity-35";

const osdReplayInput =
  "font-console h-8 w-11 rounded-md border-2 border-spire-border-subtle bg-spire-canvas px-1 text-center text-xs font-bold text-spire-primary shadow-sm outline-none ring-inset focus-visible:ring-2 focus-visible:ring-spire-ring-focus/45 tabular-nums";

/** Solid fill, same chrome family as Approve / CTA (no outline accent bar). */
const osdBtnRetry =
  `${osdBtnBase} border-spire-warning bg-spire-canvas text-spire-primary hover:bg-spire-warning/18`;

const osdBtnApprove =
  `${osdBtnBase} border-spire-success bg-spire-canvas text-spire-primary hover:bg-spire-success/18`;
const osdBtnReject =
  `${osdBtnBase} border-spire-border-strong bg-spire-panel-raised text-spire-primary hover:bg-spire-panel`;
const osdBtnCta =
  `${osdBtnBase} border-spire-secondary bg-spire-secondary/25 text-spire-primary hover:bg-spire-secondary/35`;

/** Fixed height — Relics rail, Enemies/Hand combat headers, LLM prompt, AI control share one band size. */
const osdPanelStrip =
  "flex h-12 min-h-12 shrink-0 items-center justify-between gap-2 overflow-hidden border-b-2 border-spire-border-subtle bg-spire-canvas px-3 font-console text-sm font-bold uppercase tracking-[0.12em] text-spire-primary";

const osdSectionLabel =
  "font-console text-sm font-bold uppercase tracking-[0.12em] text-spire-label";

const osdStatCaption =
  "font-console text-sm font-bold uppercase tracking-[0.18em] text-spire-label";

/** Tighter label for the HUD stats strip (label + value stack). */
const osdHudLabel =
  "font-console text-[12px] font-semibold uppercase tracking-[0.22em] text-spire-label leading-none";
const osdHudValue =
  "font-telemetry text-[15px] font-semibold tabular-nums leading-none";

function actionBtnClass(action: ActionDTO): string {
  const v = validActionVariant(action);
  return (
    "font-console rounded-md border-2 py-1.5 px-3 text-sm font-bold uppercase tracking-wide " +
    "text-spire-primary shadow-sm transition-colors duration-150 " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-spire-ring-focus/40 " +
    `valid-action--${v}`
  );
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
    label: string;
    title: string;
    n: number;
    tint: string;
    glow: string;
  }[] = [
    {
      kind: "draw",
      label: "Draw",
      title: "Draw pile — click to inspect",
      n: drawN,
      tint: "text-spire-secondary",
      glow: "group-hover:text-spire-primary",
    },
    {
      kind: "discard",
      label: "Discard",
      title: "Discard pile — click to inspect",
      n: discN,
      tint: "text-spire-warning",
      glow: "group-hover:text-spire-primary",
    },
    {
      kind: "exhaust",
      label: "Exhaust",
      title: "Exhaust pile — click to inspect",
      n: exhN,
      tint: "text-spire-danger",
      glow: "group-hover:text-spire-primary",
    },
  ];

  return (
    <div
      className="deck-telemetry flex h-8 max-h-8 shrink-0 overflow-hidden rounded-md border border-spire-border-subtle/90"
      role="group"
      aria-label="Draw, Discard, Exhaust piles — click to inspect"
    >
      {segments.map((s, i) => (
        <button
          key={s.kind}
          type="button"
          onClick={() => onInspect(s.kind)}
          title={s.title}
          className={
            "group relative flex h-full min-h-0 min-w-0 flex-1 items-center justify-between gap-2 px-2 py-0 text-left transition-[background-color,box-shadow] duration-150 " +
            "hover:bg-spire-panel/40 active:bg-spire-panel/65 " +
            "focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-spire-ring-focus/45 " +
            (i > 0 ? "border-l border-spire-border-subtle/55 " : "")
          }
        >
          <span className="min-w-0 truncate font-console text-[13px] font-semibold uppercase tracking-wide text-spire-label transition-colors group-hover:text-spire-muted">
            {s.label}
          </span>
          <span
            className={`font-telemetry text-sm font-semibold leading-none tabular-nums tracking-tight transition-colors ${s.tint} ${s.glow}`}
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

function ascensionDisplay(h: HeaderDTO | null | undefined): number {
  const n = h?.ascension_level;
  return typeof n === "number" && Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0;
}

function seedFirstSix(raw: string | null): string {
  if (raw == null || raw === "") return "—";
  return raw.length <= 6 ? raw : raw.slice(0, 6);
}

/** R · S · E = Ruby, Sapphire, Emerald — light brown when missing; gem colors when owned. */
function KeysLetters({
  keys,
}: {
  keys?: { ruby?: boolean; emerald?: boolean; sapphire?: boolean } | null;
}) {
  const ruby = keys?.ruby === true;
  const sapphire = keys?.sapphire === true;
  const emerald = keys?.emerald === true;
  const tip = `Act 3 keys\nRuby: ${ruby ? "yes" : "no"}\nSapphire: ${sapphire ? "yes" : "no"}\nEmerald: ${emerald ? "yes" : "no"}`;
  /** Unowned — warm parchment brown (not gray). */
  const offLetter =
    "text-[color-mix(in_srgb,var(--border-subtle)_42%,var(--bg-canvas))]";
  const cell = (letter: string, on: boolean, onClass: string) => (
    <span
      className={
        "min-w-[0.65rem] text-center text-sm font-bold tabular-nums " +
        (on ? onClass : offLetter)
      }
    >
      {letter}
    </span>
  );
  return (
    <HoverTip tip={tip} side="bottom" className="shrink-0">
      <div
        className="flex items-center gap-0.5 font-console tracking-tight"
        aria-label="Act 3 keys: Ruby, Sapphire, Emerald"
      >
        {cell("R", ruby, "text-spire-danger")}
        <span className={`text-[13px] ${offLetter} opacity-90`}>·</span>
        {cell("S", sapphire, "text-spire-secondary")}
        <span className={`text-[13px] ${offLetter} opacity-90`}>·</span>
        {cell("E", emerald, "text-spire-success")}
      </div>
    </HoverTip>
  );
}

/** Enemy block: header row (name, HP, intent) + powers row — layout per IDE mock. */
function EnemyCard({ m }: { m: Record<string, unknown> }) {
  const name = String(m.name ?? "?");
  const hp = String(m.hp_display ?? "");
  const intent = String(m.intent_display ?? "");
  const powers = (m.powers as Record<string, unknown>[] | undefined) ?? [];
  const tip = monsterTooltip(m);

  const rowBand =
    "flex min-h-10 items-center bg-spire-canvas px-2 py-2";

  return (
    <div className="flex flex-col overflow-hidden rounded-md border border-spire-border-subtle bg-spire-canvas shadow-sm">
      <div
        className={`${rowBand} justify-between gap-x-2 gap-y-1 border-b border-spire-border-muted`}
      >
        <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
          <HoverTip tip={tip} side="bottom" className="min-w-0">
            <span className="cursor-help whitespace-normal break-words font-console text-xs font-bold text-spire-danger underline decoration-spire-danger/40 decoration-dotted underline-offset-2">
              {name}
            </span>
          </HoverTip>
          <span className="shrink-0 font-console text-xs font-bold uppercase tracking-[0.18em] text-spire-label">
            HP
          </span>
          <span className="shrink-0 font-telemetry text-xs font-medium text-spire-primary">
            {hp ? fmtGameStatDisplay(hp) : "—"}
          </span>
        </div>
        <div className="max-w-[min(11rem,42%)] shrink-0 text-right font-console text-[13px] font-semibold uppercase tracking-wide text-spire-danger">
          <span className="block whitespace-normal break-words">
            {intent || "—"}
          </span>
        </div>
      </div>
      <div className={`${rowBand} flex-wrap gap-1`}>
        {powers.length === 0 ? (
          <span className="text-[13px] text-spire-faint">—</span>
        ) : (
          powers.map((p, i) => (
            <HoverTip
              key={i}
              tip={labeledTooltip(powerChipLabel(p), p, {
                skipPowerAmountLead: true,
              })}
              side="bottom"
              className="inline-flex"
            >
              <span className="inline-flex cursor-help rounded border border-spire-secondary/50 bg-spire-canvas px-1.5 py-1 text-[13px] font-semibold leading-tight text-spire-secondary shadow-sm">
                {powerChipLabel(p)}
              </span>
            </HoverTip>
          ))
        )}
      </div>
    </div>
  );
}

function CardTable({ cards }: { cards: Record<string, unknown>[] }) {
  return (
    <table className="w-full table-fixed text-left leading-snug whitespace-nowrap [&_td:last-child]:whitespace-normal">
      <thead className="sticky top-0 z-10 bg-spire-canvas font-console text-xs font-semibold uppercase tracking-[0.14em] text-spire-label">
        <tr>
          <th className="w-8 border-b border-spire-border-muted py-1 px-2 font-semibold">
            #
          </th>
          <th className="w-24 border-b border-spire-border-muted py-1 px-2 font-semibold">
            Hash
          </th>
          <th className="w-8 border-b border-spire-border-muted py-1 px-2 text-center font-semibold">
            $
          </th>
          <th className="w-[22%] border-b border-spire-border-muted py-1 px-2 font-semibold">
            Name
          </th>
          <th className="min-w-0 border-b border-spire-border-muted py-1 px-2 font-semibold">
            Text
          </th>
        </tr>
      </thead>
      <tbody className="divide-y divide-spire-border-muted font-telemetry text-xs font-medium text-spire-primary">
        {cards.map((c, idx) => (
            <tr key={idx} className="hover:bg-spire-panel-raised/35">
              <td className="py-1 px-2">{fmtIntEn(idx + 1)}</td>
              <td className="py-1 px-2 text-spire-label">{cardHash(c.uuid)}</td>
              <td className="py-1 px-2 text-center">
                <span className="font-extrabold tabular-nums text-spire-secondary">
                  {fmtGameStatDisplay(c.cost ?? "—")}
                </span>
              </td>
              <td
                className={`min-w-0 py-1 px-2 ${cardNameClass(c.type)}`}
                title={
                  String(c.type ?? "").trim()
                    ? `Type: ${String(c.type)}`
                    : undefined
                }
              >
                {String(c.name ?? "?")}
              </td>
              <td className="min-w-0 py-1 px-2 break-words text-spire-primary">
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay-scrim)] p-4 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label={title}
        className="custom-scroll flex max-h-[85vh] max-w-4xl flex-col overflow-hidden rounded-lg border border-spire-border-subtle bg-spire-canvas shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={osdPanelStrip}>
          <div className="flex min-w-0 items-baseline gap-3 normal-case tracking-normal">
            <span className="truncate font-console text-xs font-bold text-spire-primary">
              {title}
            </span>
            <span className="shrink-0 font-telemetry text-xs text-spire-label">
              {fmtIntEn(cards.length)} cards
            </span>
          </div>
          <button type="button" onClick={onClose} className={osdBtnGhost}>
            Close
          </button>
        </div>
        <div className="custom-scroll min-h-0 flex-1 overflow-auto p-3">
          {cards.length === 0 ? (
            <p className="py-8 text-center text-sm text-spire-label">Empty pile</p>
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
      className="flex w-full shrink-0 overflow-hidden rounded-md border-2 border-spire-border-strong bg-spire-canvas font-console text-[13px] font-bold uppercase tracking-[0.12em] shadow-sm"
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
            "min-w-0 flex-1 border-r border-spire-border-subtle/80 px-1 py-1.5 last:border-r-0 transition " +
            (current === m
              ? "bg-spire-tab-active text-spire-primary font-bold"
              : "bg-spire-canvas text-spire-label hover:bg-spire-panel-raised hover:text-spire-primary")
          }
          onClick={() => onSelect(m)}
        >
          {m}
        </button>
      ))}
    </div>
  );
}

function RelicsPowersBar({
  relics,
  playerPowers,
}: {
  relics: Record<string, unknown>[];
  playerPowers: Record<string, unknown>[];
}) {
  return (
    <div
      className="shrink-0 border-b-2 border-spire-border-subtle bg-[color-mix(in_srgb,var(--bg-panel)_55%,var(--bg-canvas))] px-3 py-2"
      aria-label="Relics and powers"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch sm:gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span className="shrink-0 font-console text-xs font-bold uppercase tracking-[0.14em] text-spire-label">
            Relics · {fmtIntEn(relics.length)}
          </span>
          <div className="custom-scroll flex min-w-0 flex-1 gap-1.5 overflow-x-auto pb-0.5">
            {relics.length === 0 ? (
              <span className="font-console text-xs italic text-spire-faint">
                None
              </span>
            ) : (
              relics.map((r, i) => (
                <HoverTip
                  key={i}
                  tip={labeledTooltip(String(r.name ?? "?"), r)}
                  side="bottom"
                  className="shrink-0"
                >
                  <div className="max-w-[10rem] cursor-help truncate rounded-md border-2 border-spire-border-subtle bg-spire-canvas px-1.5 py-0.5 text-xs font-medium text-spire-primary shadow-sm">
                    {String(r.name ?? "?")}
                  </div>
                </HoverTip>
              ))
            )}
          </div>
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-2 border-t border-spire-border-muted pt-2 sm:border-t-0 sm:border-l sm:pt-0 sm:pl-4">
          <span className="shrink-0 font-console text-xs font-bold uppercase tracking-[0.14em] text-spire-label">
            Powers
          </span>
          <div className="custom-scroll flex min-w-0 flex-1 gap-1.5 overflow-x-auto pb-0.5">
            {playerPowers.length === 0 ? (
              <span className="font-console text-xs italic text-spire-faint">
                None
              </span>
            ) : (
              playerPowers.map((p, i) => (
                <HoverTip
                  key={i}
                  tip={labeledTooltip(powerChipLabel(p), p, {
                    skipPowerAmountLead: true,
                  })}
                  side="bottom"
                  className="shrink-0"
                >
                  <div className="max-w-[9rem] cursor-help truncate rounded-md border-2 border-spire-border-subtle bg-spire-canvas px-1.5 py-0.5 text-xs font-medium text-spire-primary shadow-sm">
                    {powerChipLabel(p)}
                  </div>
                </HoverTip>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function MonitorDashboard() {
  const {
    snapshot,
    connected,
    queueManualCommand,
    setAgentMode,
    setAutoStartNextGame,
    resumeAgent,
    retryAgent,
    pushLog,
    replayRuns,
    replayPickerRun,
    setReplayPickerRun,
    replayFiles,
    replayIndex,
    replayBusy,
    replayRunName,
    replayAiSidecar,
    loadReplayRun,
    replaySeek,
    replayJumpToFrame,
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
  const [deckInspectOpen, setDeckInspectOpen] = useState(false);
  const [replayJumpInput, setReplayJumpInput] = useState("");
  const [railWidthPx, setRailWidthPx] = useState(440);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("spireRailWidthPx");
      const n = raw ? Number.parseInt(raw, 10) : NaN;
      if (Number.isFinite(n) && n >= 300) {
        setRailWidthPx(Math.min(800, Math.max(300, n)));
      }
    } catch {
      /* ignore */
    }
  }, []);

  const vm: ViewModelDTO | null = snapshot?.view_model ?? null;
  const showScreenPanel = Boolean(vm?.screen);
  const stateId = snapshot?.state_id ?? null;
  /** Recent CommunicationMod / bridge feed — not merely WebSocket connected to the dashboard. */
  const gameFeedLive = snapshot?.live_ingress === true;
  const inReplay = replayRunName !== "" && replayFiles.length > 0;
  const dashOk = connected;

  const onRailResizeMouseDown = useCallback(
    (e: ReactMouseEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startW = railWidthPx;
      const onMove = (ev: MouseEvent) => {
        const dx = startX - ev.clientX;
        setRailWidthPx(Math.min(800, Math.max(300, startW + dx)));
      };
      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        setRailWidthPx((w) => {
          try {
            localStorage.setItem("spireRailWidthPx", String(w));
          } catch {
            /* ignore */
          }
          return w;
        });
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    },
    [railWidthPx],
  );

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

  useEffect(() => {
    if (replayFiles.length === 0) {
      setReplayJumpInput("");
      return;
    }
    setReplayJumpInput(String(replayIndex + 1));
  }, [replayIndex, replayFiles.length, replayRunName]);

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
  const masterDeck =
    (inventory?.deck as Record<string, unknown>[] | undefined) ?? [];

  const potionSlots = useMemo(() => {
    const defaultCount = 3;
    const slotCount =
      potions.length === 0
        ? defaultCount
        : Math.max(defaultCount, potions.length);
    const slots: (Record<string, unknown> | null)[] = [];
    for (let i = 0; i < slotCount; i++) {
      const p = potions[i];
      if (p && typeof p === "object" && !isPotionSlotPlaceholder(p)) {
        slots.push(p);
      } else {
        slots.push(null);
      }
    }
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
          "The game process is checking LLM configuration (see browser console or game output).",
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
      };
    }
    if (proposalStatus === "running") {
      return {
        kind: "pending",
        pulse: true,
        title: "Awaiting model response",
        message:
          "The model is generating a reply (including after tool calls). This can take a while.",
      };
    }
    if (proposalStatus === "awaiting_approval") {
      return {
        kind: "pending",
        pulse: false,
        title: "Proposal ready",
        message:
          "The model returned a legal command. Use Awaiting approval below or switch to auto mode.",
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

  const tacticalPromptMarkdown = useMemo(
    () => renderPromptMarkdown(tacticalPromptText),
    [tacticalPromptText],
  );

  const aiRailTitle =
    "LLM backend and current frame id for this snapshot.";
  const runSeedRaw =
    snapshot?.agent?.run_seed != null &&
    String(snapshot.agent.run_seed).trim() !== ""
      ? String(snapshot.agent.run_seed).trim()
      : null;

  const commitReplayJump = useCallback(() => {
    const n = replayFiles.length;
    if (n === 0) return;
    const v = Number.parseInt(replayJumpInput.trim(), 10);
    if (!Number.isFinite(v) || v < 1 || v > n) return;
    replayJumpToFrame(v);
  }, [replayFiles.length, replayJumpInput, replayJumpToFrame]);

  return (
    <div className="metrics-page-bg flex h-screen flex-col overflow-hidden text-sm text-[var(--text-primary)] select-none">
      {/* Top bar — game / session controls only; combat readouts live in the stats strip */}
      <header className="flex shrink-0 items-center border-b border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-panel)_88%,transparent)] px-3 py-2 backdrop-blur-sm">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
          <SpireAgentNav page="monitor" runQuery="" />
          <div className="flex shrink-0 items-center gap-1.5">
            <div
              className={`font-console flex h-7 items-center gap-1.5 rounded border px-2 text-[13px] font-semibold uppercase tracking-wide ${
                dashOk
                  ? "border-spire-success/50 bg-spire-success/10 text-spire-success"
                  : "border-spire-danger/45 bg-spire-danger/8 text-spire-danger"
              }`}
              title={
                dashOk
                  ? "Dashboard WebSocket connected — this tab can receive pushes."
                  : "Dashboard WebSocket disconnected — reconnect to send commands and receive live snapshots."
              }
              aria-label={
                dashOk
                  ? "Dashboard link: connected"
                  : "Dashboard link: disconnected"
              }
            >
              <span className="relative flex h-1.5 w-1.5 shrink-0">
                {dashOk ? (
                  <>
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-spire-success opacity-60" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-spire-success" />
                  </>
                ) : (
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-spire-danger" />
                )}
              </span>
              <span>Dash {dashOk ? "OK" : "off"}</span>
            </div>
            <div
              className={`font-console flex h-7 items-center gap-1.5 rounded border px-2 text-[13px] font-semibold uppercase tracking-wide ${
                inReplay
                  ? "border-spire-secondary/45 bg-spire-secondary/10 text-spire-secondary"
                  : gameFeedLive
                    ? "border-spire-success/50 bg-spire-success/10 text-spire-success"
                    : "border-spire-warning/40 bg-spire-warning/8 text-spire-warning"
              }`}
              title={
                inReplay
                  ? "Replay mode: frames load from disk; live ingress does not apply."
                  : gameFeedLive
                    ? "Fresh game state is arriving from the bridge or debug ingress."
                    : !dashOk
                      ? "WebSocket offline — feed status may be unknown until connected."
                      : "Feed stale or idle — game stopped, paused, or past dashboard staleness threshold."
              }
              aria-label={
                inReplay
                  ? "Game feed: replaying log frames"
                  : gameFeedLive
                    ? "Game feed: live"
                    : "Game feed: stale or idle"
              }
            >
              {!inReplay ? (
                <span className="relative flex h-1.5 w-1.5 shrink-0">
                  {gameFeedLive ? (
                    <>
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-spire-success opacity-60" />
                      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-spire-success" />
                    </>
                  ) : (
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-spire-warning" />
                  )}
                </span>
              ) : (
                <span className="relative inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-spire-secondary" />
              )}
              <span>
                {inReplay
                  ? "Replay"
                  : gameFeedLive
                    ? "Feed live"
                    : "Feed stale"}
              </span>
            </div>
          </div>

          {snapshot?.active_log_run ? (
            <Link
              to={`/metrics?run=${encodeURIComponent(snapshot.active_log_run)}&follow=1`}
              className="font-console shrink-0 text-xs font-semibold uppercase tracking-wide text-[var(--accent-primary)] hover:text-[var(--accent-primary-hover)]"
            >
              Metrics (this run)
            </Link>
          ) : null}

          <div
            className="flex flex-wrap items-center gap-x-3 gap-y-1 border-l border-spire-border-strong/70 pl-4"
            title="Replay loads frames from logs; live snapshots are paused until you clear the run."
          >
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
                className="font-console h-8 max-w-[14rem] rounded-md border-2 border-spire-border-subtle bg-spire-canvas px-2 text-xs font-bold text-spire-primary shadow-sm outline-none"
                aria-label="Log run directory under logs/"
              >
                <option value="">Select run…</option>
                {replayRuns.map((run) => (
                  <option key={run} value={run}>
                    {run}
                  </option>
                ))}
              </select>
              {replayFiles.length > 0 ? (
                <>
                  <button
                    type="button"
                    disabled={replayBusy || replayIndex <= 0}
                    className={osdReplayBtn}
                    onClick={() => replaySeek(-10)}
                    title="Back 10 frames"
                  >
                    −10
                  </button>
                  <button
                    type="button"
                    disabled={replayBusy || replayIndex <= 0}
                    className={osdReplayBtn}
                    onClick={() => replaySeek(-1)}
                  >
                    Prev
                  </button>
                  <span className="font-telemetry min-w-[4.5rem] text-center text-xs tabular-nums text-spire-muted">
                    {fmtIntEn(replayIndex + 1)}/{fmtIntEn(replayFiles.length)}
                  </span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={replayJumpInput}
                    onChange={(e) => setReplayJumpInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitReplayJump();
                    }}
                    disabled={replayBusy}
                    className={osdReplayInput}
                    title="Frame index (1-based). Enter to jump."
                    aria-label="Replay frame index"
                  />
                  <button
                    type="button"
                    disabled={replayBusy}
                    className={osdReplayBtn}
                    onClick={() => commitReplayJump()}
                    title="Jump to frame in box (1-based)"
                  >
                    Go
                  </button>
                  <button
                    type="button"
                    disabled={
                      replayBusy || replayIndex >= replayFiles.length - 1
                    }
                    className={osdReplayBtn}
                    onClick={() => replaySeek(1)}
                  >
                    Next
                  </button>
                  <button
                    type="button"
                    disabled={
                      replayBusy || replayIndex >= replayFiles.length - 1
                    }
                    className={osdReplayBtn}
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

      {snapshot?.live_ingress === false && !inReplay ? (
        <div
          className="shrink-0 border-b border-spire-warning/35 bg-spire-warning/10 px-3 py-2 text-sm text-spire-primary/95"
          role="status"
        >
          <span className="font-console font-semibold uppercase tracking-wide text-spire-warning">
            Feed stale
          </span>
          <span className="text-spire-primary/90">
            {" "}
            — matches the amber <span className="font-medium">Feed stale</span>{" "}
            pill; start the game bridge or use{" "}
            <span className="font-medium">Replay</span>.
            {typeof snapshot.ingress_age_seconds === "number" ? (
              <span className="text-spire-warning/90">
                {" "}
                Last ingress ~{fmtIntEn(Math.round(snapshot.ingress_age_seconds))}s
                ago.
              </span>
            ) : null}
          </span>
        </div>
      ) : null}

      {/* Stats + potions — compact HUD row */}
      <div className="flex min-h-0 shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b-2 border-spire-border-subtle bg-spire-canvas px-3 py-1.5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="flex min-h-[2.25rem] flex-col justify-center gap-1">
            <span className={osdHudLabel}>Seed</span>
            <button
              type="button"
              disabled={runSeedRaw == null}
              onClick={() => {
                if (runSeedRaw) void copyClipboard(runSeedRaw, "seed");
              }}
              className="max-w-[4.5rem] truncate rounded border border-spire-border-strong/90 bg-spire-canvas/80 px-1.5 py-0.5 text-left font-mono text-[13px] font-medium tabular-nums text-spire-primary transition hover:border-spire-border-strong hover:bg-spire-panel/90 hover:text-spire-primary disabled:cursor-not-allowed disabled:opacity-40"
              title={
                runSeedRaw
                  ? `Click to copy full seed (${runSeedRaw.length} chars)`
                  : "No seed on this snapshot"
              }
            >
              {seedFirstSix(runSeedRaw)}
            </button>
          </div>
          <div className="flex min-h-[2.25rem] flex-col justify-center gap-1">
            <span className={osdHudLabel}>Class</span>
            <span className={`${osdHudValue} text-spire-warning`}>
              {(() => {
                const name = displayPlayerClassName(headerClass(header));
                if (name === "—") return "—";
                return (
                  <>
                    {name}
                    <span className="text-spire-label"> · </span>
                    <span className="tabular-nums">
                      A{fmtIntEn(ascensionDisplay(header))}
                    </span>
                  </>
                );
              })()}
            </span>
          </div>
          {(
            [
              ["Floor", header?.floor ?? "—", "text-spire-primary"],
              ["HP", header?.hp_display ?? "—", "text-spire-danger"],
              ["Gold", header?.gold ?? "—", "hud-gold-metal"],
            ] as const
          ).map(([label, val, col]) => (
            <div
              key={label}
              className="flex min-h-[2.25rem] flex-col justify-center gap-1"
            >
              <span className={osdHudLabel}>{label}</span>
              <span className={`${osdHudValue} ${col}`}>
                {fmtGameStatDisplay(val)}
              </span>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-x-4 border-l border-spire-border-strong/55 pl-4">
            {(
              [
                ["Energy", header?.energy ?? "—", "text-spire-primary"],
                ["Turn", header?.turn ?? "—", "text-spire-primary"],
              ] as const
            ).map(([label, val, col]) => (
              <div
                key={label}
                className="flex min-h-[2.25rem] flex-col justify-center gap-1"
              >
                <span className={osdHudLabel}>{label}</span>
                <span className={`${osdHudValue} ${col}`}>
                  {fmtGameStatDisplay(val)}
                </span>
              </div>
            ))}
          </div>
          <div className="flex min-h-[2.25rem] flex-col justify-center gap-1 border-l border-spire-border-strong/55 pl-4">
            <span className={osdHudLabel}>Keys</span>
            <KeysLetters keys={vm?.keys} />
          </div>
          {vm?.in_game ? (
            <div className="flex flex-wrap items-center gap-x-3 border-l border-spire-border-strong/55 pl-4">
              <div className="flex min-h-[2.25rem] flex-col justify-center gap-1">
                <span className={osdHudLabel}>Deck</span>
                <button
                  type="button"
                  onClick={() => {
                    setPileInspect(null);
                    setDeckInspectOpen(true);
                  }}
                  disabled={masterDeck.length === 0}
                  title={
                    masterDeck.length === 0
                      ? "No master deck in this snapshot"
                      : "View master deck (full run list)"
                  }
                  className="min-w-[2rem] rounded border border-spire-border-strong/90 bg-spire-canvas/80 px-1.5 py-0.5 text-center font-mono text-[13px] font-semibold tabular-nums text-spire-primary transition hover:border-spire-border-strong hover:bg-spire-panel/90 hover:text-spire-primary disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {fmtIntEn(masterDeck.length)}
                </button>
              </div>
              <div className="flex min-h-[2.25rem] flex-col justify-center gap-1">
                <span className={`${osdHudLabel}`}>Potions</span>
                <div className="flex flex-wrap items-center gap-1">
                {potionSlots.map((p, i) =>
                  p ? (
                    <HoverTip
                      key={i}
                      tip={labeledTooltip(String(p.name ?? "Potion"), p)}
                      side="bottom"
                      className="w-auto shrink-0"
                    >
                      <div className="font-console max-w-[7.5rem] truncate rounded-md border-2 border-spire-border-strong bg-spire-canvas px-1.5 py-0.5 text-xs font-bold text-spire-primary shadow-sm">
                        {String(p.name ?? "Potion")}
                      </div>
                    </HoverTip>
                  ) : (
                    <div
                      key={i}
                      className="font-console rounded border border-dashed border-spire-border-strong/70 px-1.5 py-0.5 text-xs text-spire-faint"
                    >
                      —
                    </div>
                  ),
                )}
                </div>
              </div>
            </div>
          ) : null}
          {showOrbStrip ? (
            <div className="flex flex-wrap items-center gap-1.5 border-l border-spire-border-strong/55 pl-4">
              <HoverTip
                tip={orbStripHelpText()}
                side="bottom"
                className="shrink-0"
              >
                <span
                  className={`${osdStatCaption} mr-0.5 cursor-help border-b border-dotted border-spire-label/80`}
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
                        <div className="font-console rounded border border-dashed border-spire-border-strong/70 px-1.5 py-0.5 text-xs text-spire-faint">
                          {orbMechanics.ui?.empty_chip ?? "—"}
                        </div>
                      ) : (
                        <div className="font-console max-w-[6.5rem] truncate rounded border border-spire-secondary/50 bg-spire-secondary/12 px-1.5 py-0.5 text-xs font-medium text-spire-primary">
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

      <RelicsPowersBar relics={relics} playerPowers={playerPowers} />

      {/* IDE workspace — center column + AI rail */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <main className="relative flex min-h-0 min-w-0 flex-1 flex-col border-r border-spire-border-subtle">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col lg:flex-row">
            {/* Game state — half of center column (excl. AI rail); map/screen or stacked combat */}
            <div className="flex min-h-[min(36vh,18rem)] min-w-0 flex-1 flex-col max-lg:border-b max-lg:border-spire-border-subtle lg:min-h-0 lg:min-w-0 lg:flex-1 lg:basis-0 lg:border-r lg:border-spire-border-subtle">
              {showScreenPanel && vm ? (
                <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
                  <GameScreenPanel
                    vm={vm}
                    scrollBottomPadClass="pb-28"
                    onChoose={(cmd) => void queueManualCommand(cmd)}
                  />
                </div>
              ) : (
                <div className="flex min-h-0 min-w-0 max-h-[min(68vh,44rem)] flex-1 flex-col overflow-hidden lg:max-h-none">
                  {/* Enemies above hand — each pane scrolls; empty enemy strip stays compact */}
                  <div
                    className={
                      monsters.length === 0
                        ? "flex shrink-0 flex-col border-b border-spire-border-subtle bg-spire-canvas"
                        : "flex min-h-0 min-w-0 flex-[5] flex-col border-b border-spire-border-subtle bg-spire-canvas basis-0"
                    }
                  >
                    <div className={`sticky top-0 z-10 ${osdPanelStrip}`}>
                      Enemies · {fmtIntEn(monsters.length)}
                    </div>
                    <div
                      className={
                        monsters.length === 0
                          ? "custom-scroll space-y-1.5 overflow-y-auto p-2 pb-28"
                          : "custom-scroll min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2 pb-28"
                      }
                    >
                      {monsters.length === 0 ? (
                        <div className="space-y-2 px-2 py-4 text-center text-sm text-spire-label">
                          <p className="font-medium text-spire-muted">
                            No enemies
                          </p>
                          {nonCombatBoardHint ? (
                            <p className="text-xs leading-relaxed text-spire-faint">
                              {nonCombatBoardHint}
                            </p>
                          ) : (
                            <p className="text-xs text-spire-faint">No enemies.</p>
                          )}
                        </div>
                      ) : (
                        monsters.map((m, i) => <EnemyCard key={i} m={m} />)
                      )}
                    </div>
                  </div>

                  <div className="flex min-h-0 min-w-0 flex-[7] flex-col bg-spire-canvas basis-0">
                    <div className={`sticky top-0 z-10 ${osdPanelStrip}`}>
                      <span className="min-w-0 shrink-0 truncate">
                        Hand · {fmtIntEn(hand.length)}
                      </span>
                      <div className="flex min-w-0 shrink items-stretch gap-1.5">
                        <PileTelemetryBar
                          draw={draw}
                          discard={disc}
                          exhaust={exhaust}
                          onInspect={(k) => {
                            setDeckInspectOpen(false);
                            setPileInspect(k);
                          }}
                        />
                      </div>
                    </div>
                    <div className="custom-scroll min-h-0 flex-1 overflow-y-auto pb-28">
                      {hand.length === 0 ? (
                        <div className="space-y-2 px-2 py-4 text-center text-sm text-spire-label">
                          <p className="font-medium text-spire-muted">
                            No cards in hand
                          </p>
                          {nonCombatBoardHint ? (
                            <p className="text-xs leading-relaxed text-spire-faint">
                              {nonCombatBoardHint}
                            </p>
                          ) : (
                            <p className="text-xs text-spire-faint">
                              No cards in hand.
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
            </div>

            {/* LLM user prompt — other half of center column on lg+ */}
            <div className="flex min-h-[min(28vh,15rem)] min-w-0 flex-1 flex-col bg-spire-canvas lg:min-h-0 lg:min-w-0 lg:flex-1 lg:basis-0">
              <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                <div
                  className={osdPanelStrip}
                  title="Tactical user message for this state (live trace or server preview)."
                >
                  <span className="min-w-0 shrink truncate">
                    LLM user prompt
                  </span>
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
                <div className="font-telemetry custom-scroll min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto p-3 pb-28 text-sm font-medium leading-relaxed text-spire-primary">
                  {tacticalPromptMarkdown}
                </div>
              </div>
            </div>
          </div>

          {/* Valid actions — floats over game + prompt; height follows content (scroll if huge) */}
          <div className="absolute bottom-0 left-0 right-0 z-30 flex max-h-[min(45vh,20rem)] flex-col border-t-2 border-spire-border-subtle bg-spire-canvas/95 shadow-[0_-12px_32px_rgba(42,34,24,0.18)] backdrop-blur-[3px]">
            <div
              className={`shrink-0 border-b-2 border-spire-border-muted bg-spire-canvas/95 px-2 py-1.5 backdrop-blur-[3px] ${osdSectionLabel}`}
            >
              Valid actions
            </div>
            <div className="custom-scroll max-h-[min(36vh,15rem)] shrink-0 overflow-x-hidden overflow-y-auto px-2 py-1">
              <div className="flex flex-wrap content-start gap-1">
              {actions.length === 0 ? (
                <span className="font-console text-xs text-spire-faint">
                  No actions
                </span>
              ) : (
                actions.map((a, i) => (
                  <button
                    key={`${a.command}-${i}`}
                    type="button"
                    className={actionBtnClass(a)}
                    title={a.command}
                    onClick={() => void queueManualCommand(a.command)}
                  >
                    {a.label}
                  </button>
                ))
              )}
              </div>
            </div>
          </div>
        </main>

        {/* Col 4 — AI operator rail (compact; boxed headers avoid overlap with scroll areas) */}
        <aside
          className="relative z-20 flex max-w-[min(800px,48vw)] shrink-0 flex-col border-l border-spire-success/25 bg-[var(--bg-canvas)] pl-1 shadow-[-6px_0_20px_rgba(42,34,24,0.07)]"
          style={{ width: railWidthPx }}
        >
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize AI rail"
            className="absolute left-0 top-0 z-30 h-full w-1 cursor-col-resize hover:bg-spire-accent/20"
            onMouseDown={onRailResizeMouseDown}
          />
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
              title="Clear stuck trace and allow a fresh proposal on the next tick (no-op in manual mode)."
              className={osdBtnRetry}
              onClick={() => void retryAgent()}
            >
              Retry AI
            </button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2 custom-scroll">
            <div
              className="shrink-0 rounded-md border-2 border-spire-border-subtle bg-spire-canvas px-2 py-2 shadow-sm"
              title={aiRailTitle}
            >
              <AgentModeBar
                modeRaw={agentForRail?.agent_mode}
                disabled={snapshot == null}
                onSelect={(m) => void setAgentMode(m)}
              />
              <div className="mt-3 flex items-center justify-between gap-3 rounded-md border-2 border-spire-border-subtle bg-spire-canvas px-2.5 py-2 shadow-sm">
                <div className="min-w-0">
                  <div className="font-console text-[13px] font-semibold uppercase tracking-wide text-spire-primary">
                    Auto-start next run
                  </div>
                  <p className="mt-0.5 font-telemetry text-[13px] leading-snug text-spire-label">
                    Sends start on the title screen so a new run begins without
                    in-game Continue.
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={Boolean(agentForRail?.auto_start_next_game)}
                  disabled={snapshot == null}
                  title={
                    snapshot == null
                      ? undefined
                      : "Toggle auto-start on the title screen"
                  }
                  onClick={() =>
                    void setAutoStartNextGame(
                      !Boolean(agentForRail?.auto_start_next_game),
                    )
                  }
                  className={
                    "relative h-7 w-12 shrink-0 rounded-full border transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-spire-success/40 disabled:cursor-not-allowed disabled:opacity-40 " +
                    (agentForRail?.auto_start_next_game
                      ? "border-spire-success bg-spire-success/12"
                      : "border-spire-border-strong bg-spire-panel-raised")
                  }
                >
                  <span
                    className={
                      "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-spire-primary shadow transition-transform " +
                      (agentForRail?.auto_start_next_game
                        ? "translate-x-5"
                        : "translate-x-0")
                    }
                    aria-hidden
                  />
                </button>
              </div>
            </div>

            {llmRunStatus.kind === "error" ? (
              <div className="shrink-0 rounded border border-spire-danger/45 bg-spire-danger/10 p-2 shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--danger)_18%,transparent)]">
                <div className="mb-1 flex items-start justify-between gap-2">
                  <span className="font-console text-xs font-bold uppercase tracking-[0.1em] text-spire-danger">
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
                <p className="font-telemetry text-sm leading-snug text-spire-primary/95 whitespace-pre-wrap break-words">
                  {llmRunStatus.message}
                </p>
              </div>
            ) : (
              <div className="shrink-0 rounded border border-spire-live-border bg-spire-live-surface p-2 shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--accent-primary)_14%,transparent)]">
                <div className="mb-1 flex items-center gap-2">
                  {llmRunStatus.pulse !== false ? (
                    <span
                      className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-spire-accent shadow-[0_0_10px_color-mix(in_srgb,var(--accent-primary)_55%,transparent)]"
                      aria-hidden
                    />
                  ) : null}
                  <span className="font-console text-xs font-bold uppercase tracking-[0.1em] text-spire-primary">
                    {llmRunStatus.title}
                  </span>
                </div>
                <p className="font-telemetry text-sm leading-snug text-spire-primary/90">
                  {llmRunStatus.message}
                </p>
              </div>
            )}

            {agentForRail?.pending_approval ? (
              <div className="flex shrink-0 flex-col gap-2 rounded-md border-2 border-spire-warning/60 bg-spire-canvas p-2 shadow-sm">
                <span className="font-console text-xs font-semibold uppercase tracking-[0.12em] text-spire-warning">
                  Awaiting approval
                </span>
                <div className="space-y-1 rounded-md border-2 border-spire-border-subtle bg-spire-canvas px-2 py-1.5 font-telemetry text-sm font-medium text-spire-primary">
                  {hitlQueuedSteps.length === 0 ? (
                    <div className="text-xs font-semibold text-spire-primary">—</div>
                  ) : (
                    hitlQueuedSteps.map((line, i) => (
                      <div
                        key={`${i}-${line}`}
                        className="flex gap-2 leading-snug"
                      >
                        <span className="w-5 shrink-0 text-right font-mono text-xs text-spire-label">
                          {fmtIntEn(i + 1)}.
                        </span>
                        <span className="min-w-0 flex-1 font-semibold tracking-wide text-spire-primary">
                          {line}
                        </span>
                      </div>
                    ))
                  )}
                </div>
                <p className="font-telemetry text-xs leading-snug text-spire-label">
                  {hitlReadOnly
                    ? "Replay: view only (approve/reject/edit inactive)."
                    : "Approve runs the first queued command; reject cancels this proposal."}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    className={osdBtnApprove}
                    disabled={hitlReadOnly}
                    title={
                      hitlReadOnly ? "Replay: actions disabled" : undefined
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
                      hitlReadOnly ? "Replay: actions disabled" : undefined
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
                    className="font-telemetry h-8 min-h-8 min-w-0 flex-1 rounded-md border-2 border-spire-border-subtle bg-spire-canvas px-2 py-1 text-sm font-medium leading-tight text-spire-primary shadow-sm outline-none focus-visible:border-spire-secondary focus-visible:ring-2 focus-visible:ring-spire-ring-focus/35 disabled:cursor-not-allowed disabled:opacity-50"
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
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border-2 border-spire-border-muted bg-spire-canvas shadow-sm">
                <div className="flex shrink-0 items-center justify-between gap-2 border-b-2 border-spire-border-muted bg-spire-canvas px-2 py-1.5">
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
                  className="font-telemetry custom-scroll min-h-0 flex-1 resize-none border-0 bg-transparent p-3 text-sm font-medium leading-relaxed text-spire-primary outline-none"
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
                      return "AI disabled or no API — enable LLM in agent config for raw output here.";
                    }
                    return "Raw model output from agent trace when available.";
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
      {deckInspectOpen ? (
        <PileInspectModal
          title="Master deck"
          cards={masterDeck}
          onClose={() => setDeckInspectOpen(false)}
        />
      ) : null}
    </div>
  );
}
