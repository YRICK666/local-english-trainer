# Project Workflow

本文件用于约束 local-english-trainer 的日常推进方式，避免项目在功能扩展、Git 操作和文档维护上失控。

## 1. 项目定位

local-english-trainer 是一个本地英语学习系统，核心不是单纯展示阅读材料，而是完成：

1. 导入阅读材料；
2. 完成阅读题；
3. 标注答案依据、同义替换、生词、长难句；
4. 沉淀本地词库、句库和复习材料；
5. 保留练习记录，为后续复习功能提供数据基础。

当前阶段只做最小学习闭环，不提前扩展 OCR、AI、云服务、多用户、登录注册、复杂复习算法等功能。

## 2. 推进原则

每次开发只围绕一个明确阶段展开。

阶段必须能用一句话描述，例如：

- reading_pack 导入闭环；
- practice attempt tracking；
- 本地词库保存；
- 长难句保存；
- 复习入口。

不接受一边顺手改很多东西的开发方式。

## 3. 每个阶段的固定流程

每个阶段按以下顺序推进：

1. 明确目标：写清楚本阶段要解决什么问题；
2. 明确范围：写清楚本阶段不做什么；
3. 修改文件：只改和当前阶段直接相关的文件；
4. 运行验证：至少运行相关后端测试或前端构建；
5. 记录结果：把关键命令和结果写入阶段总结；
6. Git 检查：提交前确认没有运行产物被纳入版本控制；
7. 用户确认：用户确认后再提交。

## 4. Git 安全规则

禁止随意使用以下命令：

    git add -A
    git add .
    git clean -fdX
    git reset --hard
    git push --force

除非用户明确确认，不得使用这些命令。

提交前必须检查：

    git status
    git ls-files | Select-String "node_modules|__pycache__|sqlite3|pytest_runtime_tmp|frontend/dist|frontend/build-output|\.log"

第二条命令必须没有输出。

## 5. 推荐提交方式

优先使用精确路径提交，例如：

    git add docs/PROJECT_WORKFLOW.md
    git add docs/STAGE_REPORT_GUIDE.md
    git add docs/stage-reports/000-template.md
    git add docs/run-results/README.md
    git add skills/workflow/WORKING_STYLE.md
    git add skills/workflow/CODEX_STAGE_SUMMARY_PROMPT.md

不要使用全量添加。

## 6. 阶段完成标准

一个阶段完成时，必须至少说明：

- 做了什么；
- 改了哪些文件；
- 新增或修改了哪些接口、页面、数据结构；
- 运行了哪些测试或构建命令；
- 测试结果是什么；
- 是否有已知问题；
- 下一步建议做什么。

阶段总结统一放在：

    docs/stage-reports/

运行结果和命令输出摘要统一放在：

    docs/run-results/
