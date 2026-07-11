# Inline Annotation Design

- Status: Implemented through Round 4
- Round 1 已通过 `9b82e86 feat: add precise annotation offsets` 提交。
- Round 2-4 已通过 `839fb20 feat: add inline annotation workflow` 提交。
- 本文仍是当前实现和后续演进的长期架构基线。
- 不得把后续计划误写成当前已完成能力。

当前已实现：

- 同一 `paragraph` 内选区。
- 桌面端右键创建四类 annotation：`answer_evidence`、`synonym_replacement`、`vocabulary`、`difficult_sentence`。
- Unicode code point offset，并使用 `[start_offset, end_offset)`。
- 持久化原文内联高亮。
- 部分重叠和包含 annotation 渲染。
- 旧无 offset annotation 的唯一匹配回退显示。
- `vocabulary` 与 `difficult_sentence` annotation 自动进入本地词库或句库。
- annotation 与自动入库项目保持原子事务，失败 rollback。
- 删除 annotation 后保留学习项目，并清空对应 `source_annotation_id`。
- Settings 中四类 annotation 颜色配置。
- `localStorage` 颜色配置安全回退。

后续允许演进：

- `answer_evidence` / `synonym_replacement` 绑定具体题号的交互和校验。
- Vocabulary 来源复习 UI 补强。
- AI annotation suggestion 工作流。

## Goals

- 支持在原文段落正文内拖选文字。
- 桌面端支持通过右键菜单选择四种 annotation 类型：`answer_evidence`、`synonym_replacement`、`vocabulary`、`difficult_sentence`。
- 支持原文内联持久化高亮，而不只是列表展示。
- `vocabulary` 与 `difficult_sentence` 标注可自动进入本地词库或句库。
- 在 `Settings` 中支持自定义不同标注类型的颜色。
- 保留来源回看能力，使词库和句库项目能回到原文上下文。

## Non-goals

- 不支持跨段选择。
- 不使用 `contenteditable`。
- 不做富文本编辑器方案。
- 不做 annotation `PATCH`。
- 不做颜色配置的后端同步。
- 不做 AI、OCR、词典、翻译、Anki 或复杂复习算法。

## Offset Contract

- offset 统一采用半开区间：`[start_offset, end_offset)`。
- offset 单位为 Unicode code point，不是 UTF-16 code unit。
- offset 相对于 `Paragraph.text` 的原始纯文本，不相对于 DOM、HTML 或高亮后的切片。
- `selected_text` 必须严格等于 `Paragraph.text` 的对应 slice；不一致时应视为无效输入。
- 前端从 JavaScript `Selection` 获取位置时，必须显式处理 UTF-16 到 code point 的换算，不能直接把字符串下标当作最终持久化 offset。
- 不做 Unicode normalization。
- 不保存 `normalized_text` 或其他派生标准化文本字段。

## Selection Boundary

- 只允许在同一 `paragraph` 的正文文本内选择。
- 段落序号、题目、按钮、筛选器、来源回看控件和其他 UI 不属于可标注文本范围。
- 空白选择、collapsed selection、跨段选择都应视为无效。
- 没有有效选区时，保留浏览器或平台原生菜单，不强行拦截。
- 未来移动端可以改用长按或触摸工具栏，但最终仍必须产出同一套标准 offset 数据。

## Inline Rendering

- 渲染时先收集当前段落所有 annotation 的 offset 边界。
- 按 code point 级别切片，不按 UTF-16 下标直接切。
- 每个切片可维护 coverage 集合，用于表达单个范围被哪些 annotation 覆盖。
- 渲染结果必须保持原有空格、标点和文本顺序，不允许因高亮破坏原文内容。
- 支持重叠标注。
- 来源回看 focus 态与 annotation type 颜色态必须可以共存，不能互相覆盖掉语义。
- 对旧 annotation，如果尚无 offset，但 `selected_text` 在该段内唯一匹配，可做临时定位显示。
- 对旧 annotation，如果 `selected_text` 在该段内零次匹配或多次匹配，不做错误高亮，避免误导用户。

## SQLite Compatibility

