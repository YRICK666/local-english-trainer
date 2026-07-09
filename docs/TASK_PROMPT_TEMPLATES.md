# Task Prompt Templates

本文件保存 local-english-trainer 常用任务提示词模板，用于减少每轮重复书写长 prompt。

这些模板只提供结构。具体任务仍必须在 prompt 中写清楚允许文件、禁止文件、接口字段、状态不变量和验收标准。

## 1. 5.5 Planning Template

```text
请协助规划 local-english-trainer 下一步开发。

本轮只做规划，不写代码，不修改文件，不执行 Git 写入命令。

请先读取：
- AGENTS.md
- README.md
- docs/PROJECT_WORKFLOW.md
- skills/workflow/WORKING_STYLE.md
- 与候选方向相关的源码

项目定位：
local-english-trainer 是“英语阅读训练 + 本地单词库搭建”的本地学习系统。
不要扩展 OCR、AI、云服务、复杂复习算法或大规模重构。

请输出：
1. 当前状态判断；
2. 候选方向优先级；
3. 推荐马上做的一个小闭环；
4. 本任务做什么 / 不做什么；
5. 允许修改文件 / 禁止修改文件；
6. 是否涉及后端、前端、数据库、测试；
7. 给 5.4 的执行提示词；
8. 给 5.4 mini 的备选小任务提示词；
9. 验收重点。
```

## 2. 5.4 Backend Task Template

```text
请在 G:\AI-Workstation\local-english-trainer 中执行本轮后端任务。

任务名称：
<任务名>

项目定位：
英语阅读训练 + 本地单词库搭建。
不做 OCR、AI、云服务、词典 API、复杂复习算法或无关重构。

请先读取：
- AGENTS.md
- README.md
- docs/PROJECT_WORKFLOW.md
- 后端相关 model / schema / service / route / tests

允许修改：
<精确列出文件>

禁止修改：
frontend/
docs/
skills/
README.md
package 文件
数据库文件
构建产物
真实学习资料正文

实现要求：
1. 新增或修改 model：<说明>；
2. 新增或修改 schema：<说明>；
3. 新增或修改 service：<说明>；
4. 新增或修改 route：<说明>；
5. 新增或修改 test：<说明>；
6. 必须保持不变的现有接口：<列出路径>。

验证：
运行 python -m pytest。
如果失败，先修复，不要跳过。
任务 prompt 应明确是否允许使用 `apply_patch`。
任务 prompt 应明确是否允许运行 `pytest`。

完成后输出：
1. 修改了哪些文件；
2. 新增了哪些表 / schema / service / route；
3. 新增了哪些测试；
4. pytest 结果；
5. 哪些内容本轮没有做；
6. 下一步建议。

不要执行 git add、git commit、git push 或其他 Git 写入命令。
```

## 3. 5.4 Frontend Task Template

```text
请在 G:\AI-Workstation\local-english-trainer 中执行本轮前端任务。

任务名称：
<任务名>

项目定位：
英语阅读训练 + 本地单词库搭建。
前端保持简约、清爽、文本优先、学习工具感。

请先读取：
- AGENTS.md
- README.md
- frontend/src/App.tsx
- frontend/src/styles.css
- frontend/src/api.ts
- frontend/src/types.ts
- frontend/src/mockData.ts

允许修改：
<精确列出前端文件>

禁止修改：
backend/
tests/
docs/
skills/
package 文件
数据库文件
构建产物
真实学习资料正文

api.ts / types.ts：
<明确是否允许修改；如果不允许，写“禁止修改”。>

必须保持不变：
- selectedAnswers 仍以 question_id 为 key；
- submitPracticeAttempt 仍按整份 pack.questions 提交；
- annotation 状态不能污染作答状态；
- fallback 状态不能白屏；
- 不改变现有后端接口路径和返回结构。

实现要求：
<具体组件、状态、函数、样式类要求>

验证：
运行 cd frontend && npm run build。
如果失败，先修复，不要跳过。
任务 prompt 应明确是否允许使用 `apply_patch`。
任务 prompt 应明确是否允许运行 `npm run build`。

完成后输出：
1. 修改了哪些文件；
2. 前端页面或交互改了什么；
3. 是否改了 api.ts / types.ts；
4. build 结果；
5. 哪些内容本轮没有做；
6. 下一步建议。

不要执行 Git 写入命令。
```

