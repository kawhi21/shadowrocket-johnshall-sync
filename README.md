# Shadowrocket Johnshall Safe Sync

每天北京时间 10:23（UTC 02:23）检查公开上游；GitHub 调度可能延迟。也支持 Actions → Validate Johnshall upstream → Run workflow。

上游：https://github.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/blob/release/sr_cnip_ad.conf

## 输出与隐私

仅发布 `generated/validation.json`：固定来源、SHA-256、字节数、规则类型和策略数量。**它不是 Shadowrocket 配置或订阅，不能导入。** 原始上游只在内存中校验，不写入仓库、日志或 artifact。不读取私人订阅、节点、AI-Stable 或任何本地配置，不需要添加代理 secrets。

`scripts/sync.py` 拒绝重定向、非 200、异常大小/编码、HTML、未知配置段、重复段、异常规则语法/策略和常见凭据标记；要求至少一万条规则、广告拒绝规则、唯一 CN 直连及结尾默认代理。格式变化会使工作流失败，需人工审查后调整。此为结构验证，不保证上游每条规则正确，也不验证实际代理连通性。

全部校验成功后才原子替换报告。失败不提交，保留最后合格报告。未变化不产生提交；变化通过 Git 历史保留，运行时间与失败记录在 Actions 中查看。报告哈希对应所下载原文件的全部字节，并非重新分发该文件。

## 文件与验收

- `.github/workflows/sync.yml`：定时/手动/脚本变更触发，互斥执行、五分钟超时、固定 checkout 提交、提交步骤临时认证。
- `scripts/sync.py`：仅依赖 Python 标准库。
- `tests/test_sync.py`：合成样本测试成功、幂等、异常下载、凭据输入和失败保留。

运行 `python3 -m unittest discover -s tests -v`，然后 `python3 scripts/sync.py`。访问 Actions 检查首次运行是否成功，以及生成报告。若组织策略或分支保护阻止写入，需要仓库管理员解决，脚本不会强制推送。

## Shadowrocket

保持当前 Johnshall-AI-Extended.conf 和 AI-Stable 在本地。此项目仅自动验证公共上游，不自动更新 iPad，也不导入或切换任何配置。不要将私人节点、完整订阅或 GitHub token 加入仓库或订阅 URL。
