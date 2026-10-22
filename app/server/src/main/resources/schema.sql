CREATE TABLE IF NOT EXISTS account_user (
 id VARCHAR(64) PRIMARY KEY, name VARCHAR(100) NOT NULL, email VARCHAR(254) NOT NULL UNIQUE,
 role VARCHAR(16) NOT NULL, password_hash VARCHAR(255), archived BOOLEAN NOT NULL DEFAULT FALSE,
 must_change_password BOOLEAN NOT NULL DEFAULT FALSE, demo BOOLEAN NOT NULL DEFAULT FALSE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS auth_session (
 id VARCHAR(64) PRIMARY KEY, user_id VARCHAR(64) NOT NULL, expires_at DATETIME(3) NOT NULL,
 INDEX(user_id), INDEX(expires_at), FOREIGN KEY(user_id) REFERENCES account_user(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS course (
 id VARCHAR(64) PRIMARY KEY, code VARCHAR(100) NOT NULL, title VARCHAR(300) NOT NULL,
 description TEXT NOT NULL, owner_id VARCHAR(64) NOT NULL, system_instructions TEXT NOT NULL,
 join_code VARCHAR(32) NOT NULL UNIQUE, archived BOOLEAN NOT NULL DEFAULT FALSE,
 FOREIGN KEY(owner_id) REFERENCES account_user(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS course_member (
 id VARCHAR(64) PRIMARY KEY, course_id VARCHAR(64) NOT NULL, user_id VARCHAR(64) NOT NULL,
 role VARCHAR(16) NOT NULL, archived BOOLEAN NOT NULL DEFAULT FALSE,
 UNIQUE(course_id,user_id), INDEX(user_id,archived), FOREIGN KEY(course_id) REFERENCES course(id),
 FOREIGN KEY(user_id) REFERENCES account_user(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS teaching_session (
 id VARCHAR(64) PRIMARY KEY, course_id VARCHAR(64) NOT NULL, title VARCHAR(300) NOT NULL,
 description TEXT NOT NULL, session_type VARCHAR(20) NOT NULL, topic TEXT NOT NULL,
 learning_goals TEXT NOT NULL, additional_instructions TEXT NOT NULL, teaching_language VARCHAR(16) NOT NULL,
 material_ids_json JSON NOT NULL, content_json JSON NOT NULL, revision BIGINT NOT NULL DEFAULT 0,
 published_version_id VARCHAR(64), archived BOOLEAN NOT NULL DEFAULT FALSE,
 INDEX(course_id,archived), FOREIGN KEY(course_id) REFERENCES course(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS session_version (
 id VARCHAR(64) PRIMARY KEY, session_id VARCHAR(64) NOT NULL, course_id VARCHAR(64) NOT NULL,
 revision BIGINT NOT NULL, label VARCHAR(200) NOT NULL, content_json JSON NOT NULL,
 created_at DATETIME(3) NOT NULL, UNIQUE(session_id,revision), INDEX(course_id),
 FOREIGN KEY(session_id) REFERENCES teaching_session(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS course_material (
 id VARCHAR(64) PRIMARY KEY, course_id VARCHAR(64) NOT NULL, title VARCHAR(300) NOT NULL,
 file_name VARCHAR(255) NOT NULL, relative_path VARCHAR(1024) NOT NULL, mime_type VARCHAR(100) NOT NULL,
 storage_path TEXT NOT NULL, text_content MEDIUMTEXT NOT NULL, extraction_report_json JSON, status VARCHAR(20) NOT NULL,
 visibility VARCHAR(16) NOT NULL, error_message TEXT NOT NULL, archived BOOLEAN NOT NULL DEFAULT FALSE,
 created_at DATETIME(3) NOT NULL, INDEX(course_id,archived), INDEX(status), FOREIGN KEY(course_id) REFERENCES course(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS generation_job (
 id VARCHAR(64) PRIMARY KEY, session_id VARCHAR(64) NOT NULL, owner_id VARCHAR(64) NOT NULL,
 kind VARCHAR(20) NOT NULL, status VARCHAR(20) NOT NULL, stage VARCHAR(100) NOT NULL,
 expected_revision BIGINT NOT NULL, request_json JSON NOT NULL, result_json JSON,
 error_message TEXT NOT NULL, created_at DATETIME(3) NOT NULL, updated_at DATETIME(3) NOT NULL,
 INDEX(status,created_at), INDEX(session_id,created_at), FOREIGN KEY(session_id) REFERENCES teaching_session(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS learning_record (
 id VARCHAR(64) PRIMARY KEY, session_id VARCHAR(64) NOT NULL, user_id VARCHAR(64) NOT NULL,
 version_id VARCHAR(64) NOT NULL, status VARCHAR(20) NOT NULL, answers_json JSON NOT NULL,
 messages_json JSON NOT NULL, legacy_json JSON, revision BIGINT NOT NULL DEFAULT 0,
 started_at DATETIME(3), updated_at DATETIME(3), submitted_at DATETIME(3), reviewed_at DATETIME(3), teacher_note TEXT NOT NULL,
 UNIQUE(session_id,user_id,version_id), INDEX(session_id,version_id),
 FOREIGN KEY(session_id) REFERENCES teaching_session(id), FOREIGN KEY(user_id) REFERENCES account_user(id),
 FOREIGN KEY(version_id) REFERENCES session_version(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS legacy_record (
 id VARCHAR(64) PRIMARY KEY, source_table VARCHAR(64) NOT NULL, source_key VARCHAR(255) NOT NULL,
 payload_json JSON NOT NULL, UNIQUE(source_table,source_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
