-- 目标 ruoyi_t2_lab；运行前在同一连接填写本批真实ID：SET @target_user_id=实际ID;
-- 126、127为既有观察样本；105、106为本批请求中指定的角色。
USE ruoyi_t2_lab;
START TRANSACTION READ ONLY;

-- [environment]
SELECT DATABASE() AS db,VERSION() AS version,CONNECTION_ID() AS connection_id,
 NOW() AS local_time_value,UTC_TIMESTAMP() AS utc_time_value,
 TIMESTAMPDIFF(MINUTE,UTC_TIMESTAMP(),NOW()) AS utc_offset_minutes;

-- [target_user]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user WHERE user_id=@target_user_id;

-- [target_roles]
SELECT user_id,role_id FROM sys_user_role WHERE user_id=@target_user_id ORDER BY role_id;

-- [target_posts]
SELECT user_id,post_id FROM sys_user_post WHERE user_id=@target_user_id ORDER BY post_id;

-- [inner_user_department_roles]
SELECT u.user_id,u.user_name,u.dept_id,d.dept_name,d.status AS dept_status,d.del_flag AS dept_del_flag,
 r.role_id,r.role_key,r.data_scope,r.status AS role_status,r.del_flag AS role_del_flag
FROM sys_user u INNER JOIN sys_dept d ON u.dept_id=d.dept_id
INNER JOIN sys_user_role ur ON u.user_id=ur.user_id
INNER JOIN sys_role r ON ur.role_id=r.role_id
WHERE u.user_id=@target_user_id ORDER BY r.role_id;

-- [role_menu_pairs]
SELECT ur.user_id,ur.role_id,rm.menu_id,m.menu_name,m.menu_type,m.status,m.perms
FROM sys_user_role ur INNER JOIN sys_role_menu rm ON ur.role_id=rm.role_id
INNER JOIN sys_menu m ON rm.menu_id=m.menu_id
WHERE ur.user_id=@target_user_id ORDER BY ur.role_id,rm.menu_id;

-- [role_department_scope]
SELECT ur.user_id,r.role_id,r.data_scope,rd.dept_id AS custom_dept_id,
 d.dept_name,d.status AS dept_status,d.del_flag AS dept_del_flag
FROM sys_user_role ur INNER JOIN sys_role r ON ur.role_id=r.role_id
LEFT JOIN sys_role_dept rd ON r.role_id=rd.role_id
LEFT JOIN sys_dept d ON rd.dept_id=d.dept_id
WHERE ur.user_id=@target_user_id ORDER BY r.role_id,rd.dept_id;

-- [user_post_details]
SELECT up.user_id,up.post_id,p.post_code,p.post_name,p.status
FROM sys_user_post up INNER JOIN sys_post p ON up.post_id=p.post_id
WHERE up.user_id=@target_user_id ORDER BY up.post_id;

-- [left_samples]
SELECT u.user_id,u.dept_id,d.dept_id AS matched_dept_id,ur.role_id,r.role_id AS matched_role_id,r.status AS role_status
FROM sys_user u LEFT JOIN sys_dept d ON u.dept_id=d.dept_id
LEFT JOIN sys_user_role ur ON u.user_id=ur.user_id LEFT JOIN sys_role r ON ur.role_id=r.role_id
WHERE u.user_id IN(@target_user_id,126,127) ORDER BY u.user_id,ur.role_id;

-- [inner_samples]
SELECT u.user_id,u.dept_id,d.dept_id AS matched_dept_id,ur.role_id,r.role_id AS matched_role_id,r.status AS role_status
FROM sys_user u INNER JOIN sys_dept d ON u.dept_id=d.dept_id
INNER JOIN sys_user_role ur ON u.user_id=ur.user_id INNER JOIN sys_role r ON ur.role_id=r.role_id
WHERE u.user_id IN(@target_user_id,126,127) ORDER BY u.user_id,ur.role_id;

-- [role_status_in_on]
SELECT u.user_id,ur.role_id,r.role_id AS matched_role_id,r.status AS role_status
FROM sys_user u LEFT JOIN sys_user_role ur ON u.user_id=ur.user_id
LEFT JOIN sys_role r ON ur.role_id=r.role_id AND r.status='0'
WHERE u.user_id IN(@target_user_id,126,127) ORDER BY u.user_id,ur.role_id;

-- [role_status_in_where]
SELECT u.user_id,ur.role_id,r.role_id AS matched_role_id,r.status AS role_status
FROM sys_user u LEFT JOIN sys_user_role ur ON u.user_id=ur.user_id
LEFT JOIN sys_role r ON ur.role_id=r.role_id
WHERE u.user_id IN(@target_user_id,126,127) AND r.status='0' ORDER BY u.user_id,ur.role_id;

-- [result_granularity]
SELECT COUNT(*) AS user_role_menu_rows,COUNT(DISTINCT u.user_id) AS users,
 COUNT(DISTINCT ur.role_id) AS roles,COUNT(DISTINCT rm.menu_id) AS menus
FROM sys_user u INNER JOIN sys_user_role ur ON u.user_id=ur.user_id
INNER JOIN sys_role_menu rm ON ur.role_id=rm.role_id
WHERE u.user_id=@target_user_id;

-- [reference_integrity]
SELECT 'user_department' AS relation_name,COUNT(*) AS missing_count
FROM sys_user u LEFT JOIN sys_dept d ON u.dept_id=d.dept_id
WHERE u.user_id IN(@target_user_id,126,127) AND u.dept_id IS NOT NULL AND d.dept_id IS NULL
UNION ALL
SELECT 'user_role',COUNT(*) FROM sys_user_role ur LEFT JOIN sys_role r ON ur.role_id=r.role_id
WHERE ur.user_id IN(@target_user_id,126,127) AND r.role_id IS NULL
UNION ALL
SELECT 'role_menu',COUNT(*) FROM sys_role_menu rm LEFT JOIN sys_menu m ON rm.menu_id=m.menu_id
WHERE rm.role_id IN(105,106) AND m.menu_id IS NULL
UNION ALL
SELECT 'role_department',COUNT(*) FROM sys_role_dept rd LEFT JOIN sys_dept d ON rd.dept_id=d.dept_id
WHERE rd.role_id IN(105,106) AND d.dept_id IS NULL
UNION ALL
SELECT 'user_post',COUNT(*) FROM sys_user_post up LEFT JOIN sys_post p ON up.post_id=p.post_id
WHERE up.user_id=@target_user_id AND p.post_id IS NULL;

-- [expected_visible]
-- 本例两个有效角色均有list权限：105为本部门202，106为自定义204，组合为并集。
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE del_flag='0' AND dept_id IN(202,204) ORDER BY user_id;

-- [end]
ROLLBACK;
