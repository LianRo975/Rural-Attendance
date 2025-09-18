from functools import wraps
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import check_password_hash
from db import (
    bootstrap, get_user_by_login,
    # Schools/classes/sections/teachers
    list_schools, insert_school, get_school, update_school, deactivate_school,
    list_classes_by_school, insert_class, get_class,
    list_sections_by_class, insert_section, list_sections_with_class_by_school,
    list_teachers, insert_teacher, get_teacher, update_teacher, deactivate_teacher,
    # Subjects
    list_subjects_by_school, insert_subject, get_subject, update_subject, deactivate_subject,
    # Periods
    list_periods_by_school, insert_period, get_period, update_period, deactivate_period,
    # Assignments
    list_assignments, insert_assignment, deactivate_assignment
    
)
from db import (
    # ... your existing imports ...
    list_students_by_section, insert_student, get_student, update_student, deactivate_student
)

from db import (
    # ...existing...
    list_periods_by_school, list_sections_by_class, get_class, list_students_by_section,
    get_or_create_attendance_session, list_students_with_mark, upsert_attendance_mark,
    summarize_attendance_for_class_date
)

app = Flask(__name__)
app.config.update(TEMPLATES_AUTO_RELOAD=True)

APP_NAME = "Rural Schools Attendance Monitoring System"
APP_VERSION = "v0.3.9"
APP_DATE = "2025-09-18"

app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
bootstrap()

# ---------- Auth helpers ----------
def current_user():
    return session.get("user")

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please sign in to continue.", "info")
                return redirect(url_for("login"))
            if user["role"] not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator

@app.context_processor
def inject_globals():
    return dict(
        APP_NAME=APP_NAME,
        APP_VERSION=APP_VERSION,
        APP_DATE=APP_DATE,
        current_user=current_user(),
    )

# ---------- Health & landing ----------
@app.route("/health")
def health():
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}

@app.route("/ping")
def ping():
    return "pong"

@app.route("/raw")
def raw():
    return (
        f"<!doctype html><meta charset='utf-8'>"
        f"<title>{APP_NAME} — {APP_VERSION}</title>"
        "<style>body{font-family:Arial;background:#f9fafb;padding:24px}</style>"
        f"<h1>RAW OK • {APP_VERSION}</h1>"
    )

@app.route("/")
def index():
    return render_template("index.html")

# ---------- Login / Logout ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_id = (request.form.get("login_id") or "").strip()
        password = request.form.get("password") or ""
        if not login_id or not password:
            return render_template("login.html", error="Login ID and Password are required.")
        row = get_user_by_login(login_id)
        if not row or not check_password_hash(row["password_hash"], password):
            return render_template("login.html", error="Invalid credentials.")
        role = (row["role"] or "").title()
        session["user"] = {"login_id": row["login_id"], "role": role}
        target = "dashboard_admin" if role == "Admin" else "dashboard_teacher" if role == "Teacher" else "dashboard_student"
        flash("Signed in successfully.", "success")
        return redirect(url_for(target))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Signed out.", "info")
    return redirect(url_for("index"))

# ---------- Dashboards ----------
@app.route("/dashboard")
@login_required
def dashboard_root():
    role = session["user"]["role"]
    target = "dashboard_admin" if role == "Admin" else "dashboard_teacher" if role == "Teacher" else "dashboard_student"
    return redirect(url_for(target))

@app.route("/dashboard/admin")
@login_required
@role_required("Admin")
def dashboard_admin():
    return render_template("dashboard_admin.html")

@app.route("/dashboard/teacher")
@login_required
@role_required("Teacher", "Admin")
def dashboard_teacher():
    return render_template("dashboard_teacher.html")

@app.route("/dashboard/student")
@login_required
@role_required("Student", "Teacher", "Admin")
def dashboard_student():
    return render_template("dashboard_student.html")

# ---------- Admin: Schools (existing) ----------
@app.route("/admin/schools")
@login_required
@role_required("Admin")
def admin_schools_list():
    rows = list_schools()
    return render_template("admin_schools_list.html", schools=rows)

