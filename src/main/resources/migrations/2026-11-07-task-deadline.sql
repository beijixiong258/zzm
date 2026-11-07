-- 在任务开放字段迁移之后执行一次。旧待生效任务须由教师设置截止时间后重新启用。
UPDATE teaching_session SET available = FALSE
 WHERE opens_at > UTC_TIMESTAMP(3) AND available = TRUE;

ALTER TABLE teaching_session
 DROP CHECK ck_task_schedule,
 DROP COLUMN opens_at,
 ADD COLUMN updated_at DATETIME(3) NULL;

UPDATE teaching_session SET updated_at = UTC_TIMESTAMP(3) WHERE updated_at IS NULL;
ALTER TABLE teaching_session MODIFY COLUMN updated_at DATETIME(3) NOT NULL;
