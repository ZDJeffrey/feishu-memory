# Feishu Memory

为具有本机工具的 Agent（如 Claude Code、Codex）提供可迁移的飞书远程记忆：开始任务时按需取上下文，完成任务时更新项目状态与长期条目。Agent 直接调用飞书官方 [lark-cli](https://github.com/larksuite/cli) 及其配套技能读写，本技能约定记忆的组织、读取范围与更新方式。

## 安装

使用技能安装器（`--agent` 可指定目标 Agent，省略时按安装器检测结果安装）：

```bash
npx skills add ZDJeffrey/feishu-memory --skill feishu-memory --global
```

也可从源码安装到 Codex 技能目录：

```bash
git clone https://github.com/ZDJeffrey/feishu-memory.git
cd feishu-memory
python3 scripts/install.py
```

`install.py` 将技能放入 `${CODEX_HOME:-~/.codex}/skills/feishu-memory`，不修改 `AGENTS.md` 或注册全局入口。Windows 可使用 `py -3` 执行脚本。

需要使用记忆时，在当前对话明确引入技能并说明任务，例如 `$feishu-memory 继续论文项目，整理当前进展和下一步。`（Codex）或 `/feishu-memory …`（Claude Code）。

## 首次使用

安装并调用技能后，默认流程如下：

| 执行方 | 操作 |
| --- | --- |
| 用户 | 提供已有飞书应用的 App ID。 |
| Agent | 按[官方 README](https://github.com/larksuite/cli/blob/main/README.zh.md)安装缺失的 CLI 和配套技能，选择 profile，给出可直接执行的配置命令。 |
| 用户 | 在本机终端运行命令，隐藏输入 App Secret。 |
| Agent | 核对应用配置，发起用户授权并展示链接和二维码。 |
| 用户 | 在浏览器完成授权。 |
| Agent | 完成登录，查找并连接已有记忆空间，首次建立时创建独立空间；写入本机配置、验证并继续原任务。 |

已有配置与有效授权直接复用。只有多个空间候选、入口无法定位或管理员审批等情况需要用户补充处理。[完整设置流程](references/setup.md) 随技能提供。

本机配置默认保存在 `~/.config/feishu-memory/config.json`，只记录 CLI profile、Wiki 空间与首页、核心摘要入口，结构见 [配置模板](references/config.example.json)；可用 `FEISHU_MEMORY_CONFIG` 指定其他位置。认证凭据由飞书 CLI 管理。技能源码独立于账号、文档标识和机器路径。

## 日常流程

显式启用技能后，Wiki 作为用户与 Agent 共用入口。Agent 通过 `scripts/mirror.py` 维护只读的本地 Markdown 副本：开始任务时只拉取远端改动过的页面并查看差异，在本地检索与阅读，写入仍直接修改飞书文档。开始任务时读取核心摘要与任务相关规范；项目明确时读取项目概述，入口不明时读取首页，再按需在本地副本中检索和按章节展开。启动正文约 4000 字符，常规展开单次约 12000 字符，每轮最多检查 5 个候选。

更新时 Agent 按官方 `lark-doc` 流程读取目标、携带版本号写入并回读：被新结论取代的内容直接替换或删除，比较与映射用表格，流程与架构用画板；历史由飞书文档版本记录承载，可用 `+history-revert` 回滚。删除、移动、权限变更、整篇覆盖和扩大读写范围前先取得用户确认。命令见 [读写操作](references/operations.md)。

通用记忆正文与导航保存在 Wiki 入口下；每个项目和学习主题是知识库根目录下的一棵同级目录树，树根为概述，可同时保存设计、实验、报告和汇报产物，页面标题由目录表达归属、不加项目前缀。知识库之外的资料通过概述中的资源索引登记入口与读写范围，默认只读，约定见 [外部资源接入](references/external-resources.md)。

## 换机器

安装并调用本技能，应用尚未绑定时提供原 App ID，按 Agent 给出的命令完成终端配置和浏览器授权。Agent 自动搜索“知识与协作入口”、核对 Wiki 空间并写入本机配置。具体操作见[自动发现与连接记忆空间](references/setup.md#自动发现与连接记忆空间)。

本机配置保存实际 profile 和 Wiki 入口，应用凭据与用户令牌由各机器的 CLI 独立管理。多机器同时写同一文档时，以 `--revision-id` 检测冲突并重新读取合并。

## 验证

```bash
python3 scripts/check.py
lark-cli --profile memory auth status --json --verify
```

`check.py` 检查安装的幂等性、已有指令文件不变及本地副本规划；授权检查确认当前机器的 CLI 登录状态。实际读写在用户授权的 Wiki 中执行。
