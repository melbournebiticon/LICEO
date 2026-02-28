from flask import Blueprint, render_template, request, redirect, session, flash, url_for, jsonify
from db import get_db_connection, is_branch_active
from datetime import datetime, date
from decimal import Decimal
import secrets
import psycopg2.extras

cashier_bp = Blueprint("cashier", __name__)

def generate_receipt_number():
    """Generate unique receipt number: OR-YYYYMMDD-XXXXX"""
    today = datetime.now().strftime("%Y%m%d")
    random_part = secrets.token_hex(3).upper()  # 6 character hex
    return f"OR-{today}-{random_part}"


def _require_cashier():
    return session.get("role") == "cashier"


@cashier_bp.route("/cashier")
def dashboard():
    if not _require_cashier():
        return redirect("/")
    if not session.get("branch_id"):
        flash("No branch assigned. Please contact admin.", "error")
        return redirect(url_for("auth.login"))

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT e.*, b.bill_id, b.balance, b.status AS bill_status
            FROM enrollments e
            LEFT JOIN billing b
              ON e.enrollment_id = b.enrollment_id
             AND b.branch_id = %s
            WHERE e.branch_id = %s AND e.status = 'approved'
            ORDER BY
              CASE
                WHEN b.bill_id IS NULL THEN 0
                WHEN b.status = 'pending' THEN 1
                WHEN b.status = 'partial' THEN 2
                ELSE 3
              END,
              e.created_at DESC
        """, (session.get("branch_id"), session.get("branch_id")))
        enrollments = cursor.fetchall()

        cursor.execute("""
            SELECT
              COUNT(*) AS payment_count,
              COALESCE(SUM(amount), 0) AS total_collected
            FROM payments
            WHERE payment_date::date = %s
              AND branch_id = %s
              AND received_by = %s
        """, (date.today(), session.get("branch_id"), session.get("user_id")))
        today_summary = cursor.fetchone() or {"payment_count": 0, "total_collected": 0}

        cursor.execute("""
            SELECT COUNT(*) AS pending_count
            FROM billing b
            JOIN enrollments e ON b.enrollment_id = e.enrollment_id
            WHERE e.branch_id = %s
              AND b.status IN ('pending', 'partial')
        """, (session.get("branch_id"),))
        pending_info = cursor.fetchone() or {"pending_count": 0}

        return render_template(
            "cashier_dashboard.html",
            enrollments=enrollments,
            today_summary=today_summary,
            pending_count=pending_info["pending_count"]
        )
    finally:
        cursor.close()
        db.close()


@cashier_bp.route("/cashier/create-bill/<int:enrollment_id>", methods=["GET", "POST"])
def create_bill(enrollment_id):
    if not _require_cashier():
        return redirect("/")

    if not is_branch_active(session.get("branch_id")):
        flash("This branch is currently deactivated. New billing records are not allowed.", "error")
        return redirect(url_for("cashier.dashboard"))

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT e.*, b.branch_name
            FROM enrollments e
            JOIN branches b ON e.branch_id = b.branch_id
            WHERE e.enrollment_id = %s AND e.branch_id = %s
        """, (enrollment_id, session.get("branch_id")))
        enrollment = cursor.fetchone()

        if not enrollment:
            flash("Enrollment not found", "error")
            return redirect("/cashier")

        cursor.execute("""SELECT * FROM billing WHERE enrollment_id = %s""", (enrollment_id,))
        existing_bill = cursor.fetchone()

        if existing_bill:
            flash("Bill already exists for this enrollment", "warning")
            return redirect(url_for("cashier.view_bill", bill_id=existing_bill["bill_id"]))

        cursor.execute("SELECT * FROM enrollment_books WHERE enrollment_id = %s", (enrollment_id,))
        books = cursor.fetchall()

        cursor.execute("SELECT * FROM enrollment_uniforms WHERE enrollment_id = %s", (enrollment_id,))
        uniforms = cursor.fetchall()

        if request.method == "POST":
            tuition_fee = Decimal(request.form.get("tuition_fee", "0") or "0")
            books_fee = Decimal(request.form.get("books_fee", "0") or "0")
            uniform_fee = Decimal(request.form.get("uniform_fee", "0") or "0")
            other_fees = Decimal(request.form.get("other_fees", "0") or "0")

            total_amount = tuition_fee + books_fee + uniform_fee + other_fees

            try:
                cursor.execute("""
                    INSERT INTO billing
                      (enrollment_id, branch_id, tuition_fee, books_fee, uniform_fee, other_fees,
                       total_amount, amount_paid, balance, status, created_by)
                    VALUES
                      (%s, %s, %s, %s, %s, %s,
                       %s, %s, %s, 'pending', %s)
                    RETURNING bill_id
                """, (
                    enrollment_id,
                    session.get("branch_id"),
                    tuition_fee, books_fee, uniform_fee, other_fees,
                    total_amount,
                    Decimal("0"),
                    total_amount,
                    session.get("user_id"),
                ))
                bill_id = cursor.fetchone()["bill_id"]
                db.commit()

                flash(f"Bill created successfully! Total: ₱{total_amount:,.2f}", "success")
                return redirect(url_for("cashier.view_bill", bill_id=bill_id))

            except Exception as e:
                db.rollback()
                flash(f"Failed to create bill: {str(e)}", "error")

        return render_template(
            "cashier_create_bill.html",
            enrollment=enrollment,
            books=books,
            uniforms=uniforms
        )
    finally:
        cursor.close()
        db.close()


