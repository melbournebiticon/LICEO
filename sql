-- Table: public.announcements

-- DROP TABLE IF EXISTS public.announcements;

CREATE TABLE IF NOT EXISTS public.announcements
(
    announcement_id integer NOT NULL DEFAULT nextval('announcements_announcement_id_seq'::regclass),
    title character varying(255) COLLATE pg_catalog."default" NOT NULL,
    message text COLLATE pg_catalog."default" NOT NULL,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    CONSTRAINT announcements_pkey PRIMARY KEY (announcement_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.announcements
    OWNER to postgres;

REVOKE ALL ON TABLE public.announcements FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.announcements TO liceo_db;

GRANT ALL ON TABLE public.announcements TO postgres;    

-- Table: public.billing

-- DROP TABLE IF EXISTS public.billing;

CREATE TABLE IF NOT EXISTS public.billing
(
    bill_id integer NOT NULL DEFAULT nextval('billing_bill_id_seq'::regclass),
    enrollment_id integer NOT NULL,
    branch_id integer NOT NULL,
    tuition_fee numeric(10,2) DEFAULT 0.00,
    books_fee numeric(10,2) DEFAULT 0.00,
    uniform_fee numeric(10,2) DEFAULT 0.00,
    other_fees numeric(10,2) DEFAULT 0.00,
    total_amount numeric(10,2) NOT NULL,
    amount_paid numeric(10,2) DEFAULT 0.00,
    balance numeric(10,2) NOT NULL,
    status character varying(10) COLLATE pg_catalog."default" DEFAULT 'pending'::character varying,
    created_by integer NOT NULL,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    updated_at timestamp without time zone NOT NULL DEFAULT now(),
    CONSTRAINT billing_pkey PRIMARY KEY (bill_id),
    CONSTRAINT billing_branch_id_fkey FOREIGN KEY (branch_id)
        REFERENCES public.branches (branch_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT billing_created_by_fkey FOREIGN KEY (created_by)
        REFERENCES public.users (user_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT billing_enrollment_id_fkey FOREIGN KEY (enrollment_id)
        REFERENCES public.enrollments (enrollment_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.billing
    OWNER to postgres;

REVOKE ALL ON TABLE public.billing FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.billing TO liceo_db;

GRANT ALL ON TABLE public.billing TO postgres;
-- Index: idx_billing_branch_id

-- DROP INDEX IF EXISTS public.idx_billing_branch_id;

CREATE INDEX IF NOT EXISTS idx_billing_branch_id
    ON public.billing USING btree
    (branch_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_billing_enrollment_id

-- DROP INDEX IF EXISTS public.idx_billing_enrollment_id;

CREATE INDEX IF NOT EXISTS idx_billing_enrollment_id
    ON public.billing USING btree
    (enrollment_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_billing_status

-- DROP INDEX IF EXISTS public.idx_billing_status;

CREATE INDEX IF NOT EXISTS idx_billing_status
    ON public.billing USING btree
    (status COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Table: public.branches

-- DROP TABLE IF EXISTS public.branches;

CREATE TABLE IF NOT EXISTS public.branches
(
    branch_id integer NOT NULL DEFAULT nextval('branches_branch_id_seq'::regclass),
    branch_name character varying(100) COLLATE pg_catalog."default" NOT NULL,
    location character varying(100) COLLATE pg_catalog."default",
    status character varying(10) COLLATE pg_catalog."default" DEFAULT 'active'::character varying,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT branches_pkey PRIMARY KEY (branch_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.branches
    OWNER to postgres;

REVOKE ALL ON TABLE public.branches FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.branches TO liceo_db;

GRANT ALL ON TABLE public.branches TO postgres;

-- Table: public.chatbot_faqs

-- DROP TABLE IF EXISTS public.chatbot_faqs;

CREATE TABLE IF NOT EXISTS public.chatbot_faqs
(
    id integer NOT NULL DEFAULT nextval('chatbot_faqs_id_seq'::regclass),
    branch_id integer,
    question text COLLATE pg_catalog."default" NOT NULL,
    answer text COLLATE pg_catalog."default" NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chatbot_faqs_pkey PRIMARY KEY (id),
    CONSTRAINT fk_chatbot_branch FOREIGN KEY (branch_id)
        REFERENCES public.branches (branch_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.chatbot_faqs
    OWNER to postgres;

REVOKE ALL ON TABLE public.chatbot_faqs FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.chatbot_faqs TO liceo_db;

GRANT ALL ON TABLE public.chatbot_faqs TO postgres;

-- Table: public.enrollment_books

-- DROP TABLE IF EXISTS public.enrollment_books;

CREATE TABLE IF NOT EXISTS public.enrollment_books
(
    book_id integer NOT NULL DEFAULT nextval('enrollment_books_book_id_seq'::regclass),
    enrollment_id integer NOT NULL,
    book_name character varying(100) COLLATE pg_catalog."default" NOT NULL,
    quantity integer DEFAULT 1,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    CONSTRAINT enrollment_books_pkey PRIMARY KEY (book_id),
    CONSTRAINT enrollment_books_enrollment_id_fkey FOREIGN KEY (enrollment_id)
        REFERENCES public.enrollments (enrollment_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.enrollment_books
    OWNER to postgres;

REVOKE ALL ON TABLE public.enrollment_books FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.enrollment_books TO liceo_db;

GRANT ALL ON TABLE public.enrollment_books TO postgres;

-- Table: public.enrollment_documents

-- DROP TABLE IF EXISTS public.enrollment_documents;

CREATE TABLE IF NOT EXISTS public.enrollment_documents
(
    doc_id integer NOT NULL DEFAULT nextval('enrollment_documents_doc_id_seq'::regclass),
    enrollment_id integer NOT NULL,
    file_name character varying(255) COLLATE pg_catalog."default" NOT NULL,
    file_path character varying(255) COLLATE pg_catalog."default" NOT NULL,
    uploaded_at timestamp without time zone NOT NULL DEFAULT now(),
    CONSTRAINT enrollment_documents_pkey PRIMARY KEY (doc_id),
    CONSTRAINT enrollment_documents_enrollment_id_fkey FOREIGN KEY (enrollment_id)
        REFERENCES public.enrollments (enrollment_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.enrollment_documents
    OWNER to postgres;

REVOKE ALL ON TABLE public.enrollment_documents FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.enrollment_documents TO liceo_db;

GRANT ALL ON TABLE public.enrollment_documents TO postgres;

-- Table: public.enrollment_uniforms

-- DROP TABLE IF EXISTS public.enrollment_uniforms;

CREATE TABLE IF NOT EXISTS public.enrollment_uniforms
(
    uniform_id integer NOT NULL DEFAULT nextval('enrollment_uniforms_uniform_id_seq'::regclass),
    enrollment_id integer NOT NULL,
    uniform_type character varying(50) COLLATE pg_catalog."default" NOT NULL,
    size character varying(10) COLLATE pg_catalog."default" NOT NULL,
    quantity integer NOT NULL DEFAULT 1,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    CONSTRAINT enrollment_uniforms_pkey PRIMARY KEY (uniform_id),
    CONSTRAINT enrollment_uniforms_enrollment_id_fkey FOREIGN KEY (enrollment_id)
        REFERENCES public.enrollments (enrollment_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.enrollment_uniforms
    OWNER to postgres;

REVOKE ALL ON TABLE public.enrollment_uniforms FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.enrollment_uniforms TO liceo_db;

GRANT ALL ON TABLE public.enrollment_uniforms TO postgres;

-- Table: public.enrollments

-- DROP TABLE IF EXISTS public.enrollments;

CREATE TABLE IF NOT EXISTS public.enrollments
(
    enrollment_id integer NOT NULL DEFAULT nextval('enrollments_enrollment_id_seq'::regclass),
    student_name character varying(100) COLLATE pg_catalog."default" NOT NULL,
    grade_level character varying(50) COLLATE pg_catalog."default",
    branch_id integer NOT NULL,
    status character varying(20) COLLATE pg_catalog."default",
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    user_id integer,
    gender character varying(20) COLLATE pg_catalog."default",
    dob date,
    address text COLLATE pg_catalog."default",
    contact_number character varying(20) COLLATE pg_catalog."default",
    guardian_name character varying(100) COLLATE pg_catalog."default",
    guardian_contact character varying(20) COLLATE pg_catalog."default",
    previous_school character varying(150) COLLATE pg_catalog."default",
    CONSTRAINT enrollments_pkey PRIMARY KEY (enrollment_id),
    CONSTRAINT enrollments_branch_id_fkey FOREIGN KEY (branch_id)
        REFERENCES public.branches (branch_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT enrollments_user_id_fkey FOREIGN KEY (user_id)
        REFERENCES public.users (user_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.enrollments
    OWNER to postgres;

REVOKE ALL ON TABLE public.enrollments FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.enrollments TO liceo_db;

GRANT ALL ON TABLE public.enrollments TO postgres;

-- Table: public.inventory_item_sizes

-- DROP TABLE IF EXISTS public.inventory_item_sizes;

CREATE TABLE IF NOT EXISTS public.inventory_item_sizes
(
    size_id integer NOT NULL DEFAULT nextval('inventory_item_sizes_size_id_seq'::regclass),
    item_id integer NOT NULL,
    size_label character varying(10) COLLATE pg_catalog."default" NOT NULL,
    stock_total integer NOT NULL DEFAULT 0,
    reserved_qty integer NOT NULL DEFAULT 0,
    CONSTRAINT inventory_item_sizes_pkey PRIMARY KEY (size_id),
    CONSTRAINT inventory_item_sizes_item_id_size_label_key UNIQUE (item_id, size_label),
    CONSTRAINT inventory_item_sizes_item_id_fkey FOREIGN KEY (item_id)
        REFERENCES public.inventory_items (item_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.inventory_item_sizes
    OWNER to postgres;

REVOKE ALL ON TABLE public.inventory_item_sizes FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.inventory_item_sizes TO liceo_db;

GRANT ALL ON TABLE public.inventory_item_sizes TO postgres;

-- Table: public.inventory_items

-- DROP TABLE IF EXISTS public.inventory_items;

CREATE TABLE IF NOT EXISTS public.inventory_items
(
    item_id integer NOT NULL DEFAULT nextval('inventory_items_item_id_seq'::regclass),
    branch_id integer NOT NULL,
    category text COLLATE pg_catalog."default" NOT NULL,
    item_name text COLLATE pg_catalog."default" NOT NULL,
    grade_level text COLLATE pg_catalog."default",
    is_common boolean NOT NULL DEFAULT false,
    size_label text COLLATE pg_catalog."default",
    price numeric(12,2) NOT NULL DEFAULT 0,
    stock_total integer NOT NULL DEFAULT 0,
    reserved_qty integer NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    image_url text COLLATE pg_catalog."default",
    publisher character varying(100) COLLATE pg_catalog."default",
    CONSTRAINT inventory_items_pkey PRIMARY KEY (item_id),
    CONSTRAINT inventory_items_branch_id_fkey FOREIGN KEY (branch_id)
        REFERENCES public.branches (branch_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT inventory_items_category_check CHECK (category = ANY (ARRAY['BOOK'::text, 'UNIFORM'::text]))
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.inventory_items
    OWNER to postgres;

REVOKE ALL ON TABLE public.inventory_items FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.inventory_items TO liceo_db;

GRANT ALL ON TABLE public.inventory_items TO postgres;
-- Index: idx_inventory_branch

-- DROP INDEX IF EXISTS public.idx_inventory_branch;

CREATE INDEX IF NOT EXISTS idx_inventory_branch
    ON public.inventory_items USING btree
    (branch_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Table: public.inventory_sizes

-- DROP TABLE IF EXISTS public.inventory_sizes;

CREATE TABLE IF NOT EXISTS public.inventory_sizes
(
    size_id integer NOT NULL DEFAULT nextval('inventory_sizes_size_id_seq'::regclass),
    item_id integer,
    size_label character varying(10) COLLATE pg_catalog."default",
    stock_qty integer DEFAULT 0,
    reserved_qty integer DEFAULT 0,
    CONSTRAINT inventory_sizes_pkey PRIMARY KEY (size_id),
    CONSTRAINT inventory_sizes_item_id_fkey FOREIGN KEY (item_id)
        REFERENCES public.inventory_items (item_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.inventory_sizes
    OWNER to postgres;

REVOKE ALL ON TABLE public.inventory_sizes FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.inventory_sizes TO liceo_db;

GRANT ALL ON TABLE public.inventory_sizes TO postgres;

-- Table: public.parent_student

-- DROP TABLE IF EXISTS public.parent_student;

CREATE TABLE IF NOT EXISTS public.parent_student
(
    id integer NOT NULL DEFAULT nextval('parent_student_id_seq'::regclass),
    parent_id integer NOT NULL,
    student_id integer NOT NULL,
    relationship character varying(20) COLLATE pg_catalog."default" DEFAULT 'guardian'::character varying,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    CONSTRAINT parent_student_pkey PRIMARY KEY (id),
    CONSTRAINT unique_parent_student UNIQUE (parent_id, student_id),
    CONSTRAINT parent_student_parent_id_fkey FOREIGN KEY (parent_id)
        REFERENCES public.users (user_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT parent_student_student_id_fkey FOREIGN KEY (student_id)
        REFERENCES public.enrollments (enrollment_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.parent_student
    OWNER to postgres;

REVOKE ALL ON TABLE public.parent_student FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.parent_student TO liceo_db;

GRANT ALL ON TABLE public.parent_student TO postgres;
-- Index: idx_parent_student_parent

-- DROP INDEX IF EXISTS public.idx_parent_student_parent;

CREATE INDEX IF NOT EXISTS idx_parent_student_parent
    ON public.parent_student USING btree
    (parent_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_parent_student_student

-- DROP INDEX IF EXISTS public.idx_parent_student_student;

CREATE INDEX IF NOT EXISTS idx_parent_student_student
    ON public.parent_student USING btree
    (student_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Table: public.payments

-- DROP TABLE IF EXISTS public.payments;

CREATE TABLE IF NOT EXISTS public.payments
(
    payment_id integer NOT NULL DEFAULT nextval('payments_payment_id_seq'::regclass),
    bill_id integer NOT NULL,
    enrollment_id integer NOT NULL,
    branch_id integer NOT NULL,
    amount numeric(10,2) NOT NULL,
    payment_method character varying(20) COLLATE pg_catalog."default" DEFAULT 'cash'::character varying,
    payment_date timestamp without time zone NOT NULL DEFAULT now(),
    receipt_number character varying(50) COLLATE pg_catalog."default",
    notes text COLLATE pg_catalog."default",
    received_by integer NOT NULL,
    CONSTRAINT payments_pkey PRIMARY KEY (payment_id),
    CONSTRAINT payments_receipt_number_key UNIQUE (receipt_number),
    CONSTRAINT payments_bill_id_fkey FOREIGN KEY (bill_id)
        REFERENCES public.billing (bill_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT payments_branch_id_fkey FOREIGN KEY (branch_id)
        REFERENCES public.branches (branch_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT payments_enrollment_id_fkey FOREIGN KEY (enrollment_id)
        REFERENCES public.enrollments (enrollment_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT payments_received_by_fkey FOREIGN KEY (received_by)
        REFERENCES public.users (user_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.payments
    OWNER to postgres;

REVOKE ALL ON TABLE public.payments FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.payments TO liceo_db;

GRANT ALL ON TABLE public.payments TO postgres;
-- Index: idx_payments_bill_id

-- DROP INDEX IF EXISTS public.idx_payments_bill_id;

CREATE INDEX IF NOT EXISTS idx_payments_bill_id
    ON public.payments USING btree
    (bill_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_payments_branch_id

-- DROP INDEX IF EXISTS public.idx_payments_branch_id;

CREATE INDEX IF NOT EXISTS idx_payments_branch_id
    ON public.payments USING btree
    (branch_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_payments_enrollment_id

-- DROP INDEX IF EXISTS public.idx_payments_enrollment_id;

CREATE INDEX IF NOT EXISTS idx_payments_enrollment_id
    ON public.payments USING btree
    (enrollment_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_payments_payment_date

-- DROP INDEX IF EXISTS public.idx_payments_payment_date;

CREATE INDEX IF NOT EXISTS idx_payments_payment_date
    ON public.payments USING btree
    (payment_date ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Table: public.reservation_items

-- DROP TABLE IF EXISTS public.reservation_items;

CREATE TABLE IF NOT EXISTS public.reservation_items
(
    reservation_item_id integer NOT NULL DEFAULT nextval('reservation_items_reservation_item_id_seq'::regclass),
    reservation_id integer NOT NULL,
    item_id integer NOT NULL,
    qty integer NOT NULL,
    size_label text COLLATE pg_catalog."default",
    unit_price numeric(12,2) NOT NULL DEFAULT 0,
    line_total numeric(12,2) NOT NULL DEFAULT 0,
    CONSTRAINT reservation_items_pkey PRIMARY KEY (reservation_item_id),
    CONSTRAINT reservation_items_item_id_fkey FOREIGN KEY (item_id)
        REFERENCES public.inventory_items (item_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT reservation_items_reservation_id_fkey FOREIGN KEY (reservation_id)
        REFERENCES public.reservations (reservation_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT reservation_items_qty_check CHECK (qty > 0)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.reservation_items
    OWNER to postgres;

REVOKE ALL ON TABLE public.reservation_items FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.reservation_items TO liceo_db;

GRANT ALL ON TABLE public.reservation_items TO postgres;

-- Table: public.reservations

-- DROP TABLE IF EXISTS public.reservations;

CREATE TABLE IF NOT EXISTS public.reservations
(
    reservation_id integer NOT NULL DEFAULT nextval('reservations_reservation_id_seq'::regclass),
    student_user_id integer,
    branch_id integer NOT NULL,
    student_grade_level text COLLATE pg_catalog."default",
    status text COLLATE pg_catalog."default" NOT NULL DEFAULT 'RESERVED'::text,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    paid_at timestamp without time zone,
    claimed_at timestamp without time zone,
    cancelled_at timestamp without time zone,
    reserved_by_user_id integer,
    enrollment_id integer,
    CONSTRAINT reservations_pkey PRIMARY KEY (reservation_id),
    CONSTRAINT reservations_branch_id_fkey FOREIGN KEY (branch_id)
        REFERENCES public.branches (branch_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT reservations_reserved_by_user_id_fkey FOREIGN KEY (reserved_by_user_id)
        REFERENCES public.users (user_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT reservations_student_user_id_fkey FOREIGN KEY (student_user_id)
        REFERENCES public.users (user_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT reservations_status_check CHECK (status = ANY (ARRAY['RESERVED'::text, 'PAID'::text, 'CLAIMED'::text, 'CANCELLED'::text]))
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.reservations
    OWNER to postgres;

REVOKE ALL ON TABLE public.reservations FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.reservations TO liceo_db;

GRANT ALL ON TABLE public.reservations TO postgres;
-- Index: idx_reservations_branch

-- DROP INDEX IF EXISTS public.idx_reservations_branch;

CREATE INDEX IF NOT EXISTS idx_reservations_branch
    ON public.reservations USING btree
    (branch_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_reservations_enrollment_id

-- DROP INDEX IF EXISTS public.idx_reservations_enrollment_id;

CREATE INDEX IF NOT EXISTS idx_reservations_enrollment_id
    ON public.reservations USING btree
    (enrollment_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_reservations_student

-- DROP INDEX IF EXISTS public.idx_reservations_student;

CREATE INDEX IF NOT EXISTS idx_reservations_student
    ON public.reservations USING btree
    (student_user_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Table: public.student_accounts

-- DROP TABLE IF EXISTS public.student_accounts;

CREATE TABLE IF NOT EXISTS public.student_accounts
(
    account_id integer NOT NULL DEFAULT nextval('student_accounts_account_id_seq'::regclass),
    enrollment_id integer NOT NULL,
    branch_id integer NOT NULL,
    username character varying(100) COLLATE pg_catalog."default" NOT NULL,
    password character varying(255) COLLATE pg_catalog."default" NOT NULL,
    email character varying(255) COLLATE pg_catalog."default",
    is_active boolean DEFAULT true,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    require_password_change boolean DEFAULT false,
    last_password_change timestamp without time zone,
    CONSTRAINT student_accounts_pkey PRIMARY KEY (account_id),
    CONSTRAINT student_accounts_username_key UNIQUE (username),
    CONSTRAINT student_accounts_branch_id_fkey FOREIGN KEY (branch_id)
        REFERENCES public.branches (branch_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT student_accounts_enrollment_id_fkey FOREIGN KEY (enrollment_id)
        REFERENCES public.enrollments (enrollment_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.student_accounts
    OWNER to postgres;

REVOKE ALL ON TABLE public.student_accounts FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.student_accounts TO liceo_db;

GRANT ALL ON TABLE public.student_accounts TO postgres;

-- Table: public.users

-- DROP TABLE IF EXISTS public.users;

CREATE TABLE IF NOT EXISTS public.users
(
    user_id integer NOT NULL DEFAULT nextval('users_user_id_seq'::regclass),
    branch_id integer,
    username character varying(50) COLLATE pg_catalog."default" NOT NULL,
    password character varying(255) COLLATE pg_catalog."default" NOT NULL,
    role character varying(20) COLLATE pg_catalog."default",
    status character varying(10) COLLATE pg_catalog."default" DEFAULT 'active'::character varying,
    require_password_change boolean DEFAULT false,
    last_password_change timestamp without time zone,
    CONSTRAINT users_pkey PRIMARY KEY (user_id),
    CONSTRAINT users_username_key UNIQUE (username),
    CONSTRAINT users_branch_id_fkey FOREIGN KEY (branch_id)
        REFERENCES public.branches (branch_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.users
    OWNER to postgres;

REVOKE ALL ON TABLE public.users FROM liceo_db;

GRANT INSERT, DELETE, SELECT, UPDATE ON TABLE public.users TO liceo_db;

GRANT ALL ON TABLE public.users TO postgres;