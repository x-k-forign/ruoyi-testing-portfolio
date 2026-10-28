-- 只用于本批专用库；不是初始化或故障注入脚本。
-- 故障时点的前后状态见归档快照；当前样本已清理，不能据当前结果重写历史。
USE ruoyi_t3_fault_lab;
START TRANSACTION READ ONLY;

-- [environment]
SELECT DATABASE() AS db,VERSION() AS version,CONNECTION_ID() AS connection_id;

-- [owned_users]
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE LEFT(user_name,4)='t55_' OR user_name IN('t3_fault_new','t3_fault_edit') ORDER BY user_id;

-- [owned_roles]
SELECT u.user_id,u.user_name,ur.role_id FROM sys_user u
LEFT JOIN sys_user_role ur ON u.user_id=ur.user_id
WHERE LEFT(u.user_name,4)='t55_' OR u.user_name IN('t3_fault_new','t3_fault_edit') ORDER BY u.user_id,ur.role_id;

-- [owned_posts]
SELECT u.user_id,u.user_name,up.post_id FROM sys_user u
LEFT JOIN sys_user_post up ON u.user_id=up.user_id
WHERE LEFT(u.user_name,4)='t55_' OR u.user_name IN('t3_fault_new','t3_fault_edit') ORDER BY u.user_id,up.post_id;

-- [rolled_back_generated_id]
-- 105来自本次异常标记，不是猜测的自增编号；恢复对照创建的是106。
SELECT (SELECT COUNT(*) FROM sys_user WHERE user_id=105) AS user_rows,
 (SELECT COUNT(*) FROM sys_user_role WHERE user_id=105) AS role_rows,
 (SELECT COUNT(*) FROM sys_user_post WHERE user_id=105) AS post_rows;

-- [fault_operation_logs]
SELECT oper_id,oper_name,oper_url,request_method,status,error_msg,oper_time
FROM sys_oper_log WHERE error_msg LIKE 'T3_FAULT:%' ORDER BY oper_id;

-- [normal_operation_logs]
SELECT oper_id,oper_name,oper_url,request_method,status,oper_time,
 CASE WHEN JSON_VALID(oper_param) THEN JSON_UNQUOTE(JSON_EXTRACT(oper_param,'$.userName')) ELSE NULL END AS target_name,
 CASE WHEN JSON_VALID(oper_param) THEN JSON_UNQUOTE(JSON_EXTRACT(oper_param,'$.userId')) ELSE NULL END AS target_id
FROM sys_oper_log WHERE oper_name='admin' ORDER BY oper_id;

-- [login_logs]
SELECT info_id,user_name,status,msg,login_time FROM sys_logininfor
WHERE user_name IN('admin','t55_flow_1028') ORDER BY info_id;

-- [retained_fixtures]
SELECT role_id,role_key,data_scope,status,del_flag FROM sys_role WHERE role_key IN('t55_queryRole','t55_maintRole') ORDER BY role_id;

-- [end]
ROLLBACK;
