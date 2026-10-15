# 源码职责与阅读覆盖

本表把当前55个后端模块、93个前端文件和31个发布工具/运行模板映射到八份模块报告。它是维护索引；阅读段与测试执行分别记录。

## 后端

| 文件 | 主报告 | 阅读记录 |
|---|---|---|
| `__init__.py` | [模块07](modules/07-deployment-data-tools.md) | 父模块接口/结构与选段阅读 |
| `access_control.py` | [模块01](modules/01-accounts-security.md) | full_file_static_read |
| `account_avatars.py` | [模块01](modules/01-accounts-security.md) | full_file_static_read |
| `account_features_migration.py` | [模块01](modules/01-accounts-security.md) | full_file_static_read |
| `account_import.py` | [模块01](modules/01-accounts-security.md) | full_file_static_read |
| `ai.py` | [模块06](modules/06-ai-search-services.md) | 父模块接口/结构与选段阅读 |
| `auth.py` | [模块01](modules/01-accounts-security.md) | full_file_static_read |
| `authoring.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read |
| `config.py` | [模块01](modules/01-accounts-security.md) | full_file_static_read |
| `course_lifecycle.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read |
| `course_staff.py` | [模块01](modules/01-accounts-security.md) | full_file_static_read |
| `create_teacher.py` | [模块07](modules/07-deployment-data-tools.md) | 父模块接口/结构与选段阅读 |
| `db.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read；selected-line-read |
| `document_api.py` | [模块05](modules/05-materials-documents.md) | 父模块接口/结构与选段阅读 |
| `document_bundle.py` | [模块05](modules/05-materials-documents.md) | 父模块接口/结构与选段阅读 |
| `document_jobs.py` | [模块05](modules/05-materials-documents.md) | 父模块接口/结构与选段阅读 |
| `document_storage.py` | [模块05](modules/05-materials-documents.md) | selected_ranges_static_read |
| `document_supplements.py` | [模块05](modules/05-materials-documents.md) | 父模块接口/结构与选段阅读 |
| `evidence.py` | [模块03](modules/03-learning-tutor.md) | full-text-read |
| `extraction_limits.py` | [模块05](modules/05-materials-documents.md) | 父模块接口/结构与选段阅读 |
| `feedback.py` | [模块01](modules/01-accounts-security.md) | full_file_static_read |
| `global_accounts.py` | [模块01](modules/01-accounts-security.md) | full_file_static_read |
| `guided_director.py` | [模块03](modules/03-learning-tutor.md) | full-text-read |
| `guided_engine.py` | [模块03](modules/03-learning-tutor.md) | full-text-read |
| `guided_migration.py` | [模块03](modules/03-learning-tutor.md) | full_file_static_read；full-text-read |
| `guided_reading.py` | [模块03](modules/03-learning-tutor.md) | full-text-read |
| `guided_routes.py` | [模块03](modules/03-learning-tutor.md) | full-text-read |
| `guided_state.py` | [模块03](modules/03-learning-tutor.md) | full-text-read |
| `http_security.py` | [模块01](modules/01-accounts-security.md) | full_file_static_read |
| `learning_routes.py` | [模块03](modules/03-learning-tutor.md) | full_file_static_read；full-text-read |
| `link_materials.py` | [模块05](modules/05-materials-documents.md) | selected_ranges_static_read |
| `main.py` | [模块07](modules/07-deployment-data-tools.md) | full_file_static_read；selected-line-read |
| `manage_admin.py` | [模块07](modules/07-deployment-data-tools.md) | 父模块接口/结构与选段阅读 |
| `material_extraction.py` | [模块05](modules/05-materials-documents.md) | 父模块接口/结构与选段阅读 |
| `material_library.py` | [模块05](modules/05-materials-documents.md) | full_file_static_read |
| `material_security.py` | [模块05](modules/05-materials-documents.md) | 父模块接口/结构与选段阅读 |
| `materials.py` | [模块05](modules/05-materials-documents.md) | 父模块接口/结构与选段阅读 |
| `migrations.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read |
| `model_connection.py` | [模块06](modules/06-ai-search-services.md) | 父模块接口/结构与选段阅读 |
| `models.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read；selected-line-read |
| `reading_context.py` | [模块03](modules/03-learning-tutor.md) | full-text-read |
| `roster.py` | [模块01](modules/01-accounts-security.md) | full_file_static_read |
| `service_settings.py` | [模块06](modules/06-ai-search-services.md) | 父模块接口/结构与选段阅读 |
| `services.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read；selected-line-read |
| `session_lifecycle.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read |
| `source_review.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read |
| `teacher_preview.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read；full-text-read |
| `teacher_workbench_routes.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read |
| `teaching.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read；full-text-read |
| `version_context.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read；selected-line-read |
| `versions.py` | [模块02](modules/02-course-authoring-versions.md) | full_file_static_read |
| `visual_context.py` | [模块03](modules/03-learning-tutor.md) | full-text-read |
| `web_search.py` | [模块06](modules/06-ai-search-services.md) | 父模块接口/结构与选段阅读 |
| `worksheet_import.py` | [模块05](modules/05-materials-documents.md) | 父模块接口/结构与选段阅读 |
| `worksheet_materials.py` | [模块05](modules/05-materials-documents.md) | 父模块接口/结构与选段阅读 |

