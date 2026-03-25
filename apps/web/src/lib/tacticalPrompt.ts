/**
 * Mirrors `src/agent_core/pipeline.py` + `state_prompt.py`: same user/system
 * tactical prompt the LLM receives (KB-enriched state + legal actions).
 */

import type { ViewModelDTO } from "../types/viewModel";

function compactText(text: string, limit = 160): string {
  const cleaned = (text || "").split(/\s+/).join(" ").trim();
  if (!cleaned) return "";
  if (cleaned.length <= limit) return cleaned;
  return `${cleaned.slice(0, limit - 3).trimEnd()}...`;
}

function cardLine(card: Record<string, unknown>, index: number, showToken: boolean): string {
  const parts: string[] = [`${index}. ${String(card.name ?? "?")}`];
  if (card.cost != null) parts.push(`cost=${String(card.cost)}`);
  if (card.upgrades) parts.push(`upgrades=${String(card.upgrades)}`);
  if (card.has_target) parts.push("targeted");
  if (card.is_playable === false) parts.push("unplayable");
  if (showToken) {
    const u = String(card.uuid ?? "");
    const token = u.length >= 6 ? u.slice(0, 6) : "";
    if (token) parts.push(`token=${token}`);
  }
  const kb = (card.kb as Record<string, unknown> | undefined) ?? {};
  const desc = kb.description;
  if (typeof desc === "string" && desc)
    parts.push(`desc=${desc}`);
  return parts.join(" | ");
}

function powerLine(power: Record<string, unknown>): string {
  const name = String(power.name ?? "?");
  const amount = String(power.amount ?? "?");
  const kb = (power.kb as Record<string, unknown> | undefined) ?? {};
  const effect = kb.effect;
  if (typeof effect === "string" && effect)
    return `${name}(${amount}) | effect=${compactText(effect, 120)}`;
  return `${name}(${amount})`;
}

function monsterLine(monster: Record<string, unknown>, index: number): string {
  const parts = [
    `${index}. ${String(monster.name ?? "?")}`,
    `hp=${String(monster.hp_display ?? "?")}`,
    `block=${String(monster.block ?? 0)}`,
    `intent=${String(monster.intent_display ?? monster.intent ?? "?")}`,
  ];
  const powers = (monster.powers as Record<string, unknown>[] | undefined) ?? [];
  if (powers.length)
    parts.push(`powers=${powers.map((p) => powerLine(p)).join("; ")}`);
  const kb = (monster.kb as Record<string, unknown> | undefined) ?? {};
  const moves = kb.moves;
  if (Array.isArray(moves) && moves.length)
    parts.push(`known_moves=${moves.slice(0, 3).map(String).join(", ")}`);
  if (kb.notes) parts.push(`notes=${compactText(String(kb.notes))}`);
  if (kb.ai) parts.push(`ai=${compactText(String(kb.ai))}`);
  return parts.join(" | ");
}

function relicLine(relic: Record<string, unknown>): string {
  const kb = (relic.kb as Record<string, unknown> | undefined) ?? {};
  const desc = kb.description;
  if (typeof desc === "string" && desc)
    return `${String(relic.name ?? "?")} | desc=${desc}`;
  return String(relic.name ?? "?");
}

function potionLine(idx: number, potion: Record<string, unknown>): string {
  const kb = (potion.kb as Record<string, unknown> | undefined) ?? {};
  const effect = kb.effect;
  const name = String(potion.name ?? "?");
  if (typeof effect === "string" && effect)
    return `${idx}. ${name} | effect=${compactText(effect, 120)}`;
  return `${idx}. ${name}`;
}

function tacticalStateSummary(vm: ViewModelDTO): string {
  const lines: string[] = [];
  const h = (vm.header ?? {}) as Record<string, unknown>;
  lines.push(
    `class=${h.class ?? "?"} floor=${h.floor ?? "?"} hp=${h.hp_display ?? "?"} gold=${h.gold ?? "?"} energy=${h.energy ?? "?"} turn=${h.turn ?? "?"}`,
  );

  const inv = (vm.inventory ?? {}) as Record<string, unknown>;
  const relics = inv.relics as Record<string, unknown>[] | undefined;
  if (relics?.length) {
    lines.push("relics:");
    for (const r of relics) lines.push(`  - ${relicLine(r)}`);
  }
  const potions = inv.potions as Record<string, unknown>[] | undefined;
  if (potions?.length) {
    lines.push("potions:");
    potions.forEach((p, i) => lines.push(`  - ${potionLine(i + 1, p)}`));
  }

  const com = vm.combat as Record<string, unknown> | null | undefined;
  if (com) {
    lines.push(`player_block=${String(com.player_block ?? 0)}`);
    const pws = com.player_powers as Record<string, unknown>[] | undefined;
    if (pws?.length) {
      lines.push("player_powers:");
      for (const pw of pws) lines.push(`  - ${powerLine(pw)}`);
    }
    const hand = com.hand as Record<string, unknown>[] | undefined;
    if (hand?.length) {
      lines.push("hand:");
      hand.forEach((c, i) => lines.push(`  - ${cardLine(c, i + 1, true)}`));
    }
    const monsters = com.monsters as Record<string, unknown>[] | undefined;
    if (monsters?.length) {
      lines.push("monsters:");
      let idx = 0;
      for (const m of monsters) {
        if (m.is_gone) continue;
        idx += 1;
        lines.push(`  - ${monsterLine(m, idx)}`);
      }
    }
  }

  return lines.join("\n");
}

function legalActionsSummary(vm: ViewModelDTO | null): string {
  if (!vm?.actions?.length) return "";
  return vm.actions
    .map((a) =>
      JSON.stringify({
        label: a.label ?? a.command ?? "?",
        command: a.command ?? "",
      }),
    )
    .join("\n");
}

const TACTICAL_SYSTEM = `You are a Slay the Spire tactical agent. Reply with a single JSON object only, no markdown, with keys "command" (string, must be exactly one of the listed command strings, or null) and "rationale" (short string).`;

export function buildTacticalPrompt(vm: ViewModelDTO | null): {
  system: string;
  user: string;
} {
  const rows = legalActionsSummary(vm);
  const stateBlock = vm ? tacticalStateSummary(vm) : "";
  const user =
    `Current state (KB-enriched descriptions in hand / monsters / relics / potions / powers):\n${stateBlock}\n\n` +
    `Legal actions (use the exact "command" string):\n${rows}\n\n` +
    `Respond with: {"command": "...", "rationale": "..."}`;
  return { system: TACTICAL_SYSTEM, user };
}
