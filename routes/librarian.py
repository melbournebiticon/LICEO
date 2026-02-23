from flask import Blueprint, render_template, request, redirect, session, flash, url_for, jsonify
from db import get_db_connection
import psycopg2.extras

librarian_bp = Blueprint("librarian", __name__)

GRADES = [
    "Nursery", "Kinder",
    "Grade 1", "Grade 2", "Grade 3", "Grade 4", "Grade 5", "Grade 6",
    "Grade 7", "Grade 8", "Grade 9", "Grade 10"
]

def _require_librarian():
    return session.get("role") == "librarian"


# Reuse this in SQL ORDER BY (keeps Nursery, Kinder, Grade 1..10)
GRADE_ORDER_SQL = """
CASE
    WHEN grade_level = 'Nursery' THEN 0
    WHEN grade_level = 'Kinder'  THEN 1
    WHEN grade_level = 'Grade 1' THEN 2
    WHEN grade_level = 'Grade 2' THEN 3
    WHEN grade_level = 'Grade 3' THEN 4
    WHEN grade_level = 'Grade 4' THEN 5
    WHEN grade_level = 'Grade 5' THEN 6
    WHEN grade_level = 'Grade 6' THEN 7
    WHEN grade_level = 'Grade 7' THEN 8
    WHEN grade_level = 'Grade 8' THEN 9
    WHEN grade_level = 'Grade 9' THEN 10
    WHEN grade_level = 'Grade 10' THEN 11
    ELSE 99
END
"""


@librarian_bp.route("/librarian")
def dashboard():
    if not _require_librarian():
        return redirect("/")
    return render_template("librarian_dashboard.html")


@librarian_bp.route("/librarian/books", methods=["GET"])
def books_inventory():
    if not _require_librarian():
        return redirect("/")

    branch_id = session.get("branch_id")
    if not branch_id:
        flash("No branch assigned.", "error")
        return redirect("/")

    search = (request.args.get("search") or "").strip()
    grade_filter = (request.args.get("grade") or "").strip()

    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        where = ["branch_id = %s", "is_active = TRUE", "UPPER(category) = 'BOOK'"]
        params = [branch_id]

        if grade_filter:
            where.append("grade_level = %s")
            params.append(grade_filter)

        if search:
            where.append("(item_name ILIKE %s OR COALESCE(publisher,'') ILIKE %s)")
            like = f"%{search}%"
            params.extend([like, like])

        where_sql = " AND ".join(where)

        cur.execute(f"""
            SELECT
                item_id,
                item_name AS title,
                grade_level,
                COALESCE(publisher,'') AS publisher,
                price,
                stock_total,
                reserved_qty
            FROM inventory_items
            WHERE {where_sql}
            ORDER BY
                {GRADE_ORDER_SQL},
                COALESCE(publisher,''),
                item_name
        """, params)

        items = cur.fetchall() or []

        # ---- STATS for dashboard cards / low stock alert ----
        total_items = len(items)
        total_stock = sum(int(it.get("stock_total") or 0) for it in items)
        total_reserved = sum(int(it.get("reserved_qty") or 0) for it in items)

        low_stock_count = 0
        out_stock_count = 0
        for it in items:
            available = int(it.get("stock_total") or 0) - int(it.get("reserved_qty") or 0)
            if available == 0:
                out_stock_count += 1
            elif 0 < available < 10:
                low_stock_count += 1

        stats = {
            "total_items": total_items,
            "total_stock": total_stock,
            "reserved": total_reserved,
            "low_stock": low_stock_count,
            "out_stock": out_stock_count
        }

    finally:
        cur.close()
        db.close()

    return render_template(
        "librarian_books_inventory.html",
        items=items,
        grades=GRADES,
        search=search,
        grade_filter=grade_filter,
        stats=stats
    )


