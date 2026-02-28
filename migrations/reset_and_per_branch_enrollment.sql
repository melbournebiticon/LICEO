-- ============================================================
-- MIGRATION: Reset student/parent data & enforce per-branch
--            enrollment numbering starting from 1
-- ============================================================
-- RUN THIS IN psql or pgAdmin AS the postgres or liceo_db user.
-- This DELETES all enrollment, student account, and parent data.
-- The enrollment_id (global PK) will also reset to 1.
-- branch_enrollment_no will now be the user-visible number,
-- unique and sequential PER BRANCH (1, 2, 3... per branch).
-- ============================================================

BEGIN;

-- 1. Delete all dependent data first (order matters due to FK constraints)
DELETE FROM public.reservation_items;
DELETE FROM public.reservations;
DELETE FROM public.payments;
DELETE FROM public.billing;
DELETE FROM public.enrollment_books;
DELETE FROM public.enrollment_uniforms;
DELETE FROM public.enrollment_documents;

-- 2. Delete parent links and parent users
DELETE FROM public.parent_student;
DELETE FROM public.users WHERE role = 'parent';

-- 3. Delete student accounts
DELETE FROM public.student_accounts;

-- 4. Delete all enrollments
DELETE FROM public.enrollments;

-- 5. Reset the global enrollment_id sequence back to 1
ALTER SEQUENCE public.enrollments_enrollment_id_seq RESTART WITH 1;

-- 6. Reset student_accounts sequence
ALTER SEQUENCE public.student_accounts_account_id_seq RESTART WITH 1;

-- 7. Reset parent_student sequence
ALTER SEQUENCE public.parent_student_id_seq RESTART WITH 1;

-- 8. Add branch_enrollment_no column (if it doesn't exist yet)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'enrollments'
          AND column_name  = 'branch_enrollment_no'
    ) THEN
        ALTER TABLE public.enrollments
            ADD COLUMN branch_enrollment_no INTEGER;
    END IF;
END
$$;

-- 9. Add UNIQUE constraint per branch so no two students in the same
--    branch can share the same branch_enrollment_no
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_enrollments_branch_no'
    ) THEN
        ALTER TABLE public.enrollments
            ADD CONSTRAINT uq_enrollments_branch_no
            UNIQUE (branch_id, branch_enrollment_no);
    END IF;
END
$$;

COMMIT;

-- ============================================================
-- VERIFICATION: After running, these should all return 0:
-- ============================================================
-- SELECT COUNT(*) FROM enrollments;
-- SELECT COUNT(*) FROM student_accounts;
-- SELECT COUNT(*) FROM parent_student;
-- SELECT COUNT(*) FROM users WHERE role = 'parent';
-- ============================================================
