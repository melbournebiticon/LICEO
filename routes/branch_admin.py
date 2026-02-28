from flask import Blueprint, render_template, request, session, redirect, flash, url_for
from db import get_db_connection
from werkzeug.security import generate_password_hash
import random
import re
import psycopg2.extras

branch_admin_bp = Blueprint("branch_admin", __name__)

# =======================
# GRADE RANGE MAPPINGS (for inventory grade filter / display)
# =======================
GRADE_MAPPINGS = {
    'Pre-Elementary Boys Set': ['Kinder', 'Grade 1', 'Grade 2', 'Grade 3'],
    'Pre-Elementary Girls Set': ['Kinder', 'Grade 1', 'Grade 2', 'Grade 3', 'Grade 4', 'Grade 5', 'Grade 6'],
    'Elementary G4-6 Boys Set': ['Grade 4', 'Grade 5', 'Grade 6'],
    'JHS Boys Uniform Set': ['Grade 7', 'Grade 8', 'Grade 9', 'Grade 10'],
    'JHS Girls Uniform Set': ['Grade 7', 'Grade 8', 'Grade 9', 'Grade 10'],
    'SHS Boys Uniform Set': ['Grade 11', 'Grade 12'],
    'SHS Girls Uniform Set': ['Grade 11', 'Grade 12'],
    'PE Uniform': ['Kinder'] + [f'Grade {i}' for i in range(1, 13)],
}

SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL"]  # xs to double XL


def get_grade_display(item_name, stored_grade):
    if item_name in GRADE_MAPPINGS:
        grades = GRADE_MAPPINGS[item_name]
        if len(grades) > 3:
            return f"{grades[0]} - {grades[-1]}"
        return ", ".join(grades)
    return stored_grade or "All"


def item_matches_grade_filter(item_name, stored_grade, grade_filter):
    if not grade_filter:
        return True
    if item_name in GRADE_MAPPINGS:
        return grade_filter in GRADE_MAPPINGS[item_name]
    return stored_grade == grade_filter or stored_grade is None


def get_grade_order(grade_level):
    if not grade_level:
        return 999
    grade_str = str(grade_level).strip().lower()
    if 'nursery' in grade_str:
        return -1
    if 'kinder' in grade_str or 'pre' in grade_str:
        return 0
    match = re.search(r'(\d+)', grade_str)
    if match:
        return int(match.group(1))
    return 999


# =======================
# SIZE HELPERS (inventory_item_sizes table)
# =======================
def size_sort_key(size_label: str) -> int:
    if not size_label:
        return 999
    s = str(size_label).strip().upper()
    return SIZE_ORDER.index(s) if s in SIZE_ORDER else 998


def ensure_default_sizes_exist(cursor, item_id: int):
    """
    Create default size rows (XS-XXL) if none exist for item_id.
    Assumes table name: inventory_item_sizes
      columns: size_id, item_id, size_label, stock_total, reserved_qty
    """
    cursor.execute("""
        SELECT COUNT(*)
        FROM inventory_item_sizes
        WHERE item_id = %s
    """, (item_id,))
    cnt = cursor.fetchone()[0] or 0

    if cnt > 0:
        return False  # already exists

    for sz in SIZE_ORDER:
        cursor.execute("""
            INSERT INTO inventory_item_sizes (item_id, size_label, stock_total, reserved_qty)
            VALUES (%s, %s, 0, 0)
        """, (item_id, sz))
    return True


def recompute_item_totals_from_sizes(cursor, item_id: int, branch_id: int):
    """
    Updates inventory_items.stock_total and inventory_items.reserved_qty based on sizes table totals.
    """
    cursor.execute("""
        UPDATE inventory_items
        SET
            stock_total = COALESCE((
                SELECT SUM(stock_total) FROM inventory_item_sizes WHERE item_id = %s
            ), 0),
            reserved_qty = COALESCE((
                SELECT SUM(reserved_qty) FROM inventory_item_sizes WHERE item_id = %s
            ), 0)
        WHERE item_id = %s AND branch_id = %s
    """, (item_id, item_id, item_id, branch_id))


