# Stage11 contract — multi-course presentation, global accounts and course staff

Completed and deployed as AIcademiya_V2-20261008-people, API0.9.0/schema8. Current proof: STAGE11_CHECKPOINT.md and DEPLOYMENT_STAGE11_RESULT.md. Ownership/baseline/acceptance below describe the completed implementation, not pending work.

## Authority / baseline

Operator friend Z. New request at2026-10-08 evening; explicitly **no time limit, work until done**. User explicitly selected per-course Admin/Teacher counts and **multiple assigned administrators/teachers co-managing one course**. Prior13:30 deadline applied to completedStage10, not this work. Authorized local implementation, isolated verification and established retained-data CT255 upgrade; no public ingress, paid service, model/router/GPU/KV changes or real-account test edits.

Production baseline AIcademiya_V2-20261008-security API0.8.0/schema7. Source non-Git, appD:/HermesProjects/EDUC7703/app. Protected AGENTS/originals/sample_data/config/HMAC/accounts and all learning/curriculum history. Stage11 target API0.9.0/schema8; additive migrations preserve all original23table schemas/named rows (one-time staff backfill goes to new table, not rewriting owners). Exact source snapshot artifacts/stage11/baseline.json. Read CONTEXT.md for resolved terms. Old owner-only authorization is intentionally expanded ONLY to explicitly assigned staff; global admin account powers do not automatically expose all course content.

## Product outcomes

1. Browser/document title, not only in-page logo: initialHTML and anonymous Login/globalSettings/history show AIcademiya; actual selected/course-scoped pages show AIcademiya · <actual course code>. No fixedEDUC7703 outside real course content. Cover login, course switch, course navigation, signout, unknown/deleted course, mobile/wide.
2. Course description keeps literal linebreaks/blanklines; wraps within responsive available banner width instead of520px cap. Widen edit dialog responsively, keep mobile fit; do not rewrite original description data/published versions. Preserve dark horizontal sidebar and lightLogin/V4.
3. Course summary counts **Sessions, Admins, Teachers, Students**; count1 uses Session/Admin/Teacher/Student,0/2+ plural. Admin/Teacher = active distinct assignedcourse staff filtered by CURRENT globalrole; Student = active enrollment+activeaccount+roleStudent. Counts are live operational state, never copied from immutable course metadata. Session count is actual visible/draft/published projection scope. Labels formerly Learners become Students where referring to student management.
4. Settings foradmin: **Global User Accounts**, all roles, list/filter, individual create withrole, reviewedCSV/XLSX import withrole, change another account'srole, reversible disable/restore. TeacherSettings: **Course Students**, only their assignedcourses, existing student create/import/enroll/remove/restore. Course removal never deletes/global-disables the account or touches othercourses. Preserve existing30-day course-removal retention semantics; don't silently create a permanent-delete feature.
5. Multi-staff course management: explicitassignment supports multipleAdmin/Teacher users; all assignedstaff can use same course teaching/material/session/version/roster/lifecycle capabilities. Per-user preview remainsprivate. Staff assignment changes are administrator-only (global administrativemetadata, not blanket teachingaccess). Globalaccounts UI must expose assignment workflow for anycourse, including ifcaller isnotalready assigned; staffmetadata/lightcourseindex isallowed foradmin. Teacher may view colleagues on assignedcourse but cannot grantstaff/globalroles.

## Safety / role transitions

