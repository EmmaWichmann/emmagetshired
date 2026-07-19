-- ============================================================
-- sql_practice.sql
-- Every real query used in onemoretime, pulled out into one file so
-- you can read through them without digging through database.py.
-- Ordered easiest -> hardest. Try covering the answer and writing
-- each one yourself before checking.
--
-- Simplified for teaching: the real app.py schema adds a user_id
-- column to every table (see database.py) so each visitor's data
-- stays private without needing a login. That column is left out
-- here so the core SQL patterns stay easy to read.
-- ============================================================


-- 1. CREATE TABLE — defines the shape of your data
CREATE TABLE categories (
    id    TEXT PRIMARY KEY,
    emoji TEXT NOT NULL,
    name  TEXT NOT NULL,
    sub   TEXT,
    pts   INTEGER NOT NULL DEFAULT 1,
    color TEXT
);

CREATE TABLE logs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    cat_id   TEXT NOT NULL,
    pts      INTEGER NOT NULL,
    log_date TEXT NOT NULL,
    FOREIGN KEY (cat_id) REFERENCES categories(id)
);


-- 2. INSERT — add a row
INSERT INTO logs (cat_id, pts, log_date) VALUES ('job', 1, '2026-07-15');


-- 3. SELECT * — get everything, no filtering
SELECT * FROM categories;


-- 4. SELECT with WHERE — filter rows
SELECT * FROM logs WHERE cat_id = 'job';


-- 5. UPDATE — change existing rows (ALWAYS use WHERE, or you'll update every row)
UPDATE categories SET name = 'Applications', pts = 2 WHERE id = 'job';


-- 6. DELETE — remove rows (same WHERE warning applies)
DELETE FROM rewards WHERE id = 3;


-- 7. Aggregate functions — collapse many rows into one number
SELECT COUNT(*) AS total_logs FROM logs;
SELECT SUM(pts) AS total_points FROM logs;
SELECT COUNT(DISTINCT log_date) AS active_days FROM logs;


-- 8. COALESCE — handle NULL (SUM of zero rows returns NULL, not 0)
SELECT COALESCE(SUM(pts), 0) AS total FROM logs;


-- 9. GROUP BY — aggregate per group instead of over the whole table
-- "how many logs per category?"
SELECT cat_id, COUNT(*) AS n
FROM logs
GROUP BY cat_id;


-- 10. GROUP BY + WHERE together — filter first, THEN group
-- "points logged in the last 7 days, per day"
SELECT log_date, SUM(pts) AS total
FROM logs
WHERE log_date >= date('now', '-6 days')
GROUP BY log_date
ORDER BY log_date ASC;


-- 11. JOIN — combine two tables that share a key
-- categories.id matches logs.cat_id, so we can pull category info
-- without repeating it in every log row
SELECT c.name, l.pts, l.log_date
FROM logs l
JOIN categories c ON l.cat_id = c.id;


-- 12. LEFT JOIN — like JOIN, but keeps rows from the left table even
-- if there's no match on the right (here: categories with ZERO logs
-- still show up, with total = NULL, which COALESCE turns into 0)
SELECT c.name, COALESCE(SUM(l.pts), 0) AS total
FROM categories c
LEFT JOIN logs l ON l.cat_id = c.id
GROUP BY c.id
ORDER BY total DESC;


-- 13. DISTINCT — remove duplicate values
-- used for streak calculation: collapses multiple same-day logs to 1 date
SELECT DISTINCT log_date FROM logs ORDER BY log_date DESC;


-- ============================================================
-- Practice prompts — try writing these yourself against this schema
-- ============================================================
-- a) Get the 3 categories with the most total points logged
-- b) Get every log entry made in the current month
-- c) Get the average points per log entry (hint: AVG())
-- d) Get the name of the category with the single most logs (hint: ORDER BY + LIMIT)
-- e) Count how many rewards are still unclaimed
