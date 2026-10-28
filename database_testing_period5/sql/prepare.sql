-- T5.6准备检查：不建库、不初始化、不创建业务账号。
-- 连接本机隔离库后，先SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci，再绑定参数。
-- @run_tag=8~20位字母数字唯一标记，同时作为用户名；@dept_id/@role_id/@post_id取实际夹具ID。
USE ruoyi_t3_fault_lab;
START TRANSACTION READ ONLY;

-- [environment]
SELECT DATABASE() AS db,VERSION() AS version,CONNECTION_ID() AS connection_id,
 @@autocommit AS autocommit,@@transaction_isolation AS isolation_level,
 NOW() AS local_time_value,TIMESTAMPDIFF(MINUTE,UTC_TIMESTAMP(),NOW()) AS utc_offset_minutes;

-- [batch_gate]
SELECT IF(DATABASE()='ruoyi_t3_fault_lab',1,0) AS database_ok,
 IF(@run_tag REGEXP '^[A-Za-z0-9]{8,20}$',1,0) AS tag_ok,
 (SELECT COUNT(*) FROM sys_user WHERE user_name=@run_tag) AS existing_name_rows;
-- 执行器要求database_ok=1、tag_ok=1、existing_name_rows=0；否则停止，不发创建请求。

-- [department]
SELECT dept_id,dept_name,status,del_flag FROM sys_dept WHERE dept_id=@dept_id;

-- [role]
SELECT role_id,role_key,data_scope,status,del_flag FROM sys_role WHERE role_id=@role_id;

-- [post]
SELECT post_id,post_code,status FROM sys_post WHERE post_id=@post_id;

-- [permissions]
SELECT rm.menu_id,m.perms,m.status FROM sys_role_menu rm
JOIN sys_menu m ON rm.menu_id=m.menu_id WHERE rm.role_id=@role_id ORDER BY rm.menu_id;

-- [end]
ROLLBACK;
-- 前置正常后，通过POST /system/user创建本批用户；再查询取得真实ID。
