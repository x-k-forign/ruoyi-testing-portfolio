-- T5.6清理定位和复查SQL；本文件不直接DELETE若依用户及关联表。
-- 执行器在API删除前、删除后各运行一次，使用相同真实ID+精确用户名+批次备注。
USE ruoyi_t3_fault_lab;
START TRANSACTION READ ONLY;

-- [owned_target]
SELECT user_id,user_name,dept_id,status,del_flag,remark FROM sys_user
WHERE user_id=@target_user_id AND user_name=@run_tag AND remark=@run_tag;

-- [association_counts]
SELECT (SELECT COUNT(*) FROM sys_user_role WHERE user_id=@target_user_id) AS role_rows,
 (SELECT COUNT(*) FROM sys_user_post WHERE user_id=@target_user_id) AS post_rows;

-- [visible_batch]
SELECT COUNT(*) AS visible_rows FROM sys_user
WHERE user_id=@target_user_id AND user_name=@run_tag AND remark=@run_tag AND del_flag='0';

-- [end]
ROLLBACK;
-- 删除前：owned_target恰为本批1行且del_flag=0、关联与本批记录一致，才允许DELETE /system/user/{真实ID}。
-- 归属不符、数量不符或ID属于原基线时，执行器停止，不发删除请求。
-- 删除后：本批行del_flag=2、role_rows=0、post_rows=0、visible_rows=0才算清理完成。
-- 若已清理且上述条件满足，跳过重复删除。保留逻辑删除历史和审计日志。