## 前端

93文件的完整依赖图可达，包括类型导入和CSS。组件主职责见模块04；逐文件已读/结构扫描边界由coverage JSON给出。

| 文件 | 阅读记录 |
|---|---|
| `AccessSettings.tsx` | full-text-read |
| `account-avatar.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `account-management-api.ts` | full-text-read |
| `account-management-state.ts` | full-text-read |
| `account-management-types.ts` | 静态依赖可达；模块正文报告未逐文件通读 |
| `account-management-ui.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `account-management.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `AdminAccounts.tsx` | full-text-read |
| `api.ts` | selected-line-read |
| `App.tsx` | full-text-read |
| `Authoring.tsx` | selected-line-read |
| `availability.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `Availability.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `Avatar.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `brand.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `ChangePassword.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `contrast.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `course-actions.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `course-home.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `course-library.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `course-presentation.ts` | 静态依赖可达；模块正文报告未逐文件通读 |
| `CourseActions.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `CourseLibrary.tsx` | selected-line-read |
| `CourseStaff.tsx` | selected-line-read |
| `CourseStudents.tsx` | full-text-read |
| `CourseTrash.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `design-tokens.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `document-api.ts` | full-text-read |
| `document-reader.css` | selected-line-read |
| `document-state.ts` | full-text-read |
| `document-types.ts` | 静态依赖可达；模块正文报告未逐文件通读 |
| `DocumentBlockContent.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `DocumentReader.tsx` | selected-line-read |
| `drafts.ts` | full-text-read |
| `feedback.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `Feedback.tsx` | selected-line-read |
| `GlobalAccountForms.tsx` | selected-line-read |
| `GlobalAccounts.tsx` | selected-line-read |
| `guided-study.ts` | full-text-read |
| `guided-workspace.css` | selected-line-read |
| `GuidedLearningWorkspace.tsx` | selected-line-read |
| `help-popover.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `HelpPopover.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `Home.tsx` | selected-line-read |
| `ids.ts` | full-text-read |
| `InstructionImport.tsx` | selected-line-read |
| `LearningHistory.tsx` | full-text-read |
| `LearningWorkspace.tsx` | structure-only |
| `live-connection.tsx` | full-text-read |
| `Login.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `main.tsx` | full-text-read |
| `material-manager.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `material-upload.ts` | full-text-read |
| `MaterialManager.tsx` | selected-line-read |
| `Materials.tsx` | selected-line-read |
| `ModelSettings.tsx` | selected-line-read |
| `navigation-guard.tsx` | full-text-read |
| `process-overview.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `process-overview.ts` | 静态依赖可达；模块正文报告未逐文件通读 |
| `Profile.tsx` | selected-line-read |
| `ProvisionStudent.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `Roster.tsx` | selected-line-read |
| `routes.ts` | full-text-read |
| `SavedResponses.tsx` | selected-line-read |
| `SearchSettings.tsx` | selected-line-read |
| `SearchToggle.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `SessionActions.tsx` | selected-line-read |
| `settings-workspace.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `SettingsWorkspace.tsx` | full-text-read |
| `SourceCitations.tsx` | full-text-read |
| `stage2.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `stage2.ts` | 静态依赖可达；模块正文报告未逐文件通读 |
| `stage7-settings.ts` | full-text-read |
| `study.ts` | full-text-read |
| `styles.css` | selected-line-read |
| `teacher-framework.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `teacher-workbench-import.ts` | 静态依赖可达；模块正文报告未逐文件通读 |
| `teacher-workbench.css` | selected-line-read |
| `TeacherExtractionReport.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `TeacherPreviewPane.tsx` | selected-line-read |
| `TeacherProcessOverview.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `TeacherSession.tsx` | selected-line-read |
| `teaching-profile.ts` | full-text-read |
| `TeachingFramework.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `TeachingSourceReview.tsx` | selected-line-read |
| `TeachingText.tsx` | full-text-read |
| `TutorMessage.tsx` | full-text-read |
| `types.ts` | 静态依赖可达；模块正文报告未逐文件通读 |
| `ui.tsx` | 静态依赖可达；模块正文报告未逐文件通读 |
| `uiText.ts` | 静态依赖可达；模块正文报告未逐文件通读 |
| `Versions.tsx` | selected-line-read |
| `web-search.css` | 静态依赖可达；模块正文报告未逐文件通读 |
| `WorksheetImport.tsx` | selected-line-read |