# =======================
# BRANCH ADMIN DASHBOARD (UPDATED: allow librarian)
# =======================
@branch_admin_bp.route("/branch-admin", methods=["GET", "POST"])
def dashboard():
    if session.get("role") != "branch_admin":
        return redirect("/")
    if not session.get("branch_id"):
        flash("No branch assigned. Please contact admin.", "error")
        return redirect(url_for("auth.login"))

    created_user = None
    announcements_list = []

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Load announcements for THIS branch only
        cursor.execute("""
            SELECT announcement_id AS id, title, message, created_at, is_active,
                   image_url, branch_id
            FROM announcements
            WHERE branch_id = %s
            ORDER BY created_at DESC
        """, (session.get("branch_id"),))
        announcements_list = cursor.fetchall() or []
    except Exception:
        pass
    finally:
        cursor.close()
        db.close()

    if request.method == "POST":
        # Form: Add Homepage Announcement
        if request.form.get("add_announcement") == "1":
            title   = (request.form.get("announcement_title")   or "").strip()
            message = (request.form.get("announcement_message") or "").strip()
            if title:
                # ── Handle optional photo upload ──
                image_url = None
                photo = request.files.get("announcement_photo")
                if photo and photo.filename:
                    import uuid as _uuid
                    from werkzeug.utils import secure_filename as _sfn
                    ALLOWED = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    ext = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else ''
                    if ext in ALLOWED:
                        import os as _os
                        fname  = f"{_uuid.uuid4().hex}.{ext}"
                        folder = _os.path.join("uploads", "announcements")
                        _os.makedirs(folder, exist_ok=True)
                        photo.save(_os.path.join(folder, fname))
                        image_url = f"/uploads/announcements/{fname}"
                    else:
                        flash("Photo must be PNG, JPG, GIF, or WEBP.", "warning")

                db = get_db_connection()
                cur = db.cursor()
                try:
                    cur.execute("""
                        INSERT INTO announcements (title, message, is_active, image_url, branch_id)
                        VALUES (%s, %s, TRUE, %s, %s)
                    """, (title, message, image_url, session.get("branch_id")))
                    db.commit()
                    flash("Announcement added to homepage!", "success")
                except Exception as e:
                    db.rollback()
                    flash(f"Could not add announcement: {str(e)}", "error")
                finally:
                    cur.close()
                    db.close()
            else:
                flash("Announcement title is required.", "error")
            return redirect(url_for("branch_admin.dashboard"))

        # Form: Create User
        role = (request.form.get("role") or "").strip()
        base_username = (request.form.get("username") or "").strip()
        grade_level = (request.form.get("grade_level") or "").strip()
        full_name   = (request.form.get("full_name")   or "").strip()
        gender      = (request.form.get("gender")      or "").strip().lower()

        if role not in ("registrar", "cashier", "librarian", "teacher"):
            flash("Invalid role selected.", "error")
            return redirect("/branch-admin")

        if not base_username:
            flash("Username is required.", "error")
            return redirect("/branch-admin")

        username = f"{base_username}_{role}".lower()
        temp_password = "USR-" + str(random.randint(1000, 9999))
        hashed_password = generate_password_hash(temp_password)

        db = get_db_connection()
        cursor = db.cursor()

        try:
            cursor.execute("SELECT 1 FROM users WHERE username=%s", (username,))
            if cursor.fetchone():
                flash("Username already exists. Try another base username.", "error")
                return redirect("/branch-admin")

            if role == "teacher":
                cursor.execute("""
                    INSERT INTO users (branch_id, username, password, role, require_password_change, grade_level, full_name, gender)
                    VALUES (%s, %s, %s, %s, TRUE, %s, %s, %s)
                """, (
                    session.get("branch_id"),
                    username,
                    hashed_password,
                    role,
                    grade_level or None,
                    full_name   or None,
                    gender      or None,
                ))
            else:
                cursor.execute("""
                    INSERT INTO users (branch_id, username, password, role, require_password_change)
                    VALUES (%s, %s, %s, %s, TRUE)
                """, (
                    session.get("branch_id"),
                    username,
                    hashed_password,
                    role
                ))

            db.commit()


            created_user = {"username": username, "password": temp_password, "role": role}
            flash("User created successfully!", "success")

        except Exception as e:
            db.rollback()
            flash(f"Failed to create user: {str(e)}", "error")
        finally:
            cursor.close()
            db.close()

    return render_template(
        "branch_admin_dashboard.html",
        created_user=created_user,
        announcements_list=announcements_list
    )


@branch_admin_bp.route("/branch-admin/announcements/<int:announcement_id>/hide", methods=["POST"])
def announcement_hide(announcement_id):
    if session.get("role") != "branch_admin":
        return redirect("/")
    db = get_db_connection()
    cur = db.cursor()
    try:
        cur.execute("UPDATE announcements SET is_active = FALSE WHERE id = %s", (announcement_id,))
        db.commit()
        flash("Announcement hidden from homepage.", "success")
    except Exception:
        db.rollback()
        flash("Could not hide announcement.", "error")
    finally:
        cur.close()
        db.close()
    return redirect(url_for("branch_admin.dashboard"))


