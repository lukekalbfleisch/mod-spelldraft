-- Safe addition of offered_is_talent to prestige_stats if not exists
SET @dbname = DATABASE();
SET @tablename = "prestige_stats";
SET @columnname = "offered_is_talent";
SET @preparedStatement = (SELECT IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
   WHERE table_name = @tablename
     AND column_name = @columnname
     AND table_schema = @dbname) > 0,
  "SELECT 1",
  "ALTER TABLE `prestige_stats` ADD COLUMN `offered_is_talent` TINYINT NOT NULL DEFAULT 0"
));
PREPARE stmt FROM @preparedStatement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

