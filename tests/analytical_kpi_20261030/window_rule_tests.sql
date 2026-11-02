DO $$
BEGIN
 IF pg_temp.classify_checkin_window('05:59','06:00','07:30') <> 'ON_TIME'
 OR pg_temp.classify_checkin_window('06:00','06:00','07:30') <> 'ON_TIME'
 OR pg_temp.classify_checkin_window('07:30','06:00','07:30') <> 'ON_TIME'
 OR pg_temp.classify_checkin_window('07:30:01','06:00','07:30') <> 'LATE'
 OR pg_temp.classify_checkin_window('07:30',NULL,'07:30') <> 'UNKNOWN'
 OR pg_temp.classify_checkin_window('00:30','23:00','01:00') <> 'UNKNOWN'
 THEN RAISE EXCEPTION 'Check-in classification failed'; END IF;
 IF pg_temp.classify_checkout_window('15:59','16:00','20:00') <> 'BEFORE_WINDOW'
 OR pg_temp.classify_checkout_window('16:00','16:00','20:00') <> 'IN_WINDOW'
 OR pg_temp.classify_checkout_window('20:00','16:00','20:00') <> 'IN_WINDOW'
 OR pg_temp.classify_checkout_window('20:00:01','16:00','20:00') <> 'AFTER_WINDOW'
 OR pg_temp.classify_checkout_window('17:00','16:00',NULL) <> 'UNKNOWN'
 OR pg_temp.classify_checkout_window('00:30','23:00','01:00') <> 'UNKNOWN'
 THEN RAISE EXCEPTION 'Checkout classification failed'; END IF;
END $$;
SELECT 'window rule boundaries passed' AS result;
ROLLBACK;