- Onecurrentglobalrole peraccount. Rolechange revokes target sessions; no password resets, deletion of work/avatar/feedback or auto-enrollment into everycourse. GlobalSelf rolechange/disable disallowed; lastusableactiveadmin protected atomically. Existingteacher promotionendpoint may remain compatible but must not bypass shared role/safety rules.
- Primarycoursemanager storedbyexistingowner_id remainsactive assignedstaff. Additive migration seeds owners once; restart must not resurrect removedassignments. Newcourse/seed/localCLI ownershipclaims also establishassignment correctly. No fallback that restores revoked membership.
- Changingprimarymanager'srole toStudent or disabling/removingthem requires explicit primarytransfer toanotheractive assignedstaff first. UI exposes Make primary manager; no silent ownership reassignment. Refuse operations leavinganycourse withoutactive staff, includingtrashedcourses; expose conflictreason and assignmentpath. Preserveoriginalcourseowner until anexplicit operation changesit.
- Student→staff doesNOTpromote oldstudentenrollments into teachingpermission; explicitstaffassignment required. Preserve old learningrows safely, and verify rolechanges cannot expose private teacherpreview/answers throughstudent history. Staff→student requires no remainingstaffassignments/primaryownership (detach/transfer explicitly first); return actionable409 instead of hidden privilege.
- Globaldisable uses existingarchived_at withpurge_atNULL (no newauto-purge). Oldstudentretention deadlines remain unlessexplicitlyrestored. Course-levelremovecontinuesexistingcourse-scopedarchive. Admin CRUDneverpermanentlydeletesusers.
- New/importedaccounts haveexplicittemporarypassword +must_change_password. 8–512 chars ASCIIletter+digit; plaintext neverlogged, returned, persisted inimportstaging/browserstorage/artifacts. Onlyhash inreviewstaging. Publicself-registration remainsStudentonly and honorsStage10toggle/invite. Teacher endpoints cannotacceptspoofedrole.
- Newglobalimport iscreate/skip, notbulkrolechange ofexistingaccounts: sameemail/samerole skipwithoutreset; differingrequestedrole iserror andmustbechangedexplicitly. Allerrors blockcommit, stageboundtoadmin/recheckcurrentpermissions; commit atomicallyverifiespreviewassumptions, idempotentresult/recovery and exactcreatedIDs. Retain25MiB/2MiB/ZIPactualexpansion/1000row checks as relevant. No generic job framework.

## Frozen API / DTO contract

Common: Role=admin|teacher|student, User=existing public_user projection (avatar/must_change_password/is_demo etc); nosecretfields. Alladminrequests require currentactiveadmin; teacher scoped routes useactivecourseassignment. Ordinarybody DTOsextra=forbid. Exact independentGETreadback for mutations. Existing old endpoints retained where possible.

**Course projections** add required `admin_count:number`, `teacher_count:number`, existingstudent_count nowfiltersactualroleStudent. Existingcourseowner metadata/title/description/invite/versionsemantics retained.

**Global account endpoints** (literal import routes registeredbeforedynamic uid):
- GET /api/admin/users?q=&role=&active=true|false&offset=0&limit=50 → `{items:GlobalAccount[],total,offset,limit}`; stable sortname/email/id; count+items same snapshot; limit1..100. Omitrole/active for all. qsearchname/email bounded.
- `GlobalAccount={user:User,active:boolean,archived_at:string|null,purge_at:string|null,assigned_course_count:number,owned_course_count:number}`.
- GET /api/admin/users/{uid} → GlobalAccount +`staff_courses:CourseBrief[]`.
- POST /api/admin/users `{name,email,role,temporary_password}` → `{user:User}`. Noautomaticretries afterunknownoutcome; UIretainsdraft andcanrefreshlist toinspect; responseIDsare independentlyreadback beforeclearing.
- PATCH /api/admin/users/{uid} `{role:Role}` → `{user:User}`; rolechangeonly, no silentname/password rewrite.
- PUT /api/admin/users/{uid}/status `{active:boolean}` → GlobalAccount. Turningoffrevokes sessions. Ifalreadydesiredstate, idempotentreturn.
- POST /api/admin/users/import/preview multipart`file`, `default_role` (defaultstudent), optional`default_temporary_password` → `AccountImportPreview={import_id,rows,valid_count,error_count}`. Filecolumnsname,email; optionalrole,temporary_password. `rows={row_number,name,email,role,action:create|skip|error,errors:string[],warnings:string[]}[]`. Rolecolumn overridesselecteddefault; UIshowspreviewrole beforecommit.
- POST /api/admin/users/import/{iid}/commit `{}` → `AccountImportResult={created:number,skipped:number,user_ids:string[]}`. Returnedidscoverallrows'accounts, no credentials.
- GET /api/admin/users/import/{iid} → `{status:pending|committed,preview:AccountImportPreview,result:AccountImportResult|null}`. Exactadminownership+expiry; keepcommittedresultforboundedrecovery insteadofduplicatecreation.

