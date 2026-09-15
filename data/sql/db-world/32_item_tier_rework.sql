-- Item pack follow-up from in-game testing:
--
-- 1. BUG FIX: `spellcharges_1 = -1` does NOT mean "infinite uses" in this
--    engine - it means "expendable, destroyed on the charge that hits 0"
--    (Spell.cpp ~5438: `if (SpellCharges < 0) expendable = true;`, then the
--    very first use decrements the stored charge from -1 to 0, and
--    `if (expendable && withoutCharges) DestroyItemCount(...)` fires
--    immediately). `0` is the actual "no charge tracking, cast forever"
--    value (the whole block is skippped by `if (proto->Spells[i].SpellCharges)`
--    at the top). This affected 6 of the 8 items, not just Manastone -
--    Soul Leech/Bladestorm/Poison Wind Censer/Earthshaker/Fiery Avenger would
--    all have vanished the first time their on-hit proc fired.
--
-- 2. Visual/subclass corrections from testing:
--    - Fungi Tunic: was Leather (subclass 2), should be Mail (3)
--    - Bladestorm: was a 2H sword with a red-plate look; now a 1H sword
--      ("Krol Blade"'s displayid - the closest slender-blade look available
--      in WotLK-era item art to an actual katana, which is largely a
--      post-WotLK aesthetic)
--    - Poison Wind Censer: was a fist weapon; now a 2H polearm
--      ("Bloodfall"'s displayid)
--    - Fiery Avenger: was wearing Thunderfury's model; now "Blazefury"'s,
--      an actually fire-themed 1H sword. Stays 1H per the user's own call.
--    - Earthshaker: was a 2H mace wearing Sulfuras's (fiery) model; now a 2H
--      SWORD (matching EQ's original Earthshaker) with "Boulderfist
--      Claymore"'s earthy/stone displayid.
--
-- 3. Renamed to "<Name> +1" and gated to RequiredLevel 60 - these were
--    usable at level 1 with no gate at all, which is the real source of
--    "very, very strong": an epic/legendary-tier item with zero investment
--    required. They keep their original (strong, endgame-appropriate) stats.
--
-- 4. New Rare (blue, Quality 3)  tier below them, level ~40-42, roughly half
--    the stats/weapon damage, using the ORIGINAL un-suffixed names - meant
--    to be the leveling-era item, with the "+1" versions as the later
--    upgrade. Entries 100014-100021. The 6 proc/buff items reuse their "+1"
--    counterpart's spell (993020/993031/993032/993003/993033/993035/993036)
--    rather than needing 6 new near-duplicate spells - only Manastone's
--    on-use numbers needed to actually scale, so it gets its own smaller
--    spell (993039, added in 28_eq_spell_pack.sql).

-- ============================================================
-- Part 1: fix + relevel + rename the existing 8 (100006-100013)
-- ============================================================

UPDATE `item_template` SET
    `name` = 'Manastone +1', `RequiredLevel` = 60, `spellcharges_1` = 0
WHERE `entry` = 100006;

UPDATE `item_template` SET
    `name` = 'Fungi Tunic +1', `RequiredLevel` = 60,
    `subclass` = 3, `displayid` = 64838
WHERE `entry` = 100007;

UPDATE `item_template` SET
    `name` = 'Soul Leech +1', `RequiredLevel` = 60, `spellcharges_1` = 0
WHERE `entry` = 100008;

UPDATE `item_template` SET
    `name` = 'Bladestorm +1', `RequiredLevel` = 60, `spellcharges_1` = 0,
    `subclass` = 7, `InventoryType` = 13, `displayid` = 8090
WHERE `entry` = 100009;

UPDATE `item_template` SET
    `name` = 'Poison Wind Censer +1', `RequiredLevel` = 60, `spellcharges_1` = 0,
    `subclass` = 6, `InventoryType` = 17, `displayid` = 64554
WHERE `entry` = 100010;

UPDATE `item_template` SET
    `name` = 'Rubicite Breastplate +1', `RequiredLevel` = 60
WHERE `entry` = 100011;

UPDATE `item_template` SET
    `name` = 'Earthshaker +1', `RequiredLevel` = 60, `spellcharges_1` = 0,
    `subclass` = 8, `displayid` = 39491
WHERE `entry` = 100012;

UPDATE `item_template` SET
    `name` = 'Fiery Avenger +1', `RequiredLevel` = 60, `spellcharges_1` = 0,
    `displayid` = 41389
WHERE `entry` = 100013;

-- ============================================================
-- Part 2: new Rare (blue) tier, level ~40-42 (100014-100021)
-- ============================================================

DELETE FROM `item_template` WHERE `entry` BETWEEN 100014 AND 100021;

INSERT INTO `item_template`
    (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `Flags`,
     `BuyPrice`, `SellPrice`, `InventoryType`, `AllowableClass`, `AllowableRace`,
     `ItemLevel`, `RequiredLevel`, `maxcount`, `stackable`, `bonding`, `Material`, `sheath`,
     `stat_type1`, `stat_value1`, `stat_type2`, `stat_value2`, `stat_type3`, `stat_value3`,
     `dmg_min1`, `dmg_max1`, `dmg_type1`, `delay`, `armor`,
     `spellid_1`, `spelltrigger_1`, `spellcharges_1`, `spellppmRate_1`, `spellcooldown_1`,
     `description`)
VALUES
    (100014, 4, 0, 'Manastone', 8232, 3, 0,
     0, 8000, 12, -1, -1,
     55, 42, 1, 1, 0, 1, 0,
     5, 20, 0, 0, 0, 0,
     0, 0, 0, 0, 0,
     993039, 0, 0, 0, -1,
     'A lesser echo of the true Manastone. Converts life force into mana.'),

    (100015, 4, 3, 'Fungi Tunic', 64838, 3, 0,
     0, 9000, 5, -1, -1,
     55, 42, 0, 1, 0, 8, 0,
     7, 30, 6, 20, 5, 15,
     0, 0, 0, 0, 400,
     993035, 1, 0, 0, -1,
     'A young offshoot of the fungi that grow deep underground.'),

    (100016, 2, 15, 'Soul Leech', 64671, 3, 0,
     0, 15000, 13, -1, -1,
     55, 42, 0, 1, 0, 1, 3,
     3, 30, 7, 22, 0, 0,
     180, 270, 0, 1600, 0,
     993020, 2, 0, 0, -1,
     'The blade drinks, but only shallowly.'),

    (100017, 2, 7, 'Bladestorm', 8090, 3, 0,
     0, 27000, 13, -1, -1,
     55, 42, 0, 1, 0, 1, 3,
     4, 45, 7, 35, 0, 0,
     550, 820, 0, 3400, 0,
     993031, 2, 0, 0, -1,
     'A blade that yearns for the storm it will one day become.'),

    (100018, 2, 6, 'Poison Wind Censer', 64554, 3, 0,
     0, 18000, 17, -1, -1,
     55, 42, 0, 1, 0, 1, 1,
     3, 35, 7, 25, 0, 0,
     220, 310, 0, 2000, 0,
     993032, 2, 0, 0, -1,
     'A censer of faintly choking wind.'),

    (100019, 4, 4, 'Rubicite Breastplate', 33635, 3, 0,
     0, 13500, 5, -1, -1,
     55, 42, 0, 1, 0, 6, 0,
     4, 40, 7, 45, 12, 20,
     0, 0, 0, 0, 900,
     993036, 1, 0, 0, -1,
     'Red plate of a lesser forging. It remembers only a little of how to mend itself.'),

    (100020, 2, 8, 'Earthshaker', 39491, 3, 0,
     0, 27000, 17, -1, -1,
     55, 42, 0, 1, 0, 1, 3,
     4, 48, 7, 38, 0, 0,
     560, 840, 0, 3500, 0,
     993003, 2, 0, 0, -1,
     'The earth stirs, but does not yet answer.'),

    (100021, 2, 7, 'Fiery Avenger', 41389, 3, 0,
     0, 24000, 13, -1, -1,
     55, 42, 0, 1, 0, 1, 3,
     4, 33, 7, 28, 5, 18,
     230, 340, 0, 2600, 0,
     993033, 2, 0, 0, -1,
     'A spark of righteous flame, not yet a blaze.');