- 当前项目没有 Alembic。
- `create_all` 不会自动更新旧表结构，因此不能把新增列依赖在 `create_all` 上。
- 新 offset 字段升级应采用 nullable additive `ALTER TABLE`。
- 升级前应用 `PRAGMA table_info` 做幂等检测，避免重复加列。
- 新数据库可以直接按最新 model 建表；旧数据库必须走兼容升级路径。
- 自动测试只操作临时数据库，不接触真实 `data/local_english_trainer.sqlite3`。
- 首次在真实数据库启动前应由用户自行备份。
- 任务执行方不得主动启动默认后端去升级真实数据库。

## Automatic Library Creation

- `vocabulary` annotation 自动创建 vocabulary item。
- `difficult_sentence` annotation 自动创建 sentence item。
- annotation 创建与对应库项目创建必须在一个事务中完成，并且一次 commit。
- 任一步骤失败都必须 rollback。
- 不自动生成 `meaning`、`translation` 或 `structure_note`。
- `answer_evidence` 与 `synonym_replacement` 不自动入库。

## Deletion Lifecycle

- 删除 annotation 时保留已创建的 vocabulary item 或 sentence item。
- 删除 annotation 时清空对应库项目的 `source_annotation_id`。
- 删除 annotation 时保留库项目上的 `source_pack_id`、`source_passage_id`、`source_paragraph_id`。
- 删除库项目时不反向删除 annotation。
- 旧的手动入库流程仍应兼容：没有 `source_annotation_id` 的历史词条或句条仍可继续存在和编辑。

## Color Settings

- 颜色设置保存在 `localStorage`。
- 固定 key：`local-english-trainer.annotation-colors`。
- 四种 annotation 类型各有默认颜色。
- 输入颜色值时只接受 `#RRGGBB` 格式。
- 非法值按类型逐项回退，不因单项错误污染全部设置。
- 页面样式通过 CSS variables 消费颜色配置。
- 修改颜色后应即时生效。
- 提供恢复默认颜色的能力。
- 类型表达不能只靠颜色，还需要文本标签、图例或其他非颜色提示。

## Implementation Rounds

### Round 1

- 目标：补齐精确 annotation offsets 与 SQLite 兼容升级路径。
- 主要影响区域：`backend/app/models.py`、annotation schema/service、数据库初始化与升级逻辑、相关测试。
- 验证类型：后端单元测试与兼容性测试。
- 数据库影响：新增 nullable offset 字段，要求 additive、幂等。

### Round 2

- 目标：实现 paragraph selection、context menu 与原文内联渲染。
- 主要影响区域：`frontend/src/App.tsx`、相关样式和前端类型。
- 验证类型：前端构建、交互手工验证、旧 annotation 回退验证。
- 数据库影响：无新增表；读取并使用 Round 1 已提供的 offset 字段。

### Round 3

- 目标：实现自动原子入库与删除生命周期联动。
- 主要影响区域：annotation、vocabulary、sentence service 与 API 测试。
- 验证类型：后端事务测试、失败回滚测试、删除联动测试。
- 数据库影响：可能只涉及兼容性列读取，不新增独立表。

### Round 4

- 目标：实现 annotation 颜色设置与交互回归收口。
- 主要影响区域：前端 settings、workspace 渲染、样式与手工验收说明。
- 验证类型：前端构建、设置持久化手测、交互回归。
- 数据库影响：无；颜色配置只保存在本地前端存储。

## Protected Invariants

- `selectedAnswers` 仍以 `question_id` 为 key。
- `submitPracticeAttempt` 仍提交整份 `pack.questions`。
- annotation state 不污染作答状态。
- 同 pack 来源回看保留当前作答。
- 跨 pack 切换按现有规则清理相关状态。
- Vocabulary / Sentences 的 CRUD、筛选和来源回看保持可用。
- 真实 `reading_pack` 与用户数据库不能进入 Git。

## Manual Acceptance Pack

- `pack_id`: `kaoyan-2010-english-1-text-1`
- 不重新导入该材料。
- 手工验证由用户执行。
- 自动任务不得批量写入真实数据。