@cashier_bp.route("/cashier/bill/<int:bill_id>")
def view_bill(bill_id):
    if not _require_cashier():
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT b.*, e.student_name, e.grade_level, e.guardian_name,
                   br.branch_name, u.username AS created_by_name
            FROM billing b
            JOIN enrollments e ON b.enrollment_id = e.enrollment_id
            JOIN branches br ON e.branch_id = br.branch_id
            JOIN users u ON b.created_by = u.user_id
            WHERE b.bill_id = %s AND e.branch_id = %s
        """, (bill_id, session.get("branch_id")))
        bill = cursor.fetchone()

        if not bill:
            flash("Bill not found", "error")
            return redirect("/cashier")

        cursor.execute("""
            SELECT p.*, u.username AS received_by_name
            FROM payments p
            JOIN users u ON p.received_by = u.user_id
            WHERE p.bill_id = %s
            ORDER BY p.payment_date DESC
        """, (bill_id,))
        payments = cursor.fetchall()

        return render_template("cashier_view_bill.html", bill=bill, payments=payments)
    finally:
        cursor.close()
        db.close()


@cashier_bp.route("/cashier/process-payment/<int:bill_id>", methods=["GET", "POST"])
def process_payment(bill_id):
    if not _require_cashier():
        return redirect("/")

    if not is_branch_active(session.get("branch_id")):
        flash("This branch is currently deactivated. New payments are not allowed.", "error")
        return redirect(url_for("cashier.view_bill", bill_id=bill_id))

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT b.*, e.student_name, e.grade_level
            FROM billing b
            JOIN enrollments e ON b.enrollment_id = e.enrollment_id
            WHERE b.bill_id = %s AND e.branch_id = %s
        """, (bill_id, session.get("branch_id")))
        bill = cursor.fetchone()

        if not bill:
            flash("Bill not found", "error")
            return redirect("/cashier")

        if bill["status"] == "paid":
            flash("This bill is already fully paid", "info")
            return redirect(url_for("cashier.view_bill", bill_id=bill_id))

        if request.method == "POST":
            amount = Decimal(request.form.get("amount", "0") or "0")
            payment_method = request.form.get("payment_method", "cash")
            notes = request.form.get("notes", "")

            if amount <= 0:
                flash("Payment amount must be greater than zero", "error")
            elif amount > Decimal(str(bill["balance"])):
                flash(
                    f"Payment amount (₱{amount:,.2f}) exceeds balance (₱{Decimal(str(bill['balance'])):,.2f})",
                    "error"
                )
            else:
                try:
                    receipt_number = generate_receipt_number()

                    cursor.execute("""
                        INSERT INTO payments
                          (bill_id, enrollment_id, branch_id, amount, payment_method,
                           receipt_number, notes, received_by)
                        VALUES
                          (%s, %s, %s, %s, %s,
                           %s, %s, %s)
                        RETURNING payment_id
                    """, (
                        bill_id,
                        bill["enrollment_id"],
                        session.get("branch_id"),
                        amount,
                        payment_method,
                        receipt_number,
                        notes,
                        session.get("user_id"),
                    ))
                    payment_id = cursor.fetchone()["payment_id"]

                    amount_paid_now = Decimal(str(bill.get("amount_paid", 0)))
                    total_amount = Decimal(str(bill.get("total_amount", 0)))

                    new_amount_paid = amount_paid_now + amount
                    new_balance = total_amount - new_amount_paid
                    if new_balance < 0:
                        new_balance = Decimal("0")

                    new_status = "paid" if new_balance == 0 else "partial"

                    cursor.execute("""
                        UPDATE billing
                        SET amount_paid = %s, balance = %s, status = %s
                        WHERE bill_id = %s
                    """, (new_amount_paid, new_balance, new_status, bill_id))

                    db.commit()

                    flash(f"Payment recorded successfully! Receipt: {receipt_number}", "success")
                    return redirect(url_for("cashier.print_receipt", payment_id=payment_id))

                except Exception as e:
                    db.rollback()
                    flash(f"Failed to process payment: {str(e)}", "error")

        return render_template("cashier_process_payment.html", bill=bill)
    finally:
        cursor.close()
        db.close()


