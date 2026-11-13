import re
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort, make_response, jsonify
from validators import (POSITIONS, LAGUNA_LGUS, REGIONS, FIELD_CHECKS, clean_name, validate_password,
                        validate_email, validate_person, form_vals, vals_from_admin, validate_jeep,
                        validate_driver, validate_document, validate_issue)
import mysql.connector
from db import Database
import os
import uuid
from datetime import date, datetime, timedelta
from functools import wraps

app = Flask(__name__)
try:
    from secrets_config import SECRET_KEY, REGISTRATION_CODE
except ImportError:
    SECRET_KEY, REGISTRATION_CODE = "dev-only-key", None

try:
    from secrets_config import APPS_SCRIPT_EMAIL_URL, APPS_SCRIPT_EMAIL_SECRET
except ImportError:
    APPS_SCRIPT_EMAIL_URL = ""
    APPS_SCRIPT_EMAIL_SECRET = ""
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(minutes=30)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
db_manager = Database()


def get_db():
    return db_manager.connect(session.get("admin_id"))

def send_apps_script_email(to, subject, body, html_body=None):
    if not APPS_SCRIPT_EMAIL_URL or not APPS_SCRIPT_EMAIL_SECRET:
        return False, "Apps Script email settings are missing."

    payload = {
        "secret": APPS_SCRIPT_EMAIL_SECRET,
        "to": to,
        "subject": subject,
        "body": body,
        "htmlBody": html_body or "",
    }

    request_data = Request(
        APPS_SCRIPT_EMAIL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request_data, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))

        if result.get("ok") is True:
            return True, "Email sent."

        return False, result.get("message", "Apps Script rejected the request.")

    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return False, "Could not reach the Apps Script email service."

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in to continue (your session may have timed out).")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def password_ok(stored, given):
    """Old plain-text passwords still work once, then get upgraded to a hash."""
    if stored.startswith(("scrypt:", "pbkdf2:")):
        return check_password_hash(stored, given)
    return stored == given

@app.route("/")
def landing():
    if "admin_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    remembered = request.cookies.get("remember_email", "")
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        db = get_db()
        cur = db.cursor(dictionary=True, buffered=True)
        cur.execute("SELECT * FROM admin WHERE email = %s", (email,))
        user = cur.fetchone()

        if user and password_ok(user["password"], password):
            if not user["password"].startswith(("scrypt:", "pbkdf2:")):
                cur.execute("UPDATE admin SET password = %s WHERE id = %s",
                            (generate_password_hash(password), user["id"]))
                db.commit()
            cur.close()
            db.close()
            session.clear()
            session["admin_id"] = user["id"]
            session["admin_name"] = user["full_name"]
            session.permanent = True
            log_event(user["id"], "logged in", "account", user["id"], user["email"])
            resp = make_response(redirect(url_for("dashboard")))
            if request.form.get("remember"):
                resp.set_cookie("remember_email", email, max_age=30 * 24 * 3600,
                                httponly=True, samesite="Lax")
            else:
                resp.delete_cookie("remember_email")
            return resp

        cur.close()
        db.close()
        error = "Wrong email or password."
        remembered = email
    return render_template("login.html", error=error, remembered=remembered)

@app.route("/forgot-password")
def forgot_password():
    return render_template("forgot_password.html")

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)

    cur.execute("SELECT COUNT(*) AS n FROM jeeps")
    jeeps = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM drivers")
    drivers = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM documents")
    docs = cur.fetchone()["n"]

    expiring = get_expiring(cur)

    cur.close()
    db.close()

    hour = datetime.now().hour
    greeting = ("Good morning" if hour < 12
                else "Good afternoon" if hour < 18
                else "Good evening")
    return render_template("dashboard.html", name=session["admin_name"], greeting=greeting,
                           jeeps=jeeps, drivers=drivers, docs=docs, expiring=expiring)

def log_event(admin_id, action, target_type, target_id, details):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO activity_log (admin_id, action, target_type, target_id, details)
        VALUES (%s, %s, %s, %s, %s)
    """, (admin_id, action, target_type, target_id, details))
    db.commit()
    cur.close()
    db.close()

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))

@app.route("/jeeps")
@login_required
def jeeps_list():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT j.*, d.full_name AS driver_name
        FROM jeeps j
        LEFT JOIN drivers d ON d.jeep_id = j.id
        ORDER BY j.jeep_no
    """)
    rows = cur.fetchall()
    cur.close()
    db.close()
    return render_template("jeeps.html", jeeps=rows)

