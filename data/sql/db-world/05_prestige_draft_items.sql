-- ----------------------------------------------------------------------------
-- These four items (Scroll of Reroll, Scroll of Ban, Lost Grimoire, Tome of
-- Talents) only matter in classless draft mode - the prestige-draft economy's
-- reroll/ban/bonus-draft/passive-draft currency. Traditional mode (two fixed
-- classes + native talent trees via /mct) is the server default and never
-- reads any of this, so world-drop loot for these items has no player who can
-- use it for most characters. World drops removed 2026-09-21 (and, for the
-- ids 08 migrated to, 2026-09-24); the item templates stay defined because
-- draft mode's own code paths (first-login Tome of Talents grant, the prestige
-- shop, the per-player drop roll in spelldraft_core.lua) still need them.
-- ----------------------------------------------------------------------------

-- 1. Clean up stale custom entries (99001, 99002, 99003)
DELETE FROM `item_template` WHERE `entry` IN (99001, 99002, 99003);

-- 2. Override existing unused retail templates to match our custom design.
--    Scroll of Reroll and Scroll of Ban live at 4427 and 1078 and are defined
--    in 08_consumable_id_swap.sql. This file must NOT touch 17731 or 30811:
--    those are retail quest items (Scroll of Celebras, Scroll of Demonic
--    Unbanishing) that 08 restores, and every re-apply of this file used to
--    overwrite them again and delete their quest drops.
UPDATE `item_template` SET
  `class` = 0,
  `subclass` = 0,
  `name` = 'Lost Grimoire',
  `Quality` = 3,
  `Flags` = 0,
  `BuyPrice` = 5000,
  `SellPrice` = 1250,
  `InventoryType` = 0,
  `RequiredLevel` = 1,
  `stackable` = 5,
  `maxcount` = 0,
  `spellid_1` = 24312,
  `spelltrigger_1` = 0,
  `spellcharges_1` = -1,
  `Material` = -1,
  `Description` = 'Consuming this grimoire triggers an immediate bonus spell draft.'
WHERE `entry` = 13149;

UPDATE `item_template` SET
  `class` = 12,
  `subclass` = 0,
  `name` = 'Tome of Talents',
  `Quality` = 3,
  `Flags` = 0,
  `BuyPrice` = 5000,
  `SellPrice` = 1250,
  `InventoryType` = 0,
  `RequiredLevel` = 1,
  `stackable` = 5,
  `maxcount` = 0,
  `spellid_1` = 24312,
  `spelltrigger_1` = 0,
  `spellcharges_1` = -1,
  `Material` = -1,
  `Description` = 'Consuming this grimoire triggers a passive class talent draft.'
WHERE `entry` = 25462;

-- 3. Remove every world drop of the four draft consumables (idempotent: also
--    removes rows any earlier install of this module injected). They are
--    listed by their FINAL ids; 08 moved Reroll/Ban off 17731/30811, and
--    deleting by the old ids left 7762 injected rows each on 4427 and 1078.
--    Draft-mode characters get their drops from spelldraft_core.lua instead,
--    which rolls only for players in draft mode (CONFIG.DRAFT_CONSUMABLE_DROPS).
DELETE FROM `reference_loot_template` WHERE `Entry` = 99000;
DELETE FROM `creature_loot_template` WHERE `Reference` = 99000;
DELETE FROM `creature_loot_template` WHERE `Item` IN (4427, 1078, 13149, 25462);
