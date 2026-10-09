# 若依软件测试成果

本仓库保存若依软件测试学习中的文档、测试设计、执行证据与前后端源码快照。原始开发目录保持不变。

## 内容

- [学习大纲](若依软件测试学习大纲.md)：学习范围与验收状态。
- [T1测试计划](document_design_period1/T1_测试计划与方案.md)：需求、范围、风险与测试设计；同目录含流程图、测试用例和学习练习。
- [T2账号权限与重建验收](basic_setting_period2/T2_账号权限与重建验收.md)：环境阶段的最新验收记录；同目录含环境、启动、冒烟与截图证据。

## 状态与同步

2026-10-09建立成果仓库，复制T1、T2已完成成果及引用图片。T2.5、Git文件恢复练习及T2整体验收现已通过（AI辅助验收）。详见 basic_setting_period2/T2_整体验收报告.md；尚未开始T3。

来源目录：`E:\cpmputer_jobs\software_test_learning\Ruo_Yi`。此处是成果副本，不是自动同步目录。后续复制更新后应先检查差异、凭据和链接，再逐项暂存提交，不能盲目覆盖仓库内新修改。

T2笔记副本中的本地明文凭据已替换为`REDACTED_LOCAL_PASSWORD`，原学习文件未改动。真实本地配置、数据库备份和原始导出日志不纳入。保留两份已整理的启动日志摘要，其他`.log`默认忽略。图片、XMind、Excel和Draw.io是学习材料，应在公开分享前结合使用范围复核，不把文本扫描视为完整安全审计。

远端为 `https://github.com/x-k-forign/ruoyi-testing-portfolio.git`。提交身份仅配置在本仓库；推送结果以Git实际输出为准。

## 前后端源码快照

- `sources/backend`：来自 `https://github.com/yangzongzhuan/RuoYi-Vue.git`，基线 `13db1fcef36bee9ce45d2d636a1d4e8f5ed5bbc3`。
- `sources/frontend`：来自 `https://github.com/yangzongzhuan/RuoYi-Vue3.git`，基线 `838965c5a18d2c61b73ec30c6e288057aaa08b63`；包含当前 `vite.config.js` 本地代理修改。
- 复制原仓库跟踪文件的当前内容，保留上游许可证，不嵌套`.git`，不复制依赖、构建产物或`.local`真实配置。此处是普通文件快照，不是Git子模块。
- 上游初始化SQL属于源码，明确纳入；业务数据库导出仍忽略。配置中的上游示例值不代表本机凭据，运行时须另行配置。
- 依赖安装、构建与本地配置方法参见T2环境记录；本次仅同步源码，没有重新构建或启动服务。
