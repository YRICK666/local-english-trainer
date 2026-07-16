# Local English Trainer Desktop 项目流程复盘

## 1. 项目目标与边界

项目从本地 Web 学习工具演进为 Windows 桌面版：Tauri 2 承载 React 静态 UI，完整 PyInstaller onedir FastAPI sidecar 保留既有业务 HTTP 边界，用户学习数据最终位于安装目录外。桌面端的 token、随机端口、child handle、资源路径与数据库路径只能由 Rust lifecycle 管理，不能进入 JavaScript。

P2.5 只在明确创建的临时数据根验证架构，不读写真实 SQLite；P3 才接入用户数据目录、bootstrap 和迁移；P4 才处理 NSIS、签名和发布。

## 2. 当前桌面架构

```text
React UI → LearningService（待接入） → Tauri typed command
         → Rust lifecycle / typed proxy → tokenized loopback FastAPI sidecar
         → explicit user-data root（P3） → SQLite
```

完整 onedir 作为 Tauri `bundle.resources` 资源递归携带，而非 `externalBin` 单 exe。FastAPI HTTP 边界保留；`/health` 和 `/desktop/shutdown` 是 Rust 生命周期私有接口，不是前端业务 API。

## 3. 阶段时间线与成果

| 阶段 | 成果 |
| --- | --- |
| P0/P1/P1.5 | 独立 CPython/锁文件、FastAPI desktop sidecar、随机 loopback/token/ready/health/shutdown、外部数据根与安全迁移基础。 |
| P2 | Tauri 2 最小静态壳、React 静态资源、debug no-bundle 与真实交互窗口验证。 |
| P2.25 | 定稿平台边界：React 不直连 sidecar，Rust 持有 token/port/child，未来使用 LearningService adapter。 |
| P2.5-A | 完整 PyInstaller onedir resource staging，拒绝数据库、reparse point 和不安全覆盖，验证资源目录。 |
| P2.5-B | Rust sidecar startup lifecycle：资源解析、临时根、ready/health/version 验证与安全 child 管理。 |
| P2.5-B-X/Y/Z | 修复 Windows/WebView2 与 headless probe 的实际运行差异，消除跨 target 重复模块/无效 warning。 |
| P2.5-C | CloseRequested 幂等协调、tokenized graceful shutdown、精确 child fallback、supervisor；真实 lifecycle smoke 和 Windows 回归通过。 |
| 工作流纠偏 | 将“普通工程失败应自动修复”与“真正安全停止”分离，并形成长期规则。 |
| P2.5-D1（当前） | 已有固定只读 `GET /api/reading-packs` 的 typed Rust proxy、零参数 `list_reading_packs` command 与 mock/协议单测；未提交。 |

P2.5-C 已完成并推送：`72ee325 docs: clarify agent workflow`、`3ca4075 feat: add Tauri sidecar shutdown lifecycle`。

## 4. 关键技术决策

- 继续保留 FastAPI：复用稳定业务模型、测试和 API 契约，不把桌面化变成业务重写。
- 完整 onedir resources：PyInstaller `_internal` 不可丢失，避免只复制 exe 的运行时失败。
- Rust lifecycle：token、端口、child 与 shutdown 不进入 WebView，减少本地 HTTP 与 XSS 的暴露面。
- 固定 allowlist proxy：业务 command 不接受任意 method/path/header/URL；D1 先验证一个无副作用接口。
- 临时根优先：先验证生命周期和资源，再授权真实用户数据，避免实现顺序倒置。
- 人工窗口确认独立于 headless smoke：前者验证 WebView2 视觉行为，后者验证可重复的进程与协议链路。

这些决策没有过度设计；它们是 Windows 进程安全和未来跨平台 adapter 的必要边界。需要控制的是后续代理与 service 的粒度，避免一次迁移全部 20 个 API。

## 5. 出现过的问题

- 任务范围曾过大，导致一个 prompt 同时要求实现、打包、人工验证与全回归。
- 长期安全规则反复复制到 prompt，掩盖了当轮真正目标。
- “最终工作区干净/所有验收通过”曾被误当作“开始实现”的前提。
- patch 或文本锚点失败、首次编译失败、warning 曾被误判为必须停止，而非需要诊断的工程问题。
- 自动化会话的 WebView2/GUI 权限限制与真实交互窗口行为不同；应记录环境限制，不应误判项目失败。
- 多 target 共享模块曾引入重复实现和 warning，需要通过真实模块结构收敛，而非压 warning。
- GitHub GH007 私有邮箱保护在 push 时才暴露；提交前未先核对作者邮箱。
- stash 恢复后 `lib.rs` 的 SHA-256 不同：当前 CRLF、备份 LF，标准化文本完全一致；字节哈希不应单独作为代码覆盖依据。

