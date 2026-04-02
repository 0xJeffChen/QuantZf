DELIMITER $$

DROP PROCEDURE IF EXISTS init_bars_partitions $$
CREATE PROCEDURE init_bars_partitions(IN start_date DATE, IN months_ahead INT)
BEGIN
  DECLARE d DATE;
  DECLARE next_d DATE;
  DECLARE end_d DATE;
  DECLARE parts LONGTEXT;

  SET start_date = DATE_FORMAT(start_date, '%Y-%m-01');
  SET end_d = DATE_ADD(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL months_ahead MONTH);

  SET parts = CONCAT(
    "PARTITION p_before",
    DATE_FORMAT(start_date, '%Y%m'),
    " VALUES LESS THAN ('",
    DATE_FORMAT(start_date, '%Y-%m-%d'),
    "'),"
  );

  SET d = start_date;
  WHILE d < end_d DO
    SET next_d = DATE_ADD(d, INTERVAL 1 MONTH);
    SET parts = CONCAT(
      parts,
      "PARTITION p",
      DATE_FORMAT(d, '%Y%m'),
      " VALUES LESS THAN ('",
      DATE_FORMAT(next_d, '%Y-%m-%d'),
      "'),"
    );
    SET d = next_d;
  END WHILE;

  SET parts = CONCAT(parts, "PARTITION pmax VALUES LESS THAN (MAXVALUE)");

  SET @sql = CONCAT("ALTER TABLE bars PARTITION BY RANGE COLUMNS(ts) (", parts, ")");
  PREPARE stmt FROM @sql;
  EXECUTE stmt;
  DEALLOCATE PREPARE stmt;
END $$

DROP PROCEDURE IF EXISTS extend_bars_partitions $$
CREATE PROCEDURE extend_bars_partitions(IN months_ahead INT)
BEGIN
  DECLARE last_name VARCHAR(64);
  DECLARE last_month_start DATE;
  DECLARE d DATE;
  DECLARE next_d DATE;
  DECLARE end_d DATE;
  DECLARE parts LONGTEXT;

  SET end_d = DATE_ADD(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL months_ahead MONTH);

  SELECT MAX(PARTITION_NAME)
  INTO last_name
  FROM information_schema.PARTITIONS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'bars'
    AND PARTITION_NAME REGEXP '^p[0-9]{6}$';

  IF last_name IS NULL THEN
    CALL init_bars_partitions('2010-01-01', months_ahead);
  ELSE
    SET last_month_start = STR_TO_DATE(CONCAT(SUBSTRING(last_name, 2, 6), '01'), '%Y%m%d');
    SET d = DATE_ADD(last_month_start, INTERVAL 1 MONTH);

    IF d < end_d THEN
      SET parts = "";
      WHILE d < end_d DO
        SET next_d = DATE_ADD(d, INTERVAL 1 MONTH);
        SET parts = CONCAT(
          parts,
          "PARTITION p",
          DATE_FORMAT(d, '%Y%m'),
          " VALUES LESS THAN ('",
          DATE_FORMAT(next_d, '%Y-%m-%d'),
          "'),"
        );
        SET d = next_d;
      END WHILE;

      SET parts = CONCAT(parts, "PARTITION pmax VALUES LESS THAN (MAXVALUE)");
      SET @sql = CONCAT("ALTER TABLE bars REORGANIZE PARTITION pmax INTO (", parts, ")");
      PREPARE stmt FROM @sql;
      EXECUTE stmt;
      DEALLOCATE PREPARE stmt;
    END IF;
  END IF;
END $$

DELIMITER ;

CALL init_bars_partitions('2010-01-01', 36);