@librarian_bp.route("/librarian/books/add", methods=["GET", "POST"])
def book_add():
    if not _require_librarian():
        return redirect("/")

    branch_id = session.get("branch_id")
    if not branch_id:
        flash("No branch assigned.", "error")
        return redirect("/")

    if request.method == "POST":
        grade_level = (request.form.get("grade_level") or "").strip()
        publisher = (request.form.get("publisher") or "").strip()
        title = (request.form.get("title") or "").strip()

        if not (grade_level and publisher and title):
            flash("Missing required fields.", "error")
            return redirect(url_for("librarian.book_add"))

        db = get_db_connection()
        cur = db.cursor()
        try:
            cur.execute("""
                INSERT INTO inventory_items
                    (branch_id, category, item_name, grade_level, is_common,
                     publisher, price, stock_total, reserved_qty, image_url, is_active)
                VALUES
                    (%s, 'BOOK', %s, %s, FALSE,
                     %s, 0, 0, 0, NULL, TRUE)
            """, (
                branch_id,
                title,
                grade_level,
                publisher,
            ))
            db.commit()
            flash("Book added successfully!", "success")
            return redirect(url_for("librarian.books_inventory"))
        except Exception as e:
            db.rollback()
            flash(f"Failed to add book: {e}", "error")
            return redirect(url_for("librarian.book_add"))
        finally:
            cur.close()
            db.close()

    return render_template(
        "librarian_book_form.html",
        mode="add",
        book=None,
        grades=GRADES
    )


@librarian_bp.route("/librarian/books/<int:item_id>/edit", methods=["GET", "POST"])
def book_edit(item_id):
    if not _require_librarian():
        return redirect("/")

    branch_id = session.get("branch_id")
    if not branch_id:
        flash("No branch assigned.", "error")
        return redirect("/")

    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT
                item_id,
                item_name AS title,
                grade_level,
                COALESCE(publisher,'') AS publisher,
                price,
                stock_total,
                reserved_qty
            FROM inventory_items
            WHERE item_id=%s AND branch_id=%s AND UPPER(category)='BOOK'
            LIMIT 1
        """, (item_id, branch_id))
        book = cur.fetchone()

        if not book:
            flash("Book not found.", "error")
            return redirect(url_for("librarian.books_inventory"))

        if request.method == "POST":
            grade_level = (request.form.get("grade_level") or "").strip()
            publisher = (request.form.get("publisher") or "").strip()
            title = (request.form.get("title") or "").strip()

            if not (grade_level and publisher and title):
                flash("Missing required fields.", "error")
                return redirect(url_for("librarian.book_edit", item_id=item_id))

            cur2 = db.cursor()
            try:
                cur2.execute("""
                    UPDATE inventory_items
                    SET item_name=%s, grade_level=%s, publisher=%s
                    WHERE item_id=%s AND branch_id=%s AND UPPER(category)='BOOK'
                """, (title, grade_level, publisher, item_id, branch_id))
                db.commit()
                flash("Book updated successfully!", "success")
                return redirect(url_for("librarian.books_inventory"))
            except Exception as e:
                db.rollback()
                flash(f"Failed to update book: {e}", "error")
                return redirect(url_for("librarian.book_edit", item_id=item_id))
            finally:
                cur2.close()

    finally:
        cur.close()
        db.close()

    return render_template(
        "librarian_book_form.html",
        mode="edit",
        book=book,
        grades=GRADES
    )


@librarian_bp.route("/librarian/books/<int:item_id>/restock", methods=["GET", "POST"])
def book_restock(item_id):
    if not _require_librarian():
        return redirect("/")

    branch_id = session.get("branch_id")
    if not branch_id:
        flash("No branch assigned.", "error")
        return redirect("/")

    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT
                item_id,
                item_name AS title,
                grade_level,
                COALESCE(publisher,'') AS publisher,
                price,
                stock_total,
                reserved_qty
            FROM inventory_items
            WHERE item_id=%s AND branch_id=%s AND UPPER(category)='BOOK'
            LIMIT 1
        """, (item_id, branch_id))
        book = cur.fetchone()

        if not book:
            flash("Book not found.", "error")
            return redirect(url_for("librarian.books_inventory"))

        if request.method == "POST":
            add_stock = (request.form.get("add_stock") or "").strip()

            try:
                add_val = int(add_stock)
                if add_val <= 0:
                    raise ValueError()
            except Exception:
                flash("Invalid stock quantity.", "error")
                return redirect(url_for("librarian.book_restock", item_id=item_id))

            cur2 = db.cursor()
            try:
                cur2.execute("""
                    UPDATE inventory_items
                    SET stock_total = stock_total + %s
                    WHERE item_id=%s AND branch_id=%s AND UPPER(category)='BOOK'
                """, (add_val, item_id, branch_id))
                db.commit()
                flash("Restocked successfully!", "success")
                return redirect(url_for("librarian.books_inventory"))
            except Exception as e:
                db.rollback()
                flash(f"Failed to restock: {e}", "error")
                return redirect(url_for("librarian.book_restock", item_id=item_id))
            finally:
                cur2.close()

    finally:
        cur.close()
        db.close()

    return render_template(
        "librarian_book_restock.html",
        book=book
    )


