-- 在现有数据库上执行一次，发布内容和学习记录保持原有引用。
ALTER TABLE teaching_session
 ADD COLUMN available BOOLEAN NOT NULL DEFAULT FALSE,
 ADD COLUMN opens_at DATETIME(3) NULL,
 ADD COLUMN closes_at DATETIME(3) NULL,
 ADD INDEX ix_task_expiry(available,closes_at),
 ADD CONSTRAINT ck_task_available CHECK (available IN (0,1)),
 ADD CONSTRAINT ck_task_schedule CHECK (opens_at IS NULL OR closes_at IS NULL);

UPDATE teaching_session SET available = TRUE
 WHERE archived = FALSE AND published_version_id IS NOT NULL
 AND opens_at IS NULL AND closes_at IS NULL AND available = FALSE;
