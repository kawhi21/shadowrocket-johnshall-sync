# Shadowrocket Johnshall Safe Sync

每天北京时间 **10:23** 下载并校验 Johnshall 分流与广告规则，向 Shadowrocket 提供纯规则集。GitHub 与 iOS 调度可能延迟。项目不提供代理节点或订阅，不承诺导入后即可上网。

**现有 iPad 用户：保持当前 Johnshall-AI-Extended.conf、AI-Stable 日本 A09 和原 AI 模块不动。新增模板用于新用户或新设备；不强制迁移已有设备。**

## 公共版：从这里开始

唯一公共配置入口：[下载 Public-Starter.conf](https://raw.githubusercontent.com/kawhi21/shadowrocket-johnshall-sync/main/templates/Public-Starter.conf)。它使用内置 PROXY / DIRECT / REJECT，没有 AI-Stable 或私人节点依赖。

1. 在 Shadowrocket 自行添加合法可用的节点订阅，选择一个工作节点。本仓库不接收你的订阅信息。
2. 下载入口文件到“文件”App，再作为本地配置加入 Shadowrocket。若已有工作配置，先备份并用测试副本操作；导入可能激活新配置，不要把导入动作安排为每日自动化。
3. 新用户主动使用该配置，全局路由设为“配置”。确认配置里的两条规则集 URL 下载成功。若应用导入时自动写入 update-url，应在本地副本中移除该项，保持固定本地配置只更新远程资源。
4. 配置自动更新开启后台更新、间隔设 1 天；系统后台 App 刷新允许 Shadowrocket。不再每日导入整份 .conf。关闭 App 后的执行受系统限制，不能保证准点。
5. 验证国内网站 DIRECT、普通国外 PROXY、广告 REJECT。配置规则顺序为上游 PROXY 块 → REJECT 块 → CN DIRECT → FINAL PROXY，保留上游顺序。
6. 可选：[AI-Public.sgmodule](templates/AI-Public.sgmodule)，九个 AI 域名均指向内置 PROXY，无需额外组。通过模块页面添加并启用；不含脚本、MITM 或节点。与个人 AI 模块二选一，避免重复规则。

公共配置采用 system DNS、关闭 IPv6，是明确的起始基线，不等同于每个现有用户的全部网络设置。旧 templates/Johnshall-Auto-Rules.conf 与 .example 文件继续原样保留；原有包含关系不会被本升级修改。

## 个人 AI 分流及多设备

[个人模板](templates/personal/) 保留九条 AI 规则指向 AI-Stable，组模板默认只有 PROXY；**这不是已绑定日本节点的私人备份**。每台设备需本地添加并选择自己的目标节点，再核对规则命中。

完整步骤见 [多设备接入与私人备份](docs/multi-device.md)。优先只传输无凭据模板，各设备独立添加订阅。若用户主动使用 Shadowrocket 的 iCloud 私人备份，节点数据仍不能公开；文件同步不证明分组选择、当前配置或订阅节点解析正确。本项目不启用或更改设备同步设置。

## 更新、历史及回退

- generated/proxy.list 与 generated/reject.list 是可消费的纯规则，不是节点订阅；generated/validation.json 记录上游与生成文件哈希。
- scripts/sync.py 拒绝异常下载、未知结构及策略顺序变化；全部验证通过才写出。Action 一次提交全部生成文件，失败不替换 GitHub 最后合格版本。
- 每日工作流在成功提交后构建版本快照，草稿上传、回读校验后发布 Release；已经公开的资产不被脚本覆盖。原规则服务与 Release 发布分别记录状态。
- [版本与回退指南](docs/releases-and-rollback.md) 说明如何验证快照、使用固定提交的规则副本，以及恢复每日追随 main。回退需用户主动操作，不自动切换生产配置。

旧快捷指令 shadowrocket://config/add/… 已实测会改变当前配置蓝色对勾，因此不用于无人值守更新。我们的日常更新对象是远程 RULE-SET；主配置和私人覆盖保存在本地。

## 验证与当前限制

运行：python -m unittest discover -s tests -v，然后 python scripts/check_repo.py。快照构建和只读校验也会在 PR CI 中运行；PR 无仓库写入权限，不执行同步发布。

[验证边界](docs/verification.md) 明确区分自动测试、已有 iPad 验收和待确认项。现有 iPad 的下载与 AI 分流已由用户确认；新公共模板、新设备节点绑定、至少一次无人值守后台刷新及合并后的首次真实 Release 仍需相应环境验收。

## 许可与隐私

规则来源：[Johnshall / Moshel](https://github.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever)，署名与修改说明见 [NOTICE.md](NOTICE.md)。规则数据和配置/模块模板沿用 CC BY-SA 4.0；本项目脚本、测试和工作流适用 [LICENSE](LICENSE) 中的 MIT 条款。

不要提交私人节点、密码、UUID、订阅地址、token URL 或证书。CI 检测常见凭据格式、节点字段和公开模板依赖，但不能取代人工审查，也不能保证发现任意形式的秘密。现有用户如需审查升级，请先查看 PR，不直接覆盖设备上的文件。

客户端行为依据：[LOWERTOP Shadowrocket 手册](https://github.com/LOWERTOP/Shadowrocket/wiki)；请以实际设备版本和分流日志为最终证据。
