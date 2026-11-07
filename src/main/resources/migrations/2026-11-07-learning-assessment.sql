-- 旧提交可录入教师成绩，不使用后来版本的题目回判历史作答。
CREATE TABLE IF NOT EXISTS learning_assessment (
 id VARCHAR(64) PRIMARY KEY, record_id VARCHAR(64) NOT NULL, submission_revision BIGINT NOT NULL,
 status VARCHAR(20) NOT NULL, input_json JSON NOT NULL, feedback_json JSON NULL, run_id VARCHAR(64) NULL,
 question_count INT NOT NULL, evaluated_count INT NOT NULL DEFAULT 0,
 submitted_at DATETIME(3) NOT NULL, updated_at DATETIME(3) NOT NULL, evaluated_at DATETIME(3) NULL,
 teacher_score DECIMAL(5,2) NULL, scored_at DATETIME(3) NULL,
 UNIQUE(record_id,submission_revision), INDEX ix_assessment_queue(status,submitted_at),
 CONSTRAINT ck_teacher_score CHECK (teacher_score BETWEEN 0 AND 100),
 FOREIGN KEY(record_id) REFERENCES learning_record(id) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO learning_assessment
 (id,record_id,submission_revision,status,input_json,question_count,submitted_at,updated_at)
 SELECT REPLACE(UUID(),'-',''), r.id, r.revision, 'legacy', JSON_OBJECT(), 0, r.submitted_at, UTC_TIMESTAMP(3)
 FROM learning_record r
 WHERE r.preview = FALSE AND r.submitted_at IS NOT NULL
 AND NOT EXISTS (SELECT 1 FROM learning_assessment a WHERE a.record_id = r.id);
