---
tags: []
---

# Sources & verification (not retrieved into prompts)

Expert guide bodies in this folder are **short paraphrases**. Below: **what we treat as credible** and **where key claims were cross-checked** (Firecrawl MCP web research, February 2026).

## Source tiers

1. **[Slay the Spire Wiki (Fandom)](https://slay-the-spire.fandom.com/wiki/Slay_the_Spire_Wiki)** — Large community wiki with enemy patterns, tips, and datamine-aligned intent text. **Primary verifier** for mechanics (attacks, buffs, boss tips).
2. **[Slay the Spire Wiki (wiki.gg)](https://slaythespire.wiki.gg/)** — Another wiki mirror; useful **second read** on boss pages (e.g. Hexaghost).
3. **[slaythespire.gg guides](https://slaythespire.gg/guides/strategy)** — Long-form strategy synthesis; **community opinion**, not official. Aligned with wiki on many points; use for heuristics, not raw numbers.
4. **Reddit / Steam** — **Tertiary**: good for “player consensus” and worked examples when they **repeat the same formula** as the wiki (e.g. Hexaghost Divider math).

Official game text + in-game intents remain the ground truth if a patch changes numbers.

## Topic → where it’s supported

| Topic | Multi-source? | Notes |
| --- | --- | --- |
| **Neow’s Lament (first 3 combats, enemies at 1 HP)** applies to normal / elite / boss | **Yes** | [Neow's Lament](https://slay-the-spire.fandom.com/wiki/Neow%27s_Lament), [Gameplay](https://slay-the-spire.fandom.com/wiki/Gameplay); Reddit/Steam discuss elite sniping with it. |
| **Gremlin Nob** punishes **Skills** (Rage / Strength) | **Yes** | [Gremlin Nob](https://slay-the-spire.fandom.com/wiki/Gremlin_Nob), [Strength](https://slay-the-spire.fandom.com/wiki/Strength) wiki pages. |
| **Hexaghost Divider**: damage tied to **current HP** formula | **Yes** | [Hexaghost](https://slay-the-spire.fandom.com/wiki/Hexaghost) states *(H+1)×6* with *H = floor(current HP/12)*; [wiki.gg Hexaghost](https://slaythespire.wiki.gg/wiki/Hexaghost); Reddit threads echo the formula. |
| **Time Eater** ends turn after **12 cards**; gains Strength | **Yes** | [Time Eater](https://slay-the-spire.fandom.com/wiki/Time_Eater) wiki; broad community discussion. |
| **Book of Stabbing** adds **Wounds** on unblocked hits | **Yes** | [Book of Stabbing](https://slay-the-spire.fandom.com/wiki/Book_of_Stabbing), [Painful Stabs](https://slay-the-spire.fandom.com/wiki/Painful_Stabs). |
| **Awakened One** gains Strength when you play **Powers** (phase 1) | **Yes** | [Buffs](https://slay-the-spire.fandom.com/wiki/Buffs), [Awakened One](https://slay-the-spire.fandom.com/wiki/Awakened_One). |
| **Donu & Deca** — who to focus first | **Wiki is nuanced** | Fandom **Tips**: kill **Donu** first if you **cannot out-block Circle of Power** scaling; kill **Deca** first if **Dazes** hurt low-draw decks. Not a single universal rule. |
| **Corrupt Heart** **Beat of Death** (damage per card played) | **Yes** | [Corrupt Heart](https://slay-the-spire.fandom.com/wiki/Corrupt_Heart), [Buffs](https://slay-the-spire.fandom.com/wiki/Buffs); [After Image](https://slay-the-spire.fandom.com/wiki/After_Image) tip text. |
| **Bronze Automaton** **Hyper Beam** | **Yes (mechanic name)** | [Bronze Automaton](https://slay-the-spire.fandom.com/wiki/Bronze_Automaton) wiki; **exact turn cadence** should be read from **in-game intent**, not memorized from guides. |

## Original synthesis

- [slaythespire.gg Strategy Guide](https://slaythespire.gg/guides/strategy) — Act/elite/boss **heuristics** (deckbuilding mindset, Neow options, act checks). Cross-checked against Fandom where mechanics matter; opinionated sections kept vague in our `expert_*.md` files.