@cashier_bp.route("/cashier/receipt/<int:payment_id>")
def print_receipt(payment_id):
    if not _require_cashier():
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT p.*,
                   e.student_name, e.grade_level, e.guardian_name,
                   b.total_amount, b.amount_paid, b.balance,
                   br.branch_name, br.location,
                   u.username AS received_by_name
            FROM payments p
            JOIN billing b ON p.bill_id = b.bill_id
            JOIN enrollments e ON p.enrollment_id = e.enrollment_id
            JOIN branches br ON e.branch_id = br.branch_id
            JOIN users u ON p.received_by = u.user_id
            WHERE p.payment_id = %s
        """, (payment_id,))
        payment = cursor.fetchone()

        if not payment:
            flash("Receipt not found", "error")
            return redirect("/cashier")

        return render_template("cashier_receipt.html", payment=payment)
    finally:
        cursor.close()
        db.close()


@cashier_bp.route("/cashier/reports", methods=["GET", "POST"])
def reports():
    if not _require_cashier():
        return redirect("/")

    report_date = request.form.get("report_date", date.today().strftime("%Y-%m-%d"))

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT
              p.payment_id,
              p.receipt_number,
              p.amount,
              p.payment_method,
              p.payment_date,
              e.student_name,
              e.grade_level,
              u.username AS received_by_name
            FROM payments p
            JOIN enrollments e ON p.enrollment_id = e.enrollment_id
            JOIN users u ON p.received_by = u.user_id
            WHERE p.payment_date::date = %s
              AND e.branch_id = %s
            ORDER BY p.payment_date DESC
        """, (report_date, session.get("branch_id")))
        payments = cursor.fetchall()

        cursor.execute("""
            SELECT
              COUNT(*) AS transaction_count,
              COALESCE(SUM(p.amount), 0) AS total_collected
            FROM payments p
            JOIN enrollments e ON p.enrollment_id = e.enrollment_id
            WHERE p.payment_date::date = %s
              AND e.branch_id = %s
        """, (report_date, session.get("branch_id")))
        summary = cursor.fetchone() or {"transaction_count": 0, "total_collected": 0}

        return render_template(
            "cashier_reports.html",
            payments=payments,
            summary=summary,
            report_date=report_date
        )
    finally:
        cursor.close()
        db.close()


