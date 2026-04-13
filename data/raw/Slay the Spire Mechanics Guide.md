# **Slay the Spire: An Exhaustive Analysis of Game Mechanics, Systems, and Strategic Frameworks**

## **Introduction to the Spire**

Developed by Mega Crit and officially released in 2019, *Slay the Spire* (Version 1\) established the foundational architecture for the modern roguelike deck-building genre.1 The objective requires the player to navigate a procedurally generated vertical labyrinth, commonly referred to as the Spire, by continuously evolving a primitive starting deck into a highly synergistic engine capable of overcoming escalating mathematical and strategic challenges.1

The structural loop operates on strict permadeath mechanics: failure results in the permanent loss of all current cards, relics, and progression, returning the player to the base of the Spire.2 Success dictates prioritizing immediate survival advantages against long-term scaling, as standard runs require traversing three primary Acts, culminating in highly lethal Boss encounters.2 Advanced completions necessitate surviving a secret fourth Act, demanding the player to acquire specific keys during the preliminary stages.4 The depth of the game lies within its interconnected systems: precise energy management, algorithmic map generation, floating-point damage modifiers, and distinct character archetypes.

## **Core Gameplay Loop and Mechanics**

The fundamental unit of interaction within the game is the turn-based combat system. The player and the opposing entities take alternating turns, with the player's options dictated by a dynamic hand of cards drawn from a primary deck.

### **Resource Management and Card Classifications**

The execution of cards is governed by Energy. Players typically begin each turn with three units of Energy, though this capacity can be expanded through specific cards, interactions, or Boss Relics.3 Cards possess individual Energy costs, ranging from zero to higher integers, and playing a card deducts from the available pool.3 At the end of the player's turn, all remaining unplayed cards in the hand are discarded into the Discard Pile, alongside the cards that were played.3 The player is permitted a maximum hand size of ten cards; any additional cards drawn while the hand is full are immediately discarded without effect.7 When the primary Draw Pile is exhausted, the Discard Pile is automatically shuffled and reinstated as the new Draw Pile, creating a continuous circulatory system.3

Cards are segmented into specific behavioral classifications that determine their function and longevity within a combat scenario:

| Card Classification | Functional Description | Strategic Role |
| :---- | :---- | :---- |
| **Attack Cards** | Deal direct numerical damage to enemies. Output is dynamically modified by status effects like Strength, Vulnerable, and Weak.6 | Primary win condition; necessitates immediate lethal calculations. |
| **Skill Cards** | Utility cards that provide defensive Block, facilitate additional card draw, or apply status effects without dealing direct damage.6 | Mitigation of incoming damage and acceleration of the deck engine. |
| **Power Cards** | Provide permanent scaling Buffs. Upon being played, they are permanently removed from the active deck for the remainder of the combat.6 | Essential for long-term survival in Boss and Elite encounters. |
| **Status Cards** | Detrimental, typically unplayable cards inserted into the player's deck by enemies. Automatically removed at the conclusion of combat.6 | Clutters the deck, artificially reducing the probability of drawing useful cards. |
| **Curse Cards** | Persistent negative cards acquired through events or specific relics. They remain in the player's permanent deck between combats.6 | Imposes a permanent mathematical disadvantage unless explicitly removed at a Merchant. |

### **Card-Specific Keywords**

To introduce nuance, cards possess keywords that explicitly define their mechanical behavior during combat.6 Ethereal dictates that if the card is retained in the player's hand at the end of the turn without being played, it is automatically Exhausted.6 The Exhaust keyword dictates that upon being played, the card is entirely removed from the circulatory deck for the remainder of the current combat.6 Innate guarantees that the card will be placed in the player's opening hand on the first turn of combat, securing predictable opening maneuvers.6 Retain overrides the standard discard rule, allowing the player to keep the specific card in their hand at the end of the turn to set up future combination attacks.6 Unplayable denotes that the card cannot be manually activated or played from the hand, characteristic of most Statuses and Curses.6

## **Mathematical Architecture: Damage Calculation and Status Effects**

Damage optimization requires an intimate understanding of the game's mathematical order of operations. The system calculates attack damage starting with base values, layering additive modifiers, followed by multiplicative negative modifiers, and finally multiplicative positive modifiers.8

Combat dynamics are heavily influenced by the application of temporary or permanent Buffs and Debuffs. The following table delineates the primary combat modifiers affecting damage and survival 6:

| Status Effect | Classification | Mathematical / Mechanical Impact |
| :---- | :---- | :---- |
| **Block** | Temporary Defense | Absorbs incoming attack damage before it affects HP. Removed at the start of the entity's next turn.6 |
| **Strength** | Additive Buff | Increases damage dealt by Attack cards by 1 point per stack. Can be negative, reducing damage.8 |
| **Dexterity** | Additive Buff | Increases the volume of Block generated by Skill cards by 1 point per stack.6 |
| **Vulnerable** | Multiplicative Debuff | Causes the afflicted entity to take exactly 50% additional damage from Attack cards.6 |
| **Weak** | Multiplicative Debuff | Reduces the damage output of the afflicted entity's Attack cards by 25%.6 |
| **Frail** | Multiplicative Debuff | Reduces the amount of Block generated by cards by 25%.6 |
| **Artifact** | Negation Buff | Acts as a shield, automatically nullifying the next Debuff applied to the entity.6 |
| **Poison** | Cumulative Debuff | Deals numerical damage directly to HP at the start of the turn, bypassing Block. Stack is then reduced by 1\.6 |
| **Barricade** | Persistent Buff | Prevents the total removal of Block at the start of a turn.10 |
| **Metallicize** | Persistent Buff | Passively generates a set amount of Block at the end of each turn.10 |

The game utilizes floating-point mathematics for its background calculations but floors (rounds down) the numbers for visual display and final application, which routinely leads to specific threshold behaviors.11 The complete formula can be represented mathematically as:

![][image1]  
Where the ![][image2] is 0.75 (reflecting a 25% reduction) and the ![][image3] is 1.5 (reflecting a 50% increase).6 For example, if a player uses a base 8 damage Attack while possessing 5 Strength, the intermediate calculation is 13\.12 If the player is Weak, the damage becomes ![][image4]. The visual display on the card will floor this value and show 9 damage.12 If the player then attacks an enemy that is Vulnerable, the calculation utilizes the retained floating-point value rather than the floored visual value. The damage dealt becomes ![][image5].12 The final result is floored prior to application, resulting in 14 true damage dealt to the enemy.12 Failing to account for this floating-point retention can result in lethal miscalculations against challenging elites or bosses.

## **Character Archetype: The Ironclad**

The Ironclad archetype is centered around Strength scaling, self-inflicted damage mechanics, and the Exhaust system. The character begins with 80 maximum HP and the *Burning Blood* starting relic, which heals 6 HP at the conclusion of every combat, sustaining highly aggressive early-game pathing.3

While the Exhaust keyword appears detrimental to novices by permanently removing cards, high-level analysis reveals it to be one of the most powerful mechanics in the game.13 Proper utilization of Exhaust allows the Ironclad to aggressively thin the deck down to single-digit card counts during combat, permanently eliminating basic efficiency blocks like *Strikes* and *Defends*.13 This ensures that high-value combo cards are drawn consistently every single turn, creating reliable, infinite, or near-infinite damage loops.13

The comprehensive inventory of Ironclad cards reveals a heavy reliance on brute force and sacrificial mechanics:

