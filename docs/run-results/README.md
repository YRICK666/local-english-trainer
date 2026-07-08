# Run Results

本目录用于保存项目运行、测试、构建的结果摘要。

这里不保存大型运行产物，不保存数据库文件，不保存依赖目录，不保存构建输出。

## 1. 可以保存的内容

可以保存：

- 测试命令摘要；
- 构建命令摘要；
- 手动验证步骤；
- API smoke test 结果；
- 关键错误排查记录；
- 阶段验收记录。

推荐保存为 Markdown 文件，例如：

    2026-07-08-practice-attempt-tracking.md
    2026-07-08-frontend-build.md

## 2. 不应该保存的内容

不要保存：

    node_modules/
    __pycache__/
    *.sqlite3
    pytest_runtime_tmp/
    frontend/dist/
    frontend/build-output/
    *.log

如果只是临时日志，留在本地即可，不纳入 Git。

## 3. 推荐记录格式

# Run Result: <任务名称>

## 命令

    <命令>

## 结果

    <关键输出>

## 结论

- passed / failed
- 后续动作

## 4. 提交前检查

提交前运行：

    git status --short
    git ls-files | Select-String "node_modules|__pycache__|sqlite3|pytest_runtime_tmp|frontend/dist|frontend/build-output|\.log"

第二条命令必须没有输出。
