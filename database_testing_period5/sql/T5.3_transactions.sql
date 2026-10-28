-- T5.3 双连接交替执行脚本。不能整份粘贴到一个窗口运行。
-- A/B必须是不同物理连接；按步骤号交替执行。自动化运行由执行器保持两个连接。
-- 先单独完成 T5.3_prepare.sql。新一轮须替换三个run_tag，不重置自增编号。
-- SELECT预览必须恰为预期的一行后，才执行对应UPDATE/DELETE；不符合就停止并回滚。
-- 本文件包含本批已执行顺序和标记，结果见manifest及events；不访问若依业务表。

-- [01 连接A use_database]
USE learning_databases;

-- [02 连接A set_r_tag]
SET @r_tag='T53_20261019_192505_rollback';

-- [03 连接A set_c_tag]
SET @c_tag='T53_20261019_192505_commit';

-- [04 连接A set_a_tag]
SET @a_tag='T53_20261019_192505_autocommit';

-- [05 连接A confirm_r_absent]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@r_tag ORDER BY id;

-- [06 连接A confirm_c_absent]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [07 连接A confirm_a_absent]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@a_tag ORDER BY id;

-- [08 连接B use_database]
USE learning_databases;

-- [09 连接B set_r_tag]
SET @r_tag='T53_20261019_192505_rollback';

-- [10 连接B set_c_tag]
SET @c_tag='T53_20261019_192505_commit';

-- [11 连接B set_a_tag]
SET @a_tag='T53_20261019_192505_autocommit';

-- [12 连接B confirm_r_absent]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@r_tag ORDER BY id;

-- [13 连接B confirm_c_absent]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [14 连接B confirm_a_absent]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@a_tag ORDER BY id;

-- [15 连接A rollback_begin]
START TRANSACTION;

-- [16 连接A rollback_insert]
INSERT INTO t5_dml_lab(run_tag,dept_id,role_id,status,note) VALUES(@r_tag,202,101,'0','draft');

-- [17 连接A remember_r_id]
SET @r_id=LAST_INSERT_ID();

-- [18 连接A rollback_update_preview]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE id=@r_id AND run_tag=@r_tag;

-- [19 连接A rollback_update]
UPDATE t5_dml_lab SET dept_id=204,status='1',note='changed_uncommitted' WHERE id=@r_id AND run_tag=@r_tag;

-- [20 连接A rollback_A_sees_change]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@r_tag ORDER BY id;

-- [21 连接B rollback_B_cannot_see]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@r_tag ORDER BY id;

-- [22 连接A rollback_end]
ROLLBACK;

-- [23 连接A rollback_A_empty]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@r_tag ORDER BY id;

-- [24 连接B rollback_B_empty]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@r_tag ORDER BY id;

-- [25 连接A commit_begin]
START TRANSACTION;

-- [26 连接A commit_insert]
INSERT INTO t5_dml_lab(run_tag,dept_id,role_id,status,note) VALUES(@c_tag,202,101,'0','draft');

-- [27 连接A remember_c_id]
SET @c_id=LAST_INSERT_ID();

-- [28 连接A commit_update_preview]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE id=@c_id AND run_tag=@c_tag;

-- [29 连接A commit_update]
UPDATE t5_dml_lab SET dept_id=204,status='1',note='saved_configuration' WHERE id=@c_id AND run_tag=@c_tag;

-- [30 连接A commit_A_sees_change]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [31 连接B commit_B_before_empty]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [32 连接A commit_end]
COMMIT;

-- [33 连接B commit_B_fresh_sees]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [34 连接B other_connection_rollback]
ROLLBACK;

-- [35 连接B other_connection_rollback_no_effect]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [36 连接B snapshot_begin]
START TRANSACTION;

-- [37 连接B snapshot_establish]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [38 连接A snapshot_writer_begin]
START TRANSACTION;

-- [39 连接A snapshot_update_preview]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE id=@c_id AND run_tag=@c_tag;

-- [40 连接A snapshot_update]
UPDATE t5_dml_lab SET dept_id=202,status='0',note='new_committed_version' WHERE id=@c_id AND run_tag=@c_tag;

-- [41 连接A snapshot_writer_commit]
COMMIT;

-- [42 连接B snapshot_still_old]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [43 连接B snapshot_end]
COMMIT;

-- [44 连接B snapshot_fresh_new]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [45 连接A delete_begin]
START TRANSACTION;

-- [46 连接A delete_preview]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE id=@c_id AND run_tag=@c_tag;

-- [47 连接A delete_uncommitted]
DELETE FROM t5_dml_lab WHERE id=@c_id AND run_tag=@c_tag;

-- [48 连接A delete_A_empty]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [49 连接B delete_B_still_present]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [50 连接A delete_rollback]
ROLLBACK;

-- [51 连接A delete_restored]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [52 连接A autocommit_insert]
INSERT INTO t5_dml_lab(run_tag,dept_id,role_id,status,note) VALUES(@a_tag,202,101,'0','autocommit_saved');

-- [53 连接A remember_a_id]
SET @a_id=LAST_INSERT_ID();

-- [54 连接A autocommit_late_rollback]
ROLLBACK;

-- [55 连接B autocommit_B_still_present]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@a_tag ORDER BY id;

-- [56 连接A cleanup_begin]
START TRANSACTION;

-- [57 连接A cleanup_c_preview]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE id=@c_id AND run_tag=@c_tag;

-- [58 连接A cleanup_c_delete]
DELETE FROM t5_dml_lab WHERE id=@c_id AND run_tag=@c_tag;

-- [59 连接A cleanup_a_preview]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE id=@a_id AND run_tag=@a_tag;

-- [60 连接A cleanup_a_delete]
DELETE FROM t5_dml_lab WHERE id=@a_id AND run_tag=@a_tag;

-- [61 连接A cleanup_commit]
COMMIT;

-- [62 连接B final_r_absent]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@r_tag ORDER BY id;

-- [63 连接B final_c_absent]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@c_tag ORDER BY id;

-- [64 连接B final_a_absent]
SELECT id,run_tag,dept_id,role_id,status,note FROM t5_dml_lab WHERE run_tag=@a_tag ORDER BY id;

-- [65 连接A close_A_transaction]
ROLLBACK;

-- [66 连接B close_B_transaction]
ROLLBACK;

-- [67 连接A final_session_settings]
SELECT CONNECTION_ID() AS connection_id,@@autocommit AS autocommit,@@transaction_isolation AS isolation_level;

-- [68 连接B final_session_settings]
SELECT CONNECTION_ID() AS connection_id,@@autocommit AS autocommit,@@transaction_isolation AS isolation_level;