@librarian_bp.route("/librarian/api/student-grade", methods=["GET"])
def api_student_grade():
    """Get student grade and name by enrollment ID"""
    if not _require_librarian():
        return jsonify({"error": "Unauthorized"}), 401

    branch_id = session.get("branch_id")
    if not branch_id:
        return jsonify({"error": "No branch assigned"}), 400

    enrollment_id = (request.args.get("enrollment_id") or "").strip()
    if not enrollment_id or not enrollment_id.isdigit():
        return jsonify({"grade_level": None, "student_name": None}), 200

    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT enrollment_id, student_name, branch_id, grade_level
            FROM enrollments
            WHERE enrollment_id=%s
            LIMIT 1
        """, (int(enrollment_id),))
        row = cur.fetchone()

        if not row:
            return jsonify({"grade_level": None, "student_name": None}), 200

        if int(row.get("branch_id") or 0) != int(branch_id):
            return jsonify({"grade_level": None, "student_name": None}), 200

        grade_level = (row.get("grade_level") or "").strip() or None
        student_name = (row.get("student_name") or "").strip() or None

        # Normalize grade values
        if grade_level:
            grade_level = grade_level.title().replace("  ", " ")
            if grade_level in ["Kindergarten", "Kinder Garden"]:
                grade_level = "Kinder"
            if grade_level.startswith("Grade"):
                grade_level = "Grade " + grade_level.replace("Grade", "").strip()

        return jsonify({"grade_level": grade_level, "student_name": student_name}), 200

    except Exception:
        return jsonify({"grade_level": None, "student_name": None}), 200
    finally:
        cur.close()
        db.close()


@librarian_bp.route("/librarian/releases", methods=["GET", "POST"])
def releases():
    """
    Record release of books to students.
    Creates a header in book_releases, then line items in book_release_items.
    Deducts stock_total from inventory_items.
    """
    if not _require_librarian():
        return redirect("/")

    branch_id = session.get("branch_id")
    if not branch_id:
        flash("No branch assigned.", "error")
        return redirect("/")

    grade_filter = (request.args.get("grade") or "").strip()

    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Build WHERE clause for books
        book_where = "branch_id=%s AND is_active=TRUE AND UPPER(category)='BOOK'"
        book_params = [branch_id]

        if grade_filter:
            book_where += " AND grade_level=%s"
            book_params.append(grade_filter)

        # Get books for this branch/grade (properly sorted)
        cur.execute(f"""
            SELECT
                item_id,
                grade_level,
                COALESCE(publisher,'') AS publisher,
                item_name AS title,
                price
            FROM inventory_items
            WHERE {book_where}
            ORDER BY
                {GRADE_ORDER_SQL},
                COALESCE(publisher,''),
                item_name
        """, book_params)
        books = cur.fetchall() or []

        if request.method == "POST":
            enrollment_id = (request.form.get("enrollment_id") or "").strip()
            student_name = (request.form.get("student_name") or "").strip()
            item_id = (request.form.get("item_id") or "").strip()
            qty = (request.form.get("qty") or "").strip()

            if not item_id or not qty:
                flash("Please select a book and quantity.", "error")
                return redirect(url_for("librarian.releases"))

            try:
                item_id = int(item_id)
                qty = int(qty)
                if qty <= 0:
                    raise ValueError()
            except Exception:
                flash("Invalid book/qty.", "error")
                return redirect(url_for("librarian.releases"))

            # Validate enrollment (if provided)
            enrollment_row = None
            if enrollment_id:
                if not enrollment_id.isdigit():
                    flash("Enrollment ID must be a number.", "error")
                    return redirect(url_for("librarian.releases"))

                cur.execute("""
                    SELECT enrollment_id, student_name, branch_id, grade_level
                    FROM enrollments
                    WHERE enrollment_id=%s
                    LIMIT 1
                """, (int(enrollment_id),))
                enrollment_row = cur.fetchone()

                if not enrollment_row:
                    flash("Enrollment ID not found.", "error")
                    return redirect(url_for("librarian.releases"))

                if int(enrollment_row.get("branch_id") or 0) != int(branch_id):
                    flash("This enrollment is not in your branch.", "error")
                    return redirect(url_for("librarian.releases"))

            # Lock book row for update and check availability
            cur.execute("""
                SELECT stock_total, reserved_qty, item_name, price
                FROM inventory_items
                WHERE item_id=%s AND branch_id=%s AND UPPER(category)='BOOK' AND is_active=TRUE
                FOR UPDATE
            """, (item_id, branch_id))
            bookrow = cur.fetchone()
            if not bookrow:
                flash("Book not found.", "error")
                db.rollback()
                return redirect(url_for("librarian.releases"))

            available = int(bookrow["stock_total"] or 0) - int(bookrow["reserved_qty"] or 0)
            if qty > available:
                flash(f"Not enough stock for: {bookrow['item_name']}", "error")
                db.rollback()
                return redirect(url_for("librarian.releases"))

            unit_price = float(bookrow.get("price") or 0)

            # 1) Insert header (book_releases)
            cur.execute("""
                INSERT INTO book_releases
                    (branch_id, enrollment_id, student_name, released_by_user_id)
                VALUES
                    (%s, %s, %s, %s)
                RETURNING release_id
            """, (
                branch_id,
                enrollment_row["enrollment_id"] if enrollment_row else None,
                (enrollment_row["student_name"] if enrollment_row else student_name) or None,
                session.get("user_id")
            ))
            release_id = cur.fetchone()["release_id"]

            # 2) Insert item line (book_release_items)
            cur.execute("""
                INSERT INTO book_release_items
                    (release_id, item_id, qty, unit_price)
                VALUES
                    (%s, %s, %s, %s)
            """, (release_id, item_id, qty, unit_price))

            # 3) Deduct stock_total
            cur.execute("""
                UPDATE inventory_items
                SET stock_total = stock_total - %s
                WHERE item_id=%s AND branch_id=%s AND UPPER(category)='BOOK'
            """, (qty, item_id, branch_id))

            db.commit()
            flash("Release recorded successfully!", "success")
            return redirect(url_for("librarian.releases"))

        # Get recent releases (include student_grade for UI filter)
        cur.execute(f"""
            SELECT
                br.release_id,
                br.created_at,
                br.enrollment_id,
                br.student_name,
                e.grade_level AS student_grade,
                bri.qty,
                bri.unit_price,
                (ii.grade_level || ' — ' || COALESCE(ii.publisher,'') || ' | ' || ii.item_name) AS book_display
            FROM book_releases br
            JOIN book_release_items bri ON bri.release_id = br.release_id
            JOIN inventory_items ii     ON ii.item_id = bri.item_id
            LEFT JOIN enrollments e     ON e.enrollment_id = br.enrollment_id
            WHERE br.branch_id = %s
            ORDER BY br.created_at DESC
            LIMIT 50
        """, (branch_id,))
        releases_rows = cur.fetchall() or []

    except Exception as e:
        db.rollback()
        flash(f"Error: {e}", "error")
        books = []
        releases_rows = []
    finally:
        cur.close()
        db.close()

    return render_template(
        "librarian_releases.html",
        books=books,
        releases=releases_rows,
        grades=GRADES,
        grade_filter=grade_filter
    )


@librarian_bp.route("/librarian/books/<int:item_id>/price", methods=["GET", "POST"])
def book_price(item_id):
    if not _require_librarian():
        return redirect("/")

    branch_id = session.get("branch_id")
    if not branch_id:
        flash("No branch assigned.", "error")
        return redirect("/")

    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("""
            SELECT
                item_id,
                item_name AS title,
                grade_level,
                COALESCE(publisher,'') AS publisher,
                price,
                stock_total,
                reserved_qty
            FROM inventory_items
            WHERE item_id=%s AND branch_id=%s AND UPPER(category)='BOOK' AND is_active=TRUE
            LIMIT 1
        """, (item_id, branch_id))
        book = cur.fetchone()

        if not book:
            flash("Book not found.", "error")
            return redirect(url_for("librarian.books_inventory"))

        if request.method == "POST":
            new_price = (request.form.get("new_price") or "").strip()
            try:
                new_price_val = float(new_price)
                if new_price_val <= 0:
                    raise ValueError()
            except Exception:
                flash("Invalid price.", "error")
                return redirect(url_for("librarian.book_price", item_id=item_id))

            cur2 = db.cursor()
            try:
                cur2.execute("""
                    UPDATE inventory_items
                    SET price=%s
                    WHERE item_id=%s AND branch_id=%s AND UPPER(category)='BOOK'
                """, (new_price_val, item_id, branch_id))
                db.commit()
                flash("Price updated successfully!", "success")
                return redirect(url_for("librarian.books_inventory"))
            except Exception as e:
                db.rollback()
                flash(f"Failed to update price: {e}", "error")
                return redirect(url_for("librarian.book_price", item_id=item_id))
            finally:
                cur2.close()

    finally:
        cur.close()
        db.close()

    return render_template("librarian_book_price.html", book=book)