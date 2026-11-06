package zzm.config;

import lombok.RequiredArgsConstructor;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.sql.init.dependency.DependsOnDatabaseInitialization;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** 为现有 MySQL 数据库执行可重复运行的增量结构升级。 */
@Component
@DependsOnDatabaseInitialization
@RequiredArgsConstructor
public class SchemaEvolution implements ApplicationRunner {
    private final JdbcTemplate jdbc;
    @Override public void run(ApplicationArguments arguments) {
        add("course", "workspace", "BOOLEAN NOT NULL DEFAULT FALSE");
        add("course", "course_information", "TEXT NULL");
        add("course", "student_profile", "TEXT NULL");
        add("account_user", "username", "VARCHAR(64) NULL");
        add("account_user", "invitation_hash", "VARCHAR(255) NULL");
        add("account_user", "invitation_enabled", "BOOLEAN NOT NULL DEFAULT FALSE");
        Long nullable = jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='account_user' AND column_name='email' AND is_nullable='NO'", Long.class);
        if (nullable != null && nullable > 0) jdbc.execute("ALTER TABLE account_user MODIFY email VARCHAR(254) NULL");
        Long index = jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='account_user' AND index_name='uq_account_username'", Long.class);
        if (index != null && index == 0) jdbc.execute("CREATE UNIQUE INDEX uq_account_username ON account_user(username)");
        add("generation_job", "usage_json", "JSON NULL");
        add("learning_record", "answer_history_json", "JSON NULL");
        add("learning_record", "conversation_history_json", "JSON NULL");
        add("learning_record", "preview", "BOOLEAN NOT NULL DEFAULT FALSE");
        add("learning_record", "snapshot_json", "JSON NULL");
        add("learning_record", "tutor_state_json", "JSON NULL");
        Long versionRequired = jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='learning_record' AND column_name='version_id' AND is_nullable='NO'", Long.class);
        if (versionRequired != null && versionRequired > 0) jdbc.execute("ALTER TABLE learning_record MODIFY version_id VARCHAR(64) NULL");
        add("course_material", "extraction_report_json", "JSON NULL");
        add("course_material", "retrieval_json", "JSON NULL");
        add("course_material", "retrieval_retry_at", "DATETIME(3) NULL");
        add("course_material", "owner_id", "VARCHAR(64) NULL");
        add("course_material", "record_id", "VARCHAR(64) NULL");
        add("course_material", "question_id", "VARCHAR(100) NULL");
        add("course_material", "file_size", "BIGINT NULL");
        add("course_material", "file_removed_at", "DATETIME(3) NULL");
        add("course_material", "removed_by", "VARCHAR(64) NULL");
        add("course_material", "trash_path", "TEXT NULL");
        relation("course_member", "course_id", "course", "CASCADE", false);
        relation("teaching_session", "course_id", "course", "CASCADE", false);
        relation("session_version", "session_id", "teaching_session", "CASCADE", false);
        relation("generation_job", "session_id", "teaching_session", "CASCADE", false);
        relation("learning_record", "session_id", "teaching_session", "CASCADE", false);
        relation("learning_record", "version_id", "session_version", "CASCADE", false);
        relation("learning_record_history", "record_id", "learning_record", "CASCADE", false);
        // 课程删除后保留文件回收标记，文件移走后由现有回收任务清除材料记录。
        relation("course_material", "course_id", "course", "SET NULL", true);
        jdbc.update("UPDATE course_material SET storage_path=SUBSTRING_INDEX(REPLACE(storage_path,CHAR(92),'/'),'/',-1) WHERE storage_path LIKE '/%' OR storage_path REGEXP '^[A-Za-z]:'");
        jdbc.update("UPDATE course_material SET trash_path=SUBSTRING_INDEX(REPLACE(trash_path,CHAR(92),'/'),'/',-2) WHERE trash_path LIKE '/%' OR trash_path REGEXP '^[A-Za-z]:'");
    }
    private void relation(String table, String column, String parent, String rule, boolean nullable) {
        var existing = jdbc.query("SELECT k.CONSTRAINT_NAME,r.DELETE_RULE FROM information_schema.KEY_COLUMN_USAGE k JOIN information_schema.REFERENTIAL_CONSTRAINTS r ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.TABLE_NAME=k.TABLE_NAME AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME WHERE k.CONSTRAINT_SCHEMA=DATABASE() AND k.TABLE_NAME=? AND k.COLUMN_NAME=? AND k.REFERENCED_TABLE_NAME=? AND k.REFERENCED_COLUMN_NAME='id'",
            (row, index) -> new String[] { row.getString(1), row.getString(2) }, table, column, parent);
        boolean changeNullability = nullable && jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND COLUMN_NAME=? AND IS_NULLABLE='NO'", Long.class, table, column) > 0;
        if (existing.size() == 1 && rule.equals(existing.get(0)[1]) && !changeNullability) return;
        if (existing.size() > 1) throw new IllegalStateException("Multiple foreign keys exist for " + table + "." + column);
        String name = "fk_" + table + "_" + column + "_" + rule.toLowerCase(java.util.Locale.ROOT).replace(' ', '_');
        if (!existing.isEmpty() && name.equals(existing.get(0)[0])) name += "_next";
        String drop = existing.isEmpty() ? "" : "DROP FOREIGN KEY `" + existing.get(0)[0].replace("`", "``") + "`, ";
        String modify = changeNullability ? "MODIFY `" + column + "` VARCHAR(64) NULL, " : "";
        jdbc.execute("ALTER TABLE `" + table + "` " + drop + modify + "ADD CONSTRAINT `" + name.replace("`", "``") + "` FOREIGN KEY (`" + column + "`) REFERENCES `" + parent + "` (`id`) ON DELETE " + rule);
    }
    private void add(String table, String column, String definition) {
        Long count = jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=? AND column_name=?", Long.class, table, column);
        if (count != null && count == 0) jdbc.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + definition);
    }
}