**Staff assignment / primarymanager**:
- `CourseBrief={id,code,title,owner_id:string|null,trashed_at:string|null}` (no privatecurriculum,invitationsorstudentwork).
- GET /api/admin/courses → `{courses:CourseBrief[]}` lightindex forassignment, includestrashlabel.
- GET /api/courses/{cid}/staff → `{course:CourseBrief,staff:CourseStaffMember[]}` admin(anycourse) orassignedteacher; studentsdenied. `CourseStaffMember={user:User,is_primary:boolean,active:boolean}`; includesdisabledassignedstaffforadmincleanup, activecounts exclude them.
- POST /api/courses/{cid}/staff `{user_id}` → sameStaffResponse; adminonly, targetactiveAdmin/Teacher, duplicateaddidempotent.
- DELETE /api/courses/{cid}/staff/{uid} → sameStaffResponse; adminonly, refuseprimary/lastactive; nodata/historydeletion.
- PUT /api/courses/{cid}/staff/primary `{user_id}` → sameStaffResponse; adminonlytargetalreadyactiveassignedstaff. Transferdoesnotdetacholdmanager.

Staff→student requires explicitassignmentsremoval (afterprimarytransfer). Active-global-suspension permittedonlyifsufficientotheractivecoursemanagersandtargetnotprimary. AllUI409skeepeditsandrevealclearreason; nosilentworkloss. Concurrentrole/suspension/assignment/primary changesserializeandrecheckactor/targetunderlock.

Newdb tables may be course_staff andglobalaccount importstaging; backend lane chooses implementationonlywithinthesecontracts. Keeporiginalrows/schema, backupautomaticallyincludesnewtables andhashedstaging. Migrationrollback/savepoint/restart tests required.

## File ownership / independent work

- Backend lane: backend/** including migrations/modelpermissions/allbackendtests; NO frontend/tools/runtime/docs beyond ownHANDOFF. API0.9/schema8, completecatalog/staffaccess audit includingmain,course_lifecycle,version_context,material_library/material_security,authoring/history,learning/guidedcommit,CLIownerclaims,maintenance. Do notjustpatchvisiblecourseslist.
- UI lane: frontend/src/AdminAccounts.tsx, newGlobalAccounts/CourseStaff/CourseStudents +account-management-types.ts/account-management-api.ts/scopedcss; Roster.tsx andProvisionStudent.tsx ifneeded; ownnewtests/harnesses. NO App/Home/Login/types.ts/api.ts/routes/stage7-settings/SettingsWorkspace/styles.css/uiText/index.html/public/brand. Newapi module imports existingrequest fromapi.ts; returnsfrozenDTOs. Components exports frozenbelow. KeepAccessSettings registrationcontrol.
- Parent: sharedfrontendfilesabove, titles/layout/counts/labels, shellintegration, tools/packaging/runtime/verification/deployment/docs. OriginalV4assetsnotmodified. Children do not overlap eachotherorparent.

**UI component props**:
- `AdminAccounts({user:User,onChanged?:()=>void})` rendersGlobalUserAccounts+registrationAccessSettings+accountCRUD/import+globalcourseassignmentworkflow. Parent passescurrentuser forselfguards. LayoutmustworkinsideSettingsWorkspace.
- `CourseStudents({user:User,courses:Course[],courseId?:string,onChanged?:()=>void})` course-scopedselectionwhennoid, onlyavailableassignedcourses; existingRoster mountedkeyedbycourse; displaysCourseStaffpanel (teacherread-only,admineditable) alongsideCourseStudents. Parent usesbothSettingsusersandcourseRosterroute. Never callglobalstudentAPIfromteacher.

## Acceptance / evidence

Finalschema/version rebasing isexplicit, notdroppedassertions. Unit+targetedsecurity/role/migrationtests, fullbackend/frontend/build, exactarchive boot, actualbuiltUI→HTTP/SQLite, mixedroleCSV/XLSX, unknownoutcomes, sourcepreservation, multi-course/role/account switching, learneronlyscope, historicalmaterial/figure anddirtypreview. Chrome1440,2560(or screenshotactual),3771,390; titleassertusesdocument.title, notonlyLoginmarkup. Verifyliveoperationalcounts andplural0/1/2. Atleast2assignedteachers+admin+students andunrelatedcourse inQA.

After allgates: retained-dataCT255backup/restore/migration, newrelease, readback. Originalproductionaccounts/courses/invites/work untouched exceptone-timenewtableownerbackfill; no syntheticproductionrecords or changingrealroles to test. Model/searchquality not partofthiswork; no realcalls needed. Childhandoffs reportactualpaths/tests/limits, preservefailures, closeownedlisteners. Parent verifies, deploys andcloses task.
