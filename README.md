# Feishu Memory

为 Codex 和具有本机工具的桌面对话提供可迁移的飞书远程记忆：开始任务时按需取上下文，完成任务时更新项目状态与长期条目。

## 安装

将本仓库交给 Codex 并要求安装，或在仓库目录执行：

```bash
python3 scripts/install.py --activate
```

安装器将技能放入 `${CODEX_HOME:-~/.codex}/skills/feishu-memory`，并保留已有全局指令。省略 `--activate` 时只安装技能，在对话中用 `$feishu-memory` 调用。Windows 可使用 `py -3` 执行脚本。

新开对话后可直接说：“使用 feishu-memory，配置我的远程记忆并继续当前项目。”

## 首次使用

技能先检查飞书 CLI。未安装时，由 Agent 阅读 [官方 README](https://github.com/larksuite/cli/blob/main/README.zh.md) 并完成安装；随后引导应用配置、浏览器授权和独立记忆目录初始化。已有空间可直接连接。[完整设置流程](references/setup.md) 随技能提供。

用户配置默认保存在 `~/.config/feishu-memory/config.json`，结构见 [配置模板](references/config.example.json)。认证凭据由飞书 CLI 管理。技能源码独立于账号、文档标识和机器路径。

## 日常流程

`begin` 读取核心准则和导航，`begin --project PROJECT` 加载项目状态；`search` 在记忆根目录检索，`read` 按章节或关键词展开。`replace` 校验目录链和读取版本，更新完整文本块并回读，回执保存来源、前后内容和版本。

默认每页最多 5 个搜索结果、每次最多 12000 个正文字符。内容相同跳过写入，版本冲突交回 Agent 重新读取并合并。详见 [读写操作](references/operations.md)。

## 换机器

安装本技能，复制自己的资源配置，在新机器安装飞书 CLI 并完成授权，然后运行 `begin`。CLI 可通过 PATH、`FEISHU_MEMORY_CLI` 或配置中的可选 `cli` 字段定位；资源配置可通过 `FEISHU_MEMORY_CONFIG` 或 `--config` 指定。

执行器仅使用 Python 3.9+ 标准库。当前实机验证平台为 macOS；Linux 和 Windows 分支需要对应平台验证。本机锁协调本机写入，多机器同时写同一文档时使用统一写入方。

## 验证

```bash
python3 scripts/check.py
python3 scripts/memory.py doctor
```

`check.py` 检查配置独立性、预算、目录约束、版本冲突和重复更新等行为；`doctor` 检查当前用户的运行环境。实际读写验证在用户自己的独立记忆目录中执行，结果保留在本机。