| Card Name | Rarity | Type | Cost | Effect (Upgraded parameters in parentheses) |
| :---- | :---- | :---- | :---- | :---- |
| **Bash** | Starter | Attack | 2 | Deals 8(10) damage and applies 2(3) Vulnerable. 6 |
| **Defend** | Starter | Skill | 1 | Gain 5(8) Block. 6 |
| **Strike** | Starter | Attack | 1 | Deals 6(9) damage. 6 |
| **Anger** | Common | Attack | 0 | Deals 6(8) damage; adds a copy of this card to the discard pile. 6 |
| **Armaments** | Common | Skill | 1 | Gain 5 Block; upgrade a card (ALL cards in hand) for the rest of combat. 6 |
| **Body Slam** | Common | Attack | 1(0) | Deals damage equal to your current Block. 6 |
| **Clash** | Common | Attack | 0 | Deals 14(18) damage; can only be played if every card in hand is an Attack. 6 |
| **Cleave** | Common | Attack | 1 | Deals 8(11) damage to ALL enemies. 6 |
| **Clothesline** | Common | Attack | 2 | Deals 12(14) damage; applies 2(3) Weak. 6 |
| **Flex** | Common | Skill | 0 | Gain 2(4) Strength; at the end of turn, lose 2(4) Strength. 6 |
| **Havoc** | Common | Skill | 1(0) | Play the top card of your draw pile and Exhaust it. 6 |
| **Headbutt** | Common | Attack | 1 | Deals 9(12) damage; place a card from discard pile on top of draw pile. 6 |
| **Heavy Blade** | Common | Attack | 2 | Deals 14 damage; Strength affects this card 3(5) times. 6 |
| **Iron Wave** | Common | Attack | 1 | Gain 5(7) Block and deal 5(7) damage. 6 |
| **Perfected Strike** | Common | Attack | 2 | Deals 6 damage plus 2(3) damage for ALL cards containing "Strike". 6 |
| **Pommel Strike** | Common | Attack | 1 | Deals 9(10) damage; draw 1(2) card(s). 6 |
| **Shrug it Off** | Common | Skill | 1 | Gain 8(11) Block and draw 1 card. 6 |
| **Sword Boomerang** | Common | Attack | 1 | Deals 3 damage to a random enemy 3(4) times. 6 |
| **Thunderclap** | Common | Attack | 1 | Deals 4(7) damage; applies 1 Vulnerable to ALL enemies. 6 |
| **True Grit** | Common | Skill | 1 | Gain 7(9) Block; Exhaust a random (chosen) card from your hand. 6 |
| **Twin Strike** | Common | Attack | 1 | Deals 5(7) damage twice. 6 |
| **Warcry** | Common | Skill | 0 | Draw 1(2) card(s), place a card from hand on top of draw pile. Exhaust. 6 |
| **Wild Strike** | Common | Attack | 1 | Deals 12(17) damage; shuffles a Wound into your draw pile. 6 |
| **Battle Trance** | Uncommon | Skill | 0 | Draw 3(4) cards; you cannot draw additional cards this turn. 6 |
| **Blood for Blood** | Uncommon | Attack | 4(3) | Costs 1 less energy for each time you lose HP in combat. Deals 18(22) damage. 6 |
| **Bloodletting** | Uncommon | Skill | 0 | Lose 3 HP and gain 2(3) Energy. 6 |
| **Burning Pact** | Uncommon | Skill | 1 | Exhaust 1 card and draw 2(3) cards. 6 |
| **Carnage** | Uncommon | Attack | 2 | Deals 20(28) damage. Ethereal. 6 |
| **Combust** | Uncommon | Power | 1 | At the end of turn, lose 1 HP and deal 5(7) damage to ALL enemies. 6 |
| **Dark Embrace** | Uncommon | Power | 2(1) | Whenever a card is Exhausted, draw 1 card. 6 |
| **Disarm** | Uncommon | Skill | 1 | Enemy loses 2(3) Strength. Exhaust. 6 |
| **Dropkick** | Uncommon | Attack | 1 | Deals 5(8) damage. If enemy is Vulnerable, gain 1 energy and draw 1 card. 6 |
| **Dual Wield** | Uncommon | Skill | 1 | Create 1(2) copy of an Attack or Power card in your hand. 6 |
| **Entrench** | Uncommon | Skill | 2(1) | Double your current Block. 6 |
| **Evolve** | Uncommon | Power | 1 | Whenever you draw a Status card, draw 1(2) card(s). 6 |
| **Feel No Pain** | Uncommon | Power | 1 | Whenever a card is Exhausted, gain 3(4) Block. 6 |
| **Fire Breathing** | Uncommon | Power | 1 | Whenever you draw a Status or Curse, deal 6(10) damage to ALL enemies. 6 |
| **Flame Barrier** | Uncommon | Skill | 2 | Gain 12(16) Block. Whenever attacked this turn, deal 4(6) damage to attacker. 6 |
| **Ghostly Armor** | Uncommon | Skill | 1 | Gain 10(13) Block. Ethereal. 6 |
| **Hemokinesis** | Uncommon | Attack | 1 | Lose 2 HP and deal 15(20) damage. 6 |
| **Infernal Blade** | Uncommon | Skill | 1(0) | Add a random Attack to your hand that costs 0 for the turn. Exhaust. 6 |
| **Inflame** | Uncommon | Power | 1 | Gain 2(3) Strength. 6 |
| **Intimidate** | Uncommon | Skill | 0 | Apply 1(2) Weak to ALL enemies. Exhaust. 6 |
| **Metallicize** | Uncommon | Power | 1 | At the end of your turn, gain 3(4) Block. 6 |
| **Power Through** | Uncommon | Skill | 1 | Add 2 Wounds to your hand and gain 15(20) Block. 6 |
| **Pummel** | Uncommon | Attack | 1 | Deal 2 damage 4(5) times. Exhaust. 6 |
| **Rage** | Uncommon | Skill | 0 | Whenever you play an Attack this turn, gain 3(5) Block. 6 |
| **Rampage** | Uncommon | Attack | 1 | Deal 8 damage; increase this card's damage by 5(8) for the rest of combat. 6 |
| **Reckless Charge** | Uncommon | Attack | 0 | Deal 7(10) damage; shuffle a Dazed into your draw pile. 6 |
| **Rupture** | Uncommon | Power | 1 | Whenever you lose HP from a card, gain 1(2) Strength. 6 |
| **Searing Blow** | Uncommon | Attack | 2 | Deals 12(16) damage; can be upgraded any number of times. 6 |
| **Second Wind** | Uncommon | Skill | 1 | Exhaust all non-Attack cards in hand; gain 5(7) Block for each card Exhausted. 6 |
| **Seeing Red** | Uncommon | Skill | 1(0) | Gain 2 energy. Exhaust. 6 |
| **Sentinel** | Uncommon | Skill | 1 | Gain 5(8) Block. If this card is Exhausted, gain 2(3) energy. 6 |
| **Sever Soul** | Uncommon | Attack | 2 | Exhaust all non-Attack cards in your hand; deal 16(22) damage. 6 |
| **Shockwave** | Uncommon | Skill | 2 | Apply 3(5) Weak and Vulnerable to ALL enemies. Exhaust. 6 |
| **Spot Weakness** | Uncommon | Skill | 1 | If the enemy intends to attack, gain 3(4) Strength. 6 |
| **Uppercut** | Uncommon | Attack | 2 | Deal 13 damage; apply 1(2) Weak and 1(2) Vulnerable. 6 |
| **Whirlwind** | Uncommon | Attack | X | Deal 5(8) damage to ALL enemies X times. 6 |
| **Barricade** | Rare | Power | 3(2) | Block is not removed at the start of your turn. 6 |
| **Berserk** | Rare | Power | 0 | Gain 2(1) Vulnerable; at the start of your turn, gain 1 Energy. 6 |
| **Bludgeon** | Rare | Attack | 3 | Deal 32(42) damage. 6 |
| **Brutality** | Rare | Power | 0 | Innate. At the start of your turn, lose 1 HP and draw 1 card. 6 |
| **Corruption** | Rare | Power | 3(2) | Skills cost 0 and are Exhausted when played. 6 |
| **Demon Form** | Rare | Power | 3 | At the start of each turn, gain 2(3) Strength. 6 |
| **Double Tap** | Rare | Skill | 1 | This turn, your next 1(2) Attack(s) is played twice. 6 |
| **Exhume** | Rare | Skill | 1(0) | Put a card from your Exhaust pile into your hand. Exhaust. 6 |
| **Feed** | Rare | Attack | 1 | Deal 10(12) damage. If Fatal, gain 3(4) permanent Max HP. Exhaust. 6 |
| **Fiend Fire** | Rare | Attack | 2 | Exhaust all cards in hand. Deal 7(10) damage for each Exhausted card. Exhaust. 6 |
| **Immolate** | Rare | Attack | 2 | Deal 21(28) damage to ALL enemies. Add a Burn into discard pile. 6 |
| **Impervious** | Rare | Skill | 2 | Gain 30(40) Block. Exhaust. 6 |
| **Juggernaut** | Rare | Power | 2 | Whenever you gain Block, deal 5(7) damage to a random enemy. 6 |
| **Limit Break** | Rare | Skill | 1 | Double your Strength. Exhaust (Don't Exhaust if upgraded). 6 |
| **Offering** | Rare | Skill | 0 | Lose 6 HP. Gain 2 energy and draw 3(5) cards. Exhaust. 6 |
| **Reaper** | Rare | Attack | 2 | Deal 4(5) damage to ALL enemies; heal HP equal to unblocked damage dealt. Exhaust. 6 |

## **Character Archetype: The Silent**

The Silent archetype prioritizes rapid card cycling through Discard mechanics, compounding Poison damage over time, and generating zero-cost Attack cards known as *Shivs*. The Silent begins with 70 HP and the *Ring of the Snake* starting relic, which draws two additional cards at the start of combat, immediately smoothing out mathematical variance on the first turn.13

The Silent's mechanical identity mirrors the Ironclad's Exhaust through a different operational vector: utilizing mass Draw and Discard abilities to rapidly filter out ineffective cards.13 By holding pivotal combo pieces using Retain mechanics (such as *Well-Laid Plans*), the Silent guarantees that combinations land with maximum effect.13 The ability to manipulate hand states ensures that abilities requiring extensive setup—such as applying heavy Poison followed by the multiplicative *Catalyst* card—are mathematically viable against bosses.13

The complete Silent card pool reflects this high-mobility, low-impact per-card synergy:

| Card Name | Rarity | Type | Cost | Effect (Upgraded parameters in parentheses) |
| :---- | :---- | :---- | :---- | :---- |
| **Defend** | Starter | Skill | 1 | Gain 5(8) Block. 6 |
| **Neutralize** | Starter | Attack | 0 | Deal 3(4) damage. Apply 1(2) Weak. 6 |
| **Strike** | Starter | Attack | 1 | Deal 6(9) damage. 6 |
| **Survivor** | Starter | Skill | 1 | Gain 8(11) Block. Discard a card. 6 |
| **Acrobatics** | Common | Skill | 1 | Draw 3(4) cards. Discard 1 card. 6 |
| **Backflip** | Common | Skill | 1 | Gain 5(8) Block. Draw 2 cards. 6 |
| **Bane** | Common | Attack | 1 | Deal 7(10) damage. If enemy is poisoned, deal 7(10) damage again. 6 |
| **Blade Dance** | Common | Skill | 1 | Add 3(4) Shivs to your hand. 6 |
| **Cloak And Dagger** | Common | Skill | 1 | Gain 6 Block. Add 1(2) Shiv(s) to your hand. 6 |
| **Dagger Spray** | Common | Attack | 1 | Deal 4(6) damage to all enemies twice. 6 |
| **Dagger Throw** | Common | Attack | 1 | Deal 9(12) damage. Draw 1 card. Discard 1 card. 6 |
| **Deadly Poison** | Common | Skill | 1 | Apply 5(7) Poison. 6 |
| **Deflect** | Common | Skill | 0 | Gain 4(7) Block. 6 |
| **Dodge and Roll** | Common | Skill | 1 | Gain 4(6) Block. Next turn, gain 4(6) Block. 6 |
| **Flying Knee** | Common | Attack | 1 | Deal 8(11) damage. Next turn, gain 1 Energy. 6 |
| **Outmaneuver** | Common | Skill | 1 | Next turn, gain 2(3) Energy. 6 |
| **Piercing Wail** | Common | Skill | 1 | All enemies lose 6(8) Strength for 1 turn. Exhaust. 6 |
| **Poisoned Stab** | Common | Attack | 1 | Deal 6(8) damage. Apply 3(4) Poison. 6 |
| **Prepared** | Common | Skill | 0 | Draw 1(2) card(s). Discard 1(2) card(s). 6 |
| **Quick Slash** | Common | Attack | 1 | Deal 8(12) damage. Draw 1 card. 6 |
| **Slice** | Common | Attack | 0 | Deal 6(9) damage. 6 |
| **Sneaky Strike** | Common | Attack | 2 | Deal 12(16) damage. If you discarded a card this turn, gain 2 Energy. 6 |
| **Sucker Punch** | Common | Attack | 1 | Deal 7(9) damage. Apply 1(2) Weak. 6 |
| **Accuracy** | Uncommon | Power | 1 | Shivs deal 4(6) additional damage. 6 |
| **All-Out Attack** | Uncommon | Attack | 1 | Deal 10(14) damage to all enemies. Discard 1 card at random. 6 |
| **Backstab** | Uncommon | Attack | 0 | Deal 11(15) damage. Innate. Exhaust. 6 |
| **Blur** | Uncommon | Skill | 1 | Gain 5(8) Block. Block is not removed at start of next turn. 6 |
| **Bouncing Flask** | Uncommon | Skill | 2 | Apply 3 Poison to a random enemy 3(4) times. 6 |
| **Calculated Gamble** | Uncommon | Skill | 0 | Discard your hand, then draw that many cards. Exhaust (Not Upgraded). 6 |
| **Caltrops** | Uncommon | Power | 1 | Whenever you are attacked, deal 3(5) damage back. 6 |
| **Catalyst** | Uncommon | Skill | 1 | Double(Triple) an enemy's Poison. Exhaust. 6 |
| **Choke** | Uncommon | Attack | 2 | Deal 12 damage. Whenever you play a card this turn, enemy loses 3(5) HP. 6 |
| **Concentrate** | Uncommon | Skill | 0 | Discard 3(2) cards. Gain 2 Energy. 6 |
| **Crippling Cloud** | Uncommon | Skill | 2 | Apply 4(7) Poison and 2 Weak to all enemies. Exhaust. 6 |
| **Dash** | Uncommon | Attack | 2 | Gain 10(13) Block. Deal 10(13) damage. 6 |
| **Distraction** | Uncommon | Skill | 1(0) | Add a random Skill to your hand. Costs 0 this turn. Exhaust. 6 |
| **Endless Agony** | Uncommon | Attack | 0 | Whenever drawn, add a copy to your hand. Deal 4(6) damage. Exhaust. 6 |
| **Escape Plan** | Uncommon | Skill | 0 | Draw 1 card. If you draw a Skill, gain 3(5) Block. 6 |
| **Eviscerate** | Uncommon | Attack | 3 | Costs 1 less Energy for each card discarded this turn. Deal 7(9) damage 3 times. 6 |
| **Expertise** | Uncommon | Skill | 1 | Draw cards until you have 6(7) in your hand. 6 |
| **Finisher** | Uncommon | Attack | 1 | Deal 6(8) damage for each Attack played this turn. 6 |
| **Flechettes** | Uncommon | Attack | 1 | Deal 4(6) damage for each Skill in your hand. 6 |
| **Footwork** | Uncommon | Power | 1 | Gain 2(3) Dexterity. 6 |
| **Heel Hook** | Uncommon | Attack | 1 | Deal 5(8) damage. If enemy is Weak, Gain 1 Energy and draw 1 card. 6 |
| **Infinite Blades** | Uncommon | Power | 1 | At start of turn, add a Shiv to your hand. Innate(Upgraded). 6 |
| **Leg Sweep** | Uncommon | Skill | 2 | Apply 2(3) Weak. Gain 11(14) Block. 6 |
| **Masterful Stab** | Uncommon | Attack | 0 | Costs 1 additional Energy each time you lose HP this combat. Deal 12(16) damage. 6 |
| **Noxious Fumes** | Uncommon | Power | 1 | At start of turn, apply 2(3) Poison to all enemies. 6 |
| **Predator** | Uncommon | Attack | 2 | Deal 15(20) damage. Draw 2 more cards next turn. 6 |
| **Reflex** | Uncommon | Skill | Unplayable | If discarded from your hand, draw 2(3) cards. 6 |
| **Riddle With Holes** | Uncommon | Attack | 2 | Deal 3(4) damage 5 times. 6 |
| **Setup** | Uncommon | Skill | 1(0) | Place a card from hand on top of draw pile. Costs 0 until played. 6 |
| **Skewer** | Uncommon | Attack | X | Deal 7(10) damage X times. 6 |
| **Tactician** | Uncommon | Skill | Unplayable | If discarded from your hand, gain 1(2) Energy. 6 |
| **Terror** | Uncommon | Skill | 1(0) | Apply 99 Vulnerable. Exhaust. 6 |
| **Well-Laid Plans** | Uncommon | Power | 1 | At the end of your turn, retain up to 1(2) card(s). 6 |
| **A Thousand Cuts** | Rare | Power | 2 | Whenever you play a card, deal 1(2) damage to all enemies. 6 |
| **Adrenaline** | Rare | Skill | 0 | Gain 1(2) Energy. Draw 2 cards. Exhaust. 6 |
| **After Image** | Rare | Power | 1 | Whenever you play a card, gain 1 Block. Innate(Upgraded). 6 |
| **Alchemize** | Rare | Skill | 1(0) | Obtain a random potion. Exhaust. 6 |
| **Bullet Time** | Rare | Skill | 3(2) | Cannot draw additional cards this turn. Reduce cost of all cards in hand to 0\. 6 |
| **Burst** | Rare | Skill | 1 | This turn, your next 1(2) Skill(s) is played twice. 6 |
| **Corpse Explosion** | Rare | Skill | 2 | Apply 6(9) Poison. When enemy dies, deal damage equal to max HP to all enemies. 6 |
| **Die Die Die** | Rare | Attack | 1 | Deal 13(17) damage to all enemies. Exhaust. 6 |
| **Doppelganger** | Rare | Skill | X | Next turn, draw X(+1) cards and gain X(+1) Energy. 6 |
| **Envenom** | Rare | Power | 2(1) | Whenever an attack deals unblocked damage, apply 1 Poison. 6 |
| **Glass Knife** | Rare | Attack | 1 | Deal 8(12) damage twice. Decrease damage by 2 this combat. 6 |
| **Grand Finale** | Rare | Attack | 0 | Can only be played if no cards in draw pile. Deal 50(60) damage to all enemies. 6 |
| **Malaise** | Rare | Skill | X | Enemy loses X(+1) Strength. Apply X(+1) Weak. Exhaust. 6 |
| **Nightmare** | Rare | Skill | 3(2) | Choose a card. Next turn, add 3 copies of that card into your hand. Exhaust. 6 |
| **Phantasmal Killer** | Rare | Skill | 1(0) | On your next turn, your Attacks deal double damage. 6 |
| **Storm of Steel** | Rare | Skill | 1 | Discard your hand. Add 1 Shiv(+) into hand for each card discarded. 6 |
| **Tools of the Trade** | Rare | Power | 1(0) | At the start of your turn, draw 1 card and discard 1 card. 6 |
| **Unload** | Rare | Attack | 1 | Deal 14(18) damage. Discard all non-Attack cards in your hand. 6 |
| **Wraith Form** | Rare | Power | 3 | Gain 2(3) Intangible. At the end of your turn, lose 1 Dexterity. 6 |

## **Character Archetype: The Defect**

The Defect introduces a completely proprietary mechanic known as *Orbs*, augmented by a unique statistical attribute known as *Focus*.6 The Defect starts with 75 HP, the *Cracked Core* relic (which Channels 1 Lightning at combat start), and three empty Orb Slots.15

Orbs provide passive effects at the end of each turn.15 When a new Orb is Channeled into a sequence that is already full, the rightmost Orb is *Evoked*, instantly shattering to provide a massive burst effect.6 Managing the array length of Orb slots fundamentally alters strategy: a low number of Orb slots forces rapid Evocation loops, guaranteeing immediate damage or block, while a high number of Orb slots allows for vast passive accumulation.17 Focus acts as the scaling multiplier for Orbs, directly increasing their output magnitudes.15

Orb mechanics are strictly defined as follows:

* **Lightning**: Passive deals 3 (+Focus) damage to a random enemy. Evoke deals 8 (+Focus) damage.15  
* **Frost**: Passive grants 2 (+Focus) Block. Evoke grants 5 (+Focus) Block.15  
* **Dark**: Passive adds 6 (+Focus) damage to the Orb's stored potential (does not attack passively). Evoke unleashes the total accumulated damage upon the enemy with the lowest HP.15  
* **Plasma**: Passive grants 1 Energy at the start of the turn. Evoke grants 2 Energy immediately. Plasma is the only Orb entirely unaffected by the Focus stat.14

The Defect's card pool heavily revolves around generating, accelerating, and leveraging these elemental spheres:

| Card Name | Rarity | Type | Cost | Effect (Upgraded parameters in parentheses) |
| :---- | :---- | :---- | :---- | :---- |
| **Defend B** | Starter | Skill | 1 | Gain 5(8) Block. 6 |
| **Dualcast** | Starter | Skill | 1(0) | Evoke your next Orb twice. 6 |
| **Strike B** | Starter | Attack | 1 | Deals 6(9) damage. 6 |
| **Zap** | Starter | Skill | 1(0) | Channels 1 Lightning. 6 |
| **Ball Lightning** | Common | Attack | 1 | Deals 7(10) damage, channels 1 Lightning. 6 |
| **Barrage** | Common | Attack | 1 | Deals 4(6) damage for every Channeled Orb currently held. 6 |
| **Beam Cell** | Common | Attack | 0 | Deals 3(4) damage, applies 1(2) Vulnerable. 6 |
| **Charge Battery** | Common | Skill | 1 | Gain 7(10) Block, grants 1 Energy on the following turn. 6 |
| **Claw** | Common | Attack | 0 | Deals 3(5) damage. Increases damage of every Claw card in deck by 2 this combat. 6 |
| **Cold Snap** | Common | Attack | 1 | Deals 6(9) damage, channels 1 Frost. 6 |
| **Compile Driver** | Common | Attack | 1 | Deals 7(10) damage, draw 1 card for each unique type of Orb currently held. 6 |
| **Coolheaded** | Common | Skill | 1 | Channels 1 Frost, draws 1(2) card(s). 6 |
| **Go for the Eyes** | Common | Attack | 0 | Deals 3(4) damage. If enemy intends to attack, applies 1(2) Weak. 6 |
| **Hologram** | Common | Skill | 1 | Gain 3(5) Block, return any card from discard pile to hand. Exhaust(Not Upgraded). 6 |
| **Leap** | Common | Skill | 1 | Gain 9(12) Block. 6 |
| **Rebound** | Common | Attack | 1 | Deals 9(12) damage; next card played this turn is placed on top of draw pile. 6 |
| **Recursion** | Common | Skill | 1(0) | Evoke your next Orb and immediately channel an Orb of the same type. 6 |
| **Stack** | Common | Skill | 1 | Gain Block equal to cards in discard pile (+3 if upgraded). 6 |
| **Steam Barrier** | Common | Skill | 0 | Gain 6(8) Block; block value decreases by 1 every time played this combat. 6 |
| **Streamline** | Common | Attack | 2 | Deals 15(20) damage; cost is reduced by 1 every time played. 6 |
| **Sweeping Beam** | Common | Attack | 1 | Deals 6(9) damage to all enemies, draws 1 card. 6 |
| **TURBO** | Common | Skill | 0 | Grants 2(3) Energy, adds a Void card into discard pile. 6 |
| **Aggregate** | Uncommon | Skill | 1 | Grants 1 Energy for every 4(3) cards currently in your draw pile. 6 |
| **Auto-Shields** | Uncommon | Skill | 1 | Gain 11(15) Block, but only if you currently have no Block. 6 |
| **Blizzard** | Uncommon | Attack | 1 | Deal damage to all enemies equal to 2(3) times the total Frost channeled this combat. 6 |
| **Boot Sequence** | Uncommon | Skill | 0 | Innate. Gain 10(13) Block. Exhaust. 6 |
| **Bullseye** | Uncommon | Attack | 1 | Deals 8(11) damage, applies 2(3) Lock-On. 6 |
| **Capacitor** | Uncommon | Power | 1 | Grants 2(3) additional Orb slots. 6 |
| **Chaos** | Uncommon | Skill | 1 | Channels 1(2) random Orb(s). 6 |
| **Chill** | Uncommon | Skill | 0 | Channels 1 Frost for every enemy in combat. Exhaust. Innate(Upgraded). 6 |
| **Consume** | Uncommon | Skill | 2 | Grants 2(3) Focus, lose 1 Orb slot. 6 |
| **Darkness** | Uncommon | Skill | 1 | Channels 1 Dark orb. Upgraded triggers passive of all Dark orbs currently held. 6 |
| **Defragment** | Uncommon | Power | 1 | Grants 1(2) Focus. 6 |
| **Doom and Gloom** | Uncommon | Attack | 2 | Deals 10(14) damage to all enemies, channels 1 Dark orb. 6 |
| **Double Energy** | Uncommon | Skill | 1(0) | Doubles your current Energy. Exhaust. 6 |
| **Equilibrium** | Uncommon | Skill | 2 | Gain 13(16) Block, Retain your hand at the end of the turn. 6 |
| **FTL** | Uncommon | Attack | 0 | Deals 5(6) damage. If played fewer than 3(4) cards this turn, draw 1 card. 6 |
| **Force Field** | Uncommon | Skill | 4 | Cost is reduced by 1 for every Power card played. Gain 12(16) Block. 6 |
| **Fusion** | Uncommon | Skill | 2(1) | Channels 1 Plasma. 6 |
| **Genetic Algorithm** | Uncommon | Skill | 1 | Gain 1 Block; value permanently increases by 2(3) every time played. Exhaust. 6 |
| **Glacier** | Uncommon | Skill | 2 | Gain 7(10) Block, channels 2 Frost orbs. 6 |
| **Heatsinks** | Uncommon | Power | 1 | Draw 1(2) card(s) whenever you play a Power card. 6 |
| **Hello World** | Uncommon | Power | 1 | At start of turn, add a random Common card to hand. Innate(Upgraded). 6 |
| **Loop** | Uncommon | Power | 1 | At start of turn, triggers passive ability of next Orb 1(2) time(s). 6 |
| **Melter** | Uncommon | Attack | 1 | Removes all Block from an enemy, deals 10(14) damage. 6 |
| **Overclock** | Uncommon | Skill | 0 | Draws 2(3) cards, adds a Burn into your discard pile. 6 |
| **Recycle** | Uncommon | Skill | 1(0) | Exhausts a selected card, grants Energy equal to its cost. 6 |
| **Reinforced Body** | Uncommon | Skill | X | Gain 7(9) Block X times. 6 |
| **Reprogram** | Uncommon | Skill | 1 | Reduces Focus by 1(2), increases Strength and Dexterity by 1(2). 6 |
| **Rip and Tear** | Uncommon | Attack | 1 | Deals 7(9) damage to a random enemy 2 times. 6 |
| **Scrape** | Uncommon | Attack | 1 | Deals 7(10) damage, draws 4(5) cards; discards drawn cards that do not cost 0\. 6 |
| **Self Repair** | Uncommon | Power | 1 | Heals 7(10) HP at the end of combat. 6 |
| **Skim** | Uncommon | Skill | 1 | Draws 3(4) cards. 6 |
| **Static Discharge** | Uncommon | Power | 1 | Channels 1(2) Lightning whenever you take attack damage. 6 |
| **Storm** | Uncommon | Power | 1 | Channels 1 Lightning whenever you play a Power. Innate(Upgraded). 6 |
| **Sunder** | Uncommon | Attack | 3 | Deals 24(32) damage. If Fatal, gain 3 Energy. 6 |
| **Tempest** | Uncommon | Skill | X | Channels X(X+1) Lightning orbs. Exhaust. 6 |
| **White Noise** | Uncommon | Skill | 1(0) | Adds random Power card to hand costing 0 this turn. Exhaust. 6 |
| **All for One** | Rare | Attack | 2 | Deals 10(14) damage, returns every 0-cost card from discard pile to hand. 6 |
| **Amplify** | Rare | Skill | 1 | The next 1(2) Power(s) played this turn are played twice. 6 |
| **Biased Cognition** | Rare | Power | 1 | Grants 4(5) Focus; lose 1 Focus at the start of every turn. 6 |
| **Buffer** | Rare | Power | 2 | Prevents the next 1(2) time(s) you would lose HP. 6 |
| **Core Surge** | Rare | Attack | 1 | Deals 11(15) damage, grants 1 Artifact. Exhaust. 6 |
| **Creative AI** | Rare | Power | 3(2) | At the start of every turn, adds a random Power card to hand. 6 |
| **Echo Form** | Rare | Power | 3 | The first card played every turn is played twice. Ethereal(Not Upgraded). 6 |
| **Electrodynamics** | Rare | Power | 2 | Lightning hits all enemies. Channels 2(3) Lightning. 6 |
| **Fission** | Rare | Skill | 0 | Removes all Orbs (Evoking them if upgraded). Gain 1 Energy/1 Draw per Orb. Exhaust. 6 |
| **Hyperbeam** | Rare | Attack | 2 | Deals 26(34) damage to all enemies, reduces Focus by 3\. 6 |
| **Machine Learning** | Rare | Power | 1 | Draw 1 additional card at the start of every turn. Innate(Upgraded). 6 |
| **Meteor Strike** | Rare | Attack | 5 | Deals 24(30) damage, channels 3 Plasma. 6 |
| **Multi-Cast** | Rare | Skill | X | Evokes your next Orb X(X+1) times. 6 |
| **Rainbow** | Rare | Skill | 2 | Channels 1 Lightning, 1 Frost, 1 Dark. Exhaust(Not Upgraded). 6 |
| **Reboot** | Rare | Skill | 0 | Shuffles discard into draw pile, draws 4(6) cards. Exhaust. 6 |
| **Seek** | Rare | Skill | 0 | Choose 1(2) card(s) from draw pile and place in hand. Exhaust. 6 |
| **Thunder Strike** | Rare | Attack | 3 | Deals 7(9) damage to random enemy for every Lightning channeled this combat. 6 |

## **Character Archetype: The Watcher**

The Watcher operates on an advanced stance-dancing mechanic, shifting between distinct emotional states to control the flow of damage and energy.6 The Watcher requires precise mathematical forecasting, as miscalculating lethal thresholds while residing in a vulnerable stance often results in immediate defeat.18

The stances dictate global numerical multipliers:

* **Calm**: An entry-level utility stance offering no passive combat modifiers. However, upon exiting Calm, the Watcher immediately gains a refund of 2 Energy.19  
* **Wrath**: A high-risk, high-reward stance. While in Wrath, all Attack cards deal exactly double damage. Conversely, the Watcher receives double damage from all incoming enemy attacks.19 Shifting from Calm directly into Wrath creates an explosive energy refund window, enabling massive turn extensions.19  
* **Divinity**: An ultimate stance requiring the accumulation of exactly 10 *Mantra* stacks. Upon entering Divinity, the Watcher gains an immediate 3 Energy, and all Attacks deal triple damage. The stance automatically terminates at the end of the turn, shifting the Watcher back to an un-stanced state.21

The Watcher's card pool is designed to facilitate these extreme transitions:

| Card Name | Rarity | Type | Cost | Effect (Upgraded parameters in parentheses) |
| :---- | :---- | :---- | :---- | :---- |
| **Defend** | Starter | Skill | 1 | Grants 5(8) Block. 6 |
| **Eruption** | Starter | Attack | 2(1) | Deals 9 damage. Enter Wrath. 6 |
| **Strike** | Starter | Attack | 1 | Deals 6(9) damage. 6 |
| **Vigilance** | Starter | Skill | 2 | Enter Calm. Gain 8(12) Block. 6 |
| **Bowling Bash** | Common | Attack | 1 | Deals 7(10) damage for each enemy in combat. 6 |
| **Consecrate** | Common | Attack | 0 | Deals 5(8) damage to all enemies. 6 |
| **Crescendo** | Common | Skill | 1(0) | Retain. Enter Wrath. Exhaust. 6 |
| **Crush Joints** | Common | Attack | 1 | Deals 8(10) damage. If previous card was a skill, apply 1(2) Vulnerable. 6 |
| **Cut Through Fate** | Common | Attack | 1 | Deals 7(9) damage. Scry 2(3). Draw 1 card. 6 |
| **Empty Body** | Common | Skill | 1 | Gain 7(10) Block. Exit current Stance. 6 |
| **Empty Fist** | Common | Attack | 1 | Deals 9(14) damage. Exit current Stance. 6 |
| **Evaluate** | Common | Skill | 1 | Gain 6(10) Block. Shuffle an Insight into draw pile. 6 |
| **Flurry of Blows** | Common | Attack | 0 | Deals 4(6) damage. Returns from discard to hand when stance changes. 6 |
| **Flying Sleeves** | Common | Attack | 1 | Retain. Deals 4(6) damage twice. 6 |
| **Follow-Up** | Common | Attack | 1 | Deals 7(11) damage. If previous card was an Attack, gain 1 Energy. 6 |
| **Halt** | Common | Skill | 0 | Gain 3(4) Block. If in Wrath, gain additional 9(14) Block. 6 |
| **Just Lucky** | Common | Attack | 0 | Scry 1(2), gain 2(3) Block, deal 3(4) damage. 6 |
| **Pressure Points** | Common | Skill | 1 | Apply 8(11) Mark. All enemies lose HP equal to total Mark. 6 |
| **Prostrate** | Common | Skill | 0 | Gain 2(3) Mantra. Gain 4 Block. 6 |
| **Protect** | Common | Skill | 2 | Retain. Gain 12(16) Block. 6 |
| **Sash Whip** | Common | Attack | 1 | Deals 8(10) damage. If last card played was an Attack, apply 1(2) Weak. 6 |
| **Third Eye** | Common | Skill | 1 | Gain 7(9) Block. Scry 3(5). 6 |
| **Tranquility** | Common | Skill | 1(0) | Retain. Enter Calm. Exhaust. 6 |
| **Battle Hymn** | Uncommon | Power | 1 | Innate(Upgraded). At start of turn, add a Smite to hand. 6 |
| **Carve Reality** | Uncommon | Attack | 1 | Deals 6(10) damage. Add a Smite to hand. 6 |
| **Collect** | Uncommon | Skill | X | Puts a Miracle+ in hand at start of next X(X+1) turns. Exhaust. 6 |
| **Conclude** | Uncommon | Attack | 1 | Deals 12(16) damage to all enemies. Ends your turn. 6 |
| **Deceive Reality** | Uncommon | Skill | 1 | Gain 4(7) Block. Add a Safety to hand. 6 |
| **Empty Mind** | Uncommon | Skill | 1 | Exit current Stance. Draw 2(3) cards. 6 |
| **Fasting** | Uncommon | Power | 2 | Gain 3(4) Strength and Dexterity. Gain 1 less Energy per turn. 6 |
| **Fear No Evil** | Uncommon | Attack | 1 | Deals 8(11) damage. If enemy intends to attack, enter Calm. 6 |
| **Foreign Influence** | Uncommon | Skill | 0 | Choose 1 of 3 Attacks to add to hand costing 0 this turn. Exhaust. 6 |
| **Foresight** | Uncommon | Power | 1 | At the start of your turn, Scry 3(4). 6 |
| **Indignation** | Uncommon | Skill | 1 | If in Wrath, apply 3(5) Vulnerable to all enemies; else enter Wrath. 6 |
| **Inner Peace** | Uncommon | Skill | 1 | If in Calm, draw 3(4) cards; else enter Calm. 6 |
| **Like Water** | Uncommon | Power | 1 | At the end of turn, if in Calm, gain 5(7) Block. 6 |
| **Meditate** | Uncommon | Skill | 1 | Put 1(2) card(s) from discard into hand with Retain. Enter Calm. Ends turn. 6 |
| **Mental Fortress** | Uncommon | Power | 1 | Gain 4(6) Block whenever you switch stances. 6 |
| **Nirvana** | Uncommon | Power | 1 | Gain 3(4) Block whenever you Scry. 6 |
| **Perseverance** | Uncommon | Skill | 1 | Retain. Gain 5(7) Block. Value increases by 2(3) each time Retained. 6 |
| **Pray** | Uncommon | Skill | 1 | Gain 3(4) Mantra. Shuffle an Insight into draw pile. 6 |
| **Reach Heaven** | Uncommon | Attack | 2 | Deals 10(15) damage. Shuffle a Through Violence into draw pile. 6 |
| **Rushdown** | Uncommon | Power | 1(0) | Draw 2 cards whenever you enter Wrath. 6 |
| **Sanctity** | Uncommon | Skill | 1 | Gain 6(9) Block. If previous card was a skill, draw 2 cards. 6 |
| **Sands of Time** | Uncommon | Attack | 4 | Retain. Deals 20(26) damage. Cost lowered by 1 each time Retained. 6 |
| **Signature Move** | Uncommon | Attack | 2 | Deals 30(40) damage. Can only play if it is the only attack in hand. 6 |
| **Simmering Fury** | Uncommon | Skill | 1 | At the start of next turn, enter Wrath and draw 2(3) cards. 6 |
| **Study** | Uncommon | Power | 2(1) | At the end of the turn, shuffle an Insight into draw pile. 6 |
| **Swivel** | Uncommon | Skill | 2 | Gain 8(11) Block. Next Attack played costs 0\. 6 |
| **Talk to the Hand** | Uncommon | Attack | 1 | Deals 5(7) damage. Attacks against enemy yield 2(3) Block. Exhaust. 6 |
| **Tantrum** | Uncommon | Attack | 1 | Deals 3 damage 3(4) times. Enter Wrath. Shuffle into draw pile. 6 |
| **Wallop** | Uncommon | Attack | 2 | Deals 9(12) damage. Gain Block equal to unblocked damage dealt. 6 |
| **Wave of the Hand** | Uncommon | Skill | 1 | Whenever you gain Block this turn, apply 1(2) Weak to all enemies. 6 |
| **Weave** | Uncommon | Attack | 0 | Deals 4(6) damage. Returns from discard to hand whenever you Scry. 6 |
| **Wheel Kick** | Uncommon | Attack | 2 | Deals 15(20) damage. Draw 2 cards. 6 |
| **Windmill Strike** | Uncommon | Attack | 2 | Retain. Deals 7(10) damage. Damage increases by 4(5) each time Retained. 6 |
| **Worship** | Uncommon | Skill | 2 | Gain 5 Mantra. Retain(Upgraded). 6 |
| **Wreath of Flame** | Uncommon | Skill | 1 | Your next Attack deals an additional 5(8) damage. 6 |
| **Alpha** | Rare | Skill | 1 | Innate(Upgraded). Shuffle a Beta into draw pile. Exhaust. 6 |
| **Blasphemy** | Rare | Skill | 1 | Retain. Enter Divinity. Die next turn. Exhaust. 6 |
| **Brilliance** | Rare | Attack | 1 | Deals 12(16) damage \+ damage based on total Mantra gained this combat. 6 |
| **Conjure Blade** | Rare | Skill | X | Shuffle an Expunger into draw pile with X(X+1) hits. Exhaust. 6 |
| **Deus Ex Machina** | Rare | Skill | Unplayable | When drawn, add 2(3) Miracles to hand. Exhaust. 6 |
| **Deva Form** | Rare | Power | 3 | Ethereal(Not Upgraded). At start of turn, gain Energy and increase Energy gain by 1\. 6 |
| **Devotion** | Rare | Power | 1 | Gain 2(3) Mantra at the start of each turn. 6 |
| **Establishment** | Rare | Power | 1 | Innate(Upgraded). Whenever a card is Retained, lower its cost by 1\. 6 |
| **Judgment** | Rare | Skill | 1 | If an enemy has 30(40) HP or less, set their HP to 0\. 6 |
| **Lesson Learned** | Rare | Attack | 2 | Deals 10(13) damage. If Fatal, upgrade a random card in deck. Exhaust. 6 |
| **Master Reality** | Rare | Power | 1(0) | Whenever a card is created during combat, it is upgraded. 6 |
| **Omniscience** | Rare | Skill | 4(3) | Choose a card from draw pile, play it twice, then Exhaust it. Exhaust. 6 |
| **Ragnarok** | Rare | Attack | 3 | Deals 5(6) damage to a random enemy 5(6) times. 6 |
| **Scrawl** | Rare | Skill | 1(0) | Draw cards until hand is full. Exhaust. 6 |
| **Spirit Shield** | Rare | Skill | 2 | Gain 3(4) Block for every card currently in your hand. 6 |
| **Vault** | Rare | Skill | 3(2) | Take an extra turn after this one. Ends current turn. Exhaust. 6 |
| **Wish** | Rare | Skill | 3 | Choose: gain 6(8) Plated Armor, 3(4) Strength, or 25(30) Gold. Exhaust. 6 |

## **Spire Topography: Map Algorithms and Rest Site Economics**

To achieve victory, the macro-level strategy of pathing across the game's map is mathematically equal in importance to micro-level combat.22

### **Grid Generation and Node Probabilities**

The map architecture is rigidly generated via a 7x15 isometric grid algorithm.23 At the base (the first floor), the system selects a random starting room, subsequently connecting it via linear pathways to up to three adjacent nodes on the second floor.23 This branching iterates upward for 15 floors, strictly governed by geometric intersection rules ensuring paths never cross.23 To heighten the difficulty curve organically, the generation engine sets Act 1 Elite encounter spawn rates at exactly 8%, which escalates to 16% across Acts 2 and 3\.23

Event nodes (Question Marks) exhibit dynamic probability shifting designed to prevent infinite narrative chains. The underlying mathematics constantly adjust based on the player's prior node encounters.24 At the initiation of an Act, the baseline generation probabilities for a Question Mark Node are:

| Node Outcome | Base Probability at Act Start | Algorithmic Increment on Non-Hit |
| :---- | :---- | :---- |
| **Monster** | 10% | \+10% |
| **Shop** | 3% | \+3% |
| **Treasure** | 2% | \+2% |
| **Narrative Event** | 85% | (Absorbs remaining probability) |

If the player lands on an Event node, the background probabilities for the non-event options augment sequentially by their base chance.24 If the first node rolls an Event, the second Question Mark node will possess a 20% chance of being a Monster, 6% Shop, 4% Treasure, and 70% Event.24 If a Monster is then subsequently rolled, the Monster variable hard-resets to 10%, while the Shop and Treasure variables maintain their escalation.24

### **Rest Site Action Utility**

Rest Sites (Campfires) are safe harbors allowing the player to execute a single strategic action.25 The standard options are Rest (Heal for 30% of Max HP) or Smith (Upgrade one card for permanent combat enhancements).25 Upgrading cards improves numerical efficiency, drawing speed, or energy cost, serving as a primary vector for deck improvement.6

However, specialized passive Relics introduce alternative choices, significantly elevating the value of Campfire routing:

* *Peace Pipe* grants the **Toke** action, allowing the permanent removal of a card from the deck.26  
* *Shovel* grants the **Dig** action, yielding a random relic.26  
* *Girya* grants the **Lift** action, permanently raising the player's Strength attribute up to a maximum of three times across a run.26

## **The Spire Economy: Merchants and Resource Allocation**

Merchants provide essential deck cultivation services, operating strictly on accumulated Gold. Efficient allocation of capital separates standard play from high-ascension viability.29

### **Merchant Inventory and Pricing Matrices**

The Shop invariably generates an inventory consisting of specific allocations: 5 Colored Class-Cards (2 Attacks, 2 Skills, 1 Power), 2 Colorless Cards (Uncommon and Rare), 3 Relics (with the rightmost being an exclusive Shop Relic), 3 Potions, and the Card Removal Service.30

Base pricing parameters are systematically defined within tight numeric bands 30:

| Item Category | Base Cost Range (Gold) |
| :---- | :---- |
| Common Class Card | 45 \- 55 |
| Uncommon Class Card | 68 \- 82 |
| Rare Class Card | 135 \- 165 |
| Uncommon Colorless Card | 81 \- 99 |
| Rare Colorless Card | 162 \- 198 |
| Common Relic | 143 \- 157 |
| Uncommon Relic | 238 \- 262 |
| Shop-Exclusive Relic | 190 \- 210 |
| Common Potion | 48 \- 52 |
| Uncommon Potion | 72 \- 78 |

Crucially, upon reaching Ascension level 16 and beyond, all Merchant prices suffer an automatic 10% inflation tax, radically tightening economic constraints and penalizing sub-optimal purchases.30

### **Card Removal Service Economics**

Deck optimization heavily relies on eliminating substandard starter cards (Strikes and Defends). The Merchant facilitates this via the Card Removal Service, which can be utilized exactly once per shop instance.30 The base cost is 75 Gold, but the service operates on an escalating integer algorithm: each subsequent removal across the entire run increases the cost by 25 Gold (75 ![][image6] 100 ![][image6] 125 ![][image6] 150).30

Economic efficiency can be artificially manipulated via specific relics:

* *Membership Card*: A Shop-exclusive Relic granting a permanent 50% discount on all future goods and services.30  
* *The Courier*: Reduces prices by an additional 20% and instantly replenishes purchased inventory slots, allowing unlimited mass purchasing if capital allows.31  
* *Smiling Mask*: Locks the escalating cost of the Card Removal Service to a permanent static flat rate of 50 Gold, bypassing the compounding penalty entirely.30

## **Relics and Potions: Auxiliary Power Scaling**

The mathematical rigor of card interactions is frequently disrupted by Relics and Potions, which provide nonlinear power spikes capable of circumventing standard energy economics.

### **The Relic Framework**

Relics are persistent passive Buffs separated into rarity tiers: Common, Uncommon, Rare, Boss, and Shop.32 Their functions range from simple numerical advantages to absolute mechanical overhauls. Procuring a synergistic Relic often dictates the entire trajectory of deck construction.32

A core sampling of potent V1 Relics illustrates their capacity to manipulate the game state:

| Relic Name | Rarity | Mechanical Effect |
| :---- | :---- | :---- |
| **Akabeko** | Common | Your first Attack each combat deals 8 additional damage.32 |
| **Anchor** | Common | Start each combat with 10 Block.32 |
| **Bag of Preparation** | Common | At the start of each combat, draw 2 additional cards.32 |
| **Bronze Scales** | Common | Start each combat with 3 Thorns.32 |
| **Blue Candle** | Uncommon | Unplayable Curse cards can now be played and Exhausted.32 |
| **Bottled Lightning** | Uncommon | Upon pickup, choose a Skill card. It starts each combat in your hand (Innate).32 |
| **Toxic Egg** | Uncommon | Whenever you add a Skill card to your deck, it is automatically Upgraded.32 |
| **Calipers** | Rare | At the start of your turn, lose 15 Block rather than all of your Block.32 |
| **Dead Branch** | Rare | Whenever you Exhaust a card, add a random card to your hand.32 |
| **Du-Vu Doll** | Rare | For each Curse in your deck, start each combat with 1 Strength.32 |

Relics such as *Dead Branch* generate vast probabilistic advantages. When paired with the Ironclad's *Corruption* card (which reduces Skill costs to zero but Exhausts them), *Dead Branch* fuels an infinite loop of free cards, entirely bypassing the game's energy limitations.6

### **The Calculus of Potions**

Potions function as single-use consumables restricted exclusively to combat sequences.7 Analytical miscalculations frequently result in players hoarding potions, mistakenly perceiving them as endgame reserves.33 In reality, potions serve as immediate tactical solvers designed to bridge localized deck inadequacies against specific Elite or Boss algorithmic checks.33

For example, encountering *Lagavulin* (a highly threatening Act 1 Elite that debuffs player strength and dexterity) with a mathematically poor opening draw state can yield catastrophic HP loss.33 Expending an *Attack Potion* or a *Dexterity Potion* strictly to accelerate the damage or defense threshold of this specific encounter saves substantial HP.33 This preservation of HP subsequently permits an aggressive path against another Elite to secure a permanent Relic, snowballing early advantages.33

The potion inventory includes standard and character-specific effects:

| Potion Name | Effect Description | Tactical Utility |
| :---- | :---- | :---- |
| **Attack Potion** | Add 1 of 3 random Attack cards to your hand; it costs 0 this turn.34 | Emergency lethal damage injection. |
| **Block Potion** | Gain immediate temporary Block.34 | Surviving heavy, telegraphed Boss attacks. |
| **Dexterity Potion** | Gain 2 Dexterity for the duration of the combat.34 | Long-term defensive scaling against Bosses. |
| **Energy Potion** | Gain 2 Energy immediately.34 | Extending complex combo sequences on pivotal turns. |
| **Artifact Potion** | Gain 1 Artifact, negating the next incoming Debuff.34 | Pre-empting severe Boss debuffs (e.g., Vulnerable). |

In high-ascension routing, obtaining a Boss Relic like *Sozu*—which grants \+1 Energy per turn but permanently prevents further potion acquisition—presents extreme mathematical danger.33 In Act 4 encounters, where enemies routinely attack for lethal damage on turn two, lacking an emergency potion to fix a poor draw is frequently fatal.33

## **The Ultimate Convergence: Act 4 and The Corrupt Heart**

Completing the standard progression of three Acts unlocks basic ascension scaling, but the true mechanical resolution of the game requires surviving a hidden fourth Act culminating in the Corrupt Heart. Achieving entry demands precise macro-strategic deviations during the first three Acts to collect three specific colored Keys.4

### **Key Acquisition Protocols**

Collecting the Keys incurs a direct opportunity cost, forcing the player to sacrifice immediate mathematical advantages for the prospect of endgame access:

1. **The Ruby Key**: Demands the player sacrifice one Campfire action to choose the "Recall" option.5 This denies a critical Rest or Smith cycle, requiring the player's deck to be strong enough to survive without that upgrade.36  
2. **The Sapphire Key**: Located exclusively inside Treasure Chests alongside Relics.36 Acquiring the key mandates abandoning the Relic housed within. Optimal strategies involve delaying this acquisition until late in the run when a generated Relic holds little synergistic value to the established deck engine.36  
3. **The Emerald Key**: Obtained by routing through a specialized "Flaming Elite" node.5 This node houses a standard Act Elite arbitrarily buffed with increased statistics, artificial regeneration, or modified strength.36 Navigating to the Emerald Key prematurely can destroy a fragile run; sophisticated routing dictates waiting until Act 3, when the deck's scaling algorithms have fully matured and can absorb the statistical anomaly of the buffed Elite.36

Once synthesized, these keys grant access to Act 4, presenting the game's ultimate defensive and scaling checks.35 The Corrupt Heart acts as the final mathematical filter. It weaponizes the *Beat of Death*—a passive mechanic applying 1 or 2 unblockable damage to the player for every single card they play.37 Simultaneously, the Heart generates compounding artificial strength limits (a damage cap preventing the player from dealing more than 200 or 300 damage per turn), which entirely restricts infinite zero-cost loops from winning on turn one.37 Furthermore, the Heart introduces *Painful Stabs* and inserts Status cards into the player's deck, forcing a definitive, high-velocity conclusion before the player's scaling is mathematically overwhelmed.37

Victory in *Slay the Spire* is strictly dictated by a player's capability to understand statistical probability, the nuanced manipulation of floating-point multipliers, and the willingness to construct hyper-efficient, thinned decks. By forcing constant strategic pivots, the Spire fundamentally tests adaptive economic and tactical mastery.

#### **Works cited**

1. Slay the Spire \- Wikipedia, accessed April 12, 2026, [https://en.wikipedia.org/wiki/Slay\_the\_Spire](https://en.wikipedia.org/wiki/Slay_the_Spire)  
2. The Beginner's Guide to Slay the Spire | Raise Your Game, accessed April 12, 2026, [https://raiseyourgame.com/2024/01/11/slay-the-spire-beginner-guide/](https://raiseyourgame.com/2024/01/11/slay-the-spire-beginner-guide/)  
3. Gameplay | Slay the Spire Wiki \- Fandom, accessed April 12, 2026, [https://slay-the-spire.fandom.com/wiki/Gameplay](https://slay-the-spire.fandom.com/wiki/Gameplay)  
4. How to unlock the keys? : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/13xo3if/how\_to\_unlock\_the\_keys/](https://www.reddit.com/r/slaythespire/comments/13xo3if/how_to_unlock_the_keys/)  
5. Keys | Slay the Spire Wiki \- Fandom, accessed April 12, 2026, [https://slay-the-spire.fandom.com/wiki/Keys](https://slay-the-spire.fandom.com/wiki/Keys)  
6. Keywords | Slay the Spire Wiki | Fandom, accessed April 12, 2026, [https://slay-the-spire.fandom.com/wiki/Keywords](https://slay-the-spire.fandom.com/wiki/Keywords)  
7. How to play guide for Slay the Spire, accessed April 12, 2026, [https://slaythespire-archive.fandom.com/wiki/How\_to\_play\_guide\_for\_Slay\_the\_Spire](https://slaythespire-archive.fandom.com/wiki/How_to_play_guide_for_Slay_the_Spire)  
8. Strength \- Slay the Spire Wiki \- Fandom, accessed April 12, 2026, [https://slay-the-spire.fandom.com/wiki/Strength](https://slay-the-spire.fandom.com/wiki/Strength)  
9. The order of operations for the game : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/rqxm6e/the\_order\_of\_operations\_for\_the\_game/](https://www.reddit.com/r/slaythespire/comments/rqxm6e/the_order_of_operations_for_the_game/)  
10. Combat Mechanics | Slay the Spire Wiki | Fandom, accessed April 12, 2026, [https://slay-the-spire.fandom.com/wiki/Combat\_Mechanics](https://slay-the-spire.fandom.com/wiki/Combat_Mechanics)  
11. slay the spire maths: %25 of 1 \= 0, 0x2 \= 1 : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/fk21x0/slay\_the\_spire\_maths\_25\_of\_1\_0\_0x2\_1/](https://www.reddit.com/r/slaythespire/comments/fk21x0/slay_the_spire_maths_25_of_1_0_0x2_1/)  
12. Why does damage sometimes round up and sometimes round down when attacking Vulnerable enemies? : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/z7gedm/why\_does\_damage\_sometimes\_round\_up\_and\_sometimes/](https://www.reddit.com/r/slaythespire/comments/z7gedm/why_does_damage_sometimes_round_up_and_sometimes/)  
13. Why do ironclad and the silent feel so much worse than defect and watcher? \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/1qanjlf/why\_do\_ironclad\_and\_the\_silent\_feel\_so\_much\_worse/](https://www.reddit.com/r/slaythespire/comments/1qanjlf/why_do_ironclad_and_the_silent_feel_so_much_worse/)  
14. What are the different kinds of orbs for and what is channeling. : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/kjwlw9/what\_are\_the\_different\_kinds\_of\_orbs\_for\_and\_what/](https://www.reddit.com/r/slaythespire/comments/kjwlw9/what_are_the_different_kinds_of_orbs_for_and_what/)  
15. Orbs | Slay the Spire Wiki \- Fandom, accessed April 12, 2026, [https://slay-the-spire.fandom.com/wiki/Orbs](https://slay-the-spire.fandom.com/wiki/Orbs)  
16. Defect | Slay the Spire Wiki \- Fandom, accessed April 12, 2026, [https://slay-the-spire.fandom.com/wiki/Defect](https://slay-the-spire.fandom.com/wiki/Defect)  
17. Does anybody else play a low-orb "evoke" strategy with defect? : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/16uhx0e/does\_anybody\_else\_play\_a\_loworb\_evoke\_strategy/](https://www.reddit.com/r/slaythespire/comments/16uhx0e/does_anybody_else_play_a_loworb_evoke_strategy/)  
18. How do you rank all 4 chars from most fave to least? : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/1ph1qum/how\_do\_you\_rank\_all\_4\_chars\_from\_most\_fave\_to/](https://www.reddit.com/r/slaythespire/comments/1ph1qum/how_do_you_rank_all_4_chars_from_most_fave_to/)  
19. Can we talk about Stances? : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/d32zcm/can\_we\_talk\_about\_stances/](https://www.reddit.com/r/slaythespire/comments/d32zcm/can_we_talk_about_stances/)  
20. I don't really like the new hero's Stances :: Slay the Spire General Discussions, accessed April 12, 2026, [https://steamcommunity.com/app/646570/discussions/0/2803982773092176790/](https://steamcommunity.com/app/646570/discussions/0/2803982773092176790/)  
21. Divinity | Slay the Spire Wiki \- Fandom, accessed April 12, 2026, [https://slay-the-spire.fandom.com/wiki/Divinity](https://slay-the-spire.fandom.com/wiki/Divinity)  
22. Stop Losing Runs Because of Bad Pathing | Slay the Spire 2 Guide \- YouTube, accessed April 12, 2026, [https://www.youtube.com/watch?v=kdSsSzSALE8](https://www.youtube.com/watch?v=kdSsSzSALE8)  
23. Communauté Steam :: Guide :: Map Generation in Slay the Spire, accessed April 12, 2026, [https://steamcommunity.com/sharedfiles/filedetails/?l=french\&id=2830078257\&searchtext=Hledat+n%C3%A1vody+pro+hru+Slay+the+Spire](https://steamcommunity.com/sharedfiles/filedetails/?l=french&id=2830078257&searchtext=Hledat+n%C3%A1vody+pro+hru+Slay+the+Spire)  
24. (Almost) Everything about Question Mark Nodes : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/7w51qz/almost\_everything\_about\_question\_mark\_nodes/](https://www.reddit.com/r/slaythespire/comments/7w51qz/almost_everything_about_question_mark_nodes/)  
25. Every Campfire Option… Every Time (This Was Broken) | Slay the Spire 2 \- YouTube, accessed April 12, 2026, [https://www.youtube.com/watch?v=KSqJrWudSZg](https://www.youtube.com/watch?v=KSqJrWudSZg)  
26. Too many choices, need more campfires : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/sux1uf/too\_many\_choices\_need\_more\_campfires/](https://www.reddit.com/r/slaythespire/comments/sux1uf/too_many_choices_need_more_campfires/)  
27. A boss relic that lets you perform two actions at a campfire : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/tm1eri/a\_boss\_relic\_that\_lets\_you\_perform\_two\_actions\_at/](https://www.reddit.com/r/slaythespire/comments/tm1eri/a_boss_relic_that_lets_you_perform_two_actions_at/)  
28. What exactly does this do? What options? : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/1rt3xlr/what\_exactly\_does\_this\_do\_what\_options/](https://www.reddit.com/r/slaythespire/comments/1rt3xlr/what_exactly_does_this_do_what_options/)  
29. Stop Wasting Gold – Every Shop Relic Ranked (Slay the Spire) \- YouTube, accessed April 12, 2026, [https://www.youtube.com/watch?v=pxs7rmjo8nA](https://www.youtube.com/watch?v=pxs7rmjo8nA)  
30. Merchant | Slay the Spire Wiki \- Fandom, accessed April 12, 2026, [https://slay-the-spire.fandom.com/wiki/Merchant](https://slay-the-spire.fandom.com/wiki/Merchant)  
31. Still learning the game, but I keep getting mixed advice: How often do you focus on removing cards? Do you hit up shops to remove or hope 's will help you do it? I imagine the answer is it all depends on context, but I still want to hear different points of view. : r \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/yj93f9/still\_learning\_the\_game\_but\_i\_keep\_getting\_mixed/](https://www.reddit.com/r/slaythespire/comments/yj93f9/still_learning_the_game_but_i_keep_getting_mixed/)  
32. Slay the Spire Relics \- Staircase Spirit, accessed April 12, 2026, [https://www.rigelatin.net/staircase/slay-the-spire-relics.php](https://www.rigelatin.net/staircase/slay-the-spire-relics.php)  
33. A good tip for those climbing the spire: Appreciate potions more : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/1pm89sr/a\_good\_tip\_for\_those\_climbing\_the\_spire/](https://www.reddit.com/r/slaythespire/comments/1pm89sr/a_good_tip_for_those_climbing_the_spire/)  
34. Slay the Spire Potions \- GM Binder, accessed April 12, 2026, [https://www.gmbinder.com/share/-LIy-gd-aqAijROy-XrG](https://www.gmbinder.com/share/-LIy-gd-aqAijROy-XrG)  
35. Guide Part 3 \- Act 4 \- Steam Community, accessed April 12, 2026, [https://steamcommunity.com/sharedfiles/filedetails/?id=2965359242](https://steamcommunity.com/sharedfiles/filedetails/?id=2965359242)  
36. Can somebody explain to me how the keys work and what are the strategies? Thanks\! : r/slaythespire \- Reddit, accessed April 12, 2026, [https://www.reddit.com/r/slaythespire/comments/mbuum4/can\_somebody\_explain\_to\_me\_how\_the\_keys\_work\_and/](https://www.reddit.com/r/slaythespire/comments/mbuum4/can_somebody_explain_to_me_how_the_keys_work_and/)  
37. Guide :: Slaying The Spire From The Ground Up: Building a Good Foundation, accessed April 12, 2026, [https://steamcommunity.com/sharedfiles/filedetails/?id=2673443183](https://steamcommunity.com/sharedfiles/filedetails/?id=2673443183)

[image1]: <data:image/png;base64,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>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAIcAAAAYCAYAAADQ1+6cAAAHCElEQVR4Xu2YechnUxjHv7Jk37Nkey2RfTcpyzs1tj9IlsZk+cceWRvCZF6hsZR9Itk12UPIkviFMpYMImWJkQihhDBZns8893HPPb977+835h2N5n7r27y/e8499znn+T7LGalDhw4dOnRYYrGycR3j0vnAYgrsxF7s/jdYy3iQcaN84L/C2sZXjX8l/Mq4q3FD45xs7EPjlvPflI7Jxh43rlSMjScmGr+Vf+N5Df7GFONPKu16yrh8ZUYVp6ic+7vxLrXPH4QVjQ+pXBMHB5YyHlqQv5uwm/E149XGucZtq8NDrzMuOF++kdPzAcOF8rHD8gHDDsYXjCPZ8/EGQv3CeHk+0ACc+4BcVC8bV6kO/4MtjM8a52n4tYcF50agbZY829H4o9oFu4zxPuMs4z3G34x7VmYMt8644Wi5ABBJjhAHc1Kg2GnG/bLniwKTjH8YD8kHGrCB/GAfkUfe+tXh+VhWvrcZ6o/whQUOftjYU7Ws8M1RecZuAmJCVOcYN5Fn6jw7DLPOuOFg+QFxWClGjJ+oXjikuqvkhi5qYNd3xq3zgQbsZbxSbvPP8jKZAzGQDe9Uf4QvLBDnZ8YbsufDIAJhPMW6UMCgP413J89Q62XG69QvDiKDiMtrYQ6EQ/2kNjY1VuuqvfEibZI+eyqjMJq1uowAsBXHw7qsQKM4Jnfi+xrcy2DDqNr3sZpxf7kQ95WXgzTT8R52rJo8S8He2M90eckYLX7nZWPQOvhtRG4rtkQDz3PK0T5yv0D+JpBam3wWIcJScfDsCpUHnI7tbbxA/ekuwIenGj8ynmE8yviiqiUIZ8w0PlGMsz6Oeq4YC0SajSjkYKjHZK0n1e9UhHuzPMuE6NOSiM1nyoUd+27qN2IfbxtPkq/zjvFclXtnDuX1jWL8NuOXqmY6zpD9sV/eR9w5jjTeavxU3iuR0djz5smcQesgSs7wRuMR8vevkdtKdaDBfcn4mPF+46nywBhTC+KQIoLY8PXyhi0XDgrn8JsiCOfcJBfGSPKcZpc6Clifg8BQIg6ECDiUVHSRZqM7P9G4szy66iI++g2a0Gjc0nK5h3wNcLLqMwvARvb5gbz2B3DQD8bt5Haep+pecdhbKjMdWeqO4jkZDeGk66Vgfk/er3COKQatg/O5pU1OnmEjjTm9Cf4kSyNe/DlBvm/231r+SF9zVW6ICD+rGMuFQ3RwqE3gXZw5VvzmkA+Q3wpiMxwwc8gYgXBkvjZR/Yv8YLim4hDsOFvltTpF9Bsg9pUKe0wuSNZBiE39RtjIlT1F9Gf8yy2C8jGWjOf9BmX1BPk3Z8tvIrnjA223srZ1EM57xfPYG4H9oPFweSBfVIxxewvxrWc8TQMa2zhEUiOL4gg+CEiNpMiePMWR0tr+YwdlcnjfyJtZlHu8yhoZPUTuFESHCBFjIOby/w/fy1PhNsl4HaLfAGQPDiOEfZxcPIADIQXXZZ8mG0FkG8SBAOapXBPwd95vAISEyNOAyLG7fE7YX4e6dSIDkDk+l+/pErkvU4Qv8wBsxRpyYSCQ6fL6FwjhcMgXq/3qGofK/KZmMdZjXtpsISqclao4jaQVijlfG7dK5qQgGqLfiN9ECeuOystLlKxwRF2UNtkY62ETPUtP/TYjzrqbFUKiRJHam1AXIDnq1kkF2wZEx57Z+9CIWkfzRnTiiEAcFB8nlVEmmsDBz1L//R7QEfO/h7Eejg6EOHmXv6+VZ5pJqv7/BpuPSGUdmq3lijFASieVskaA75DFKC2ILdDWb3DwZL0oRwEEQbPIDY6s1FM184R4CKQ15U3zxvL1cCiORWw0hpGZUzDOd5sE1LQOTm8SFbZFQPBeLuaBYAE2STrkJpIihNP08RykO5qlNB0jthnGY4u/n1HZeEKaOhxF1JE2mQv4naZ2xBG/JxcMsM4U9Te0rIHo07nhxLqyARhHVNgZgcIZEThPq6zrNN49lYFAfUfMiGpT4y1yJx5o/FUu6gnylJ/aCCLr5tkqRdM6fItslt/KCKqZ8j1Eia1rdgeCDXEg+YshjkvVv6E6kFloCOfIbyT0HLPl16zATsZ35bcKHMDVkm+/Kb9m0biSaXg3dRDPaby4wtIXxU0H0dGXIDBIYzuxGENQZBPsCgenc6nTt6uagQBZ5hX5gTKOvVNVzarMiQPHbkQ9zfix3EZuRjGPqyfP7lVpd4rIVnVlLtC2DhmQ7+JH7OUsuXJHpufsEBD93wKDrNCUbnaRp8kFAaIi9eflJYDRHEhECcLjmpZGDe/mUcR72Il4FjXCJlJ30/d4zni6z9Wz32CQ3fQBXJEppW1oWyfOFJvzQOY35bbuvQ6LIXAm//9wl/yaSj/R1G90WMKwvTxbUJIelZeBDh3mg8xBL/e6vFdpuwl26NChQ4cO/1f8DQLnoeKCLCsUAAAAAElFTkSuQmCC>

[image3]: <data:image/png;base64,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>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAIoAAAAXCAYAAADUf9f5AAAFfklEQVR4Xu2ZechmUxzHv0JZs4yIaF4Kydi3RmjKnkiWyJoUUmSaLCP0SrITBlnK1tglhWzx8o81WzOjlEKWEP4ZsmT5fd7fPfOce+49997nbd7nNXW/9e1533PPc+45v/P9Lec8Uo8ePXr06NGjx6qBMeOJaWOB1Yz7GG8z3mk83rhuqcdosLbxJOM9xuuN25cfZ3Ge8VrjtsbNE25qXN24lvE045zib9q2NJ4lt81MILX7AUVbGw4zPiRfS7rezYxrFv3Yx32N68nHxRanGHctnq/ADsZzja8Z/zY+WH48iTWMtxqvlhsOY79pXGKcHfWbbmxgfMV4lXxhLGaZ8di4Uwas698Mlxo3MW5ofKfm+Y0aGHaU4J3jxneNO8n36g3jlWoXy8WqriPwJ/lY7OsTNc+flNu6BL5wtFxVX6teKPRh8JflGwROlg+K0kcFFv+ecaOojXl8KveSHJjz88bF8kgU+IDxOw2EFvrhAJ8Xz/Hmtk2ZLhxj/FMeHQL2k+/F3KitDvcZn1F5vfcavzBepMGa6Md6vzI+ZTxCHkmzICR9qXqhEN6/N35snFW0sQiEwouawITGis8cGLMtjSEORJLOby/jcuNRSXsM1kbYJp3EOMF4gwZzQyiMT/+ZBnNFtL8a94jawz41OSjruEseJWMg+ofl6TvgdpXHb0WTUABhOUQTDLvI+I9cME0gvF1qnK96sRCtMMjs9EGCENXS+bFIjElazGFj4+5J247GR1QOsf8noTCXCeWFwrOwHykQAqLA9gHUHkSM1M4rXSgBbPahxp/VPXfTB8+9UGWxdBUJCIJI55drbwIGJg9jzLT9cePN8nD8jfFZzUwh2yYUUmNTuo2BYIhARNAUOPwtxg/kpcdbxt1KPRJ0EcpB8lz2g/FuVUNbE1KxDCMScKQ81aXzm4pQqOqJJrHHATbnJblBmSOkcP5MzfMkYr0ot01XXj75zWaMG3+Tp9cAapS/5HvVNfLtLz8EVApUw/3GhRrUJdiGILD3ih4JugglgEGvMf4iF09XBLFQVA0jEnC4Vo5QMNbbxrPTB3JhrF98BrBJbNZ41DYqYB9EykYyJ+xHTYgdugoFZ3hU+ZqG9cbFK6daIgvfSR1pEsMIBQQDEqLJf12xp/Fb42Wqr1lyyAki154DJwj645ldEMZ/Ve0F93RgTP5u0uCHxlPVXqPEmCN3aE6HXdCa2pqEsrNckXwGhP5pDm0C9x6Edu5hrlC1ZmnCNvKjbDq/sJEUzF3AOnJzvk4e1g+O2sL4E8pvDGuYJbdJV3I4mApCUZ+LECmInEQgUneKM+QHknOitrCvkL8raBIKbWnYDwYMlzdtCCIJ6YYwOoxYQnFHyoqPuaQ+7hriFEh62ULVcYkIeCeCQ3gpWB+XjrFQQuQkl6fjBbCWA43HDcG0kK7DLsaP5PdcAVwDMJ+5URvvx651BwtSFeKvi6DhUi4WSkg9E8o4RhDKYlUNwoA/qnzxQ9HDSziv1+ayCIjkOVVrkmHFwjspBLcu/uc7FJvUHKFQw7O57/lD1Uspiu+lynsLP19cosFc+FwoD93Z4m4aEQr48eJ/1ojQU5vfpHK/gNxdTAD2WaSywCjkf1fNbTeeiILwJF4Glxs/kV8bAyZIccMkzzQuKPo8VjxrwjryAjYVSQCF1Pnym+E2sCCM9LrcyxAJGx//LoEXvKD6kwo5l9ybEwrj32F82ni6/LcSIiaF9EwA735fvk7szt9EtrRWukAeVdPNDRE0JxQcgb3EnoxPOmO9/KTTxXFrwRfH5BsEtyo9HR2Yx3by8M0PZHXhtgmIn5CeM0Q8/jxVb3NHDd4/T1O3Oc5C2mm6lmdcxj9E7Y7fo0ePHj169OjRo8eqg/8Arko/26vls30AAAAASUVORK5CYII=>

[image5]: <data:image/png;base64,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>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABMAAAAXCAYAAADpwXTaAAAAiElEQVR4XmNgGAWjgGqAA4jTgJgHXYIcwAjErUBsjC5BLgAZ1AvELOgS5ACQ6wqAOA7KRgECQCxJIpYD4vlAPBmI+RiggBuIq4F4Fhl4BxB/BeJmIGZnoACYAPFqIJZBlyAVCAPxYiCWR5cgB2QBcQS6IDkAlGinArE0ugQ5AJQUeKH0KBhMAABVixNKp22j3QAAAABJRU5ErkJggg==>