-- ----------------------------------------------------------------------------
-- Lost Grimoire and Tome of Talents live at 2793 and 4156 (both deprecated,
-- dropless retail templates, confirmed unreferenced by any loot table, quest
-- reward/requirement, vendor or mail). They used to hijack 13149 and 25462,
-- which are retail quest items (Eldarathian Tome of Summoning Vol. 1, Tome of
-- Dusk - both required by quest 9637 "Kalynna's Request"); this file moves the
-- draft items off them and restores both, the same pattern
-- 08_consumable_id_swap.sql already used for Scroll of Reroll/Ban.
--
-- No world drop is defined here or anywhere in SQL: draft consumables drop only
-- for characters in draft mode, rolled per player in spelldraft_core.lua
-- (CONFIG.DRAFT_CONSUMABLE_DROPS). 05_prestige_draft_items.sql deletes any
-- leftover loot rows for them.
-- ----------------------------------------------------------------------------

-- 1. Swap target templates to entries 2793 (Lost Grimoire) and 4156 (Tome of
--    Talents)
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
  `bonding` = 0,
  -- 2793 was a readable book (PageText 243 in base data); a nonzero PageText
  -- makes the client open the reading UI on right-click instead of using it.
  `PageText` = 0,
  `Description` = 'Consuming this grimoire triggers an immediate bonus spell draft.'
WHERE `entry` = 2793;

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
  `bonding` = 0,
  `PageText` = 0,
  `Description` = 'Consuming this grimoire triggers a passive class talent draft.'
WHERE `entry` = 4156;

-- 2. Restore the hijacked retail item templates (13149 and 25462) to their
--    base-data values (data/sql/base/db_world/item_template.sql)
UPDATE `item_template` SET
  `class` = 0,
  `subclass` = 0,
  `name` = 'Eldarathian Tome of Summoning Vol. 1',
  `Quality` = 1,
  `Flags` = 0,
  `BuyPrice` = 0,
  `SellPrice` = 0,
  `InventoryType` = 0,
  `RequiredLevel` = 0,
  `stackable` = 1,
  `maxcount` = 1,
  `spellid_1` = 0,
  `spelltrigger_1` = 0,
  `spellcharges_1` = 0,
  `Material` = -1,
  `bonding` = 1,
  `Description` = ''
WHERE `entry` = 13149;

UPDATE `item_template` SET
  `class` = 12,
  `subclass` = 0,
  `name` = 'Tome of Dusk',
  `Quality` = 1,
  `Flags` = 2048,
  `BuyPrice` = 0,
  `SellPrice` = 0,
  `InventoryType` = 0,
  `RequiredLevel` = 0,
  `stackable` = 1,
  `maxcount` = 0,
  `spellid_1` = 0,
  `spelltrigger_1` = 0,
  `spellcharges_1` = 0,
  `Material` = -1,
  `bonding` = 4,
  `Description` = ''
WHERE `entry` = 25462;

-- 3. Restore the retail drop of Tome of Dusk (base data: Grand Warlock
--    Nethekurse, 100%, quest-required), which earlier installs of 05 deleted.
--    Eldarathian Tome of Summoning Vol. 1 has no creature drop in retail data
--    (it is quest 9637's other RequiredItemId, 25461 "Scroll of Dusk", that
--    drops - 13149 does not), so nothing is restored for it here.
DELETE FROM `creature_loot_template` WHERE `Entry` = 20568 AND `Item` = 25462;
INSERT INTO `creature_loot_template` (`Entry`, `Item`, `Reference`, `Chance`, `QuestRequired`, `LootMode`, `GroupId`, `MinCount`, `MaxCount`, `Comment`) VALUES
(20568, 25462, 0, 100, 1, 1, 0, 1, 1, 'Grand Warlock Nethekurse (1) - Tome of Dusk');
