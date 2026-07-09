# AGENTS.md

## 项目定位

本项目是一个本地英语学习系统，核心是：

阅读训练 + 本地单词库搭建

它不是 OCR 项目，不是单纯刷题 App，也不是单纯背单词 App。

核心学习流程：

导入 reading_pack
→ 阅读文章
→ 做题
→ 标答案依据
→ 标同义替换
→ 标生词
→ 标长难句
→ 生词进入本地单词库
→ 长难句进入句子库
→ 后续复习

## 开发原则

1. 优先保证项目可运行、可理解、可回滚。
2. 每一轮只做一个小闭环。
3. 不要一次性铺开过多功能。
4. 后端、前端、测试要同步收口。
5. 修改完成后必须说明改了什么、测试结果如何。
6. 默认本地运行，默认使用 SQLite。
7. 前端风格保持简约、清爽、文本优先、学习工具感。

## 命名约束

1. 不要使用 v1、v2 这种命名。
2. 不要把功能命名成 xxx v1、xxx v2。
3. 使用自然名称，例如：
   - reading_pack import
   - practice attempts
   - reading annotations
   - vocabulary library
   - sentence library

## 禁止事项

除非用户明确要求，否则不要做：

1. OCR
2. AI 功能
3. 云服务接入
4. 模型训练
5. PDF 解析
6. Anki 导出
7. 复杂复习算法
8. 大规模 UI 重构
9. 恢复旧 CET6/OCR/private paper 文件
10. 提交真实学习资料正文
11. 提交数据库文件
12. 提交 node_modules
13. 提交构建产物

## 数据安全约束

不要提交：

- .env
- *.sqlite3
- *.db
- data/user/*
- frontend/dist/
- frontend/build-output/
- frontend/node_modules/
- Python 虚拟环境
- Python 缓存
- 日志文件

## Codex 工作方式

每次开始任务前：

1. 确认当前目录是项目根目录。
2. 运行 git status。
3. 阅读本文件和 README.md。
4. 只完成用户指定的当前任务。
5. 不要扩大范围。

每次完成任务后：

1. 按任务类型运行验证：
   - 后端任务：运行 `python -m pytest`
   - 前端任务：运行 `cd frontend && npm run build`
   - 全栈任务：运行后端测试和前端构建
   - 纯文档任务：不强制运行 pytest 或 build，但必须说明未运行原因
   - 如果用户当前明确要求不运行某个命令，以用户当前指令为准
2. 输出简短总结：
   - 修改了哪些文件
   - 新增了哪些表或接口
   - 前端改了什么
   - 哪些地方仍是 mock/fallback
   - pytest 结果
   - build 结果

## 当前阶段优先级

优先完成这些闭环：

1. reading_pack 导入和读取
2. Workspace 作答
3. practice attempt 保存
4. reading annotation 持久化
5. vocabulary / sentence 入库

不要在这些闭环完成前扩展 OCR、AI 或复杂复习功能。

## Workflow References

- 规划和执行提示词模板参考 `docs/TASK_PROMPT_TEMPLATES.md`。
- 代码验收和只读 review 参考 `docs/CODE_REVIEW_GUIDE.md`。
- 本文件只保留长期项目规则；单次任务的允许文件、禁止文件、接口字段和验收标准应写在任务 prompt 中。
## 验收 / review 阶段的 Git 使用规则

在代码验收、review、检查模型是否越界修改文件时，默认允许使用只读 Git 命令。

允许的只读 Git 命令包括：

- `git status --short`
- `git diff --name-only`
- `git diff -- <path>`
- `git log --oneline --decorate -3`
- `git ls-files`

这些命令只用于确认：

- 本次修改了哪些文件；
- 是否只修改了任务允许的文件；
- 是否误改了接口、类型、mockData、后端、测试、依赖或文档；
- 是否存在运行产物进入 Git 跟踪范围。

只读 Git 命令不会修改仓库状态，不应和 `git add`、`git commit`、`git push`、`git reset`、`git clean` 混为一类。

如果用户明确说“不要运行任何 Git 命令”，则仍然以用户当前指令为准，并在验收结论中说明无法使用 Git 验证 diff。

未经用户明确确认，禁止执行会改变仓库状态的 Git 命令，例如：

- `git add`
- `git commit`
- `git push`
- `git reset`
- `git clean`
- `git restore`
- `git checkout`
- `git merge`
- `git rebase`