@app.route("/jeeps/add", methods=["GET", "POST"])
@login_required
def jeep_add():
    form = {
        "jeep_no": (request.form.get("jeep_no") or "").strip(),
        "plate_no": (request.form.get("plate_no") or "").strip(),
        "route": (request.form.get("route") or "").strip(),
        "registration_expiry": (request.form.get("registration_expiry") or "").strip(),
    }
    errors = []

    if request.method == "POST":
        errors = validate_jeep(
            form["jeep_no"],
            form["plate_no"],
            form["route"],
            form["registration_expiry"],
        )

        if not errors:
            db = get_db()
            cur = db.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO jeeps
                        (jeep_no, plate_no, route, registration_expiry)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        form["jeep_no"],
                        form["plate_no"],
                        form["route"],
                        form["registration_expiry"] or None,
                    ),
                )
                db.commit()
                return redirect(url_for("jeeps_list"))
            except mysql.connector.IntegrityError:
                errors.append("That jeep number or plate number already exists.")
            finally:
                cur.close()
                db.close()

    return render_template(
        "jeep_form.html",
        jeep=form,
        errors=errors,
        title="Add jeep",
    )

@app.route("/jeeps/<int:jeep_id>/edit", methods=["GET", "POST"])
@login_required
def jeep_edit(jeep_id):
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    errors = []

    try:
        cur.execute("SELECT * FROM jeeps WHERE id = %s", (jeep_id,))
        jeep = cur.fetchone()

        if not jeep:
            return redirect(url_for("jeeps_list"))

        form = {
            "jeep_no": jeep["jeep_no"],
            "plate_no": jeep["plate_no"],
            "route": jeep["route"] or "",
            "registration_expiry": jeep["registration_expiry"] or "",
        }

        if request.method == "POST":
            form = {
                "jeep_no": (request.form.get("jeep_no") or "").strip(),
                "plate_no": (request.form.get("plate_no") or "").strip(),
                "route": (request.form.get("route") or "").strip(),
                "registration_expiry": (
                    request.form.get("registration_expiry") or ""
                ).strip(),
            }

            errors = validate_jeep(
                form["jeep_no"],
                form["plate_no"],
                form["route"],
                form["registration_expiry"],
            )

            if not errors:
                try:
                    cur.execute(
                        """
                        UPDATE jeeps
                        SET jeep_no = %s, plate_no = %s, route = %s,
                            registration_expiry = %s
                        WHERE id = %s
                        """,
                        (
                            form["jeep_no"],
                            form["plate_no"],
                            form["route"],
                            form["registration_expiry"] or None,
                            jeep_id,
                        ),
                    )
                    db.commit()
                    return redirect(url_for("jeeps_list"))
                except mysql.connector.IntegrityError:
                    errors.append(
                        "That jeep number or plate number already exists."
                    )

        return render_template(
            "jeep_form.html",
            jeep=form,
            errors=errors,
            title="Edit jeep",
        )
    finally:
        cur.close()
        db.close()

