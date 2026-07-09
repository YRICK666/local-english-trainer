# Code Review Guide

本文件固定 Codex / 5.5 对 local-english-trainer 做只读验收时的检查规则。

验收目标是确认任务是否按范围完成、是否破坏现有学习闭环、是否引入越界功能。默认不写代码、不修改文件。

## 1. Review Mode

- 验收默认只读。
- 不修改文件。
- 不写代码。
- 不执行 Git 写入命令。
- 不使用 `apply_patch`。
- 不因为缺少 `rg`、删除失败或权限失败就放开沙盒权限。
- 可以使用只读命令确认状态，例如：
  - `git status --short`
  - `git diff --name-only`
  - `git diff -- <path>`
  - `git log --oneline --decorate -10`
  - `git ls-files`
  - `git grep "keyword"`
  - `Get-Content .\path\to\file`
  - `Get-ChildItem -Recurse -File -Include *.md,*.ts,*.tsx,*.py | Select-String "keyword"`
- 禁止执行：
  - `git add`
  - `git commit`
  - `git push`
  - `git reset`
  - `git clean`
  - `git restore`
  - `git checkout`
  - `git merge`
  - `git rebase`
  - `apply_patch`
  - 会写入文件的 PowerShell 命令
  - 会生成产物的验证命令，除非用户当前明确要求

如果用户明确要求不运行任何 Git 命令，则以用户当前指令为准，并在验收结论中说明无法用 Git 验证 diff。

只读搜索优先顺序建议为：

1. `git grep "keyword"`
2. `Get-ChildItem ... | Select-String "keyword"`
3. `Get-Content` 读取已定位文件

如果搜索范围较大，应限制目录和后缀，避免扫到 `node_modules`、构建产物、缓存目录和无关附件。

## 2. Scope Check

验收时先确认修改范围：

1. 查看 `git diff --name-only`。
2. 对照任务允许文件，确认是否只改了允许文件。
3. 查看 `git status --short`，确认是否有未跟踪文件。
4. 判断未跟踪文件是否属于本轮任务。
5. 不要把以下内容误要求提交：
   - `.claude/`
   - `Gemini/`
   - 非本轮阶段报告草稿
   - 非本轮 `package-lock`
6. 不要提交：
   - 数据库文件
   - `node_modules`
   - 构建产物
   - Python 缓存
   - 真实学习资料正文

处理未跟踪文件时：

- 先记录其路径和类型，不要直接假设属于本轮改动。
- 如果任务是只读验收，只做识别和汇报，不做清理。
- 如果用户没有要求提交未跟踪文件，不要把它们算进“应提交文件”。
- 如果未跟踪文件疑似构建产物、缓存或本地工具目录，应在结论中明确排除。

## 3. Backend Review Checklist

后端任务重点检查：

- model 表名、字段、可空性、唯一约束是否符合任务。
- schema 是否和 API 请求/响应对齐。
- service 是否包含必要校验。
- route 是否捕获 service error 并转换为明确 HTTP 错误。
- PATCH 是否为部分更新，未传字段不能被覆盖。
- 测试是否覆盖成功路径和失败路径。
- 测试是否使用项目已有测试数据库方式。
- 测试是否避免写入真实 `data/local_english_trainer.sqlite3`。
- 是否没有引入外部 API、AI、OCR、词典、复杂复习算法等越界功能。
- 是否没有为了测试改变 existing API 行为。

## 4. Frontend Review Checklist

前端任务重点检查：

- 是否只修改允许的前端文件。
- 是否误改 `frontend/src/api.ts`、`frontend/src/types.ts`、`frontend/src/mockData.ts`。
- 状态是否保持职责分离。
- `selectedAnswers` 是否仍以 `question_id` 为 key。
- `submitPracticeAttempt` 是否仍按整份 `pack.questions` 提交。
- annotation 状态是否没有污染作答状态。
- fallback 状态下页面是否不白屏。
- loading、submitting、error 状态是否仍清楚。
- `npm run build` 是否通过；如果未运行，是否说明原因。
- 是否没有引入 UI 框架、图表库或新依赖。

## 5. High-risk Invariants

当前项目高风险不变量：

- `selectedAnswers` 不应被 annotation 状态污染。
- `submitPracticeAttempt` 不应改成只提交当前 passage。
- 切换 passage 不应清空作答。
- 切换 pack 应清空旧 pack 相关状态。
- annotation API 不应自动生成 vocabulary，除非任务明确要求。
- vocabulary API 不应自动生成 meaning。
- 后端测试不应写真实数据库文件。
- 真实学习资料和真题正文不应默认提交仓库。
- 不要使用 `v1` / `v2` 命名功能或文件。
- 不要把项目做成单纯背单词 App 或单纯刷题 App。

## 6. Review Output Format

验收输出建议固定为：

1. 验收结论：通过 / 基本通过 / 不通过；
2. 修改范围是否合格；
3. 核心功能是否合格；
4. 是否发现越界内容；
5. 测试是否通过；
6. 是否有必须修复问题；
7. 是否建议提交；
8. 只应提交哪些文件；
9. 建议本地检查命令。

如果任务要求“只输出结论”，优先遵守用户当前输出格式。


## 7. PowerShell Search Snippets

常用 PowerShell 只读搜索写法：

- 全仓搜索：
  - `Get-ChildItem -Recurse -File -Include *.md,*.ts,*.tsx,*.py | Select-String "keyword"`
- 前端搜索：
  - `Get-ChildItem -Path .\frontend\src -Recurse -File -Include *.ts,*.tsx | Select-String "keyword"`
- 后端搜索：
  - `Get-ChildItem -Path .\backend\app -Recurse -File -Include *.py | Select-String "keyword"`
- 文档搜索：
  - `Get-ChildItem -Path .\docs -Recurse -File -Include *.md | Select-String "keyword"`
