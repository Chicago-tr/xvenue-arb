-- Migration: add regression_beta to cross_ex_regression
-- cross_ex_regression is Spark-managed (not in Drizzle schema).
-- Run this once against your database after upgrading to the beta hedge-ratio version.
ALTER TABLE cross_ex_regression
    ADD COLUMN IF NOT EXISTS regression_beta DOUBLE PRECISION;