@app.route("/jeeps/<int:jeep_id>/delete", methods=["POST"])
@login_required
def jeep_delete(jeep_id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM jeeps WHERE id = %s", (jeep_id,))
        db.commit()
    except mysql.connector.IntegrityError:
        flash("Can't delete this jeep: it still has a driver, documents or issues linked to it.")
    finally:
        cur.close()
        db.close()
    return redirect(url_for("jeeps_list"))

# ---------- DRIVERS ----------
UPLOAD_DIR = os.path.join(app.root_path, "static", "uploads", "drivers")
ALLOWED_PHOTOS = {"png", "jpg", "jpeg", "webp"}

def save_photo(file):
    """Save an uploaded photo and return its path, or None if no file was chosen."""
    if not file or file.filename == "":
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_PHOTOS:
        raise ValueError("Photo must be a png, jpg, jpeg or webp file.")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = uuid.uuid4().hex + "." + ext
    file.save(os.path.join(UPLOAD_DIR, name))
    return "uploads/drivers/" + name

def free_jeeps(cur, current=None):
    """Jeeps with no driver yet, plus the driver's current jeep when editing."""
    cur.execute("""
        SELECT id, jeep_no, plate_no FROM jeeps
        WHERE id NOT IN (SELECT jeep_id FROM drivers WHERE jeep_id IS NOT NULL)
           OR id = %s
        ORDER BY jeep_no
    """, (current,))
    return cur.fetchall()

def clean_driver_form(form):
    keys = [
        "full_name",
        "birth_date",
        "address",
        "contact_no",
        "license_no",
        "license_expiry",
        "date_joined",
        "emergency_name",
        "emergency_contact_no",
    ]
    data = {key: (form.get(key) or "").strip() or None for key in keys}
    data["full_name"] = clean_name(data["full_name"])
    if data["emergency_name"]:
        data["emergency_name"] = clean_name(data["emergency_name"])

    jeep_value = (form.get("jeep_id") or "").strip()
    data["jeep_id"] = int(jeep_value) if jeep_value else None
    data["assigned_since"] = (form.get("assigned_since") or "").strip() or None
    return data

def driver_values(data, photo):
    return (data["full_name"], photo, data["birth_date"], data["address"],
            data["contact_no"], data["license_no"], data["license_expiry"],
            data["jeep_id"], data["date_joined"], data["emergency_name"],
            data["emergency_contact_no"])

@app.route("/drivers")
@login_required
def drivers_list():
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    cur.execute("""
        SELECT d.*, TIMESTAMPDIFF(YEAR, d.birth_date, CURDATE()) AS age,
               j.jeep_no, j.plate_no
        FROM drivers d
        LEFT JOIN jeeps j ON d.jeep_id = j.id
        ORDER BY d.full_name
    """)
    rows = cur.fetchall()
    cur.close()
    db.close()
    return render_template("drivers.html", drivers=rows)

@app.route("/drivers/add", methods=["GET", "POST"])
@login_required
def driver_add():
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    errors = []
    try:
        if request.method == "POST":
            errors = validate_driver(request.form)
            if not errors:
                data = clean_driver_form(request.form)
                try:
                    photo = save_photo(request.files.get("photo"))
                    cur.execute("""
                        INSERT INTO drivers (full_name, photo_path, birth_date, address,
                            contact_no, license_no, license_expiry, jeep_id, date_joined,
                            emergency_name, emergency_contact_no)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, driver_values(data, photo))
                    if data["jeep_id"]:
                        cur.execute(
                            "UPDATE jeeps SET driver_assigned_since = COALESCE(%s, CURDATE()) WHERE id = %s",
                            (data["assigned_since"], data["jeep_id"]))
                    db.commit()
                    return redirect(url_for("drivers_list"))
                except ValueError as e:
                    errors.append(str(e))
                except mysql.connector.IntegrityError:
                    db.rollback()
                    errors.append("That jeep is already assigned to another driver.")
        jeeps = free_jeeps(cur)
        return render_template("driver_form.html", driver=request.form, jeeps=jeeps,
                               errors=errors, title="Add driver")
    finally:
        cur.close()
        db.close()

@app.route("/drivers/<int:driver_id>/edit", methods=["GET", "POST"])
@login_required
def driver_edit(driver_id):
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    errors = []
    try:
        cur.execute("""
            SELECT d.*, j.driver_assigned_since AS assigned_since
            FROM drivers d LEFT JOIN jeeps j ON d.jeep_id = j.id
            WHERE d.id = %s
        """, (driver_id,))
        driver = cur.fetchone()
        if not driver:
            return redirect(url_for("drivers_list"))
        current_jeep = driver["jeep_id"]

        if request.method == "POST":
            errors = validate_driver(request.form)
            if not errors:
                data = clean_driver_form(request.form)
                try:
                    photo = save_photo(request.files.get("photo")) or driver["photo_path"]
                    cur.execute("""
                        UPDATE drivers SET full_name=%s, photo_path=%s, birth_date=%s,
                            address=%s, contact_no=%s, license_no=%s, license_expiry=%s,
                            jeep_id=%s, date_joined=%s, emergency_name=%s,
                            emergency_contact_no=%s
                        WHERE id=%s
                    """, driver_values(data, photo) + (driver_id,))
                    if current_jeep and current_jeep != data["jeep_id"]:
                        cur.execute("UPDATE jeeps SET driver_assigned_since = NULL WHERE id = %s",
                                    (current_jeep,))
                    if data["jeep_id"]:
                        cur.execute(
                            "UPDATE jeeps SET driver_assigned_since = COALESCE(%s, CURDATE()) WHERE id = %s",
                            (data["assigned_since"], data["jeep_id"]))
                    db.commit()
                    return redirect(url_for("drivers_list"))
                except ValueError as e:
                    errors.append(str(e))
                except mysql.connector.IntegrityError:
                    db.rollback()
                    errors.append("That jeep is already assigned to another driver.")
            driver = {**driver, **request.form.to_dict()}

        jeeps = free_jeeps(cur, current_jeep)
        return render_template("driver_form.html", driver=driver, jeeps=jeeps,
                               errors=errors, title="Edit driver")
    finally:
        cur.close()
        db.close()

@app.route("/drivers/<int:driver_id>/delete", methods=["POST"])
@login_required
def driver_delete(driver_id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE jeeps SET driver_assigned_since = NULL
            WHERE id = (SELECT jeep_id FROM drivers WHERE id = %s)
        """, (driver_id,))
        cur.execute("DELETE FROM drivers WHERE id = %s", (driver_id,))
        db.commit()
    except mysql.connector.IntegrityError:
        db.rollback()
        flash("Can't delete this driver: documents or issue reports are linked to them.")
    finally:
        cur.close()
        db.close()
    return redirect(url_for("drivers_list"))

# ---------- DOCKTRACK ----------
DOC_DIR = os.path.join(app.root_path, "uploads", "documents")
ALLOWED_DOCS = {"pdf", "png", "jpg", "jpeg", "webp"}
DOC_TYPES = ["OR", "CR", "PA", "Decision", "ICAR", "ID", "License", "Other"]

def save_document(file):
    if not file or file.filename == "":
        raise ValueError("Please choose a file to upload.")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_DOCS:
        raise ValueError("File must be a pdf, png, jpg, jpeg or webp.")
    os.makedirs(DOC_DIR, exist_ok=True)
    name = uuid.uuid4().hex + "." + ext
    file.save(os.path.join(DOC_DIR, name))
    return name

def get_expiring(cur, days=30):
    """Everything expired or expiring within `days`: documents, jeep registrations, driver licenses."""
    cur.execute("""
        SELECT 'Jeep registration' AS what, j.plate_no AS who,
               j.registration_expiry AS expiry,
               DATEDIFF(j.registration_expiry, CURDATE()) AS days_left
        FROM jeeps j
        WHERE j.registration_expiry IS NOT NULL
          AND j.registration_expiry <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
        UNION ALL
        SELECT 'Driver license', dr.full_name, dr.license_expiry,
               DATEDIFF(dr.license_expiry, CURDATE())
        FROM drivers dr
        WHERE dr.license_expiry IS NOT NULL
          AND dr.license_expiry <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
        UNION ALL
        SELECT d.doc_type, COALESCE(j.plate_no, dr.full_name), d.expiry_date,
               DATEDIFF(d.expiry_date, CURDATE())
        FROM documents d
        LEFT JOIN jeeps j ON d.jeep_id = j.id
        LEFT JOIN drivers dr ON d.driver_id = dr.id
        WHERE d.expiry_date IS NOT NULL
          AND d.expiry_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
        ORDER BY expiry
    """, (days, days, days))
    return cur.fetchall()

@app.route("/docs")
@login_required
def docs_list():
    doc_type = request.args.get("type")
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    sql = """
        SELECT d.*, j.jeep_no, j.plate_no, dr.full_name AS driver_name,
               a.full_name AS uploader,
               DATEDIFF(d.expiry_date, CURDATE()) AS days_left
        FROM documents d
        LEFT JOIN jeeps j ON d.jeep_id = j.id
        LEFT JOIN drivers dr ON d.driver_id = dr.id
        LEFT JOIN admin a ON d.uploaded_by = a.id
    """
    if doc_type in DOC_TYPES:
        cur.execute(sql + " WHERE d.doc_type = %s ORDER BY d.doc_date DESC, d.id DESC", (doc_type,))
    else:
        doc_type = None
        cur.execute(sql + " ORDER BY d.doc_date DESC, d.id DESC")
    docs = cur.fetchall()
    expiring = get_expiring(cur)
    cur.close()
    db.close()
    return render_template("docs.html", docs=docs, expiring=expiring,
                           doc_types=DOC_TYPES, current_type=doc_type)

@app.route("/docs/add", methods=["GET", "POST"])
@login_required
def docs_add():
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    errors = []
    try:
        if request.method == "POST":
            errors = validate_document(request.form, DOC_TYPES)
            kind, _, oid = (request.form.get("owner") or "").partition(":")

            if not errors:
                if kind == "jeep":
                    cur.execute("SELECT id FROM jeeps WHERE id = %s", (int(oid),))
                else:
                    cur.execute("SELECT id FROM drivers WHERE id = %s", (int(oid),))
                if not cur.fetchone():
                    errors.append("The selected jeep or driver could not be found.")

            if not errors:
                try:
                    stored = save_document(request.files.get("file"))
                except ValueError as e:
                    errors.append(str(e))
                else:
                    try:
                        cur.execute("""
                            INSERT INTO documents
                              (jeep_id, driver_id, doc_type, doc_date, expiry_date, file_path)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (int(oid) if kind == "jeep" else None,
                              int(oid) if kind == "driver" else None,
                              request.form["doc_type"], request.form.get("doc_date") or None,
                              request.form.get("expiry_date") or None, stored))
                        db.commit()
                        return redirect(url_for("docs_list"))
                    except mysql.connector.IntegrityError:
                        db.rollback()
                        errors.append("The selected jeep or driver could not be saved.")
        cur.execute("SELECT id, jeep_no, plate_no FROM jeeps ORDER BY jeep_no")
        jeeps = cur.fetchall()
        cur.execute("SELECT id, full_name FROM drivers ORDER BY full_name")
        drivers = cur.fetchall()
        return render_template("doc_form.html", form=request.form, jeeps=jeeps,
                               drivers=drivers, doc_types=DOC_TYPES, errors=errors)
    finally:
        cur.close()
        db.close()

@app.route("/docs/<int:doc_id>/file")
@login_required
def docs_file(doc_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT file_path, doc_type FROM documents WHERE id = %s", (doc_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    if not row:
        abort(404)
    log_event(session["admin_id"], "viewed", "document", doc_id,
              row["doc_type"] + " #" + str(doc_id))
    return send_from_directory(DOC_DIR, row["file_path"])

@app.route("/docs/<int:doc_id>/delete", methods=["POST"])
@login_required
def docs_delete(doc_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT file_path FROM documents WHERE id = %s", (doc_id,))
    row = cur.fetchone()
    if row:
        cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
        db.commit()
        try:
            os.remove(os.path.join(DOC_DIR, row["file_path"]))
        except OSError:
            pass
    cur.close()
    db.close()
    return redirect(url_for("docs_list"))


# ---------- ISSUETRACK ----------
ISSUE_DIR = os.path.join(app.root_path, "uploads", "issues")
ISSUE_TYPES = ["Mechanical", "Route", "Gas", "Other"]
ISSUE_STATUSES = ["Open", "In Progress", "Resolved"]
PAID_BY = ["Company", "Driver"]
ALLOWED_ISSUE_PHOTOS = {"png", "jpg", "jpeg", "webp"}

def file_ext(f):
    return f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""

def save_issue_photos(cur, issue_id, files):
    """Validate every chosen photo first, then save them all."""
    files = [f for f in files if f and f.filename]
    for f in files:
        if file_ext(f) not in ALLOWED_ISSUE_PHOTOS:
            raise ValueError("Photos must be png, jpg, jpeg or webp files.")
    os.makedirs(ISSUE_DIR, exist_ok=True)
    for f in files:
        name = uuid.uuid4().hex + "." + file_ext(f)
        f.save(os.path.join(ISSUE_DIR, name))
        cur.execute("INSERT INTO issue_photos (issue_id, file_path) VALUES (%s, %s)",
                    (issue_id, name))

def clean_issue_form(f):
    data = {
        "jeep_id": int(f["jeep_id"]) if f.get("jeep_id") else None,
        "issue_type": f.get("issue_type") if f.get("issue_type") in ISSUE_TYPES else "Other",
        "issue": (f.get("issue") or "").strip(),
        "status": f.get("status") if f.get("status") in ISSUE_STATUSES else "Open",
        "date_broken": (f.get("date_broken") or "").strip() or None,
        "date_fixed": (f.get("date_fixed") or "").strip() or None,
        "cost": (f.get("cost") or "").strip() or None,
        "shop_place": (f.get("shop_place") or "").strip() or None,
        "technician": (f.get("technician") or "").strip() or None,
        "paid_by": f.get("paid_by") if f.get("paid_by") in PAID_BY else None,
        "repair_details": (f.get("repair_details") or "").strip() or None,
        "substitute_jeep_id": int(f["substitute_jeep_id"]) if f.get("substitute_jeep_id") else None,
    }
    # A fixed date means the repair is done, so mark it Resolved automatically
    if data["date_fixed"]:
        data["status"] = "Resolved"
    return data

def issue_fields(d):
    return (d["issue_type"], d["issue"], d["status"], d["date_broken"], d["date_fixed"],
            d["cost"], d["shop_place"], d["technician"], d["paid_by"],
            d["repair_details"], d["substitute_jeep_id"])

@app.route("/issues")
@login_required
def issues_list():
    status = request.args.get("status")
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    sql = """
        SELECT i.*, j.jeep_no, j.plate_no, dr.full_name AS driver_name,
               cb.full_name AS reporter, ub.full_name AS editor,
               DATEDIFF(COALESCE(i.date_fixed, CURDATE()), i.date_broken) AS days_stopped
        FROM issues i
        JOIN jeeps j ON i.jeep_id = j.id
        LEFT JOIN drivers dr ON i.driver_id = dr.id
        LEFT JOIN admin cb ON i.created_by = cb.id
        LEFT JOIN admin ub ON i.updated_by = ub.id
    """
    order = " ORDER BY (i.status = 'Resolved'), i.date_broken DESC, i.id DESC"
    if status in ISSUE_STATUSES:
        cur.execute(sql + " WHERE i.status = %s" + order, (status,))
    else:
        status = None
        cur.execute(sql + order)
    rows = cur.fetchall()
    cur.close()
    db.close()
    return render_template("issues.html", issues=rows, statuses=ISSUE_STATUSES,
                           current_status=status)

@app.route("/issues/add", methods=["GET", "POST"])
@login_required
def issues_add():
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    errors = []
    try:
        if request.method == "POST":
            errors = validate_issue(request.form, ISSUE_TYPES, ISSUE_STATUSES, PAID_BY)
            if not errors:
                data = clean_issue_form(request.form)
                cur.execute("SELECT id FROM jeeps WHERE id = %s", (data["jeep_id"],))
                if not cur.fetchone():
                    errors.append("The selected jeep could not be found.")

                if data["substitute_jeep_id"]:
                    cur.execute("SELECT id FROM jeeps WHERE id = %s",
                                (data["substitute_jeep_id"],))
                    if not cur.fetchone():
                        errors.append("The selected substitute jeep could not be found.")

            if not errors:
                try:
                    cur.execute("SELECT id FROM drivers WHERE jeep_id = %s", (data["jeep_id"],))
                    drv = cur.fetchone()
                    cur.execute("""
                        INSERT INTO issues (jeep_id, driver_id, issue_type, issue, status,
                            date_broken, date_fixed, cost, shop_place, technician, paid_by,
                            repair_details, substitute_jeep_id)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (data["jeep_id"], drv["id"] if drv else None) + issue_fields(data))
                    save_issue_photos(cur, cur.lastrowid, request.files.getlist("photos"))
                    db.commit()
                    return redirect(url_for("issues_list"))
                except ValueError as e:
                    db.rollback()
                    errors.append(str(e))
                except mysql.connector.IntegrityError:
                    db.rollback()
                    errors.append("The issue could not be saved because a selected jeep is invalid.")
        cur.execute("SELECT id, jeep_no, plate_no FROM jeeps ORDER BY jeep_no")
        jeeps = cur.fetchall()
        return render_template("issue_form.html", issue=request.form, jeeps=jeeps,
                               errors=errors, title="Add issue", editing=False,
                               today=date.today().isoformat(), issue_types=ISSUE_TYPES,
                               statuses=ISSUE_STATUSES, paid_by=PAID_BY,
                               photos=[], history=[])
    finally:
        cur.close()
        db.close()

@app.route("/issues/<int:issue_id>", methods=["GET", "POST"])
@login_required
def issues_edit(issue_id):
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    errors = []
    try:
        cur.execute("""
            SELECT i.*, j.jeep_no, j.plate_no, dr.full_name AS driver_name,
                   DATEDIFF(COALESCE(i.date_fixed, CURDATE()), i.date_broken) AS days_stopped
            FROM issues i
            JOIN jeeps j ON i.jeep_id = j.id
            LEFT JOIN drivers dr ON i.driver_id = dr.id
            WHERE i.id = %s
        """, (issue_id,))
        issue = cur.fetchone()
        if not issue:
            return redirect(url_for("issues_list"))

        if request.method == "POST":
            form = request.form.to_dict()
            form["jeep_id"] = str(issue["jeep_id"])
            errors = validate_issue(form, ISSUE_TYPES, ISSUE_STATUSES, PAID_BY)
            if not errors:
                data = clean_issue_form(form)
                data["jeep_id"] = issue["jeep_id"]
                if data["substitute_jeep_id"]:
                    cur.execute("SELECT id FROM jeeps WHERE id = %s",
                                (data["substitute_jeep_id"],))
                    if not cur.fetchone():
                        errors.append("The selected substitute jeep could not be found.")

                if not errors:
                    try:
                        cur.execute("""
                            UPDATE issues SET issue_type=%s, issue=%s, status=%s, date_broken=%s,
                                date_fixed=%s, cost=%s, shop_place=%s, technician=%s, paid_by=%s,
                                repair_details=%s, substitute_jeep_id=%s
                            WHERE id=%s
                        """, issue_fields(data) + (issue_id,))
                        save_issue_photos(cur, issue_id, request.files.getlist("photos"))
                        db.commit()
                        flash("Issue saved.")
                        return redirect(url_for("issues_list"))
                    except ValueError as e:
                        db.rollback()
                        errors.append(str(e))
                    except mysql.connector.IntegrityError:
                        db.rollback()
                        errors.append("The issue could not be saved because a selected jeep is invalid.")
            issue = {**issue, **request.form.to_dict()}

        cur.execute("SELECT id, jeep_no, plate_no FROM jeeps ORDER BY jeep_no")
        jeeps = cur.fetchall()
        cur.execute("SELECT id FROM issue_photos WHERE issue_id = %s ORDER BY id", (issue_id,))
        photos = cur.fetchall()
        cur.execute("""
            SELECT i.id, i.issue_type, i.issue, i.status, i.date_broken, i.date_fixed, i.cost,
                   DATEDIFF(COALESCE(i.date_fixed, CURDATE()), i.date_broken) AS days_stopped
            FROM issues i
            WHERE i.jeep_id = %s AND i.id <> %s
            ORDER BY i.date_broken DESC
        """, (issue["jeep_id"], issue_id))
        history = cur.fetchall()
        return render_template("issue_form.html", issue=issue, jeeps=jeeps, errors=errors,
                               title="Issue report", editing=True,
                               today=date.today().isoformat(), issue_types=ISSUE_TYPES,
                               statuses=ISSUE_STATUSES, paid_by=PAID_BY,
                               photos=photos, history=history)
    finally:
        cur.close()
        db.close()

@app.route("/issues/photo/<int:photo_id>")
@login_required
def issues_photo(photo_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT file_path FROM issue_photos WHERE id = %s", (photo_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    if not row:
        abort(404)
    return send_from_directory(ISSUE_DIR, row["file_path"])

@app.route("/issues/photo/<int:photo_id>/delete", methods=["POST"])
@login_required
def issues_photo_delete(photo_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT issue_id, file_path FROM issue_photos WHERE id = %s", (photo_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        db.close()
        return redirect(url_for("issues_list"))
    cur.execute("DELETE FROM issue_photos WHERE id = %s", (photo_id,))
    db.commit()
    try:
        os.remove(os.path.join(ISSUE_DIR, row["file_path"]))
    except OSError:
        pass
    cur.close()
    db.close()
    return redirect(url_for("issues_edit", issue_id=row["issue_id"]))

@app.route("/issues/<int:issue_id>/delete", methods=["POST"])
@login_required
def issues_delete(issue_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT file_path FROM issue_photos WHERE issue_id = %s", (issue_id,))
    files = [r["file_path"] for r in cur.fetchall()]
    cur.execute("DELETE FROM issues WHERE id = %s", (issue_id,))
    db.commit()
    for name in files:
        try:
            os.remove(os.path.join(ISSUE_DIR, name))
        except OSError:
            pass
    cur.close()
    db.close()
    return redirect(url_for("issues_list"))

# ---------- TOP BAR: bell, search, profile ----------

@app.context_processor
def inject_topbar():
    if "admin_id" not in session:
        return {}
    try:
        db = get_db()
        cur = db.cursor(dictionary=True, buffered=True)
        items = get_expiring(cur)
        cur.execute("SELECT photo_path FROM admin WHERE id = %s", (session["admin_id"],))
        me = cur.fetchone()
        cur.close()
        db.close()
    except mysql.connector.Error:
        return {"bell_items": [], "bell_count": 0, "my_photo": None}
    return {"bell_items": items[:6], "bell_count": len(items),
            "my_photo": me["photo_path"] if me else None}

@app.route("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    results = {"jeeps": [], "drivers": [], "docs": [], "issues": []}
    if q:
        like = "%" + q + "%"
        db = get_db()
        cur = db.cursor(dictionary=True, buffered=True)

        cur.execute("""
            SELECT id, jeep_no, plate_no, route FROM jeeps
            WHERE jeep_no LIKE %s OR plate_no LIKE %s OR route LIKE %s
            ORDER BY jeep_no LIMIT 20
        """, (like, like, like))
        results["jeeps"] = cur.fetchall()

        cur.execute("""
            SELECT d.id, d.full_name, d.contact_no, d.license_no, j.jeep_no
            FROM drivers d LEFT JOIN jeeps j ON d.jeep_id = j.id
            WHERE d.full_name LIKE %s OR d.contact_no LIKE %s
               OR d.license_no LIKE %s OR d.address LIKE %s
            ORDER BY d.full_name LIMIT 20
        """, (like, like, like, like))
        results["drivers"] = cur.fetchall()

        cur.execute("""
            SELECT d.id, d.doc_type, d.doc_date, d.expiry_date,
                   j.jeep_no, j.plate_no, dr.full_name AS driver_name
            FROM documents d
            LEFT JOIN jeeps j ON d.jeep_id = j.id
            LEFT JOIN drivers dr ON d.driver_id = dr.id
            WHERE d.doc_type LIKE %s OR j.plate_no LIKE %s OR j.jeep_no LIKE %s
               OR dr.full_name LIKE %s
            ORDER BY d.doc_date DESC LIMIT 20
        """, (like, like, like, like))
        results["docs"] = cur.fetchall()

        cur.execute("""
            SELECT i.id, i.issue_type, i.issue, i.status, i.date_broken,
                   j.jeep_no, j.plate_no, dr.full_name AS driver_name
            FROM issues i
            JOIN jeeps j ON i.jeep_id = j.id
            LEFT JOIN drivers dr ON i.driver_id = dr.id
            WHERE i.issue LIKE %s OR i.shop_place LIKE %s OR i.technician LIKE %s
               OR i.repair_details LIKE %s OR j.plate_no LIKE %s OR j.jeep_no LIKE %s
               OR dr.full_name LIKE %s
            ORDER BY i.date_broken DESC LIMIT 20
        """, (like,) * 7)
        results["issues"] = cur.fetchall()

        cur.close()
        db.close()
    total = sum(len(v) for v in results.values())
    return render_template("search.html", q=q, results=results, total=total)

ADMIN_PHOTO_DIR = os.path.join(app.root_path, "static", "uploads", "admins")

def save_admin_photo(file):
    if not file or file.filename == "":
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_PHOTOS:
        raise ValueError("Photo must be a png, jpg, jpeg or webp file.")
    os.makedirs(ADMIN_PHOTO_DIR, exist_ok=True)
    name = uuid.uuid4().hex + "." + ext
    file.save(os.path.join(ADMIN_PHOTO_DIR, name))
    return "uploads/admins/" + name

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    errors = []
    try:
        cur.execute("SELECT * FROM admin WHERE id = %s", (session["admin_id"],))
        admin = cur.fetchone()
        vals = vals_from_admin(admin)
        if request.method == "POST":
            f = request.form
            vals = form_vals(f)
            person, errors = validate_person(f)
            if not errors:
                cur.execute("SELECT id FROM admin WHERE contact_no = %s AND id <> %s",
                            (person["contact_no"], admin["id"]))
                if cur.fetchone():
                    errors.append("That contact number is already registered.")
            photo = admin["photo_path"]
            if not errors:
                try:
                    photo = save_admin_photo(request.files.get("photo")) or photo
                except ValueError as e:
                    errors.append(str(e))
            if not errors:
                cur.execute("""
                    UPDATE admin SET full_name=%s, position=%s, contact_no=%s,
                        address=%s, photo_path=%s
                    WHERE id=%s
                """, (person["full_name"], person["position"], person["contact_no"],
                      person["address"], photo, session["admin_id"]))
                db.commit()
                session["admin_name"] = person["full_name"]
                flash("Profile saved.")
                return redirect(url_for("profile"))
        return render_template("profile.html", admin=admin, vals=vals, errors=errors,
                               form=request.form, positions=POSITIONS, lgus=LAGUNA_LGUS,
                               regions=REGIONS)
    finally:
        cur.close()
        db.close()

# ---------- REGISTER ----------
@app.route("/check_field", methods=["POST"])
def check_field():
    """Live check of ONE box while the user types (same idea as check_field.php)."""
    field = request.form.get("field", "")
    value = request.form.get("value", "")
    if field in FIELD_CHECKS:
        value = value.strip()
        if field == "name":
            value = clean_name(value)
        errors = FIELD_CHECKS[field](value)
    elif field == "password":
        errors = validate_password(value)
    elif field == "confirm":
        other = request.form.get("other", "")
        if value == "":
            errors = ["Please confirm your password."]
        elif value != other:
            errors = ["Passwords do not match."]
        else:
            errors = []
    else:
        errors = ["Unknown field."]
    return jsonify(errors=errors)

@app.route("/register", methods=["GET", "POST"])
def register():
    errors = []
    if request.method == "POST":
        f = request.form
        email = f.get("email", "").strip().lower()
        password = f.get("password", "")
        confirm = f.get("confirm", "")

        person, errors = validate_person(f)
        errors += validate_email(email)
        errors += validate_password(password)
        if confirm == "":
            errors.append("Please confirm your password.")
        elif password != confirm:
            errors.append("Passwords do not match.")

        if not REGISTRATION_CODE:
            errors.append("Registration isn't set up yet. Ask the system owner.")
        elif f.get("code", "").strip() != REGISTRATION_CODE:
            errors.append("Wrong registration code. Ask MDCE for the code.")

        if not errors:
            db = get_db()
            cur = db.cursor()
            cur.execute("SELECT email, contact_no FROM admin WHERE email = %s OR contact_no = %s",
                        (email, person["contact_no"]))
            for row_email, row_contact in cur.fetchall():
                if row_email == email:
                    errors.append("That email is already registered.")
                if row_contact == person["contact_no"]:
                    errors.append("That contact number is already registered.")
            errors = list(dict.fromkeys(errors))
            if not errors:
                try:
                    cur.execute("""
                        INSERT INTO admin (email, password, full_name, position, contact_no, address)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (email, generate_password_hash(password), person["full_name"],
                          person["position"], person["contact_no"], person["address"]))
                    db.commit()
                    flash("Account created. You can log in now.")
                    return redirect(url_for("login"))
                except mysql.connector.IntegrityError:
                    errors.append("That email is already registered.")
            cur.close()
            db.close()
    return render_template("register.html", form=request.form, vals=form_vals(request.form),
                           errors=errors, positions=POSITIONS, lgus=LAGUNA_LGUS, regions=REGIONS)

@app.route("/activity")
@login_required
def activity():
    user = request.args.get("user", type=int)
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    cur.execute("SELECT id, full_name FROM admin ORDER BY full_name")
    users = cur.fetchall()
    sql = """
        SELECT l.*, a.full_name AS who
        FROM activity_log l LEFT JOIN admin a ON l.admin_id = a.id
    """
    if user:
        cur.execute(sql + " WHERE l.admin_id = %s ORDER BY l.id DESC LIMIT 300", (user,))
    else:
        cur.execute(sql + " ORDER BY l.id DESC LIMIT 300")
    rows = cur.fetchall()
    cur.close()
    db.close()
    return render_template("activity.html", rows=rows, users=users, current_user=user)

# ---------- ERROR PAGES ----------
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="That page doesn't exist."), 404

@app.errorhandler(413)
def file_too_large(e):
    return render_template("error.html", code=413, message="That file is too big. The limit is 25 MB."), 413

@app.errorhandler(mysql.connector.Error)
def database_error(e):
    return render_template("error.html", code=500,
        message="Can't reach the database. Make sure MySQL is running in XAMPP, then try again."), 500

@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Something went wrong. Please try again."), 500

if __name__ == "__main__":
    app.run(debug=True)
