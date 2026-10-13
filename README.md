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

安装并调用技能后，默认流程如下：

| 执行方 | 操作 |
| --- | --- |
| 用户 | 提供已有飞书应用的 App ID。 |
| Agent | 按[官方 README](https://github.com/larksuite/cli/blob/main/README.zh.md)安装缺失的 CLI 和配套技能，选择 profile，给出可直接执行的配置命令。 |
| 用户 | 在本机终端运行命令，隐藏输入 App Secret。 |
| Agent | 核对应用配置，发起用户授权并展示链接和二维码。 |
| 用户 | 在浏览器完成授权。 |
| Agent | 完成登录，查找并连接已有记忆空间，首次建立时创建独立空间；生成本机配置、登记入口、验证并继续原任务。 |

已有配置与有效授权直接复用。profile、目录与资源配置由 Agent 管理；只有多个空间候选、迁移检索受阻或管理员审批等情况需要用户补充处理。

首次调用会登记全局记忆入口，准备就绪后继续原任务，结束时维护项目状态。[完整设置流程](references/setup.md) 随技能提供。通过 `npx` 安装时，入口登记使用 `scripts/install.py --activate-only` 保留原安装位置；用户可指定仅在本次任务使用。

用户配置默认保存在 `~/.config/feishu-memory/config.json`，结构见 [配置模板](references/config.example.json)。认证凭据由飞书 CLI 管理。技能源码独立于账号、文档标识和机器路径。

## 日常流程

`begin` 读取核心准则和导航，`begin --project PROJECT` 加载项目状态；`search` 在记忆根目录检索，`read` 按章节或关键词展开。`replace` 校验目录链和读取版本，更新完整文本块并回读，回执保存来源、前后内容和版本。

默认每页最多 5 个搜索结果、每次最多 12000 个正文字符。内容相同跳过写入，版本冲突交回 Agent 重新读取并合并。详见 [读写操作](references/operations.md)。

运行状态统一保存到 `~/.local/state/feishu-memory/`，包括快照、搜索缓存和写回回执；各会话共用，可通过 `--state-dir PATH` 指定其他位置。

## 换机器

安装并调用本技能，应用尚未绑定时提供原 App ID，按 Agent 给出的命令完成终端配置和浏览器授权。Agent 自动搜索“记忆系统入口”、核对原空间并生成本机资源配置。CLI 已就绪时直接进入空间发现；已有配置文件和入口链接可作为可选的定位方式。具体操作见[自动发现与连接记忆空间](references/setup.md#自动发现与连接记忆空间)。

资源配置保存本机实际 profile 和远程记忆位置，应用凭据与用户令牌由各机器的 CLI 独立管理。CLI 可通过 PATH、`FEISHU_MEMORY_CLI` 或配置中的可选 `cli` 字段定位；资源配置可通过 `FEISHU_MEMORY_CONFIG` 或 `--config` 指定。

执行器仅使用 Python 3.9+ 标准库。当前实机验证平台为 macOS；Linux 和 Windows 分支需要对应平台验证。本机锁协调本机写入，多机器同时写同一文档时使用统一写入方。

## 验证

```bash
python3 scripts/check.py
python3 scripts/memory.py doctor
```

`check.py` 检查配置独立性、预算、目录约束、版本冲突和重复更新等行为；`doctor` 检查当前用户的运行环境。实际读写验证在用户自己的独立记忆目录中执行，结果保留在本机。
