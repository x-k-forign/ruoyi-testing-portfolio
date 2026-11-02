-- T6.4本批历史对象只读复查；不用于新批次创建或清理。
-- 109、110、111已逻辑删除；当前查询结果与执行中未删除状态不同。
-- 查询结构来自本批实际只读SQL，整份脚本未在收尾后重新运行。
USE ruoyi_t3_fault_lab;
START TRANSACTION READ ONLY;
SELECT user_id,user_name,dept_id,status,del_flag,remark
FROM sys_user WHERE user_id IN (109,110,111) ORDER BY user_id;
SELECT user_id,role_id FROM sys_user_role WHERE user_id=109;
SELECT role_id,data_scope,status,del_flag FROM sys_role WHERE role_id=100;
SELECT oper_id,oper_name,oper_url,request_method,status,oper_time
FROM sys_oper_log WHERE oper_id=129;
ROLLBACK;
