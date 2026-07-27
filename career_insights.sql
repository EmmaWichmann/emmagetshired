-- ============================================================
-- career_insights.sql
--
-- Read-only analysis queries against EmmaGetsHired's real, current
-- schema (see database.py -> init_db()). These are portfolio/analysis
-- queries, written to be read and run on their own — they are NOT
-- imported or executed by the Flask app. The app's equivalent
-- read/write functions live in database.py (e.g. get_career_action_
-- count_this_week, get_career_action_counts_by_type) — those were
-- written independently for the app's own needs, so don't assume this
-- file is "powering" any page just because the topic overlaps.
--
-- Every query below is scoped to one visitor via a `:user_id` named
-- parameter (bind it before running, e.g. in the sqlite3 CLI:
--   sqlite3 onemoretime.db
--   .param set :user_id 'some-uuid-here'
--   -- then paste a query
-- or from Python: conn.execute(sql, {"user_id": "some-uuid-here"}) ).
--
-- Relevant tables:
--   career_actions(id, user_id, action_type, title, log_date)
--     -- one row per completed career move: Today card, Walk and
--     -- Speak, LinkedIn Message Creator, Career Event Finder. This is
--     -- the single source of truth for Progress.
-- ============================================================


-- 1. Career actions completed this week
-- Demonstrates: SELECT, WHERE, an aggregate function (COUNT)
SELECT COUNT(*) AS actions_this_week
FROM career_actions
WHERE user_id = :user_id
  AND log_date >= date('now', '-6 days');


-- 2. Actions grouped by activity type (all-time)
-- Demonstrates: SELECT, WHERE, GROUP BY, ORDER BY, COUNT
SELECT
    action_type,
    COUNT(*) AS total
FROM career_actions
WHERE user_id = :user_id
GROUP BY action_type
ORDER BY total DESC;


-- 3. Activity totals by week
-- strftime('%Y-W%W', ...) buckets each log_date into its week-of-year,
-- so totals can be compared week over week rather than day by day.
-- Demonstrates: SELECT, WHERE, GROUP BY, ORDER BY, COUNT
SELECT
    strftime('%Y-W%W', log_date) AS week,
    COUNT(*) AS total
FROM career_actions
WHERE user_id = :user_id
GROUP BY week
ORDER BY week ASC;


-- 4. Most frequent action type, with a friendly label
-- Demonstrates: SELECT, WHERE, GROUP BY, ORDER BY, COUNT, CASE
SELECT
    action_type,
    COUNT(*) AS total,
    CASE action_type
        WHEN 'speech'       THEN 'Walk and Speak practice'
        WHEN 'linkedin'     THEN 'LinkedIn messages'
        WHEN 'event'        THEN 'Event searches'
        WHEN 'job_review'   THEN 'Job description reviews'
        WHEN 'networking'   THEN 'Networking follow-ups'
        ELSE action_type
    END AS friendly_label
FROM career_actions
WHERE user_id = :user_id
GROUP BY action_type
ORDER BY total DESC
LIMIT 1;


-- 5. Most active career-action day (all-time)
-- Demonstrates: SELECT, WHERE, GROUP BY, ORDER BY (multi-column), COUNT
SELECT
    log_date,
    COUNT(*) AS total
FROM career_actions
WHERE user_id = :user_id
GROUP BY log_date
ORDER BY total DESC, log_date DESC
LIMIT 1;


-- 6. Recent seven-day activity trend, with a running total
-- The CTE (last_seven_days) first collapses the raw rows into one total
-- per day — the outer SELECT then adds a window function that sums those
-- daily totals as it walks forward through the week, so each row shows
-- "how many actions so far this week" as of that day.
-- Demonstrates: a CTE, SELECT, WHERE, GROUP BY, ORDER BY, COUNT,
-- a window function (SUM ... OVER)
WITH last_seven_days AS (
    SELECT
        log_date,
        COUNT(*) AS daily_total
    FROM career_actions
    WHERE user_id = :user_id
      AND log_date >= date('now', '-6 days')
    GROUP BY log_date
)
SELECT
    log_date,
    daily_total,
    SUM(daily_total) OVER (
        ORDER BY log_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM last_seven_days
ORDER BY log_date ASC;
