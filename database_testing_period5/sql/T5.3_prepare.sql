-- T5.3 独立教学表；只在 learning_databases 执行。
-- 先确认同名表不存在、账号有CREATE权限。若已存在，停止并核对用途和结构。
-- 本文件必须在事务实验开始前单独执行；不与回滚实验混跑。
CREATE TABLE learning_databases.t5_dml_lab (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '本次草稿记录ID',
  run_tag VARCHAR(64) NOT NULL COMMENT '唯一实验分支标记',
  dept_id BIGINT NOT NULL COMMENT '模拟若依所属部门，不关联真实业务表',
  role_id BIGINT NOT NULL COMMENT '模拟若依角色配置，不授予真实权限',
  status CHAR(1) NOT NULL COMMENT '模拟账号状态0正常1停用',
  note VARCHAR(100) NOT NULL COMMENT '实验步骤说明',
  PRIMARY KEY (id),
  UNIQUE KEY uk_t5_run_tag (run_tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='T5专用事务练习表，不是若依业务表';
