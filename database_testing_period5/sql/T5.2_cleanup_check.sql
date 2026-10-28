-- 本批收尾复查，只读；ID和名称来自 T52_20261019_185631/manifest.json。
-- 这不是删除脚本，不会重新创建已清理对象。
USE ruoyi_t2_lab;
START TRANSACTION READ ONLY;

-- [owned_users]
SELECT u.user_id,u.user_name,u.dept_id,u.status,u.del_flag,
 (SELECT COUNT(*) FROM sys_user_role ur WHERE ur.user_id=u.user_id) AS role_rows,
 (SELECT COUNT(*) FROM sys_user_post up WHERE up.user_id=u.user_id) AS post_rows
FROM sys_user u
WHERE (u.user_id=166 AND u.user_name='t521019185631a')
   OR (u.user_id=167 AND u.user_name='t521019185631b')
ORDER BY u.user_id;

-- [remaining_visible_batch]
SELECT COUNT(*) AS remaining_rows FROM sys_user
WHERE del_flag='0' AND user_name IN ('t521019185631a','t521019185631b');

-- [after_cleanup_counts]
SELECT del_flag,COUNT(*) AS row_count FROM sys_user GROUP BY del_flag ORDER BY del_flag;

-- [end]
ROLLBACK;