@branch_admin_bp.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# =======================
# BRANCH ADMIN: FAQ MANAGEMENT
# =======================
@branch_admin_bp.route("/branch-admin/faqs", methods=["GET"])
def branch_admin_faqs():
    if session.get("role") != "branch_admin":
        return redirect("/")

    branch_id = session.get("branch_id")

    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT id, question, answer
            FROM chatbot_faqs
            WHERE branch_id IS NULL
            ORDER BY id ASC
        """)
        general_faqs = cursor.fetchall() or []

        cursor.execute("""
            SELECT id, question, answer
            FROM chatbot_faqs
            WHERE branch_id = %s
            ORDER BY id ASC
        """, (branch_id,))
        branch_faqs = cursor.fetchall() or []
    finally:
        cursor.close()
        db.close()

    return render_template(
        "branch_admin_faqs.html",
        general_faqs=general_faqs,
        branch_faqs=branch_faqs
    )


@branch_admin_bp.route("/branch-admin/faqs/add", methods=["POST"])
def branch_admin_faq_add():
    if session.get("role") != "branch_admin":
        return redirect("/")

    branch_id = session.get("branch_id")
    question = (request.form.get("question") or "").strip()
    answer = (request.form.get("answer") or "").strip()

    if not question or not answer:
        flash("Question and Answer are required.", "error")
        return redirect("/branch-admin/faqs")

    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO chatbot_faqs (question, answer, branch_id)
            VALUES (%s, %s, %s)
        """, (question, answer, branch_id))
        db.commit()
        flash("FAQ added successfully!", "success")
    except Exception:
        db.rollback()
        flash("Failed to add FAQ.", "error")
    finally:
        cursor.close()
        db.close()

    return redirect("/branch-admin/faqs")


@branch_admin_bp.route("/branch-admin/faqs/<int:faq_id>/edit", methods=["POST"])
def branch_admin_faq_edit(faq_id):
    if session.get("role") != "branch_admin":
        return redirect("/")

    branch_id = session.get("branch_id")
    question = (request.form.get("question") or "").strip()
    answer = (request.form.get("answer") or "").strip()

    if not question or not answer:
        flash("Question and Answer are required.", "error")
        return redirect("/branch-admin/faqs")

    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE chatbot_faqs
            SET question=%s, answer=%s
            WHERE id=%s AND branch_id=%s
        """, (question, answer, faq_id, branch_id))
        db.commit()
        flash("FAQ updated successfully!", "success")
    except Exception:
        db.rollback()
        flash("Failed to update FAQ.", "error")
    finally:
        cursor.close()
        db.close()

    return redirect("/branch-admin/faqs")


@branch_admin_bp.route("/branch-admin/faqs/<int:faq_id>/delete", methods=["POST"])
def branch_admin_faq_delete(faq_id):
    if session.get("role") != "branch_admin":
        return redirect("/")

    branch_id = session.get("branch_id")

    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            DELETE FROM chatbot_faqs
            WHERE id=%s AND branch_id=%s
        """, (faq_id, branch_id))
        db.commit()
        flash("FAQ deleted.", "success")
    except Exception:
        db.rollback()
        flash("Failed to delete FAQ.", "error")
    finally:
        cursor.close()
        db.close()

    return redirect("/branch-admin/faqs")