@cashier_bp.route("/cashier/search", methods=["GET", "POST"])
def search():
    if not _require_cashier():
        return redirect("/")

    results = []
    search_query = ""

    if request.method == "POST":
        search_query = request.form.get("search_query", "").strip()

        if search_query:
            db = get_db_connection()
            cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            try:
                is_numeric = search_query.isdigit()

                cursor.execute("""
                    SELECT e.*, b.bill_id, b.balance, b.status AS bill_status,
                           b.total_amount, b.amount_paid
                    FROM enrollments e
                    LEFT JOIN billing b ON e.enrollment_id = b.enrollment_id
                    WHERE e.branch_id = %s
                      AND (
                        (%s AND e.enrollment_id = %s)
                        OR (e.student_name ILIKE %s)
                      )
                    ORDER BY e.created_at DESC
                """, (
                    session.get("branch_id"),
                    is_numeric,
                    int(search_query) if is_numeric else 0,
                    f"%{search_query}%"
                ))

                results = cursor.fetchall()
            finally:
                cursor.close()
                db.close()

    return render_template("cashier_search.html", results=results, search_query=search_query)


# =======================
# CASHIER RESERVATIONS (NO students TABLE)
# =======================

def _normalize_category(raw: str | None) -> str | None:
    if not raw:
        return None
    c = raw.strip().upper()
    # keep it strict to what you support in UI
    if c in ("UNIFORM", "BOOK"):
        return c
    return None


