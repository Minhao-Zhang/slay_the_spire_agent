/**
 * KB text extraction aligned with `src/ui/state_processor.py` enrich shapes
 * (`relic.kb.description`, `potion.kb.effect`, `power.kb.effect|type|stacks`) and
 * with `src/agent/prompt_builder.py` / tactical preview lines for the LLM.
 */

function compactSnippet(text: string, limit: number): string {
  const cleaned = (text || "").split(/\s+/).join(" ").trim();
  if (!cleaned) return "";
  if (cleaned.length <= limit) return cleaned;
  return `${cleaned.slice(0, limit - 3).trimEnd()}...`;
}

/** In-run stack / intensity from CommunicationMod (`amount`); optional legacy top-level `stacks` number. */
export function powerRuntimeAmount(
  p: Record<string, unknown> | null | undefined,
): number | null {
  if (!p) return null;
  const a = p.amount;
  if (typeof a === "number" && Number.isFinite(a)) return a;
  if (typeof a === "string" && a.trim() !== "") {
    const n = Number(a.trim().replace(/,/g, ""));
    if (Number.isFinite(n)) return n;
  }
  const s = p.stacks;
  if (typeof s === "number" && Number.isFinite(s)) return s;
  return null;
}

/** Chip text: `Name (N)` when a runtime amount exists; `*` when `just_applied` (Slay debuff UX). */
export function powerChipLabel(p: Record<string, unknown>): string {
  const name = String(p.name ?? "?");
  const n = powerRuntimeAmount(p);
  const base = n != null ? `${name} (${n})` : name;
  return p.just_applied === true ? `${base} *` : base;
}

function powerTooltipLead(obj: Record<string, unknown>): string {
  const n = powerRuntimeAmount(obj);
  const ja = obj.just_applied === true;
  if (n != null && ja) return `Amount: ${n} (just applied this turn)\n\n`;
  if (n != null) return `Amount: ${n}\n\n`;
  if (ja) return "Just applied this turn\n\n";
  return "";
}

function isPowerTooltipCandidate(obj: Record<string, unknown>): boolean {
  return (
    powerRuntimeAmount(obj) != null ||
    obj.just_applied === true ||
    (obj.name != null &&
      obj.kb != null &&
      typeof obj.kb === "object" &&
      !Array.isArray(obj.kb) &&
      typeof (obj.kb as Record<string, unknown>).effect === "string")
  );
}

export type EntityTooltipOptions = {
  /** When true, omit the `Amount: N` lead (e.g. chip title already shows it via powerChipLabel). */
  skipPowerAmountLead?: boolean;
};

/** Plain-text tooltip body from KB / projection fields. */
export function entityTooltip(
  obj: Record<string, unknown> | null | undefined,
  opts?: EntityTooltipOptions,
): string {
  if (!obj) return "";
  const lead =
    !opts?.skipPowerAmountLead && isPowerTooltipCandidate(obj)
      ? powerTooltipLead(obj)
      : "";

  const direct =
    obj.description ?? obj.text ?? obj.body_text ?? obj.help;
  if (typeof direct === "string" && direct.trim())
    return lead + direct.trim();

  const kb = obj.kb;
  if (kb && typeof kb === "object" && !Array.isArray(kb)) {
    const k = kb as Record<string, unknown>;
    const cardRelicDesc =
      typeof k.description === "string" && k.description.trim()
        ? k.description.trim()
        : "";
    const effect =
      typeof k.effect === "string" && k.effect.trim() ? k.effect.trim() : "";
    const powType =
      typeof k.type === "string" && k.type.trim() ? k.type.trim() : "";
    const kbStacks =
      typeof k.stacks === "string" && k.stacks.trim() ? k.stacks.trim() : "";

    const kbLines: string[] = [];
    if (cardRelicDesc) kbLines.push(cardRelicDesc);
    if (powType) kbLines.push(powType);
    if (kbStacks) kbLines.push(`Stacks: ${kbStacks}`);
    if (effect) kbLines.push(effect);
    if (kbLines.length) {
      return lead + kbLines.join("\n\n");
    }

    const parts: string[] = [];
    if (k.general) parts.push(String(k.general));
    if (k.notes) parts.push(String(k.notes));
    if (k.ai) parts.push(`AI: ${k.ai}`);
    if (k.hp_range) parts.push(`HP range: ${k.hp_range}`);
    if (Array.isArray(k.moves)) parts.push(`Moves: ${k.moves.join(", ")}`);
    if (parts.length) return lead + parts.join("\n\n");
  }
  if (lead.trim()) return lead.trim();
  return "";
}

export function labeledTooltip(
  name: string,
  obj: Record<string, unknown>,
  opts?: EntityTooltipOptions,
): string {
  const t = entityTooltip(obj, opts);
  if (t) return `${name}\n\n${t}`;
  return name.trim() ? name : "";
}

export function monsterTooltip(m: Record<string, unknown>): string {
  const name = String(m.name ?? "?");
  const body = entityTooltip(m);
  if (body) return `${name}\n\n${body}`;
  const intent = m.intent_display ? String(m.intent_display) : "";
  const powers = (m.powers as Record<string, unknown>[] | undefined) ?? [];
  const pStr = powers.length
    ? powers
        .map((p) => {
          const label = powerChipLabel(p);
          const d = entityTooltip(p, { skipPowerAmountLead: true });
          return d ? `${label} — ${d}` : label;
        })
        .join("\n")
    : "";
  return [name, intent, pStr].filter(Boolean).join("\n");
}

/** One relic row for tactical / LLM-style state summaries (matches prompt_builder intent). */
export function relicLlmLine(relic: Record<string, unknown>): string {
  const name = String(relic.name ?? "?");
  const kb = (relic.kb as Record<string, unknown> | undefined) ?? {};
  const desc = typeof kb.description === "string" ? kb.description : "";
  if (desc) return `${name} | desc=${compactSnippet(desc, 200)}`;
  return name;
}

export function potionLlmLine(
  idx: number,
  potion: Record<string, unknown>,
): string {
  const kb = (potion.kb as Record<string, unknown> | undefined) ?? {};
  const effect = typeof kb.effect === "string" ? kb.effect : "";
  const name = String(potion.name ?? "?");
  if (effect)
    return `${idx}. ${name} | effect=${compactSnippet(effect, 120)}`;
  return `${idx}. ${name}`;
}

export function powerLlmLine(power: Record<string, unknown>): string {
  const name = String(power.name ?? "?");
  const n = powerRuntimeAmount(power);
  const amountStr = n != null ? String(n) : "?";
  const kb = (power.kb as Record<string, unknown> | undefined) ?? {};
  const effect = typeof kb.effect === "string" ? kb.effect : "";
  const pType =
    typeof kb.type === "string" && kb.type.trim() ? kb.type.trim() : "";
  const parts: string[] = [`${name}(${amountStr})`];
  if (pType) parts.push(`type=${pType}`);
  if (effect) parts.push(`effect=${compactSnippet(effect, 120)}`);
  return parts.join(" | ");
}