# =======================
# BRANCH ADMIN: INVENTORY (existing)
# =======================
@branch_admin_bp.route("/branch-admin/inventory", methods=["GET"])
def branch_admin_inventory():
    if session.get("role") != "branch_admin":
        return redirect("/")

    branch_id = session.get("branch_id")

    search = (request.args.get("search") or "").strip()
    category_filter = (request.args.get("category") or "").strip()
    grade_filter = (request.args.get("grade") or "").strip()
    status_filter = (request.args.get("status") or "active").strip()

    if not category_filter or category_filter.upper() == 'BOOK':
        return redirect("/branch-admin/inventory?category=UNIFORM&status=" + status_filter)

    db = get_db_connection()
    cursor = db.cursor()
    try:
        where = ["branch_id = %s", "category = %s"]
        params = [branch_id, category_filter]

        if status_filter in ("active", "inactive"):
            where.append("is_active = %s")
            params.append(status_filter == "active")

        if search:
            where.append("""
                (
                  item_name ILIKE %s OR
                  category ILIKE %s OR
                  COALESCE(grade_level,'') ILIKE %s OR
                  COALESCE(size_label,'') ILIKE %s
                )
            """)
            like = f"%{search}%"
            params.extend([like, like, like, like])

        where_sql = " AND ".join(where)

        cursor.execute(f"""
            SELECT
                item_id, category, item_name, grade_level, is_common,
                size_label, price, stock_total, reserved_qty, image_url, is_active
            FROM inventory_items
            WHERE {where_sql}
        """, params)

        all_items = cursor.fetchall() or []

        if grade_filter:
            items = []
            for item in all_items:
                item_name = item[2]
                stored_grade = item[3]
                if item_matches_grade_filter(item_name, stored_grade, grade_filter):
                    items.append(item)
        else:
            items = all_items

        enhanced_items = []
        for item in items:
            item_list = list(item)
            item_list.append(get_grade_display(item[2], item[3]))  # index 11
            enhanced_items.append(tuple(item_list))

        def sort_key(item):
            category = item[1]
            grade_level = item[3]
            item_name = item[2]
            # normalize category comparisons
            cat = str(category or "").strip().upper()
            cat_order = 0 if cat == "BOOK" else (1 if cat == "UNIFORM" else 2)
            return (cat_order, get_grade_order(grade_level), item_name.lower())

        enhanced_items = sorted(enhanced_items, key=sort_key)

        cursor.execute("""
            SELECT
              COUNT(*) AS total_items,
              COALESCE(SUM(stock_total),0) AS total_stock,
              COALESCE(SUM(reserved_qty),0) AS total_reserved,
              COALESCE(SUM(CASE WHEN (stock_total - reserved_qty) < 10 THEN 1 ELSE 0 END),0) AS low_stock_items
            FROM inventory_items
            WHERE branch_id = %s AND is_active = TRUE AND category != 'BOOK'
        """, (branch_id,))
        stats = cursor.fetchone()

    finally:
        cursor.close()
        db.close()

    return render_template(
        "branch_admin_inventory.html",
        items=enhanced_items,
        stats=stats,
        search=search,
        category_filter=category_filter,
        grade_filter=grade_filter,
        status_filter=status_filter
    )


@branch_admin_bp.route("/branch-admin/inventory/add", methods=["GET", "POST"])
def branch_admin_inventory_add():
    if session.get("role") != "branch_admin":
        return redirect("/")

    branch_id = session.get("branch_id")
    message = None
    error = None

    if request.method == "POST":
        category = (request.form.get("category") or "").strip()
        item_name = (request.form.get("item_name") or "").strip()
        grade_level = (request.form.get("grade_level") or "").strip()
        is_common = request.form.get("is_common") == "on"
        size_label = (request.form.get("size_label") or "").strip() or None
        price = (request.form.get("price") or "").strip()
        stock_total = (request.form.get("stock_total") or "").strip()
        image_url = (request.form.get("image_url") or "").strip() or None

        if not (category and item_name and price and stock_total):
            flash("Missing required fields", "error")
            return redirect("/branch-admin/inventory/add")

        db = get_db_connection()
        cursor = db.cursor()
        try:
            cursor.execute("""
                INSERT INTO inventory_items
                (branch_id, category, item_name, grade_level, is_common, size_label,
                 price, stock_total, reserved_qty, image_url, is_active)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,%s,TRUE)
                RETURNING item_id
            """, (branch_id, category, item_name, grade_level, is_common, size_label,
                  price, stock_total, image_url))
            new_item_id = cursor.fetchone()[0]
            db.commit()

            flash("Item added successfully!", "success")
            return redirect("/branch-admin/inventory?category=" + category)
        except Exception as e:
            db.rollback()
            flash(f"Failed to add item: {e}", "error")
        finally:
            cursor.close()
            db.close()

    return render_template("branch_admin_inventory_add.html", message=message, error=error)