## 6. 做得好的地方

- 始终把真实 SQLite 与 P2.5 临时根隔离，未以“验证方便”为由突破数据边界。
- 使用精确 child handle，而非按进程名或端口 broad-kill。
- 每个生命周期关键点都有可自动验证的 marker、协议约束和故障场景。
- 外部资源、sidecar 启动、健康校验和退出清理均在真实 Windows 上得到验证；视觉内容由用户真实会话确认。
- D1 从最小只读接口开始，并将不泄漏 token/endpoint 变成结构性约束与测试，而不是口头约定。

## 7. 流程低效的根本原因

核心问题不是安全要求本身，而是没有稳定地区分：已声明 baseline 与未知污染、普通工程失败与真实风险、单元测试与 smoke、功能完成与已推送。每次都把历史背景、工具链细节、禁止项和最终验收完整复述，使 prompt 变长、执行目标反而变模糊。

解决方式是：长期规则在 `AGENTS.md`/`AGENT_WORKFLOW.md`，阶段设计在架构文档，当轮 prompt 只描述一个小闭环和特殊例外。

## 8. 后续工作流建议

- 一个任务只做一个可验证闭环；允许 dirty baseline 时先登记清单，不要求绝对干净。
- 开始只做轻量 preflight；实现中运行受影响的编译和单测；完整回归只在阶段末。
- patch 失败后改用符号定位或受控整文件写入；首次失败必须诊断并重试。
- feature、docs/workflow 和生成/配置变更分开提交；功能完成后及时提交，不长期堆积多个阶段。
- 提交前检查 `git config user.email` 与远端邮箱保护策略；不要在 push 失败后才修正身份。
- stash 前后同时记录字节 hash、BOM、换行和标准化文本比较；只在实际内容差异时处理冲突。
- 构建、协议 smoke、人工视觉确认分别记录 PASS/SKIP/人工确认，不能互相替代。
- 如阶段状态较多，可在每个 P2.5 子阶段结束时更新一页简短状态记录；无需引入维护成本高的独立 CHANGELOG。

## 9. 当前项目状态

- P2.5-C 已完成、已提交并已推送。
- P2.5-D1 已实现但未提交。
- D1 选择固定只读接口：`GET /api/reading-packs`。
- 已有零参数 Tauri command：`list_reading_packs`。
- 当前 D1 的 `cargo check --all-targets` 与 `cargo test --all-targets` 已通过（34 tests）。
- 尚未做真实 D1 sidecar/proxy smoke，尚未接入 React `LearningService`，也未实现写接口。

## 10. 建议的后续阶段

1. **D1 收口**：只做真实临时根 sidecar 的只读 proxy smoke，确认 command → Rust → sidecar → shutdown；通过后提交 D1。
2. **D2 React LearningService adapter**：把既有 `api.ts` 包装为 web/tauri/mock adapter，先迁移 reading-pack 读取，不改变页面业务行为。
3. **D3 typed write operations**：按业务簇分批加入导入、attempt、annotation、vocabulary/sentence，逐项建立 DTO、大小限制、错误映射和测试。
4. **P3 用户数据与 bootstrap**：取得明确授权后才实现目录选择、首次启动、迁移、备份与恢复 UX。
5. **P4 安装与发布**：NSIS、升级/卸载数据保留、签名和 release smoke。

## 11. 维护建议

| 时机 | 建议 |
| --- | --- |
| 立即执行 | 完成 D1 的一次真实只读 smoke 后立即以功能提交收口；继续保持 master 上的小而完整提交即可，无需此时引入功能分支。 |
| 下一阶段 | D2 先建立 adapter contract，再迁移一个读取流；D3 按业务簇而非按所有 endpoint 一次性实现。 |
| 暂缓执行 | 真实用户数据目录、迁移、安装器、签名、Android；它们依赖 P2.5 通信边界稳定。 |

当前 sidecar lifecycle 对 P2.5 已足够：启动、ready/health、意外退出、graceful/fallback cleanup 和 supervisor 均已覆盖。Typed proxy 应只覆盖页面实际需要的业务操作，并保留一个 command 对一个业务意图的语义；不应退回通用 HTTP 隧道。测试数量目前与风险相称：单元测试保障协议，smoke 验证进程链路，人工确认覆盖 GUI。后续优先维护这三层，而不是堆叠同类 smoke。

## 12. 下一轮最短提示词模板

> 在已声明 D1 baseline 上完成真实临时根只读 proxy smoke：仅验证 `list_reading_packs`，不访问真实 SQLite、不改 React；通过后报告并建议精确 D1 提交范围，遵守 AGENTS.md。