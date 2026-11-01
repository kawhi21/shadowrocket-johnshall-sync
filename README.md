# Shadowrocket Johnshall Safe Sync

每天北京时间 10:23（UTC 02:23）下载、校验并生成可供 Shadowrocket 引用的纯规则集。GitHub 调度与 iPad 后台刷新不保证准点，Actions 支持手动运行。

## 服务端输出

- generated/proxy.list：上游起始代理规则块。
- generated/reject.list：随后广告拒绝规则块。
- generated/validation.json：上游哈希、数量及生成文件的哈希。

来源：Johnshall/Shadowrocket-ADBlock-Rules-Forever 的 release/sr_cnip_ad.conf。数据归属与 CC BY-SA 4.0 授权见 [NOTICE.md](NOTICE.md)。仅输出白名单规则字段，去掉原始配置段、注释、脚本、重写、MITM 与代理信息；IPv6 CIDR 规范化为 IP-CIDR6。不读取私人订阅、不需要代理 secrets。

## 保持本地扩展的架构

本地 Johnshall-AI-Extended.conf 始终保持为当前配置，AI-Stable 与 AI 模块留在本地。它通过“通用 → 包含配置”包含本地 Johnshall-Auto-Rules.conf，后者引用两份远程 RULE-SET。日常只更新远程列表，不再导入官方原版。

[本地基础配置样例](templates/Johnshall-Auto-Rules.conf.example) 下载后保存为 Johnshall-Auto-Rules.conf。不含 update-url、私人节点、AI 分组或模块。它保留经审查的上游 General 基线和路由，不包含 Google URL 重写、MITM 或脚本；未来 General 变化需另行审查。

## 一次性 iPad 接入及验收：尚需设备端完成

1. 确认远程列表可以匿名下载。仓库私有时不能直接使用 raw 地址；不要在 URL 中放 GitHub token。尚未获准公开时先不要接入。
2. 在文件 App 备份原扩展配置与 AI 模块。停用会调用 shadowrocket://config/add/… 的旧导入自动化。
3. 将基础配置样例保存为本地文件并加入 Shadowrocket，不把它单独用作生产配置。如果导入过程激活它，立即恢复原扩展配置。无法远程替用户验证该导入行为。
4. 在 Johnshall-AI-Extended.conf → 通用 → 包含配置，将 sr_cnip_ad.conf 改为 Johnshall-Auto-Rules.conf。不删原文件，不改 AI-Stable，不重建 AI 模块。
5. 使用/编译原扩展配置。确认两个规则集 URL 成功；蓝色对勾仍为扩展配置；ChatGPT/Muse AI 命中 AI-Stable 且走原日本节点；国内直连及普通国外代理正常。
6. Shadowrocket 设置中，配置自动更新开启后台更新，更新间隔设为 1 天；系统后台 App 刷新允许 Shadowrocket。入口以设备版本为准。旧导入自动化保持停用。
7. 至少观察一次后台刷新，确认远程规则更新而当前配置、节点选择、AI 规则未变。在此之前不声称端到端完成。

依据：[LOWERTOP/Shadowrocket Wiki](https://github.com/LOWERTOP/Shadowrocket/wiki) 的自动更新、包含配置和规则集章节。无 update-url 的本地配置可只更新其远程资源；iOS 调度可能延迟，重启或强制结束 App 后后台任务可能无法启动。本文架构仍需设备版本实际验收。

## 验证和失败保护

运行 python3 -m unittest discover -s tests -v，然后 python3 scripts/sync.py。

校验 HTTP 状态、大小、编码、配置段、规则语法、关键策略及凭据标记。只允许上游顺序为连续 PROXY → REJECT → GEOIP,CN,DIRECT → FINAL,PROXY；顺序或格式变化会停止发布，需人工审查。不会简单按策略重新排序。测试将转换后的规则逐条还原对比原序列。

验证通过后才写出，Action 一次提交全部三份文件；下载/校验失败不提交，GitHub 保留最后合格版本及历史。生成无变化不重复提交。提交失败不会强制推送。

结构验证不保证每条上游规则正确，不能代替设备测试。客户端分别下载两个列表，网络失败可能造成其中一个未更新，须核对成功状态。回退时恢复备份，或将包含配置改回原 sr_cnip_ad.conf 并重新编译原扩展配置。
