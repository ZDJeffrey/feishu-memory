# Agent 协作

按记忆空间“模型能力与任务分配”的路由与 effort、分派与验收章节选择模型和档位，提供任务目标、范围、适用规范和验收标准。子 Agent 继承启用状态时，明确传递该状态与父任务已同步的本地副本位置。

当前协作工具的 `task_name` 使用小写字母、数字和下划线，以模型前缀标明执行者，例如 `terra_<task>`、`luna_<task>`、`astra_<task>` 或 `sol_<task>`。工具自动生成包含父任务路径的完整名称；模型由 `model` 参数显式指定完整模型 ID，名称本身不会切换模型。选择不同模型且工具要求独立上下文时使用 `fork_turns=none`，传递完成任务所需的上下文；可用模型、参数与名称规则以当前工具为准。

例如，指定 `task_name="terra_skill_routing"` 与 `model="gpt-6.1-terra"`，根 Agent 创建的子任务显示为 `/root/terra_skill_routing`。当前工具的 `/root` 前缀由运行器生成，没有通过技能修改为 `/terra` 的参数；嵌套任务保留父级路径。