## 当前运行工具

下面工具在当前builder collect中进入发布包，Stage名称仅标注形成阶段。

| 发布路径 | 主报告 |
|---|---|
| `app/runtime_v2/aicademiya-model-proxy.service` | [模块07](modules/07-deployment-data-tools.md) |
| `app/runtime_v2/aicademiya-model-proxy.socket` | [模块07](modules/07-deployment-data-tools.md) |
| `app/runtime_v2/aicademiya.conf.example` | [模块07](modules/07-deployment-data-tools.md) |
| `app/runtime_v2/aicademiya.service` | [模块07](modules/07-deployment-data-tools.md) |
| `app/runtime_v2/start-linux.sh` | [模块07](modules/07-deployment-data-tools.md) |
| `app/tools/backup_data.py` | [模块07](modules/07-deployment-data-tools.md) |
| `app/tools/build_v2_release.py` | [模块07](modules/07-deployment-data-tools.md) |
| `app/tools/document_stage12/document_ssh_bridge.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/document_stage12/document_worker_service.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/document_stage12/gpu_lease.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/document_stage12/page_vision_runtime.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/document_stage12/parser_helpers.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/document_stage12/parser_worker.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage13/archive_guard.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage13/ocr_verification.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage13/office_inventory.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage13/parse_material.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage13/prepared_material.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage13/simple_material.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage13/source_text.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage15/__init__.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage15/adapter.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage15/page_worker.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage15/prepared.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage15/provenance.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage16/legacy_office.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage16/workbook_inventory.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage16/workbook_material.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/material_stage16/workbook_supplements.py` | [模块05](modules/05-materials-documents.md) |
| `app/tools/start-linux.sh` | [模块07](modules/07-deployment-data-tools.md) |
| `app/tools/warm_aicademiya_prefix.py` | [模块07](modules/07-deployment-data-tools.md) |

## 证据入口

- `evidence/backend-review-coverage.json`：后端审阅的全文/局部及对应测试。
- `evidence/frontend-learning-review-coverage.json`：学习/前端读段、结构扫描与活跃组件链。
- `evidence/source-module-map.json`：当前职责映射，按Python去重校验。
- `verification.md`：真实执行结果和历史范围。
