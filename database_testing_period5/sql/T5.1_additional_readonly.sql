-- T5.1 补充：数据范围与部门归属、时区数字偏移。
USE ruoyi_t2_lab;
START TRANSACTION READ ONLY;

-- [time_offset]
SELECT NOW() AS database_local_time, UTC_TIMESTAMP() AS database_utc_time,
       TIMESTAMPDIFF(MINUTE, UTC_TIMESTAMP(), NOW()) AS utc_offset_minutes;

-- [multi_role_user]
SELECT u.user_id,u.user_name,u.dept_id,d.dept_name,u.status,u.del_flag,
       ur.role_id,r.role_name,r.data_scope,r.status AS role_status,r.del_flag AS role_del_flag
FROM sys_user u
LEFT JOIN sys_dept d ON u.dept_id=d.dept_id
LEFT JOIN sys_user_role ur ON u.user_id=ur.user_id
LEFT JOIN sys_role r ON ur.role_id=r.role_id
WHERE u.user_id=131 ORDER BY ur.role_id;

-- [sample_after]
SELECT u.user_id,u.user_name,u.dept_id,u.status,u.del_flag,
 (SELECT COUNT(*) FROM sys_user_role ur WHERE ur.user_id=u.user_id) AS role_rows,
 (SELECT COUNT(*) FROM sys_user_post up WHERE up.user_id=u.user_id) AS post_rows
FROM sys_user u WHERE u.user_id IN(101,134,151,153) ORDER BY u.user_id;

-- [end]
ROLLBACK;