## 4. 5.4 Mini Small Fix Template

```text
请在 local-english-trainer 做一个非常小的修补。

本轮只改 1 到 2 个文件，不扩大范围。

允许修改：
<精确列出文件>

禁止修改：
backend/
tests/
docs/
skills/
frontend/src/api.ts
frontend/src/types.ts
frontend/src/mockData.ts
package 文件
数据库文件
构建产物

具体修改：
1. 在 <组件/函数/位置> 做 <具体动作>；
2. 不新增依赖；
3. 不新增后端接口；
4. 不改数据库；
5. 不自由发挥；
6. 不做无关重构或额外美化。

验证：
前端小修运行 cd frontend && npm run build。
纯文档小修不需要运行 pytest 或 build，但必须说明原因。
任务 prompt 应明确是否允许使用 `apply_patch`。

完成后输出：
1. 修改了哪个文件；
2. 具体改了什么；
3. 是否没有改禁止文件；
4. 检查结果；
5. 是否建议提交。

不要执行 Git 写入命令。
```

## 5. Read-only Review Template

```text
请只做代码验收，不修改任何文件，不写代码，不执行 Git 写入命令。

默认不使用 `apply_patch`。
默认不运行会生成产物的 `pytest` / `build` / 其他验证命令，除非用户当前明确要求。

允许使用只读 Git 命令：
- git status --short
- git diff --name-only
- git diff -- <path>
- git log --oneline --decorate -10
- git ls-files
- git grep "keyword"

允许使用只读读取 / 搜索命令：
- Get-Content .\path\to\file
- Get-ChildItem -Recurse -File -Include *.md,*.ts,*.tsx,*.py | Select-String "keyword"

禁止执行：
- git add
- git commit
- git push
- git reset
- git clean
- git restore
- git checkout
- git merge
- git rebase
- apply_patch
- 会生成产物的 pytest / build
- 提权、清理、reset 类命令

请先读取：
- AGENTS.md
- 与本轮任务相关的源码和测试

搜索优先顺序：
1. git grep
2. Get-ChildItem + Select-String
3. Get-Content

如果命令失败：
- 先汇报失败原因和影响；
- 不要提权；
- 不要清理文件；
- 不要执行 reset / restore。

验收内容：
1. 修改范围是否只包含允许文件；
2. 是否误改禁止文件；
3. 核心功能是否满足任务目标；
4. 关键不变量是否保持；
5. 是否引入越界内容；
6. 测试或构建结果是否可信；
7. 是否建议提交。

最后只输出：
1. 验收结论：通过 / 基本通过 / 不通过；
2. 修改范围是否合格；
3. 核心功能是否合格；
4. 是否发现越界内容；
5. 是否发现必须修复的问题；
6. 是否建议提交；
7. 只应提交哪些文件；
8. 建议本地检查命令。
```

## 6. Prompt Writing Rules

- 任务 prompt 必须明确允许修改哪些文件。
- 任务 prompt 必须明确禁止修改哪些文件。
- 任务 prompt 必须明确本轮不要做什么。
- 任务 prompt 必须明确测试或构建命令；如果不运行，也要说明原因。
- 任务 prompt 必须明确是否允许 `apply_patch`。
- 任务 prompt 必须明确是否允许运行 `pytest` / `build`。
- 任务 prompt 必须明确完成后的输出格式。
- 搜索默认优先使用 `git grep` 或 `Get-ChildItem + Select-String`，不要默认依赖 `rg`。
- 命令失败时先汇报，不要提权、不要清理、不要 reset。
- 5.4 mini 任务必须极窄，通常只改 1 到 2 个文件。
- 后端表/API 任务必须先验收再提交。
- 涉及真实资料、数据库、依赖、Git 写入的任务必须额外确认。
- 不要在模板文件里写某次具体业务任务的长规格。
