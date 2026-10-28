-- T5.3 本批只读收尾复查。ID与标记取自本轮manifest，不用于删除。
USE learning_databases;
START TRANSACTION READ ONLY;

-- [owned_rows]
SELECT id,run_tag,dept_id,role_id,status,note
FROM t5_dml_lab
WHERE (id=1 AND run_tag='T53_20261019_192505_rollback')
   OR (id=2 AND run_tag='T53_20261019_192505_commit')
   OR (id=3 AND run_tag='T53_20261019_192505_autocommit')
ORDER BY id;

-- [batch_remaining]
SELECT COUNT(*) AS remaining_rows FROM t5_dml_lab
WHERE run_tag IN ('T53_20261019_192505_rollback',
                 'T53_20261019_192505_commit',
                 'T53_20261019_192505_autocommit');

-- [table_remaining]
SELECT COUNT(*) AS table_rows FROM t5_dml_lab;

-- [end]
ROLLBACK;
