# Codex Stage Summary Prompt

把下面这段提示词发给 Codex，可用于让 Codex 在一个阶段完成后生成项目阶段总结。

---

请为 local-english-trainer 当前阶段生成一份阶段总结。

要求：

1. 使用中文；
2. 不要修改代码；
3. 不要提交 Git；
4. 不要使用 git add -A；
5. 不要使用 git add .；
6. 先检查当前 Git 状态；
7. 总结必须具体到文件路径、接口、测试命令和测试结果；
8. 如果有不确定内容，明确写不确定，不要编造；
9. 输出内容按 docs/stage-reports/000-template.md 的结构组织。

请重点检查并总结：

- 本阶段目标；
- 实际完成内容；
- 修改文件清单；
- 新增或修改的接口；
- 前端页面或交互变化；
- 数据库或数据结构变化；
- 后端测试结果；
- 前端构建结果；
- 已知问题；
- 下一步建议；
- Git 检查结果。

必须运行或要求用户提供以下检查结果：

    git status --short
    git ls-files | Select-String "node_modules|__pycache__|sqlite3|pytest_runtime_tmp|frontend/dist|frontend/build-output|\.log"

第二条命令必须没有输出，才可以认为没有运行产物被纳入 Git 跟踪。
