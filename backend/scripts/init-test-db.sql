-- Runs once when the Postgres volume is first created.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE researchflow_test OWNER researchflow;
\c researchflow_test
CREATE EXTENSION IF NOT EXISTS vector;
