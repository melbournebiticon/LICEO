-- Run this once in pgAdmin or psql to create the teacher_announcements table

CREATE TABLE IF NOT EXISTS teacher_announcements (
    announcement_id SERIAL PRIMARY KEY,
    teacher_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    branch_id       INTEGER NOT NULL REFERENCES branches(branch_id) ON DELETE CASCADE,
    grade_level     VARCHAR(20) NOT NULL,
    title           VARCHAR(150) NOT NULL,
    body            TEXT,
    created_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Index for fast lookups by branch + grade
CREATE INDEX IF NOT EXISTS idx_teacher_ann_branch_grade
    ON teacher_announcements(branch_id, grade_level);
