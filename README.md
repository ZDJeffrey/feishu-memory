# Feishu Memory

为 Codex 和具有本机工具的桌面对话提供可迁移的飞书远程记忆：开始任务时按需取上下文，完成任务时更新项目状态与长期条目。

## 安装

将仓库链接交给 Codex 并要求安装，或使用技能安装器：

```bash
npx skills add ZDJeffrey/feishu-memory --skill feishu-memory --agent codex --global
```

也可从源码安装：

```bash
git clone https://github.com/ZDJeffrey/feishu-memory.git
cd feishu-memory
python3 scripts/install.py --activate
```

仓库安装器将技能放入 `${CODEX_HOME:-~/.codex}/skills/feishu-memory`；`--activate` 同时登记全局调用入口并保留已有指令。Windows 可使用 `py -3` 执行脚本。

新开对话后直接给出任务，例如：`$feishu-memory 继续论文项目，整理当前进展和下一步。`

## 首次使用

Agent 将环境准备作为任务的前置步骤：检查 Python、飞书 CLI 和配套技能，按照 [官方 README](https://github.com/larksuite/cli/blob/main/README.zh.md) 补齐安装与应用配置，引导用户授权，并连接记忆空间。已有配置优先复用，空间尚未明确时询问连接目标；浏览器授权和管理员审批由用户配合完成。

首次调用会登记全局记忆入口，准备就绪后继续原任务，结束时维护项目状态。[完整设置流程](references/setup.md) 随技能提供。通过 `npx` 安装时，入口登记使用 `scripts/install.py --activate-only` 保留原安装位置；用户可指定仅在本次任务使用。

用户配置默认保存在 `~/.config/feishu-memory/config.json`，结构见 [配置模板](references/config.example.json)。认证凭据由飞书 CLI 管理。技能源码独立于账号、文档标识和机器路径。

## 日常流程

`begin` 读取核心准则和导航，`begin --project PROJECT` 加载项目状态；`search` 在记忆根目录检索，`read` 按章节或关键词展开。`replace` 校验目录链和读取版本，更新完整文本块并回读，回执保存来源、前后内容和版本。

默认每页最多 5 个搜索结果、每次最多 12000 个正文字符。内容相同跳过写入，版本冲突交回 Agent 重新读取并合并。详见 [读写操作](references/operations.md)。

## 换机器

安装本技能，复制自己的资源配置或提供飞书入口，再用 `$feishu-memory` 提出任务。Agent 按需安装 CLI、配置应用并引导授权，然后读取记忆继续工作。CLI 可通过 PATH、`FEISHU_MEMORY_CLI` 或配置中的可选 `cli` 字段定位；资源配置可通过 `FEISHU_MEMORY_CONFIG` 或 `--config` 指定。

执行器仅使用 Python 3.9+ 标准库。当前实机验证平台为 macOS；Linux 和 Windows 分支需要对应平台验证。本机锁协调本机写入，多机器同时写同一文档时使用统一写入方。

## 验证

```bash
python3 scripts/check.py
python3 scripts/memory.py doctor
```

`check.py` 检查配置独立性、预算、目录约束、版本冲突和重复更新等行为；`doctor` 检查当前用户的运行环境。实际读写验证在用户自己的独立记忆目录中执行，结果保留在本机。