@cashier_bp.route("/cashier/reservations")
def cashier_reservations():
    if not _require_cashier():
        return redirect(url_for("auth.login"))

    branch_id = session.get("branch_id")
    conn = get_db_connection()
    cur = None
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                r.reservation_id,          -- 0
                COALESCE(u.username, '') AS username,   -- 1
                r.student_user_id,         -- 2
                r.student_grade_level,     -- 3
                COALESCE(
                    e.student_name,
                    svp.student_name,
                    u.username,
                    ''
                ) AS full_name,            -- 4
                COALESCE(r.student_grade_level, svp.grade_level) AS grade_level, -- 5
                NULL AS strand,            -- 6
                r.status,                  -- 7
                r.created_at,              -- 8
                CASE
                  WHEN r.reserved_by_user_id IS NOT NULL
                       AND reserved_by.role = 'parent'
                  THEN 'parent'
                  ELSE 'student'
                END AS reserved_by_role,   -- 9
                CASE
                  WHEN r.reserved_by_user_id IS NOT NULL
                       AND reserved_by.role = 'parent'
                  THEN COALESCE(
                    svp.guardian_name,
                    reserved_by.username
                  )
                  ELSE NULL
                END AS parent_name,        -- 10
                svp.relationship           -- 11
            FROM reservations r
            LEFT JOIN users u ON u.user_id = r.student_user_id
            LEFT JOIN student_accounts sa ON sa.username = u.username
            LEFT JOIN enrollments e ON e.enrollment_id = sa.enrollment_id
            LEFT JOIN users reserved_by ON reserved_by.user_id = r.reserved_by_user_id
            LEFT JOIN LATERAL (
                SELECT
                    e2.student_name,
                    e2.grade_level,
                    e2.guardian_name,
                    ps2.relationship
                FROM parent_student ps2
                JOIN enrollments e2 ON e2.enrollment_id = ps2.student_id
                WHERE ps2.parent_id = r.reserved_by_user_id
                ORDER BY ps2.student_id
                LIMIT 1
            ) svp ON (reserved_by.role = 'parent')
            WHERE r.branch_id = %s
            ORDER BY r.created_at DESC
        """, (branch_id,))
        rows = cur.fetchall() or []
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()

    return render_template("cashier_reservations.html", rows=rows)


@cashier_bp.route("/cashier/reservations/<int:reservation_id>")
def cashier_reservation_view(reservation_id):
    if not _require_cashier():
        return redirect(url_for("auth.login"))

    branch_id = session.get("branch_id")
    conn = get_db_connection()
    cur = None
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                r.reservation_id,
                COALESCE(u.username, '') AS username,
                r.student_user_id,
                r.student_grade_level,
                COALESCE(
                    e.student_name,
                    svp.student_name,
                    u.username,
                    ''
                ) AS full_name,
                COALESCE(r.student_grade_level, svp.grade_level) AS grade_level,
                NULL AS strand,
                r.status,
                r.created_at,
                CASE
                  WHEN r.reserved_by_user_id IS NOT NULL
                       AND reserved_by.role = 'parent'
                  THEN 'parent'
                  ELSE 'student'
                END AS reserved_by_role,
                CASE
                  WHEN r.reserved_by_user_id IS NOT NULL
                       AND reserved_by.role = 'parent'
                  THEN COALESCE(
                    svp.guardian_name,
                    reserved_by.username
                  )
                  ELSE NULL
                END AS parent_name,
                svp.relationship
            FROM reservations r
            LEFT JOIN users u ON u.user_id = r.student_user_id
            LEFT JOIN student_accounts sa ON sa.username = u.username
            LEFT JOIN enrollments e ON e.enrollment_id = sa.enrollment_id
            LEFT JOIN users reserved_by ON reserved_by.user_id = r.reserved_by_user_id
            LEFT JOIN LATERAL (
                SELECT
                    e2.student_name,
                    e2.grade_level,
                    e2.guardian_name,
                    ps2.relationship
                FROM parent_student ps2
                JOIN enrollments e2 ON e2.enrollment_id = ps2.student_id
                WHERE ps2.parent_id = r.reserved_by_user_id
                ORDER BY ps2.student_id
                LIMIT 1
            ) svp ON (reserved_by.role = 'parent')
            WHERE r.reservation_id = %s AND r.branch_id = %s
            LIMIT 1
        """, (reservation_id, branch_id))
        header = cur.fetchone()
        if not header:
            return render_template("template_missing.html", missing="Reservation not found")

        # 1) Get available categories for this reservation (so UI can show BOOK + UNIFORM)
        cur.execute("""
            SELECT DISTINCT ii.category
            FROM reservation_items ri
            JOIN inventory_items ii ON ii.item_id = ri.item_id
            WHERE ri.reservation_id = %s
            ORDER BY ii.category
        """, (reservation_id,))
        categories = [row[0] for row in (cur.fetchall() or []) if row and row[0]]

        # 2) Determine selected category (default UNIFORM if present)
        selected_category = _normalize_category(request.args.get("category"))
        if not selected_category:
            if "UNIFORM" in categories:
                selected_category = "UNIFORM"
            elif categories:
                # fallback to first available category in DB
                selected_category = str(categories[0]).upper()
            else:
                selected_category = None

        # 3) Compute grand total (ALL categories)
        cur.execute("""
            SELECT COALESCE(SUM(ri.line_total), 0)
            FROM reservation_items ri
            WHERE ri.reservation_id = %s
        """, (reservation_id,))
        grand_total = cur.fetchone()[0] or 0

        # 4) Fetch items (filtered by selected_category, like your UI tabs/filter)
        if selected_category:
            cur.execute("""
                SELECT ii.item_name, ri.qty,
                       COALESCE(NULLIF(TRIM(ri.size_label), ''), ii.publisher, ii.size_label) AS display_label,
                       ri.unit_price, ri.line_total, ii.category
                FROM reservation_items ri
                JOIN inventory_items ii ON ii.item_id = ri.item_id
                WHERE ri.reservation_id = %s
                  AND UPPER(ii.category) = %s
                ORDER BY ii.item_name
            """, (reservation_id, selected_category))
        else:
            # no items / no category
            cur.execute("""
                SELECT ii.item_name, ri.qty,
                       COALESCE(NULLIF(TRIM(ri.size_label), ''), ii.publisher, ii.size_label) AS display_label,
                       ri.unit_price, ri.line_total, ii.category
                FROM reservation_items ri
                JOIN inventory_items ii ON ii.item_id = ri.item_id
                WHERE ri.reservation_id = %s
                ORDER BY ii.category, ii.item_name
            """, (reservation_id,))

        items = cur.fetchall() or []
        total = sum(item[4] for item in items)  # filtered total (based on selected_category)

    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()

    return render_template(
        "cashier_reservation_view.html",
        header=header,
        items=items,
        total=total,                 # filtered total
        grand_total=grand_total,     # total for ALL items
        categories=categories,       # ['BOOK','UNIFORM', ...]
        selected_category=selected_category
    )


