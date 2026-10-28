-- 只读核对本批168；真实ID和名字来自本批manifest，不能用于清理其他批次。
USE ruoyi_t2_lab;
START TRANSACTION READ ONLY;

-- [owned_user]
SELECT u.user_id,u.user_name,u.dept_id,u.status,u.del_flag,
 (SELECT COUNT(*) FROM sys_user_role ur WHERE ur.user_id=u.user_id) AS role_rows,
 (SELECT COUNT(*) FROM sys_user_post up WHERE up.user_id=u.user_id) AS post_rows
FROM sys_user u WHERE u.user_id=168 AND u.user_name='t541028082458';

-- [visible_batch]
SELECT COUNT(*) AS remaining_rows FROM sys_user
WHERE user_id=168 AND user_name='t541028082458' AND del_flag='0';

-- [active_total]
SELECT COUNT(*) AS active_rows FROM sys_user WHERE del_flag='0';

-- [end]
ROLLBACK;
