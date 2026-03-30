import { useMemo, useState, type ReactNode } from "react";

import { cardNameClass } from "../../lib/cardTypeStyle";
import { fmtGameStatDisplay, fmtIntEn } from "../../lib/formatDisplayNumber";
import type { GameScreenDTO, ViewModelDTO } from "../../types/viewModel";
import { MapView, type MapVizData } from "./MapView";

const strip =
  "flex shrink-0 items-center border-b border-slate-700/85 bg-slate-800/95 px-3 py-2 font-console text-sm font-semibold uppercase tracking-[0.12em] text-slate-300";

const optionBase =
  "w-full max-w-xl rounded border border-slate-700 bg-slate-800/60 px-3 py-2.5 text-left font-telemetry text-sm text-slate-200 transition hover:border-sky-600/70 hover:bg-slate-800/90 disabled:cursor-not-allowed disabled:opacity-45";

function cardDesc(card: Record<string, unknown>): string {
  const raw = card.description;
  if (typeof raw === "string" && raw.trim()) return raw.trim();
  const kb = card.kb as Record<string, unknown> | undefined;
  const d =
    kb && typeof kb.description === "string" ? kb.description.trim() : "";
  return d || "—";
}

function CardPickTile({
  card,
  onPick,
  footer,
}: {
  card: Record<string, unknown>;
  onPick: () => void;
  footer?: ReactNode;
}) {
  const up = Number(card.upgrades) > 0 ? "+" : "";
  const typeHint = String(card.type ?? "").trim();
  return (
    <button
      type="button"
      onClick={onPick}
      title={typeHint ? `Type: ${typeHint}` : undefined}
      className="relative flex min-h-[4.5rem] w-[9.5rem] shrink-0 flex-col rounded border border-slate-700 bg-slate-900/90 p-2 text-left shadow-sm transition hover:border-sky-600/80 hover:bg-slate-800/90"
    >
      <span className="absolute top-1.5 right-1.5 flex h-5 min-w-[1.25rem] items-center justify-center rounded bg-sky-700 px-1 font-console text-[10px] font-bold text-white">
        {fmtGameStatDisplay(card.cost ?? "—")}
      </span>
      <span className={`pr-6 text-sm leading-tight ${cardNameClass(card.type)}`}>
        {String(card.name ?? "?")}
        {up}
      </span>
      <span className="mt-1 line-clamp-4 border-t border-slate-800 pt-1 text-xs leading-snug text-slate-400">
        {cardDesc(card)}
      </span>
      {footer ? (
        <div className="mt-auto border-t border-slate-800 pt-1 text-center font-console text-xs font-semibold text-sky-400">
          {footer}
        </div>
      ) : null}
    </button>
  );
}

function asStr(v: unknown): string {
  return v == null ? "" : String(v);
}

