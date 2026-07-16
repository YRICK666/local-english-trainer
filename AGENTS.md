# AGENTS.md

## 项目与范围

Local English Trainer 是本地英语学习工具：导入 reading pack → 阅读、作答与标注 → 本地词库和句库沉淀。保持 React/Vite、FastAPI/SQLite 与 Tauri Windows 壳的职责分离；不将桌面生命周期、Windows 路径、token 或端口泄漏到 React。

除非用户明确要求，不扩展 OCR、AI、云服务、PDF 解析、Anki、复杂复习算法或大规模 UI 重构。

## 不可突破的安全边界

- 不提交或读取真实学习资料、`.env`、数据库、用户数据、构建产物、`node_modules`、虚拟环境或日志。
- 未获当轮明确授权，不访问、复制、迁移、覆盖或删除真实 SQLite；测试只使用归属明确的临时根。
- 不 broad-kill、按进程名清理或影响用户既有进程；只操作本轮保存的精确 child/PID。
- 不修改永久 PATH、代理、Java、系统安全设置、ACL、所有者或工具链，除非用户明确授权。
- 未获明确授权，不执行 Git 写操作（包括 `add`、`commit`、`push`、`reset`、`restore`、`clean`、`checkout`、`merge`、`rebase`）。

## 执行摘要

1. 每轮只完成一个可验证的小闭环；先读相关代码和文档，再实施。
2. 已声明、属于当前阶段的中间修改是工作基线，不是污染；开始时登记文件清单。
3. patch/锚点、命令、编译、测试或 warning 的首次失败都应分析、修复并重试，不能直接停止。
4. 仅因未知 staged 内容、范围外未知修改、真实数据风险、未授权高风险操作或无法安全理解代码而停止。
5. 结束时按任务范围做验证并报告：修改文件、验证结果、剩余 warning/SKIP、Git 状态，以及功能完成/可提交/已推送分别处于何种状态。

完整 preflight、失败分流、Git、测试、smoke 和人工确认规则见 [docs/AGENT_WORKFLOW.md](docs/AGENT_WORKFLOW.md)。后续任务 prompt 只需写目标、允许文件、已声明的 dirty baseline、验收和特殊限制。

## 领域长期约束

- 默认本地运行与 SQLite；用户数据、安装目录和桌面资源必须分离。
- 原文标注定位使用 `paragraph_id`、`start_offset`、`end_offset`、`selected_text`；offset 为原始段落纯文本的 Unicode code point `[start_offset, end_offset)`，`selected_text` 必须等于 slice。
- SQLite 升级必须 additive、幂等、可测试，且不得触碰真实库；annotation 与自动 vocabulary/sentence 入库必须原子。
- 删除 annotation 不删除已积累的词库或句库项目，只清空其 `source_annotation_id`。
- 不引入 `contenteditable`、富文本编辑器、第三方高亮库或全局状态库实现标注，除非后续明确批准。

详细标注设计见 [docs/INLINE_ANNOTATION_DESIGN.md](docs/INLINE_ANNOTATION_DESIGN.md)。桌面架构与阶段边界见 [docs/DESKTOP_ARCHITECTURE.md](docs/DESKTOP_ARCHITECTURE.md) 和 [docs/P2_25_PLATFORM_AND_SIDECAR_DESIGN.md](docs/P2_25_PLATFORM_AND_SIDECAR_DESIGN.md)。