BEGIN TRANSACTION;
CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT
            );
INSERT INTO "events" VALUES(20,212697019,'2025-11-22T23:05:35.836902','craving','{"level": 1}');
INSERT INTO "events" VALUES(21,212697019,'2025-11-22T23:05:52.340384','craving','{"level": 1}');
INSERT INTO "events" VALUES(22,212697019,'2025-11-22T23:06:45.587514','diary','{"text": "Drunk few such\n-\nThink"}');
INSERT INTO "events" VALUES(23,212697019,'2025-11-23T12:28:34.858759','diary','{"text": "grttrggtrtrgrttrgrthtrwggtbwrthgb gtrgtrhtrh btgrhbtrhgrt. ghhtrrhtrhtrh htrhtrhtr"}');
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('events',23);
CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                created_at TEXT,
                last_sober_date TEXT,
                streak INTEGER,
                goal TEXT,
                sober_since_date TEXT,
                weekly_alcohol_spend REAL,
                weekly_alcohol_hours REAL,
                morning_time TEXT,
                evening_time TEXT,
                last_morning_sent_date TEXT,
                last_evening_sent_date TEXT,
                waiting_for_craving_number INTEGER,
                waiting_for_sober_since INTEGER,
                waiting_for_weekly_spend INTEGER,
                waiting_for_weekly_hours INTEGER,
                waiting_for_morning_time INTEGER,
                waiting_for_evening_time INTEGER
            , onboarding_completed INTEGER DEFAULT 0, motivation TEXT, triggers TEXT, waiting_for_diary_entry INTEGER DEFAULT 0, waiting_for_goal_motivation INTEGER DEFAULT 0, waiting_for_triggers INTEGER DEFAULT 0, goals TEXT, reasons TEXT, waiting_for_goal_add INTEGER DEFAULT 0, waiting_for_reasons_add INTEGER DEFAULT 0);
INSERT INTO "users" VALUES(212697019,'2025-11-21T23:20:53.436796',NULL,0,'не задана','2025-11-08',3000.0,30.0,'11:00','21:00',NULL,NULL,0,0,0,0,0,0,1,'','[]',0,0,0,'[]','[]',0,0);
COMMIT;
