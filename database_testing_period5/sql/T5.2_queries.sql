-- T5.2：只读业务查询。先连接本机 ruoyi_t2_lab。
-- 先执行下一行，再设置下面的会话参数，使字符串变量与表列排序规则一致。
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
-- 参数必须取自本轮 manifest.json，不能把历史账号当成本轮样本。
-- 在同一连接先填写：SET @batch_prefix='实际批次前缀';
-- SET @normal_name='本批正常账号'; SET @stopped_name='本批停用账号';
-- SET @normal_id=实际正常用户ID; SET @dept_a=202; SET @dept_b=204;
USE ruoyi_t2_lab;
START TRANSACTION READ ONLY;

-- [environment]
SELECT DATABASE() AS current_db,VERSION() AS version,CONNECTION_ID() AS connection_id,
 @@autocommit AS autocommit,@@transaction_isolation AS isolation_level,
 NOW() AS database_local_time,UTC_TIMESTAMP() AS database_utc_time,
 TIMESTAMPDIFF(MINUTE,UTC_TIMESTAMP(),NOW()) AS utc_offset_minutes;

-- [batch_exact]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE user_name IN (@normal_name,@stopped_name) ORDER BY user_id;

-- [admin_all]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' ORDER BY user_id;

-- [department_exact]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' AND dept_id=@dept_a ORDER BY user_id;

-- [department_tree]
-- 若依部门树筛选包含所选部门及其下级；不能简单写成 dept_id=202。
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' AND (dept_id=@dept_a OR dept_id IN
 (SELECT dept_id FROM sys_dept WHERE FIND_IN_SET(@dept_a,ancestors))) ORDER BY user_id;

-- [department_tree_normal]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' AND status='0' AND (dept_id=@dept_a OR dept_id IN
 (SELECT dept_id FROM sys_dept WHERE FIND_IN_SET(@dept_a,ancestors))) ORDER BY user_id;

-- [disabled_users]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' AND status='1' ORDER BY user_id;

-- [batch_like]
-- 本批前缀只含字母数字，不含 LIKE 通配符 % 或 _。
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' AND user_name LIKE CONCAT('%',@batch_prefix,'%') ORDER BY user_id;

-- [exact_id]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' AND user_id=@normal_id ORDER BY user_id;

-- [ordinary_all]
-- 本轮普通账号仅角色101、本部门范围3，其所属部门为202。
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' AND dept_id=@dept_a ORDER BY user_id;

-- [ordinary_outside]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' AND dept_id=@dept_a AND (dept_id=@dept_b OR dept_id IN
 (SELECT dept_id FROM sys_dept WHERE FIND_IN_SET(@dept_b,ancestors))) ORDER BY user_id;

-- [ordinary_batch]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' AND dept_id=@dept_a AND user_name LIKE CONCAT('%',@batch_prefix,'%') ORDER BY user_id;

-- [page_1]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' ORDER BY user_id LIMIT 0,5;

-- [page_2]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' ORDER BY user_id LIMIT 5,5;

-- [department_counts]
SELECT dept_id,COUNT(*) AS user_count,COUNT(dept_id) AS non_null_dept_count
FROM sys_user WHERE del_flag='0' GROUP BY dept_id ORDER BY dept_id;

-- [department_status_counts]
SELECT dept_id,status,COUNT(*) AS user_count FROM sys_user
WHERE del_flag='0' GROUP BY dept_id,status ORDER BY dept_id,status;

-- [having_multiple_users]
SELECT dept_id,COUNT(*) AS user_count FROM sys_user
WHERE del_flag='0' GROUP BY dept_id HAVING COUNT(*)>=2 ORDER BY user_count DESC,dept_id;

-- [null_counts]
SELECT COUNT(*) AS user_count,COUNT(dept_id) AS known_dept_count,
 COUNT(DISTINCT dept_id) AS distinct_known_departments,
 SUM(CASE WHEN dept_id IS NULL THEN 1 ELSE 0 END) AS null_dept_count
FROM sys_user WHERE del_flag='0';

-- [null_department]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' AND dept_id IS NULL ORDER BY user_id;

-- [deletion_counts]
SELECT del_flag,COUNT(*) AS row_count FROM sys_user GROUP BY del_flag ORDER BY del_flag;

-- [historical_deleted]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE user_id IN(151,153) ORDER BY user_id;

-- [end]
ROLLBACK;
-- 只结束当前只读事务；不能撤销后端接口已提交的数据。
