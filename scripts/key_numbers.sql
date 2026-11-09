SELECT (SELECT count(*) FROM bpa_edp.demo.bronze_buyin_log) AS bronze_rows,
       (SELECT count(*) FROM bpa_edp.demo.silver_buyin_log) AS silver_rows,
       (SELECT count(*) FROM bpa_edp.demo.buyin_quarantine) AS quarantine_cells,
       (SELECT count(*) FROM bpa_edp.demo.buyin_quarantine WHERE fixed_value IS NULL AND column_name IN ('movement_volume','received_date')) AS need_a_person,
       (SELECT MEASURE(breach_rate_pct) FROM bpa_edp.demo.mv_buyin_sla) AS breach_rate,
       (SELECT MEASURE(pending_items) FROM bpa_edp.demo.mv_buyin_sla) AS pending,
       (SELECT count(*) FROM bpa_edp.demo.buyin_corrections) AS corrections,
       (SELECT count(*) FROM bpa_edp.demo.silver_buyin_log WHERE movement_volume IS NULL) AS null_volumes
