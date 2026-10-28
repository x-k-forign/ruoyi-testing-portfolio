-- T5.6业务核验：@target_user_id必须来自本轮创建后的精确查询；不得猜测或沿用上一轮ID。
-- @run_tag/@dept_id/@role_id/@post_id保持本轮参数，查询只选必要字段。
USE ruoyi_t3_fault_lab;
START TRANSACTION READ ONLY;

-- [owned_user]
SELECT user_id,user_name,dept_id,status,del_flag,remark FROM sys_user
WHERE user_id=@target_user_id AND user_name=@run_tag AND remark=@run_tag;

-- [roles]
SELECT user_id,role_id FROM sys_user_role WHERE user_id=@target_user_id ORDER BY role_id;

-- [posts]
SELECT user_id,post_id FROM sys_user_post WHERE user_id=@target_user_id ORDER BY post_id;

-- [joined]
SELECT u.user_id,u.user_name,u.dept_id,d.status AS dept_status,
 r.role_id,r.role_key,r.data_scope,r.status AS role_status,p.post_id,p.status AS post_status
FROM sys_user u JOIN sys_dept d ON u.dept_id=d.dept_id
JOIN sys_user_role ur ON u.user_id=ur.user_id JOIN sys_role r ON ur.role_id=r.role_id
JOIN sys_user_post up ON u.user_id=up.user_id JOIN sys_post p ON up.post_id=p.post_id
WHERE u.user_id=@target_user_id AND u.user_name=@run_tag ORDER BY r.role_id,p.post_id;

-- [expected_visible]
-- 本轮只配置经核实的本部门查询角色，预期为本部门未删除用户完整集合。
SELECT user_id,user_name,dept_id,status,del_flag FROM sys_user
WHERE dept_id=@dept_id AND del_flag='0' ORDER BY user_id;

-- [end]
ROLLBACK;
