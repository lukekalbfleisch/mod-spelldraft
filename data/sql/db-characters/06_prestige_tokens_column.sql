-- Safe addition of prestige_tokens column to prestige_stats if it does not exist
SET @dbname = DATABASE();
SET @tablename = "prestige_stats";
SET @columnname = "prestige_tokens";
SET @preparedStatement = (SELECT IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
   WHERE table_name = @tablename
     AND column_name = @columnname
     AND table_schema = @dbname) > 0,
  "SELECT 1",
  "ALTER TABLE `prestige_stats` ADD COLUMN `prestige_tokens` INT UNSIGNED NOT NULL DEFAULT 0"
));
PREPARE stmt FROM @preparedStatement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