@cashier_bp.route("/cashier/reservations/<int:reservation_id>/mark-paid", methods=["POST"])
def cashier_mark_paid(reservation_id):
    if not _require_cashier():
        return redirect(url_for("auth.login"))

    branch_id = session.get("branch_id")
    if not is_branch_active(branch_id):
        flash("This branch is currently deactivated. Changes to reservations are not allowed.", "error")
        return redirect(url_for("cashier.cashier_reservation_view", reservation_id=reservation_id))
    conn = get_db_connection()
    cur = None
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE reservations
            SET status = 'PAID', paid_at = NOW()
            WHERE reservation_id = %s AND branch_id = %s AND status = 'RESERVED'
        """, (reservation_id, branch_id))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()

    return redirect(url_for("cashier.cashier_reservation_view", reservation_id=reservation_id))


@cashier_bp.route("/cashier/reservations/<int:reservation_id>/mark-claimed", methods=["POST"])
def cashier_mark_claimed(reservation_id):
    if not _require_cashier():
        return redirect(url_for("auth.login"))

    branch_id = session.get("branch_id")
    if not is_branch_active(branch_id):
        flash("This branch is currently deactivated. Changes to reservations are not allowed.", "error")
        return redirect(url_for("cashier.cashier_reservation_view", reservation_id=reservation_id))
    conn = get_db_connection()
    cur = None
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT status
            FROM reservations
            WHERE reservation_id = %s AND branch_id = %s
            FOR UPDATE
        """, (reservation_id, branch_id))
        r = cur.fetchone()
        if not r:
            raise Exception("Reservation not found.")
        if r[0] not in ("PAID", "RESERVED"):
            raise Exception("Reservation must be RESERVED or PAID.")

        cur.execute("SELECT item_id, qty FROM reservation_items WHERE reservation_id = %s", (reservation_id,))
        lines = cur.fetchall() or []

        for item_id, qty in lines:
            cur.execute("""
                SELECT stock_total, reserved_qty
                FROM inventory_items
                WHERE item_id = %s AND branch_id = %s
                FOR UPDATE
            """, (item_id, branch_id))
            it = cur.fetchone()
            if not it:
                raise Exception("Item not found.")

            stock_total, reserved_qty = int(it[0] or 0), int(it[1] or 0)

            if qty > reserved_qty or qty > stock_total:
                raise Exception("Stock mismatch.")

            # ✅ FIX: include branch_id in WHERE to avoid updating other branches
            cur.execute("""
                UPDATE inventory_items
                SET stock_total = stock_total - %s,
                    reserved_qty = reserved_qty - %s
                WHERE item_id = %s AND branch_id = %s
            """, (qty, qty, item_id, branch_id))

        cur.execute("""
            UPDATE reservations
            SET status = 'CLAIMED', claimed_at = NOW()
            WHERE reservation_id = %s AND branch_id = %s
        """, (reservation_id, branch_id))

        conn.commit()

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()

    return redirect(url_for("cashier.cashier_reservation_view", reservation_id=reservation_id))