# ✅ UPDATED: Restock is now BY SIZE (if size rows exist)
@branch_admin_bp.route("/branch-admin/inventory/<int:item_id>/restock", methods=["GET", "POST"])
def branch_admin_inventory_restock(item_id):
    if session.get("role") != "branch_admin":
        return redirect("/")

    branch_id = session.get("branch_id")
    error = None
    message = None

    db = get_db_connection()
    cursor = db.cursor()

    try:
        cursor.execute("""
            SELECT item_id, item_name, category, stock_total, reserved_qty, price
            FROM inventory_items
            WHERE item_id = %s AND branch_id = %s
            LIMIT 1
        """, (item_id, branch_id))
        item = cursor.fetchone()

        if not item:
            return "Item not found", 404

        cursor.execute("""
            SELECT size_id, size_label, stock_total, reserved_qty
            FROM inventory_item_sizes
            WHERE item_id = %s
        """, (item_id,))
        size_rows = cursor.fetchall() or []
        size_rows = sorted(size_rows, key=lambda r: size_sort_key(r[1]))

        if request.method == "POST":
            action = (request.form.get("action") or "").strip()

            if action == "create_sizes":
                created = ensure_default_sizes_exist(cursor, item_id)
                recompute_item_totals_from_sizes(cursor, item_id, branch_id)
                db.commit()
                if created:
                    flash("✅ Size rows created (XS-XXL). You can now restock per size.", "success")
                else:
                    flash("Sizes already exist for this item.", "info")

                return redirect(url_for("branch_admin.branch_admin_inventory_restock", item_id=item_id))

            size_label = (request.form.get("size_label") or "").strip().upper()
            add_stock = (request.form.get("add_stock") or "").strip()

            if not size_label:
                raise Exception("Please select a size (XS-XXL).")

            if not add_stock:
                raise Exception("Please enter stock quantity to add.")

            add_stock = int(add_stock)
            if add_stock <= 0:
                raise Exception("Stock quantity must be greater than 0.")

            cursor.execute("""
                SELECT 1
                FROM inventory_item_sizes
                WHERE item_id = %s AND UPPER(size_label) = %s
                LIMIT 1
            """, (item_id, size_label))
            exists = cursor.fetchone()

            if not exists:
                raise Exception("Selected size row does not exist. Click 'Create default sizes' first.")

            cursor.execute("""
                UPDATE inventory_item_sizes
                SET stock_total = stock_total + %s
                WHERE item_id = %s AND UPPER(size_label) = %s
            """, (add_stock, item_id, size_label))

            recompute_item_totals_from_sizes(cursor, item_id, branch_id)

            db.commit()
            flash(f"✅ Restocked {add_stock} for size {size_label}.", "success")

            return redirect(url_for("branch_admin.branch_admin_inventory_restock", item_id=item_id))

        cursor.execute("""
            SELECT size_id, size_label, stock_total, reserved_qty
            FROM inventory_item_sizes
            WHERE item_id = %s
        """, (item_id,))
        size_rows = cursor.fetchall() or []
        size_rows = sorted(size_rows, key=lambda r: size_sort_key(r[1]))

    except Exception as e:
        db.rollback()
        error = str(e)
        flash(error, "error")
    finally:
        cursor.close()
        db.close()

    return render_template(
        "branch_admin_inventory_restock.html",
        item=item,
        size_rows=size_rows,
        size_order=SIZE_ORDER,
        message=message,
        error=error
    )


@branch_admin_bp.route("/branch-admin/inventory/<int:item_id>/price", methods=["GET", "POST"])
def branch_admin_inventory_price(item_id):
    if session.get("role") != "branch_admin":
        return redirect("/")

    branch_id = session.get("branch_id")
    message = None
    error = None

    db = get_db_connection()
    cursor = db.cursor()

    try:
        cursor.execute("""
            SELECT item_id, item_name, category, price, stock_total
            FROM inventory_items
            WHERE item_id = %s AND branch_id = %s
        """, (item_id, branch_id))
        item = cursor.fetchone()

        if not item:
            return "Item not found", 404

        if request.method == "POST":
            new_price = (request.form.get("new_price") or "").strip()
            if not new_price:
                raise Exception("Please enter new price")

            new_price = float(new_price)
            if new_price <= 0:
                raise Exception("Price must be greater than 0")

            cursor.execute("""
                UPDATE inventory_items
                SET price = %s
                WHERE item_id = %s AND branch_id = %s
            """, (new_price, item_id, branch_id))
            db.commit()
            flash("Price updated successfully!", "success")

            cursor.execute("""
                SELECT item_id, item_name, category, price, stock_total
                FROM inventory_items
                WHERE item_id = %s AND branch_id = %s
            """, (item_id, branch_id))
            item = cursor.fetchone()

    except Exception as e:
        db.rollback()
        error = str(e)
        flash(error, "error")
    finally:
        cursor.close()
        db.close()

    return render_template("branch_admin_inventory_price.html", item=item, message=message, error=error)


@branch_admin_bp.route("/branch-admin/inventory/<int:item_id>/toggle", methods=["POST"])
def branch_admin_inventory_toggle(item_id):
    if session.get("role") != "branch_admin":
        return redirect("/")

    branch_id = session.get("branch_id")

    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE inventory_items
            SET is_active = NOT is_active
            WHERE item_id = %s AND branch_id = %s
        """, (item_id, branch_id))
        db.commit()
        flash("Item status updated.", "success")
    except Exception:
        db.rollback()
        flash("Failed to toggle item.", "error")
    finally:
        cursor.close()
        db.close()

    return redirect(request.referrer or "/branch-admin/inventory?category=UNIFORM")

