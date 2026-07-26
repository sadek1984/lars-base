-- ============================================================================
-- LARS :: Food-Poisoning KPI views  (DuckDB)
-- Executed automatically at the end of ingest_poisoning_workbook().
-- Every view is bilingual-ready: *_ar columns feed the Arabic UI directly.
-- ============================================================================

-- 1. Headline card row -------------------------------------------------------
CREATE OR REPLACE VIEW v_poisoning_kpi_headline AS
SELECT
    COUNT(*)                                                    AS incidents,
    SUM(cases_count)                                            AS people_affected,
    COUNT(DISTINCT license_no)                                  AS establishments,
    COUNT(DISTINCT municipality_key)                            AS municipalities,
    SUM(CASE WHEN decision_code = 'CONVICTED' THEN 1 ELSE 0 END) AS convictions,
    ROUND(100.0 * SUM(CASE WHEN decision_code = 'CONVICTED' THEN 1 ELSE 0 END)
          / NULLIF(COUNT(*), 0), 1)                             AS conviction_rate_pct,
    ROUND(MEDIAN(incubation_hours), 2)                          AS median_incubation_h,
    MAX(cases_count)                                            AS largest_cluster,
    MAX(incident_date)                                          AS last_incident
FROM poisoning_incidents;

-- 2. Municipality league table (the map / bar chart) -------------------------
CREATE OR REPLACE VIEW v_poisoning_by_municipality AS
SELECT
    municipality,
    municipality_key,
    COUNT(*)                                                     AS incidents,
    SUM(cases_count)                                             AS people_affected,
    SUM(CASE WHEN decision_code = 'CONVICTED' THEN 1 ELSE 0 END) AS convictions,
    ROUND(AVG(cases_count), 1)                                   AS avg_cluster_size,
    MAX(incident_date)                                           AS last_incident
FROM poisoning_incidents
GROUP BY 1, 2
ORDER BY people_affected DESC, incidents DESC;

-- 3. Monthly trend (seasonality — the line chart) ----------------------------
CREATE OR REPLACE VIEW v_poisoning_monthly AS
SELECT
    date_trunc('month', incident_date)                           AS month,
    strftime(incident_date, '%Y-%m')                             AS month_label,
    COUNT(*)                                                     AS incidents,
    SUM(cases_count)                                             AS people_affected,
    SUM(CASE WHEN decision_code = 'CONVICTED' THEN 1 ELSE 0 END) AS convictions
FROM poisoning_incidents
GROUP BY 1, 2
ORDER BY 1;

-- 4. Repeat-offender watchlist (the single most actionable view) -------------
CREATE OR REPLACE VIEW v_poisoning_repeat_offenders AS
SELECT
    license_no,
    any_value(establishment_name)                                AS establishment_name,
    any_value(municipality)                                      AS municipality,
    COUNT(*)                                                     AS incidents,
    SUM(cases_count)                                             AS people_affected,
    SUM(CASE WHEN decision_code = 'CONVICTED' THEN 1 ELSE 0 END) AS convictions,
    MIN(incident_date)                                           AS first_incident,
    MAX(incident_date)                                           AS last_incident,
    date_diff('day', MIN(incident_date), MAX(incident_date))     AS span_days
FROM poisoning_incidents
GROUP BY license_no
HAVING COUNT(*) > 1
ORDER BY incidents DESC, people_affected DESC;

-- 5. Incubation-window / likely-agent profile (the epidemiology chart) -------
CREATE OR REPLACE VIEW v_poisoning_agent_profile AS
SELECT
    agent_class_code,
    any_value(agent_class_ar)                                    AS agent_class_ar,
    any_value(agent_class_en)                                    AS agent_class_en,
    COUNT(*)                                                     AS incidents,
    SUM(cases_count)                                             AS people_affected,
    ROUND(MIN(incubation_hours), 2)                              AS min_incubation_h,
    ROUND(MAX(incubation_hours), 2)                              AS max_incubation_h
FROM poisoning_incidents
GROUP BY agent_class_code
ORDER BY incidents DESC;

-- 6. Committee-decision audit: does the ministry guide get applied evenly? ---
CREATE OR REPLACE VIEW v_poisoning_decision_audit AS
SELECT
    incident_id,
    incident_date,
    municipality,
    establishment_name,
    incubation_hours,
    cases_count,
    kinship_en,
    decision_en,
    attribution_flag,
    attribution_reason_en,
    attribution_reason_ar,
    decision_matches_advisory,
    CASE
        WHEN decision_matches_advisory THEN 'ALIGNED'
        WHEN decision_code = 'NOT_CONVICTED' THEN 'REVIEW: cleared despite supportive evidence'
        WHEN decision_code = 'CONVICTED'     THEN 'REVIEW: convicted against weak evidence'
        ELSE 'PENDING'
    END                                                          AS audit_flag,
    CASE
        WHEN decision_code = 'NOT_CONVICTED'
             AND (non_conviction_reason_ar IS NULL OR trim(non_conviction_reason_ar) = '')
        THEN TRUE ELSE FALSE
    END                                                          AS missing_justification
FROM poisoning_incidents
ORDER BY incident_date;

-- 7. Data-quality gate (run before any dashboard refresh) --------------------
CREATE OR REPLACE VIEW v_poisoning_data_quality AS
SELECT 'unparsed_incubation' AS issue, COUNT(*) AS n
FROM poisoning_incidents WHERE incubation_raw IS NOT NULL AND incubation_hours IS NULL
UNION ALL SELECT 'missing_license', COUNT(*)
FROM poisoning_incidents WHERE license_no IS NULL OR license_no = ''
UNION ALL SELECT 'missing_date', COUNT(*)
FROM poisoning_incidents WHERE incident_date IS NULL
UNION ALL SELECT 'unknown_decision', COUNT(*)
FROM poisoning_incidents WHERE decision_code = 'UNKNOWN'
UNION ALL SELECT 'unknown_kinship', COUNT(*)
FROM poisoning_incidents WHERE kinship_code = 'UNKNOWN'
UNION ALL SELECT 'not_convicted_without_reason', COUNT(*)
FROM poisoning_incidents
WHERE decision_code = 'NOT_CONVICTED'
  AND (non_conviction_reason_ar IS NULL OR trim(non_conviction_reason_ar) = '');

-- 8. Cross-dataset hook: poisoning incident vs. prior lab results ------------
--    Enable once the lab-sample table exposes an establishment licence number.
--    This is the join that turns a register into an early-warning system.
-- CREATE OR REPLACE VIEW v_poisoning_lab_linkage AS
-- SELECT
--     p.incident_id, p.incident_date, p.establishment_name, p.cases_count,
--     s.sample_id, s.collection_date, s.parameter, s.result_value, s.is_above_limit,
--     date_diff('day', s.collection_date, p.incident_date) AS days_before_incident
-- FROM poisoning_incidents p
-- LEFT JOIN lab_samples s
--        ON s.license_no = p.license_no
--       AND s.collection_date BETWEEN p.incident_date - INTERVAL 180 DAY
--                                 AND p.incident_date
-- ORDER BY p.incident_date, s.collection_date;