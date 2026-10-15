# AIcademiya · 项目协作入口

当前生产基线为Stage16 R4/API0.11.0/schema9。先读 `../docs/project-review-20261014/README.md`、`README.md`、`CONTEXT.md`和 `DEPLOYMENT_STAGE16_RESULT.md`，再读对应模块源码与测试。历史Stage文档按功能查阅；当前用户请求决定授权、预算、并发和文件所有权。

Windows使用项目 `.venv/Scripts/python.exe`和frontend本地npm依赖；模块 `backend.aicademiya`，配置 `AICADEMIYA_*`，默认新数据 `data-v2`。产物文案采用 `anti-defensive-writing`，作用与结论先行，证据与适用条件集中交代。

## Historical development authorization

Stage2的授权和分工记录保留供历史对照。当前任务范围、预算与并发按最新用户请求确定；远端变更、真实服务调用和账号操作另核当前授权。

- Product name: **AIcademiya**; EDUC7703 remains the course code.
- Current website UI is English; the teaching language follows the saved profile.
- Reference eligibility and delivery follow the selected immutable edition/teaching profile.
- Teacher confirms completion; no automatic formal grade.
- Existing teaching-router/cache integration must remain compatible; never restart or modify model services/shared environment for this work.
- Main validates any Codex subscription integration; do not read/export provider credentials.

## Historical parallel file ownership (returned)

- Backend core: backend/ except worksheet_import.py, link_materials.py and their dedicated tests/fixtures reserved in STAGE2_CONTRACT.md.
- Frontend: frontend/ (including brand assets and frontend tests).
- Import helpers: only the pure import/link modules and dedicated tests/fixtures listed in STAGE2_CONTRACT.md; no core DB/routes/requirements edits.
- Main: top-level contract/docs, tools, baseline snapshots, integration/verification and handed-back fixes. sample_data and original materials remain read-only.

The above lane split records Stage2 development. Use the current task's explicit ownership. Protect original classroom sources, existing databases, uploads and configuration. Cleanup uses the system Recycle Bin; confirmed rebuildable downloads may skip backup under current authorization. Keep receipts and exact recovery paths. Do not delete databases to make tests pass.

## Practical conventions

Project-local Python `.venv` (3.13); local npm dependencies. ASCII engineering paths. Test data synthetic and explicitly demo. Real API failures must be visible, not replaced with made-up success. `.env`, local database, cookies, uploads, logs and browser profiles must not be committed. A student API response must not contain teacher-only answer keys. Read secrets only when authorized in the intended client; never emit them into tool output.

Return real test results, exact artifact paths and remaining blockers. Use isolated synthetic data and explicitly selected Hermes scratch paths. Backend test entry is `tools/run_backend_tests.py`; frontend Node26 storage requirements are recorded in the current review's verification report. Main owns integration and long-running app servers.