export function GameScreenPanel({
  vm,
  onChoose,
}: {
  vm: ViewModelDTO;
  onChoose: (command: string) => void;
}) {
  const screen: GameScreenDTO | null | undefined = vm.screen;
  const [rawOpen, setRawOpen] = useState(false);

  const map = vm.map as MapVizData | null | undefined;

  /** Single human-readable line (avoid showing title + raw type side by side). */
  const title = useMemo(() => {
    const t = screen?.title?.trim();
    if (t) return t;
    const ty = screen?.type?.trim();
    return ty ? ty.replace(/_/g, " ") : "Screen";
  }, [screen?.title, screen?.type]);

  const content = screen?.content ?? {};
  const type = String(screen?.type ?? "");

  const body = (() => {
    switch (type) {
      case "MAP": {
        const posLabel = asStr(content.current_pos_label);
        const bossAvail = Boolean(
          content.boss_available ?? map?.boss_available,
        );
        return (
          <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden p-3">
            <div className="shrink-0 font-console text-xs font-medium text-sky-400/95">
              {posLabel || "Selecting first node"}
            </div>
            <div className="min-h-0 flex-1 overflow-auto">
              <MapView
                mapData={map}
                onChoose={onChoose}
                bossAvailable={bossAvail}
              />
            </div>
            {bossAvail ? (
              <button
                type="button"
                className="shrink-0 rounded border border-red-800/80 bg-red-950/50 py-2 font-console text-sm font-semibold uppercase tracking-wide text-red-100 hover:bg-red-900/60"
                onClick={() => onChoose("choose boss")}
              >
                Challenge Boss
              </button>
            ) : null}
          </div>
        );
      }

      case "EVENT": {
        const opts = (content.options as Record<string, unknown>[]) ?? [];
        return (
          <div className="custom-scroll min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
              {asStr(content.body_text)}
            </p>
            <div className="font-console text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
              Options
            </div>
            <div className="flex max-w-xl flex-col gap-2">
              {opts.map((o, i) => {
                const dis = Boolean(o.disabled);
                const idx = o.choice_index ?? i;
                return (
                  <button
                    key={i}
                    type="button"
                    disabled={dis}
                    className={optionBase}
                    onClick={() => onChoose(`choose ${idx}`)}
                  >
                    <div className="font-semibold text-slate-100">
                      {asStr(o.label)}
                    </div>
                    <div className="mt-1 text-sm text-slate-500">
                      {asStr(o.text)}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        );
      }

      case "COMBAT_REWARD": {
        const rewards =
          (content.rewards as Record<string, unknown>[]) ?? [];
        return (
          <div className="custom-scroll min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            <div className="grid max-w-xl gap-2">
              {rewards.map((r, i) => {
                const idx = r.choice_index ?? i;
                const rkb = r.relic_kb as Record<string, unknown> | undefined;
                return (
                  <button
                    key={i}
                    type="button"
                    className={optionBase}
                    onClick={() => onChoose(`choose ${idx}`)}
                  >
                    <div>{asStr(r.label)}</div>
                    {rkb && asStr(rkb.description) ? (
                      <div className="mt-1 text-xs text-slate-500">
                        {asStr(rkb.description)}
                      </div>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>
        );
      }

      case "CARD_REWARD": {
        const cards = (content.cards as Record<string, unknown>[]) ?? [];
        return (
          <div className="custom-scroll min-h-0 flex-1 overflow-y-auto p-3">
            <div className="flex flex-wrap justify-center gap-4 py-2">
              {cards.map((card, i) => (
                <CardPickTile
                  key={i}
                  card={card}
                  onPick={() => onChoose(`choose ${i}`)}
                />
              ))}
            </div>
          </div>
        );
      }

      case "REST": {
        const restOpts =
          (content.rest_options as Record<string, unknown>[]) ?? [];
        return (
          <div className="custom-scroll min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            <div className="mx-auto grid max-w-xl gap-2">
              {restOpts.map((o, i) => (
                <button
                  key={i}
                  type="button"
                  className={optionBase}
                  onClick={() =>
                    onChoose(`choose ${asStr(o.choice_name)}`)
                  }
                >
                  <div className="font-semibold text-slate-100">
                    {asStr(o.label)}
                  </div>
                  <div className="mt-1 text-sm text-slate-500">
                    {asStr(o.description)}
                  </div>
                </button>
              ))}
            </div>
          </div>
        );
      }

      case "GRID":
      case "HAND_SELECT": {
        const cards = (content.cards as Record<string, unknown>[]) ?? [];
        const num = Number(content.num_cards ?? 1) || 1;
        const reason =
          type === "HAND_SELECT" ? asStr(content.screen_reason) : "";
        return (
          <div className="custom-scroll min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
            {reason ? (
              <p className="text-sm text-slate-400">{reason}</p>
            ) : null}
            <p className="font-semibold text-sky-400/95">
              Pick {fmtIntEn(num)} card(s)
            </p>
            <div className="flex flex-wrap gap-3">
              {cards.map((card, i) => (
                <CardPickTile
                  key={i}
                  card={card}
                  onPick={() => onChoose(`choose ${i}`)}
                />
              ))}
            </div>
          </div>
        );
      }

      case "SHOP_ROOM": {
        const choices = (content.choices as unknown[]) ?? [];
        return (
          <div className="custom-scroll min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            <div className="mx-auto grid max-w-sm gap-2">
              {choices.map((ch, i) => {
                const s = asStr(ch);
                const label =
                  s.length > 0
                    ? s.charAt(0).toUpperCase() + s.slice(1)
                    : s;
                return (
                  <button
                    key={i}
                    type="button"
                    className={optionBase}
                    onClick={() => onChoose(`choose ${s}`)}
                  >
                    <span className="text-lg font-bold">{label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        );
      }

      case "SHOP_SCREEN": {
        const gold = content.gold;
        const shopCards =
          (content.shop_cards as Record<string, unknown>[]) ?? [];
        const shopRelics =
          (content.shop_relics as Record<string, unknown>[]) ?? [];
        const shopPotions =
          (content.shop_potions as Record<string, unknown>[]) ?? [];
        const purge = Boolean(content.purge_available);
        const purgeCost = content.purge_cost;
        return (
          <div className="custom-scroll min-h-0 flex-1 space-y-5 overflow-y-auto p-3">
            <div className="font-telemetry text-sm font-semibold text-amber-200/95">
              Gold:{" "}
              {gold === undefined || gold === null
                ? "?"
                : fmtGameStatDisplay(gold)}
            </div>
            <div>
              <h3 className="mb-2 font-console text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                Cards
              </h3>
              <div className="flex flex-wrap gap-3">
                {shopCards.map((card, i) => (
                  <CardPickTile
                    key={i}
                    card={card}
                    onPick={() =>
                      onChoose(`choose ${asStr(card.name)}`)
                    }
                    footer={
                      <span>{fmtGameStatDisplay(asStr(card.price) || "—")} Gold</span>
                    }
                  />
                ))}
              </div>
            </div>
            <div>
              <h3 className="mb-2 font-console text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                Relics
              </h3>
              <div className="flex flex-wrap gap-2">
                {shopRelics.map((r, i) => {
                  const kb = r.kb as Record<string, unknown> | undefined;
                  return (
                    <button
                      key={i}
                      type="button"
                      className={`${optionBase} max-w-[14rem] flex-1`}
                      onClick={() => onChoose(`choose ${asStr(r.name)}`)}
                    >
                      <div className="font-semibold">{asStr(r.name)}</div>
                      {kb && asStr(kb.description) ? (
                        <div className="mt-1 text-xs text-slate-500">
                          {asStr(kb.description)}
                        </div>
                      ) : null}
                      <div className="mt-1 font-mono text-sky-400">
                        {fmtGameStatDisplay(asStr(r.price) || "—")} Gold
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
            <div>
              <h3 className="mb-2 font-console text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                Potions
              </h3>
              <div className="flex flex-wrap gap-2">
                {shopPotions.map((p, i) => (
                  <button
                    key={i}
                    type="button"
                    className={`${optionBase} max-w-[14rem] flex-1`}
                    onClick={() => onChoose(`choose ${asStr(p.name)}`)}
                  >
                    <div className="font-semibold">{asStr(p.name)}</div>
                    <div className="mt-1 font-mono text-sky-400">
                      {fmtGameStatDisplay(asStr(p.price) || "—")} Gold
                    </div>
                  </button>
                ))}
              </div>
            </div>
            {purge ? (
              <button
                type="button"
                className="max-w-md rounded border border-red-800/80 bg-red-950/45 py-2 font-console text-sm font-semibold text-red-100 hover:bg-red-900/55"
                onClick={() => onChoose("choose purge")}
              >
                Remove Card (
                {purgeCost === undefined || purgeCost === null
                  ? "?"
                  : fmtGameStatDisplay(purgeCost)}{" "}
                Gold)
              </button>
            ) : null}
          </div>
        );
      }

      case "CHEST":
        return (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-6">
            <p className="text-slate-400">{asStr(content.chest_type) || "Chest"}</p>
            <button
              type="button"
              className="w-full max-w-sm rounded border border-sky-800/80 bg-sky-950/60 py-2 font-console text-sm font-semibold text-sky-100 hover:bg-sky-900/75"
              onClick={() => onChoose("choose open")}
            >
              Open Chest
            </button>
          </div>
        );

      case "BOSS_REWARD": {
        const relics = (content.relics as Record<string, unknown>[]) ?? [];
        return (
          <div className="custom-scroll min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            <div className="mx-auto grid max-w-xl gap-2">
              {relics.map((r, i) => {
                const kb = r.kb as Record<string, unknown> | undefined;
                return (
                  <button
                    key={i}
                    type="button"
                    className={optionBase}
                    onClick={() => onChoose(`choose ${asStr(r.name)}`)}
                  >
                    <div className="font-semibold">{asStr(r.name)}</div>
                    {kb && asStr(kb.description) ? (
                      <div className="mt-1 text-xs text-slate-500">
                        {asStr(kb.description)}
                      </div>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>
        );
      }

      case "GAME_OVER":
        return (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
            <div className="font-console text-2xl font-bold text-slate-100">
              {content.victory ? "Victory!" : "Defeated"}
            </div>
            <div className="text-slate-500">
              Score: {fmtGameStatDisplay(content.score ?? 0)}
            </div>
          </div>
        );

      case "COMPLETE":
        return (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
            <div className="font-console text-xl font-bold text-emerald-300/95">
              Run complete
            </div>
            <p className="text-sm text-slate-500">
              {title.replace(/_/g, " ")}
            </p>
          </div>
        );

      default: {
        const choices = (content.choices as unknown[]) ?? [];
        const raw = content.raw_screen_state;
        if (choices.length > 0) {
          return (
            <div className="custom-scroll min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
              <div className="mx-auto grid max-w-xl gap-2">
                {choices.map((ch, i) => (
                  <button
                    key={i}
                    type="button"
                    className={optionBase}
                    onClick={() => onChoose(`choose ${i}`)}
                  >
                    {asStr(ch)}
                  </button>
                ))}
              </div>
            </div>
          );
        }
        return (
          <div className="custom-scroll min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            <p className="text-sm italic text-slate-500">
              No choices available for this screen type ({type || "unknown"}).
            </p>
            {raw !== undefined ? (
              <div className="mt-2">
                <button
                  type="button"
                  className="font-console text-xs text-sky-400 hover:underline"
                  onClick={() => setRawOpen((v) => !v)}
                >
                  {rawOpen ? "Hide" : "Show"} raw screen state
                </button>
                {rawOpen ? (
                  <pre className="mt-2 max-h-48 overflow-auto rounded border border-slate-800 bg-slate-950/80 p-2 font-mono text-[11px] text-slate-400">
                    {JSON.stringify(raw, null, 2)}
                  </pre>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      }
    }
  })();

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-slate-900/40">
      <div className={strip} title={type ? `Screen type: ${type}` : undefined}>
        <span className="min-w-0 flex-1 truncate">{title}</span>
      </div>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {body}
      </div>
    </div>
  );
}
