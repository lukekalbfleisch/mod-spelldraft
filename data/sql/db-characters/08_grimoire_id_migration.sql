-- Migrate existing player items from old hijacked IDs to new consumable IDs
-- (same pattern as 02_consumable_id_migration.sql, for Lost Grimoire and Tome
-- of Talents; see db-world/36_grimoire_id_swap.sql).
UPDATE `item_instance` SET `itemEntry` = 2793 WHERE `itemEntry` = 13149;
UPDATE `item_instance` SET `itemEntry` = 4156 WHERE `itemEntry` = 25462;
