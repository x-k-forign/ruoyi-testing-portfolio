# T2.6 Git实操与验收

日期：2026-10-09。对应大纲“使用Git完成克隆、分支、差异查看、提交与恢复并管理脱敏测试成果”。用户执行VS Code暂存、提交及放弃修改，AI执行仓库初始化、成果同步、推送、排障和用户明确要求的历史回退。自测为AI辅助说明。

## 仓库与提交

- 成果仓库：E:\cpmputer_jobs\software_test_learning\Ruo_Yi_git。
- 分支：t2-git-practice；远端：https://github.com/x-k-forign/ruoyi-testing-portfolio.git。
- 原始前后端Git克隆仍在Ruo_Yi/sources，固定版本和来源见环境盘点记录；成果仓库的sources保存普通文件快照，不含嵌套.git。
- babc308：提交T1、T2文档及证据。
- 696c3903dc323379cf32bf8069d4f9b7707dffa2：提交前后端源码快照与代理修改。
- 73d91f7531854c58d18972d8798fbaf0bf803768：用户提交git-practice.txt基线。
- b7cc5e7d2d10463a06bc20e4a2f2203f4f8cf065：按用户要求撤销上述练习提交。

最后两条已按用户明确要求从本地及远端分支历史移除；不能把当前历史中没有它们解释为未做过练习，也不能声称仍可从普通clone得到这两条提交。截图及[核验记录](evidence_t2_6/Git核验记录.txt)作为长期证据，本地reflog会过期。

## 三种恢复的区别

| 操作 | 本次实际效果 | 历史影响 |
|---|---|---|
| 放弃工作区修改 | 临时第二行删除，baseline保留 | 没有新提交，未改变已有提交 |
| git revert | 新建b7cc5e7，删除整个git-practice.txt；文件树与696c390相同 | 保留原提交，增加撤销提交 |
| git reset --hard | 分支指向696c390，工作区回到该版本 | 73d91f7和b7cc5e7不再属于分支历史 |

前两次截图见[暂存基线](evidence_t2_6/暂存基线.png)、[临时差异](evidence_t2_6/临时修改差异.png)、[放弃修改后](evidence_t2_6/放弃修改后状态.png)、[撤销提交差异](evidence_t2_6/撤销提交差异.png)。AI只读检查确认放弃修改后文件与HEAD均为baseline、diff为空。随后用户明确要求删除两条提交，AI先确认工作区干净、HEAD正确，才执行reset，并使用带确切旧远端提交号的force-with-lease更新远端。普通文件恢复练习不应照搬整仓库reset。

## 常用检查命令

在成果仓库目录执行：

```powershell
git status --short --branch
git diff
git diff --cached
git log --oneline -5
```

git diff比较工作区与暂存区；git diff --cached比较暂存区与HEAD。提交只保存已暂存内容。commit是本地保存，push是发送提交到远端。↑1表示本地领先一个提交，不代表还有未提交修改。

## 脱敏与同步

.gitignore排除.local、依赖、构建产物、真实环境文件、备份、原始日志和编辑器临时文件。初始化SQL与已检查的前端.env开发/生产/预发布文件明确保留。两份已整理启动日志允许入库。

T2原笔记发现本地明文凭据，首次提交前只对成果副本替换为REDACTED_LOCAL_PASSWORD；原笔记未变，不可直接覆盖回成果副本。已核查文本及Excel/XMind归档中已知凭据匹配、文件链接和嵌套仓库记录。检查范围不是完整秘密审计，原本聊天截图出现过的密码也不能因成果脱敏就称已完成轮换。

## 同步超时排障

[报错截图](evidence_t2_6/同步连接超时.png)显示GitHub443连接超时；VS Code日志中失败的是同步过程的pull。实测直连超时，系统现有代理127.0.0.1:7897访问成功。仅在成果仓库配置http.https://github.com.proxy后推送成功并核对远端SHA。代理关闭或换端口后需调整；不关闭TLS验证，不把网络失败当成提交丢失。

## 自测（AI辅助）

git diff为空不保证下一次提交无变化：暂存区可能已有内容，应再看git diff --cached和status。

.gitignore不清理历史，也不会自动停止跟踪已跟踪文件。已提交凭据需另行处理撤销/更换和历史清理，不能只改忽略规则。

## 逐项验收

四项通过：真实克隆记录可复用环境盘点；分支、暂存截图及实际提交明确；专用文件修改与恢复有前后证据；成果已有真实提交；自测已按约定由AI补充。回退历史是额外练习，不否定已完成的文件恢复。不以本节通过宣称全套功能或安全测试通过。
