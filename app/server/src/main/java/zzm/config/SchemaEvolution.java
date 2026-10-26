package zzm.config;

import lombok.RequiredArgsConstructor;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.sql.init.dependency.DependsOnDatabaseInitialization;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Additive, idempotent upgrades for existing local MySQL databases. */
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
        Long versionRequired = jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='learning_record' AND column_name='version_id' AND is_nullable='NO'", Long.class);
        if (versionRequired != null && versionRequired > 0) jdbc.execute("ALTER TABLE learning_record MODIFY version_id VARCHAR(64) NULL");
        add("course_material", "extraction_report_json", "JSON NULL");
        add("course_material", "owner_id", "VARCHAR(64) NULL");
        add("course_material", "record_id", "VARCHAR(64) NULL");
        add("course_material", "question_id", "VARCHAR(100) NULL");
        add("course_material", "file_size", "BIGINT NULL");
        add("course_material", "file_removed_at", "DATETIME(3) NULL");
        add("course_material", "removed_by", "VARCHAR(64) NULL");
        add("course_material", "trash_path", "TEXT NULL");
    }
    private void add(String table, String column, String definition) {
        Long count = jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=? AND column_name=?", Long.class, table, column);
        if (count != null && count == 0) jdbc.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + definition);
    }
}
