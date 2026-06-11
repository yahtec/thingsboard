-- Correction des ts des 5 resolutions evt_* injectees le 2026-06-10 sur 2623001001
-- (inject-evt-resolution.py avait pose l'heure du PC; heure reelle RTC = 09:20,
--  echelonnee a la seconde pour eviter les collisions de PK (entity_id,key,ts)).
-- Valide par l'utilisateur le 2026-06-10.

BEGIN;

-- f88/sub50 : 12:34:52.843 -> 09:20:00
INSERT INTO ts_kv (entity_id, key, ts, bool_v, str_v, long_v, dbl_v, json_v)
SELECT entity_id, key, 1781076000000, bool_v,
  CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_time') THEN '09:20:00' ELSE str_v END,
  CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_id') THEN 1781076000 ELSE long_v END,
  dbl_v, json_v
FROM ts_kv WHERE entity_id='f85bb930-5f4c-11f1-a0da-59181ba6b240' AND ts=1781087692843;
DELETE FROM ts_kv WHERE entity_id='f85bb930-5f4c-11f1-a0da-59181ba6b240' AND ts=1781087692843;

-- f88/sub51 : 12:44:17.862 -> 09:20:01
INSERT INTO ts_kv (entity_id, key, ts, bool_v, str_v, long_v, dbl_v, json_v)
SELECT entity_id, key, 1781076001000, bool_v,
  CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_time') THEN '09:20:01' ELSE str_v END,
  CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_id') THEN 1781076001 ELSE long_v END,
  dbl_v, json_v
FROM ts_kv WHERE entity_id='f85bb930-5f4c-11f1-a0da-59181ba6b240' AND ts=1781088257862;
DELETE FROM ts_kv WHERE entity_id='f85bb930-5f4c-11f1-a0da-59181ba6b240' AND ts=1781088257862;

-- f88/sub65 : 12:44:18.533 -> 09:20:02
INSERT INTO ts_kv (entity_id, key, ts, bool_v, str_v, long_v, dbl_v, json_v)
SELECT entity_id, key, 1781076002000, bool_v,
  CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_time') THEN '09:20:02' ELSE str_v END,
  CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_id') THEN 1781076002 ELSE long_v END,
  dbl_v, json_v
FROM ts_kv WHERE entity_id='f85bb930-5f4c-11f1-a0da-59181ba6b240' AND ts=1781088258533;
DELETE FROM ts_kv WHERE entity_id='f85bb930-5f4c-11f1-a0da-59181ba6b240' AND ts=1781088258533;

-- f91/sub50 : 12:44:19.155 -> 09:20:03
INSERT INTO ts_kv (entity_id, key, ts, bool_v, str_v, long_v, dbl_v, json_v)
SELECT entity_id, key, 1781076003000, bool_v,
  CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_time') THEN '09:20:03' ELSE str_v END,
  CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_id') THEN 1781076003 ELSE long_v END,
  dbl_v, json_v
FROM ts_kv WHERE entity_id='f85bb930-5f4c-11f1-a0da-59181ba6b240' AND ts=1781088259155;
DELETE FROM ts_kv WHERE entity_id='f85bb930-5f4c-11f1-a0da-59181ba6b240' AND ts=1781088259155;

-- f93/sub50 : 12:44:19.770 -> 09:20:04
INSERT INTO ts_kv (entity_id, key, ts, bool_v, str_v, long_v, dbl_v, json_v)
SELECT entity_id, key, 1781076004000, bool_v,
  CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_time') THEN '09:20:04' ELSE str_v END,
  CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_id') THEN 1781076004 ELSE long_v END,
  dbl_v, json_v
FROM ts_kv WHERE entity_id='f85bb930-5f4c-11f1-a0da-59181ba6b240' AND ts=1781088259770;
DELETE FROM ts_kv WHERE entity_id='f85bb930-5f4c-11f1-a0da-59181ba6b240' AND ts=1781088259770;

-- ts_kv_latest pointait sur le bundle f93 (1781088259770) : realignement
UPDATE ts_kv_latest SET ts=1781076004000,
  str_v = CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_time') THEN '09:20:04' ELSE str_v END,
  long_v = CASE WHEN key=(SELECT key_id FROM key_dictionary WHERE key='evt_id') THEN 1781076004 ELSE long_v END
WHERE entity_id='f85bb930-5f4c-11f1-a0da-59181ba6b240'
  AND key IN (SELECT key_id FROM key_dictionary WHERE key LIKE 'evt%')
  AND ts=1781088259770;

COMMIT;