@cashier_bp.route("/cashier/reservations/<int:reservation_id>/cancel", methods=["POST"])
def cashier_cancel_reservation(reservation_id):
    if not _require_cashier():
        return redirect(url_for("auth.login"))

    branch_id = session.get("branch_id")
    if not is_branch_active(branch_id):
        flash("This branch is currently deactivated. Changes to reservations are not allowed.", "error")
        return redirect(url_for("cashier.cashier_reservation_view", reservation_id=reservation_id))
    conn = get_db_connection()
    cur = None
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT status
            FROM reservations
            WHERE reservation_id = %s AND branch_id = %s
            FOR UPDATE
        """, (reservation_id, branch_id))
        r = cur.fetchone()
        if not r:
            raise Exception("Reservation not found.")
        if r[0] != "RESERVED":
            raise Exception("Only RESERVED can be cancelled.")

        cur.execute("SELECT item_id, qty FROM reservation_items WHERE reservation_id = %s", (reservation_id,))
        lines = cur.fetchall() or []

        for item_id, qty in lines:
            cur.execute("""
                UPDATE inventory_items
                SET reserved_qty = GREATEST(reserved_qty - %s, 0)
                WHERE item_id = %s AND branch_id = %s
            """, (qty, item_id, branch_id))

        cur.execute("""
            UPDATE reservations
            SET status = 'CANCELLED', cancelled_at = NOW()
            WHERE reservation_id = %s AND branch_id = %s
        """, (reservation_id, branch_id))

        conn.commit()

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()

    return redirect(url_for("cashier.cashier_reservation_view", reservation_id=reservation_id))


@cashier_bp.route("/cashier/reservations/<int:reservation_id>/receipt")
def reservation_receipt(reservation_id):
    if not _require_cashier():
        return redirect(url_for("auth.login"))

    branch_id = session.get("branch_id")
    conn = get_db_connection()
    cur = None
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                r.reservation_id,                       -- 0
                COALESCE(u.username, '') AS username,   -- 1
                r.student_grade_level,                  -- 2
                r.status,                               -- 3
                r.created_at,                           -- 4
                r.claimed_at,                           -- 5
                b.branch_name,                          -- 6
                CASE
                  WHEN r.reserved_by_user_id IS NOT NULL
                       AND reserved_by.role = 'parent'
                  THEN 'parent'
                  ELSE 'student'
                END AS reserved_by_role,                -- 7
                CASE
                  WHEN r.reserved_by_user_id IS NOT NULL
                       AND reserved_by.role = 'parent'
                  THEN COALESCE(svp.guardian_name, reserved_by.username)
                  ELSE NULL
                END AS parent_name,                     -- 8
                svp.relationship,                       -- 9
                COALESCE(e.student_name, svp.student_name, u.username, '') AS student_name -- 10
            FROM reservations r
            LEFT JOIN users u ON u.user_id = r.student_user_id
            LEFT JOIN student_accounts sa ON sa.username = u.username
            LEFT JOIN enrollments e ON e.enrollment_id = sa.enrollment_id
            LEFT JOIN branches b ON b.branch_id = r.branch_id
            LEFT JOIN users reserved_by ON reserved_by.user_id = r.reserved_by_user_id
            LEFT JOIN LATERAL (
                SELECT
                    e2.student_name,
                    e2.grade_level,
                    e2.guardian_name,
                    ps2.relationship
                FROM parent_student ps2
                JOIN enrollments e2 ON e2.enrollment_id = ps2.student_id
                WHERE ps2.parent_id = r.reserved_by_user_id
                ORDER BY ps2.student_id
                LIMIT 1
            ) svp ON (reserved_by.role = 'parent')
            WHERE r.reservation_id = %s AND r.branch_id = %s
            LIMIT 1
        """, (reservation_id, branch_id))
        header = cur.fetchone()

        if not header:
            return render_template("template_missing.html", missing="Receipt not found"), 404

        # NOTE: status is header[3]
        if header[3] != "CLAIMED":
            return render_template("template_missing.html", missing="Receipt only for claimed"), 403

        cur.execute("""
            SELECT ii.item_name, ri.qty,
                   COALESCE(NULLIF(TRIM(ri.size_label), ''), ii.publisher, ii.size_label) AS display_label,
                   ri.unit_price, ri.line_total, ii.category
            FROM reservation_items ri
            JOIN inventory_items ii ON ii.item_id = ri.item_id
            WHERE ri.reservation_id = %s
            ORDER BY ii.category, ii.item_name
        """, (reservation_id,))
        items = cur.fetchall() or []

        total = sum(item[4] for item in items)

        return render_template("reservation_receipt.html", header=header, items=items, total=total, now=datetime.now)
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()
        
@cashier_bp.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response