@app.route("/admin/schools/new", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_schools_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        address = (request.form.get("address") or "").strip()
        state = (request.form.get("state") or "").strip()
        district = (request.form.get("district") or "").strip()
        if not name:
            return render_template("admin_schools_new.html", error="School name is required.")
        ok = insert_school(name, address or None, state or None, district or None)
        if not ok:
            return render_template("admin_schools_new.html", error="A school with this name already exists.")
        flash("School added.", "success")
        return redirect(url_for("admin_schools_list"))
    return render_template("admin_schools_new.html")

# (edit/delete routes omitted here for brevity – keep your existing ones)

# ---------- Admin: Classes (existing) ----------
@app.route("/admin/schools/<int:school_id>/classes")
@login_required
@role_required("Admin")
def admin_classes_list(school_id):
    school = get_school(school_id)
    if not school:
        flash("School not found.", "error")
        return redirect(url_for("admin_schools_list"))
    rows = list_classes_by_school(school_id)
    return render_template("admin_classes_list.html", school=school, classes=rows)

@app.route("/admin/schools/<int:school_id>/classes/new", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_classes_new(school_id):
    school = get_school(school_id)
    if not school:
        flash("School not found.", "error")
        return redirect(url_for("admin_schools_list"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            return render_template("admin_classes_new.html", school=school, error="Class name is required.")
        ok = insert_class(school_id, name)
        if not ok:
            return render_template("admin_classes_new.html", school=school, error="This class already exists for the school.")
        flash("Class added.", "success")
        return redirect(url_for("admin_classes_list", school_id=school_id))
    return render_template("admin_classes_new.html", school=school)

# ---------- Admin: Sections (existing) ----------
@app.route("/admin/classes/<int:class_id>/sections")
@login_required
@role_required("Admin")
def admin_sections_list(class_id):
    cls = get_class(class_id)
    if not cls:
        flash("Class not found.", "error")
        return redirect(url_for("admin_schools_list"))
    rows = list_sections_by_class(class_id)
    return render_template("admin_sections_list.html", cls=cls, sections=rows)

@app.route("/admin/classes/<int:class_id>/sections/new", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_sections_new(class_id):
    cls = get_class(class_id)
    if not cls:
        flash("Class not found.", "error")
        return redirect(url_for("admin_schools_list"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            return render_template("admin_sections_new.html", cls=cls, error="Section name is required.")
        ok = insert_section(class_id, name)
        if not ok:
            return render_template("admin_sections_new.html", cls=cls, error="This section already exists for the class.")
        flash("Section added.", "success")
        return redirect(url_for("admin_sections_list", class_id=class_id))
    return render_template("admin_sections_new.html", cls=cls)

# ---------- Admin: Students ----------
@app.route("/admin/classes/<int:class_id>/sections/<int:section_id>/students")
@login_required
@role_required("Admin")
def admin_students_list(class_id, section_id):
    cls = get_class(class_id)
    if not cls:
        flash("Class not found.", "error")
        return redirect(url_for("admin_schools_list"))
    # verify section belongs to class
    secs = list_sections_by_class(class_id)
    sec = next((s for s in secs if s["id"] == section_id), None)
    if not sec:
        flash("Section not found.", "error")
        return redirect(url_for("admin_sections_list", class_id=class_id))

    rows = list_students_by_section(section_id)
    return render_template("admin_students_list.html", cls=cls, sec=sec, students=rows)

@app.route("/admin/classes/<int:class_id>/sections/<int:section_id>/students/new", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_students_new(class_id, section_id):
    cls = get_class(class_id)
    if not cls:
        flash("Class not found.", "error")
        return redirect(url_for("admin_schools_list"))
    secs = list_sections_by_class(class_id)
    sec = next((s for s in secs if s["id"] == section_id), None)
    if not sec:
        flash("Section not found.", "error")
        return redirect(url_for("admin_sections_list", class_id=class_id))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        roll_no = request.form.get("roll_no", type=int)
        admission_no = (request.form.get("admission_no") or "").strip() or None
        dob = (request.form.get("dob") or "").strip() or None
        gender = (request.form.get("gender") or "").strip() or None
        guardian_name = (request.form.get("guardian_name") or "").strip() or None
        guardian_phone = (request.form.get("guardian_phone") or "").strip() or None
        address = (request.form.get("address") or "").strip() or None

        if not name:
            return render_template("admin_students_new.html", cls=cls, sec=sec,
                                   error="Student name is required.")

        ok = insert_student(
            school_id=cls["school_id"], class_id=class_id, section_id=section_id,
            name=name, roll_no=roll_no, admission_no=admission_no, dob=dob, gender=gender,
            guardian_name=guardian_name, guardian_phone=guardian_phone, address=address
        )
        if not ok:
            return render_template("admin_students_new.html", cls=cls, sec=sec,
                                   error="Duplicate Roll No in this section or Admission No in this school.")
        flash("Student added.", "success")
        return redirect(url_for("admin_students_list", class_id=class_id, section_id=section_id))

    return render_template("admin_students_new.html", cls=cls, sec=sec)

@app.route("/admin/students/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_students_edit(student_id):
    st = get_student(student_id)
    if not st:
        flash("Student not found.", "error")
        return redirect(url_for("admin_schools_list"))

    cls = get_class(st["class_id"])
    secs = list_sections_by_class(st["class_id"])
    sec = next((s for s in secs if s["id"] == st["section_id"]), None)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        roll_no = request.form.get("roll_no", type=int)
        admission_no = (request.form.get("admission_no") or "").strip() or None
        dob = (request.form.get("dob") or "").strip() or None
        gender = (request.form.get("gender") or "").strip() or None
        guardian_name = (request.form.get("guardian_name") or "").strip() or None
        guardian_phone = (request.form.get("guardian_phone") or "").strip() or None
        address = (request.form.get("address") or "").strip() or None

        if not name:
            return render_template("admin_students_edit.html", st=st, cls=cls, sec=sec,
                                   error="Student name is required.")

        ok = update_student(
            student_id, name, roll_no, admission_no, dob, gender,
            guardian_name, guardian_phone, address
        )
        if not ok:
            return render_template("admin_students_edit.html", st=st, cls=cls, sec=sec,
                                   error="Duplicate Roll No in this section or Admission No in this school.")
        flash("Student updated.", "success")
        return redirect(url_for("admin_students_list", class_id=st["class_id"], section_id=st["section_id"]))

    return render_template("admin_students_edit.html", st=st, cls=cls, sec=sec)

@app.route("/admin/students/<int:student_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def admin_students_delete(student_id):
    st = get_student(student_id)
    if not st:
        flash("Student not found.", "error")
        return redirect(url_for("admin_schools_list"))
    deactivate_student(student_id)
    flash("Student deleted.", "info")
    return redirect(url_for("admin_students_list", class_id=st["class_id"], section_id=st["section_id"]))

# ---------- Admin: Teachers (existing) ----------
@app.route("/admin/teachers")
@login_required
@role_required("Admin")
def admin_teachers_list():
    school_id = request.args.get("school_id", type=int)
    schools = list_schools()
    rows = list_teachers(school_id)
    return render_template("admin_teachers_list.html", teachers=rows, schools=schools, selected_school_id=school_id)

# (new/edit/delete routes already in your v0.3.6 – keep them)

# ---------- Admin: Teachers (create) ----------
@app.route("/admin/teachers/new", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_teachers_new():
    from db import list_schools, insert_teacher  # local import to avoid circulars in some setups
    schools = list_schools()
    if not schools:
        flash("Create a school first.", "error")
        return redirect(url_for("admin_schools_list"))

    if request.method == "POST":
        school_id = request.form.get("school_id", type=int)
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip() or None

        if not (school_id and name and email):
            return render_template("admin_teachers_new.html", schools=schools,
                                   error="School, Name, and Email are required.")

        ok = insert_teacher(school_id, name, email, phone)
        if not ok:
            return render_template("admin_teachers_new.html", schools=schools,
                                   error="A teacher with this email already exists.")

        flash("Teacher added.", "success")
        return redirect(url_for("admin_teachers_list", school_id=school_id))

    return render_template("admin_teachers_new.html", schools=schools)

# ---------- Admin: Teachers (edit) ----------
@app.route("/admin/teachers/<int:teacher_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_teachers_edit(teacher_id):
    from db import list_schools, get_teacher, update_teacher
    teacher = get_teacher(teacher_id)
    if not teacher:
        flash("Teacher not found.", "error")
        return redirect(url_for("admin_teachers_list"))

    schools = list_schools()

    if request.method == "POST":
        school_id = request.form.get("school_id", type=int)
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip() or None

        if not (school_id and name and email):
            return render_template("admin_teachers_edit.html",
                                   teacher=teacher, schools=schools,
                                   error="School, Name, and Email are required.")

        ok = update_teacher(teacher_id, school_id, name, email, phone)
        if not ok:
            return render_template("admin_teachers_edit.html",
                                   teacher=teacher, schools=schools,
                                   error="A teacher with this email may already exist.")
        flash("Teacher updated.", "success")
        # Preserve filter if provided
        to_school = request.args.get("school_id", type=int) or school_id
        return redirect(url_for("admin_teachers_list", school_id=to_school))

    return render_template("admin_teachers_edit.html", teacher=teacher, schools=schools)

# ---------- Admin: Teachers (delete) ----------
@app.route("/admin/teachers/<int:teacher_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def admin_teachers_delete(teacher_id):
    from db import deactivate_teacher, get_teacher
    teacher = get_teacher(teacher_id)
    if not teacher:
        flash("Teacher not found.", "error")
        return redirect(url_for("admin_teachers_list"))

    deactivate_teacher(teacher_id)
    flash("Teacher deleted.", "info")
    # Preserve filter if provided
    to_school = request.form.get("school_id", type=int) or teacher["school_id"]
    return redirect(url_for("admin_teachers_list", school_id=to_school))

# ---------- Admin: Subjects (NEW) ----------
@app.route("/admin/subjects")
@login_required
@role_required("Admin")
def admin_subjects_list():
    school_id = request.args.get("school_id", type=int)
    schools = list_schools()
    rows = list_subjects_by_school(school_id or schools[0]["id"]) if schools else []
    return render_template("admin_subjects_list.html", subjects=rows, schools=schools, selected_school_id=school_id or (schools[0]["id"] if schools else None))

@app.route("/admin/subjects/new", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_subjects_new():
    schools = list_schools()
    if not schools:
        flash("Create a school first.", "error")
        return redirect(url_for("admin_schools_list"))
    if request.method == "POST":
        school_id = request.form.get("school_id", type=int)
        name = (request.form.get("name") or "").strip()
        if not (school_id and name):
            return render_template("admin_subjects_new.html", schools=schools, error="School and Subject name are required.")
        ok = insert_subject(school_id, name)
        if not ok:
            return render_template("admin_subjects_new.html", schools=schools, error="This subject already exists for the school.")
        flash("Subject added.", "success")
        return redirect(url_for("admin_subjects_list", school_id=school_id))
    return render_template("admin_subjects_new.html", schools=schools)

@app.route("/admin/subjects/<int:subject_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_subjects_edit(subject_id):
    row = get_subject(subject_id)
    if not row:
        flash("Subject not found.", "error")
        return redirect(url_for("admin_subjects_list"))
    schools = list_schools()
    if request.method == "POST":
        school_id = request.form.get("school_id", type=int)
        name = (request.form.get("name") or "").strip()
        if not (school_id and name):
            return render_template("admin_subjects_edit.html", subject=row, schools=schools, error="School and Subject name are required.")
        ok = update_subject(subject_id, school_id, name)
        if not ok:
            return render_template("admin_subjects_edit.html", subject=row, schools=schools, error="Duplicate subject for that school.")
        flash("Subject updated.", "success")
        return redirect(url_for("admin_subjects_list", school_id=school_id))
    return render_template("admin_subjects_edit.html", subject=row, schools=schools)

@app.route("/admin/subjects/<int:subject_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def admin_subjects_delete(subject_id):
    deactivate_subject(subject_id)
    flash("Subject deleted.", "info")
    return redirect(url_for("admin_subjects_list"))

# ---------- Admin: Periods (NEW) ----------
@app.route("/admin/periods")
@login_required
@role_required("Admin")
def admin_periods_list():
    school_id = request.args.get("school_id", type=int)
    schools = list_schools()
    active_school_id = school_id or (schools[0]["id"] if schools else None)
    rows = list_periods_by_school(active_school_id) if active_school_id else []
    return render_template("admin_periods_list.html", periods=rows, schools=schools, selected_school_id=active_school_id)

@app.route("/admin/periods/new", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_periods_new():
    schools = list_schools()
    if not schools:
        flash("Create a school first.", "error")
        return redirect(url_for("admin_schools_list"))
    if request.method == "POST":
        school_id = request.form.get("school_id", type=int)
        name = (request.form.get("name") or "").strip()
        start_time = (request.form.get("start_time") or "").strip() or None
        end_time = (request.form.get("end_time") or "").strip() or None
        sort_order = request.form.get("sort_order", type=int) or 0
        if not (school_id and name):
            return render_template("admin_periods_new.html", schools=schools, error="School and Period name are required.")
        ok = insert_period(school_id, name, start_time, end_time, sort_order)
        if not ok:
            return render_template("admin_periods_new.html", schools=schools, error="This period already exists for the school.")
        flash("Period added.", "success")
        return redirect(url_for("admin_periods_list", school_id=school_id))
    return render_template("admin_periods_new.html", schools=schools)

@app.route("/admin/periods/<int:period_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_periods_edit(period_id):
    row = get_period(period_id)
    if not row:
        flash("Period not found.", "error")
        return redirect(url_for("admin_periods_list"))
    schools = list_schools()
    if request.method == "POST":
        school_id = request.form.get("school_id", type=int)
        name = (request.form.get("name") or "").strip()
        start_time = (request.form.get("start_time") or "").strip() or None
        end_time = (request.form.get("end_time") or "").strip() or None
        sort_order = request.form.get("sort_order", type=int) or 0
        if not (school_id and name):
            return render_template("admin_periods_edit.html", period=row, schools=schools, error="School and Period name are required.")
        ok = update_period(period_id, school_id, name, start_time, end_time, sort_order)
        if not ok:
            return render_template("admin_periods_edit.html", period=row, schools=schools, error="Duplicate period for that school.")
        flash("Period updated.", "success")
        return redirect(url_for("admin_periods_list", school_id=school_id))
    return render_template("admin_periods_edit.html", period=row, schools=schools)

@app.route("/admin/periods/<int:period_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def admin_periods_delete(period_id):
    deactivate_period(period_id)
    flash("Period deleted.", "info")
    return redirect(url_for("admin_periods_list"))

# ---------- Admin: Teacher Assignments (NEW) ----------
@app.route("/admin/assignments")
@login_required
@role_required("Admin")
def admin_assignments_list():
    school_id = request.args.get("school_id", type=int)
    schools = list_schools()
    rows = list_assignments(school_id)
    return render_template("admin_assignments_list.html", assignments=rows, schools=schools, selected_school_id=school_id)

@app.route("/admin/assignments/new", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_assignments_new():
    # Step 1: choose school (loads options filtered to that school)
    schools = list_schools()
    school_id = request.args.get("school_id", type=int) or request.form.get("school_id", type=int)

    if request.method == "POST":
        if not school_id:
            return render_template("admin_assignments_new.html", schools=schools, error="Please choose a school.")
        teacher_id = request.form.get("teacher_id", type=int)
        subject_id = request.form.get("subject_id", type=int)
        class_id = request.form.get("class_id", type=int)
        section_id = request.form.get("section_id", type=int)
        if not all([teacher_id, subject_id, class_id, section_id]):
            return render_template("admin_assignments_new.html",
                                   schools=schools, school_id=school_id,
                                   teachers=list_teachers(school_id),
                                   subjects=list_subjects_by_school(school_id),
                                   sections=list_sections_with_class_by_school(school_id),
                                   error="All fields are required.")
        ok = insert_assignment(school_id, teacher_id, subject_id, class_id, section_id)
        if not ok:
            return render_template("admin_assignments_new.html",
                                   schools=schools, school_id=school_id,
                                   teachers=list_teachers(school_id),
                                   subjects=list_subjects_by_school(school_id),
                                   sections=list_sections_with_class_by_school(school_id),
                                   error="This assignment already exists.")
        flash("Assignment created.", "success")
        return redirect(url_for("admin_assignments_list", school_id=school_id))

    # GET
    if school_id:
        return render_template("admin_assignments_new.html",
                               schools=schools, school_id=school_id,
                               teachers=list_teachers(school_id),
                               subjects=list_subjects_by_school(school_id),
                               sections=list_sections_with_class_by_school(school_id))
    else:
        return render_template("admin_assignments_new.html", schools=schools)

@app.route("/admin/assignments/<int:assignment_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def admin_assignments_delete(assignment_id):
    deactivate_assignment(assignment_id)
    flash("Assignment deleted.", "info")
    return redirect(url_for("admin_assignments_list"))

# ---------- Admin: Schools (edit) ----------
@app.route("/admin/schools/<int:school_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def admin_schools_edit(school_id):
    school = get_school(school_id)
    if not school:
        flash("School not found.", "error")
        return redirect(url_for("admin_schools_list"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        address = (request.form.get("address") or "").strip()
        state = (request.form.get("state") or "").strip()
        district = (request.form.get("district") or "").strip()
        if not name:
            return render_template("admin_schools_edit.html", school=school, error="School name is required.")
        ok = update_school(school_id, name, address or None, state or None, district or None)
        if not ok:
            return render_template("admin_schools_edit.html", school=school, error="A school with this name already exists.")
        flash("School updated.", "success")
        return redirect(url_for("admin_schools_list"))

    return render_template("admin_schools_edit.html", school=school)

# ---------- Admin: Schools (delete) ----------
@app.route("/admin/schools/<int:school_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def admin_schools_delete(school_id):
    deactivate_school(school_id)
    flash("School deleted.", "info")
    return redirect(url_for("admin_schools_list"))


# ---------- Attendance: select (date/period/class/section) ----------
from datetime import date as _date

@app.route("/attendance/select", methods=["GET", "POST"])
@login_required
@role_required("Teacher", "Admin")
def attendance_select():
    # For MVP, let’s select school via class -> we already know class.school_id
    class_id = request.args.get("class_id", type=int)
    classes = []
    # If you have a teacher-school scoping later, filter classes accordingly.
    if class_id:
        cls = get_class(class_id)
    else:
        cls = None

    if request.method == "POST":
        class_id = request.form.get("class_id", type=int)
        section_id = request.form.get("section_id", type=int)
        period_id = request.form.get("period_id", type=int)
        date_str = request.form.get("date") or _date.today().isoformat()
        return redirect(url_for("attendance_mark",
                                class_id=class_id, section_id=section_id,
                                period_id=period_id, date=date_str))
    # Build dropdowns if class is known
    sections = list_sections_by_class(class_id) if class_id else []
    periods = []
    if cls:
        periods = list_periods_by_school(cls["school_id"])

    return render_template("attendance_select.html",
                           cls=cls, sections=sections, periods=periods,
                           today=_date.today().isoformat())

# ---------- Attendance: mark page ----------
@app.route("/attendance/mark", methods=["GET", "POST"])
@login_required
@role_required("Teacher", "Admin")
def attendance_mark():
    class_id = request.args.get("class_id", type=int) or request.form.get("class_id", type=int)
    section_id = request.args.get("section_id", type=int) or request.form.get("section_id", type=int)
    period_id = request.args.get("period_id", type=int) or request.form.get("period_id", type=int)
    date_str = request.args.get("date") or request.form.get("date") or _date.today().isoformat()

    cls = get_class(class_id)
    if not cls:
        flash("Class not found.", "error")
        return redirect(url_for("dashboard_teacher"))
    # ensure session
    session_id = get_or_create_attendance_session(
        school_id=cls["school_id"], class_id=class_id, section_id=section_id,
        period_id=period_id, date_str=date_str,
        taken_by=(current_user().get("login_id") if current_user() else None)
    )

    if request.method == "POST" and request.form.get("action") == "save":
        # form fields: status_<student_id> with values Present/Absent
        for key, value in request.form.items():
            if key.startswith("status_"):
                sid = int(key.split("_")[1])
                status = "Present" if value == "Present" else "Absent"
                upsert_attendance_mark(session_id, sid, status)
        flash("Attendance saved.", "success")
        return redirect(url_for("attendance_mark",
                                class_id=class_id, section_id=section_id,
                                period_id=period_id, date=date_str))

    # Load students + existing mark
    students = list_students_with_mark(session_id, section_id)
    # Load periods for header
    periods = list_periods_by_school(cls["school_id"])
    period = next((p for p in periods if p["id"] == period_id), None)

    return render_template("attendance_mark.html",
                           cls=cls, section_id=section_id, date_str=date_str,
                           period=period, students=students,
                           class_id=class_id, period_id=period_id)

# ---------- Attendance: daily report (class) ----------
@app.route("/attendance/report/daily/<int:class_id>", methods=["GET"])
@login_required
@role_required("Teacher", "Admin")
def attendance_report_daily(class_id):
    date_str = request.args.get("date") or _date.today().isoformat()
    cls = get_class(class_id)
    if not cls:
        flash("Class not found.", "error")
        return redirect(url_for("dashboard_teacher"))
    summary = summarize_attendance_for_class_date(class_id, date_str)
    return render_template("attendance_report_day.html",
                           cls=cls, date_str=date_str, summary=summary)

# ---------- Errors ----------
@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403, message="Forbidden: you do not have access to this page."), 403

if __name__ == "__main__":
    app.run(debug=True)
