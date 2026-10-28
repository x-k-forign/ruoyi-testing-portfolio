-- T5.1 实际结构与业务关联核验，MySQL 8.4。
-- 在现有授权客户端连接本机 ruoyi_t2_lab 后运行，不包含凭据。
-- 只读；不是初始化或恢复脚本。101/134 是现有基线用户，151/153 是 T4 已删除历史用户。
USE ruoyi_t2_lab;
START TRANSACTION READ ONLY;

-- [connection]
SELECT VERSION() AS server_version, @@version_comment AS product,
       @@port AS server_port, DATABASE() AS current_db,
       CURRENT_USER() AS privilege_account, USER() AS connection_account,
       CONNECTION_ID() AS connection_id, @@session.autocommit AS autocommit,
       @@session.transaction_isolation AS isolation_level,
       @@session.time_zone AS session_time_zone, @@system_time_zone AS system_time_zone;

-- [grants]
SHOW GRANTS;

-- [inventory]
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION, TABLE_COMMENT
FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()
ORDER BY TABLE_NAME;

-- [columns]
SELECT TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
       COLUMN_DEFAULT, COLUMN_KEY, EXTRA, CHARACTER_SET_NAME, COLLATION_NAME, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN
('sys_user','sys_dept','sys_role','sys_menu','sys_post','sys_user_role','sys_role_menu','sys_role_dept','sys_user_post')
ORDER BY TABLE_NAME, ORDINAL_POSITION;

-- [indexes]
SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, INDEX_TYPE
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN
('sys_user','sys_dept','sys_role','sys_menu','sys_post','sys_user_role','sys_role_menu','sys_role_dept','sys_user_post')
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

-- [constraints]
SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN
('sys_user','sys_dept','sys_role','sys_menu','sys_post','sys_user_role','sys_role_menu','sys_role_dept','sys_user_post')
ORDER BY TABLE_NAME, CONSTRAINT_NAME;

-- [foreign_keys]
SELECT TABLE_NAME,COLUMN_NAME,CONSTRAINT_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL
AND TABLE_NAME IN ('sys_user','sys_dept','sys_role','sys_menu','sys_post','sys_user_role','sys_role_menu','sys_role_dept','sys_user_post')
ORDER BY TABLE_NAME,CONSTRAINT_NAME,ORDINAL_POSITION;

-- [user_baseline]
SELECT user_id,user_name,dept_id,status,del_flag
FROM sys_user WHERE user_id IN (101,134,151,153) ORDER BY user_id;

-- [user_department]
SELECT u.user_id,u.user_name,u.dept_id,u.status AS user_status,u.del_flag AS user_del_flag,
       d.dept_name,d.parent_id,d.ancestors,d.status AS dept_status,d.del_flag AS dept_del_flag
FROM sys_user u LEFT JOIN sys_dept d ON u.dept_id=d.dept_id
WHERE u.user_id IN (101,134,151,153) ORDER BY u.user_id;

-- [user_roles]
SELECT u.user_id,ur.role_id,r.role_name,r.role_key,r.data_scope,r.status AS role_status,r.del_flag AS role_del_flag
FROM sys_user u LEFT JOIN sys_user_role ur ON u.user_id=ur.user_id
LEFT JOIN sys_role r ON ur.role_id=r.role_id
WHERE u.user_id IN (101,134,151,153) ORDER BY u.user_id,ur.role_id;

-- [role_menus]
SELECT rm.role_id,rm.menu_id,m.menu_name,m.parent_id,m.menu_type,m.visible,m.status,m.perms
FROM sys_role_menu rm LEFT JOIN sys_menu m ON rm.menu_id=m.menu_id
WHERE rm.role_id IN (101,102,106) ORDER BY rm.role_id,rm.menu_id;

-- [custom_scope]
SELECT r.role_id,r.role_name,r.data_scope,rd.dept_id,d.dept_name,d.status,d.del_flag
FROM sys_role r LEFT JOIN sys_role_dept rd ON r.role_id=rd.role_id
LEFT JOIN sys_dept d ON rd.dept_id=d.dept_id
WHERE r.role_id IN (101,102,106) ORDER BY r.role_id,rd.dept_id;

-- [custom_scope_users]
SELECT u.user_id,u.user_name,u.dept_id,u.status,u.del_flag,ur.role_id
FROM sys_user_role ur JOIN sys_user u ON u.user_id=ur.user_id
WHERE ur.role_id=106 ORDER BY u.user_id;

-- [user_posts]
SELECT up.user_id,up.post_id,p.post_name,p.status
FROM sys_user_post up LEFT JOIN sys_post p ON up.post_id=p.post_id
WHERE up.user_id IN (101,134,151,153) ORDER BY up.user_id,up.post_id;

-- [historical_cleanup]
SELECT u.user_id,u.user_name,u.status,u.del_flag,
 (SELECT COUNT(*) FROM sys_user_role ur WHERE ur.user_id=u.user_id) AS role_rows,
 (SELECT COUNT(*) FROM sys_user_post up WHERE up.user_id=u.user_id) AS post_rows
FROM sys_user u WHERE u.user_id IN (151,153) ORDER BY u.user_id;

-- [sample_consistency]
SELECT 'sample_user_missing_dept' AS check_name,COUNT(*) AS issue_count
FROM sys_user u LEFT JOIN sys_dept d ON u.dept_id=d.dept_id
WHERE u.user_id IN (101,134,151,153) AND u.dept_id IS NOT NULL AND d.dept_id IS NULL
UNION ALL
SELECT 'sample_role_missing_role',COUNT(*) FROM sys_user_role ur LEFT JOIN sys_role r ON ur.role_id=r.role_id
WHERE ur.user_id IN (101,134,151,153) AND r.role_id IS NULL
UNION ALL
SELECT 'sample_menu_missing_menu',COUNT(*) FROM sys_role_menu rm LEFT JOIN sys_menu m ON rm.menu_id=m.menu_id
WHERE rm.role_id IN (101,102,106) AND m.menu_id IS NULL
UNION ALL
SELECT 'sample_scope_missing_dept',COUNT(*) FROM sys_role_dept rd LEFT JOIN sys_dept d ON rd.dept_id=d.dept_id
WHERE rd.role_id IN (101,102,106) AND d.dept_id IS NULL
UNION ALL
SELECT 'sample_post_missing_post',COUNT(*) FROM sys_user_post up LEFT JOIN sys_post p ON up.post_id=p.post_id
WHERE up.user_id IN (101,134,151,153) AND p.post_id IS NULL;

-- [end]
ROLLBACK;
-- 结束本次只读事务。这里没有业务写入，也不用于撤销其他连接已经提交的数据。
