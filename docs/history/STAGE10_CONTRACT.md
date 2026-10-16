# Stage10 — public-test security preparation (completed/deployed)

Completed before deadline. Current release AIcademiya_V2-20261008-security; verified result DEPLOYMENT_STAGE10_SECURITY_RESULT.md, latest state STAGE10_CHECKPOINT.md. Public ingress remains a separate unexecuted rollout. The contract below records scope, ownership and gates already completed.

Operator friend Z. Authorized review and repair before public testing, including admin registration switch. Hard deadline 2026-10-08 13:30 Asia/Shanghai; stop new changes at that time. Children return by12:55; no new production cutover after13:20, leave cleanup/rollback margin. No public DNS/proxy/NAT/firewall exposure changes in this task. Preserve all accounts, data, config, materials, active model services and AGENTS.md. No real inference or search calls.

Current production baseline: AIcademiya_V2-20261008-account-feedback-light, API0.8.0/schema7. Previous exact manifest/archive are the backend deployed baseline; parent frontend source snapshot is artifacts/stage10/parent-frontend-baseline.zip. Synthetic tests only, no new production users/feedback/materials or guesses at passwords. No permission implied to close all new registrations: existing registration policy remains default ON (invite required); admin may switch OFF in Settings → User Management.

Auth child owns main/auth/config/new HTTP security/access settings+tests. Data child owns material/link/parser helpers+tests; main hooks handed back without concurrent main editing. Parent owns frontend, infra observations, packaging, integration, deployment/docs. Findings require concrete source or reproducible evidence; distinguish configuration prerequisites from exploits, and advisory scan absence from proof of security.

Frozen registration API: admin GET/PUT /api/admin/access-settings {registration_enabled:boolean}. Strict body, persistent settings, auth+admin enforced. Public bootstrap registration_enabled. OFF rejects direct registration before creation/enrollment, login/manual staff provisioning unaffected. ON still needs valid course invite. No schema/user row changes for the setting. Frontend save is followed by independent GET and visible verified status; closure notice instead of public signup. API/schema stay0.8.0/7 for this compatible hardening patch unless coordinated.

Public rollout will still need the actual HTTPS domain, proxy peer, secure cookie, exact allowed Origin and restricted backend access. Never claim public ingress tested from private-IP HTTP alone. Production stays private for this task.
