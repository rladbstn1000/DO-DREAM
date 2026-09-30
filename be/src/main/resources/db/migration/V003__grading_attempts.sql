-- Phase 3-A additive, rerunnable MySQL 8 migration. Apply before application start.
-- Never infer historical snapshots. Legacy rows keep NULL snapshot fields.
CREATE TABLE IF NOT EXISTS grading_attempts (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 attempt_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 student_id BIGINT NOT NULL, material_id BIGINT NOT NULL,
 idempotency_key CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 request_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 state VARCHAR(20) NOT NULL, execution_generation INT NOT NULL DEFAULT 0,
 execution_token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 deadline_at DATETIME(6) NULL, dispatched_at DATETIME(6) NULL,
 created_at DATETIME(6) NOT NULL, completed_at DATETIME(6) NULL, failure_code VARCHAR(64) NULL,
 CONSTRAINT uq_grading_public UNIQUE(attempt_id),
 CONSTRAINT uq_grading_student_key UNIQUE(student_id,idempotency_key),
 INDEX idx_grading_student_material(student_id,material_id,id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS grading_attempt_items (
 attempt_id BIGINT NOT NULL, quiz_id BIGINT NOT NULL, quiz_version BIGINT NOT NULL,
 question_number INT NOT NULL, question_type VARCHAR(50) NULL, title VARCHAR(255) NOT NULL,
 question_content TEXT NOT NULL, correct_answer TEXT NOT NULL, student_answer TEXT NOT NULL,
 grading_version VARCHAR(32) NOT NULL,
 PRIMARY KEY(attempt_id,quiz_id), INDEX idx_grading_item_quiz(quiz_id),
 CONSTRAINT fk_grading_item_attempt FOREIGN KEY(attempt_id) REFERENCES grading_attempts(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS grading_attempt_results (
 attempt_id BIGINT NOT NULL, quiz_id BIGINT NOT NULL, is_correct BOOLEAN NOT NULL,
 ai_feedback TEXT NOT NULL,
 PRIMARY KEY(attempt_id,quiz_id),
 CONSTRAINT fk_grading_result_item FOREIGN KEY(attempt_id,quiz_id) REFERENCES grading_attempt_items(attempt_id,quiz_id)
) ENGINE=InnoDB;

SET @grading_ddl = IF(EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='quizzes') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='quizzes' AND column_name='version'), 'ALTER TABLE quizzes ADD COLUMN version BIGINT NOT NULL DEFAULT 0', 'SELECT 1');
PREPARE grading_stmt FROM @grading_ddl; EXECUTE grading_stmt; DEALLOCATE PREPARE grading_stmt;

SET @grading_ddl = IF(EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='student_quiz_logs') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='student_quiz_logs' AND column_name='attempt_id'), 'ALTER TABLE student_quiz_logs ADD COLUMN attempt_id BIGINT NULL', 'SELECT 1');
PREPARE grading_stmt FROM @grading_ddl; EXECUTE grading_stmt; DEALLOCATE PREPARE grading_stmt;

SET @grading_ddl = IF(EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='student_quiz_logs') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='student_quiz_logs' AND column_name='submitted_at'), 'ALTER TABLE student_quiz_logs ADD COLUMN submitted_at DATETIME(6) NULL', 'SELECT 1');
PREPARE grading_stmt FROM @grading_ddl; EXECUTE grading_stmt; DEALLOCATE PREPARE grading_stmt;

SET @grading_ddl = IF(EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='student_quiz_logs') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='student_quiz_logs' AND column_name='snapshot_correct_answer'), 'ALTER TABLE student_quiz_logs ADD COLUMN snapshot_correct_answer TEXT NULL', 'SELECT 1');
PREPARE grading_stmt FROM @grading_ddl; EXECUTE grading_stmt; DEALLOCATE PREPARE grading_stmt;

SET @grading_ddl = IF(EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='student_quiz_logs') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='student_quiz_logs' AND column_name='snapshot_question_content'), 'ALTER TABLE student_quiz_logs ADD COLUMN snapshot_question_content TEXT NULL', 'SELECT 1');
PREPARE grading_stmt FROM @grading_ddl; EXECUTE grading_stmt; DEALLOCATE PREPARE grading_stmt;

SET @grading_ddl = IF(EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='student_quiz_logs') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='student_quiz_logs' AND column_name='snapshot_quiz_version'), 'ALTER TABLE student_quiz_logs ADD COLUMN snapshot_quiz_version BIGINT NULL', 'SELECT 1');
PREPARE grading_stmt FROM @grading_ddl; EXECUTE grading_stmt; DEALLOCATE PREPARE grading_stmt;

SET @grading_ddl = IF(EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='student_quiz_logs') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='student_quiz_logs' AND column_name='grading_version'), 'ALTER TABLE student_quiz_logs ADD COLUMN grading_version VARCHAR(32) NULL', 'SELECT 1');
PREPARE grading_stmt FROM @grading_ddl; EXECUTE grading_stmt; DEALLOCATE PREPARE grading_stmt;

SET @grading_ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='student_quiz_logs' AND column_name='student_answer' AND data_type<>'text'), 'ALTER TABLE student_quiz_logs MODIFY COLUMN student_answer TEXT NOT NULL', 'SELECT 1');
PREPARE grading_stmt FROM @grading_ddl; EXECUTE grading_stmt; DEALLOCATE PREPARE grading_stmt;

SET @grading_ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='quizzes' AND column_name='correct_answer' AND data_type<>'text'), 'ALTER TABLE quizzes MODIFY COLUMN correct_answer TEXT NOT NULL', 'SELECT 1');
PREPARE grading_stmt FROM @grading_ddl; EXECUTE grading_stmt; DEALLOCATE PREPARE grading_stmt;

SET @grading_ddl = IF(EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='student_quiz_logs') AND NOT EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='student_quiz_logs' AND index_name='uq_quiz_log_attempt'), 'ALTER TABLE student_quiz_logs ADD CONSTRAINT uq_quiz_log_attempt UNIQUE(attempt_id,quiz_id)', 'SELECT 1');
PREPARE grading_stmt FROM @grading_ddl; EXECUTE grading_stmt; DEALLOCATE PREPARE grading_stmt;
