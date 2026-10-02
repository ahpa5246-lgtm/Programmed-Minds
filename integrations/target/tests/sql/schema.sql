-- Run only in an owned disposable local database with pgTAP already installed.
-- Replace the table contract with the actual application schema.
BEGIN;
SELECT plan(3);
SELECT has_table('public', 'projects', 'projects table exists');
SELECT col_is_pk('public', 'projects', 'id', 'project IDs form the primary key');
SELECT col_not_null('public', 'projects', 'name', 'project names are required');
SELECT * FROM finish();
ROLLBACK;
