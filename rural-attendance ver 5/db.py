# db.py
import sqlite3
from pathlib import Path

DB_PATH = Path("rural_attendance.db")

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

-- Users
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  login_id TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('Admin','Teacher','Student')),
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_users_login ON users (login_id);

-- Schools
CREATE TABLE IF NOT EXISTS schools (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  address TEXT,
  state TEXT,
  district TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_schools_active ON schools (is_active);

-- Classes
CREATE TABLE IF NOT EXISTS classes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT (datetime('now')),
  UNIQUE(school_id, name),
  FOREIGN KEY (school_id) REFERENCES schools(id)
);
CREATE INDEX IF NOT EXISTS idx_classes_school ON classes (school_id, is_active);

-- Sections
CREATE TABLE IF NOT EXISTS sections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  class_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT (datetime('now')),
  UNIQUE(class_id, name),
  FOREIGN KEY (class_id) REFERENCES classes(id)
);
CREATE INDEX IF NOT EXISTS idx_sections_class ON sections (class_id, is_active);

-- Teachers
CREATE TABLE IF NOT EXISTS teachers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  phone TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT (datetime('now')),
  FOREIGN KEY (school_id) REFERENCES schools(id)
);
CREATE INDEX IF NOT EXISTS idx_teachers_school ON teachers (school_id, is_active);

-- Subjects (unique per school)
CREATE TABLE IF NOT EXISTS subjects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT (datetime('now')),
  UNIQUE(school_id, name),
  FOREIGN KEY (school_id) REFERENCES schools(id)
);
CREATE INDEX IF NOT EXISTS idx_subjects_school ON subjects (school_id, is_active);

-- Periods (named slots per school)
CREATE TABLE IF NOT EXISTS periods (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  start_time TEXT, -- "09:00"
  end_time TEXT,   -- "09:45"
  sort_order INTEGER DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT (datetime('now')),
  UNIQUE(school_id, name),
  FOREIGN KEY (school_id) REFERENCES schools(id)
);
CREATE INDEX IF NOT EXISTS idx_periods_school ON periods (school_id, is_active);

-- Teacher Assignments: which teacher teaches what/where
CREATE TABLE IF NOT EXISTS teacher_assignments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id INTEGER NOT NULL,
  teacher_id INTEGER NOT NULL,
  subject_id INTEGER NOT NULL,
  class_id INTEGER NOT NULL,
  section_id INTEGER NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT (datetime('now')),
  UNIQUE(teacher_id, subject_id, class_id, section_id),
  FOREIGN KEY(school_id) REFERENCES schools(id),
  FOREIGN KEY(teacher_id) REFERENCES teachers(id),
  FOREIGN KEY(subject_id) REFERENCES subjects(id),
  FOREIGN KEY(class_id) REFERENCES classes(id),
  FOREIGN KEY(section_id) REFERENCES sections(id)
);
CREATE INDEX IF NOT EXISTS idx_assign_school ON teacher_assignments (school_id, is_active);

-- Daily timetable entries for per-day schedules (NEW)
CREATE TABLE IF NOT EXISTS timetable_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id INTEGER NOT NULL,
  date TEXT NOT NULL,           -- YYYY-MM-DD
  period_id INTEGER NOT NULL,
  class_id INTEGER NOT NULL,
  section_id INTEGER NOT NULL,
  subject_id INTEGER NOT NULL,
  teacher_id INTEGER NOT NULL,
  created_at DATETIME DEFAULT (datetime('now')),
  UNIQUE(school_id, date, period_id, class_id, section_id),
  FOREIGN KEY(school_id) REFERENCES schools(id),
  FOREIGN KEY(period_id) REFERENCES periods(id),
  FOREIGN KEY(class_id) REFERENCES classes(id),
  FOREIGN KEY(section_id) REFERENCES sections(id),
  FOREIGN KEY(subject_id) REFERENCES subjects(id),
  FOREIGN KEY(teacher_id) REFERENCES teachers(id)
);
CREATE INDEX IF NOT EXISTS idx_tt_school_date ON timetable_entries (school_id, date);

-- Students (per school/class/section)
CREATE TABLE IF NOT EXISTS students (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id INTEGER NOT NULL,
  class_id INTEGER NOT NULL,
  section_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  roll_no INTEGER,                 -- roll within section
  admission_no TEXT,               -- optional unique per school
  dob TEXT,                        -- YYYY-MM-DD
  gender TEXT,                     -- optional
  guardian_name TEXT,
  guardian_phone TEXT,
  address TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT (datetime('now')),
  UNIQUE(section_id, roll_no),
  UNIQUE(school_id, admission_no),
  FOREIGN KEY (school_id) REFERENCES schools(id),
  FOREIGN KEY (class_id) REFERENCES classes(id),
  FOREIGN KEY (section_id) REFERENCES sections(id)
);
CREATE INDEX IF NOT EXISTS idx_students_school ON students (school_id, is_active);
CREATE INDEX IF NOT EXISTS idx_students_section ON students (section_id, is_active);

-- Attendance sessions (one row per class/section/period/date)
CREATE TABLE IF NOT EXISTS attendance_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id INTEGER NOT NULL,
  class_id INTEGER NOT NULL,
  section_id INTEGER NOT NULL,
  period_id INTEGER NOT NULL,
  date TEXT NOT NULL, -- YYYY-MM-DD
  taken_by TEXT,      -- login_id of teacher/admin
  taken_at DATETIME DEFAULT (datetime('now')),
  UNIQUE (school_id, class_id, section_id, period_id, date),
  FOREIGN KEY (school_id) REFERENCES schools(id),
  FOREIGN KEY (class_id) REFERENCES classes(id),
  FOREIGN KEY (section_id) REFERENCES sections(id),
  FOREIGN KEY (period_id) REFERENCES periods(id)
);
CREATE INDEX IF NOT EXISTS idx_att_sess_school_date ON attendance_sessions (school_id, date);

-- Attendance marks (one row per student in a session)
CREATE TABLE IF NOT EXISTS attendance_marks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  student_id INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('Present','Absent')),
  marked_at DATETIME DEFAULT (datetime('now')),
  UNIQUE (session_id, student_id),
  FOREIGN KEY (session_id) REFERENCES attendance_sessions(id),
  FOREIGN KEY (student_id) REFERENCES students(id)
);
CREATE INDEX IF NOT EXISTS idx_att_marks_session ON attendance_marks (session_id);

"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def bootstrap():
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)

# ---- Users ----
def get_user_by_login(login_id: str):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM users WHERE login_id = ? AND is_active = 1",
            (login_id,),
        )
        return cur.fetchone()

def insert_user(login_id: str, password_hash: str, role: str) -> bool:
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO users(login_id, password_hash, role) VALUES(?,?,?)",
                (login_id, password_hash, role),
            )
        return True
    except sqlite3.IntegrityError:
        return False

# ---- Schools ----
def list_schools():
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT id, name, address, state, district, is_active, created_at
            FROM schools
            WHERE is_active = 1
            ORDER BY name COLLATE NOCASE
        """)
        return cur.fetchall()

def insert_school(name: str, address: str | None = None,
                  state: str | None = None, district: str | None = None) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO schools (name, address, state, district)
                VALUES (?,?,?,?)
            """, (name.strip(), address, state, district))
        return True
    except sqlite3.IntegrityError:
        return False

def get_school(school_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT id, name, address, state, district, is_active, created_at
            FROM schools WHERE id = ? AND is_active = 1
        """, (school_id,))
        return cur.fetchone()

def update_school(school_id: int, name: str,
                  address: str | None, state: str | None, district: str | None) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE schools
                SET name = ?, address = ?, state = ?, district = ?
                WHERE id = ? AND is_active = 1
            """, (name.strip(), address, state, district, school_id))
        return True
    except sqlite3.IntegrityError:
        return False

def deactivate_school(school_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE schools SET is_active = 0 WHERE id = ?", (school_id,))

# ---- Classes ----
def list_classes_by_school(school_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT id, school_id, name, is_active, created_at
            FROM classes
            WHERE school_id = ? AND is_active = 1
            ORDER BY 
              CASE name
                WHEN 'LKG' THEN 0 WHEN 'UKG' THEN 1
                ELSE 2
              END,
              name COLLATE NOCASE
        """, (school_id,))
        return cur.fetchall()

def insert_class(school_id: int, name: str) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO classes (school_id, name)
                VALUES (?, ?)
            """, (school_id, name.strip()))
        return True
    except sqlite3.IntegrityError:
        return False

def get_class(class_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT c.id, c.school_id, c.name, c.is_active, c.created_at,
                   s.name AS school_name
            FROM classes c
            JOIN schools s ON s.id = c.school_id
            WHERE c.id = ? AND c.is_active = 1 AND s.is_active = 1
        """, (class_id,))
        return cur.fetchone()

# ---- Sections ----
def list_sections_by_class(class_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT id, class_id, name, is_active, created_at
            FROM sections
            WHERE class_id = ? AND is_active = 1
            ORDER BY name COLLATE NOCASE
        """, (class_id,))
        return cur.fetchall()

def insert_section(class_id: int, name: str) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO sections (class_id, name)
                VALUES (?, ?)
            """, (class_id, name.strip()))
        return True
    except sqlite3.IntegrityError:
        return False

# Helper: sections with class names for a school (for assignment form)
def list_sections_with_class_by_school(school_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT sec.id AS section_id, sec.name AS section_name,
                   cls.id AS class_id, cls.name AS class_name
            FROM sections sec
            JOIN classes cls ON cls.id = sec.class_id
            WHERE cls.school_id = ? AND sec.is_active = 1 AND cls.is_active = 1
            ORDER BY cls.name COLLATE NOCASE, sec.name COLLATE NOCASE
        """, (school_id,))
        return cur.fetchall()

# ---- Teachers ----
def list_teachers(school_id: int | None = None):
    with get_conn() as conn:
        if school_id:
            cur = conn.execute("""
                SELECT t.id, t.name, t.email, t.phone, t.created_at,
                       s.id AS school_id, s.name AS school_name
                FROM teachers t
                JOIN schools s ON s.id = t.school_id
                WHERE t.is_active = 1 AND s.is_active = 1 AND t.school_id = ?
                ORDER BY t.name COLLATE NOCASE
            """, (school_id,))
        else:
            cur = conn.execute("""
                SELECT t.id, t.name, t.email, t.phone, t.created_at,
                       s.id AS school_id, s.name AS school_name
                FROM teachers t
                JOIN schools s ON s.id = t.school_id
                WHERE t.is_active = 1 AND s.is_active = 1
                ORDER BY s.name COLLATE NOCASE, t.name COLLATE NOCASE
            """)
        return cur.fetchall()

def insert_teacher(school_id: int, name: str, email: str, phone: str | None):
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO teachers (school_id, name, email, phone)
                VALUES (?,?,?,?)
            """, (school_id, name.strip(), email.strip().lower(), phone))
        return True
    except sqlite3.IntegrityError:
        return False

def get_teacher(teacher_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT t.id, t.school_id, t.name, t.email, t.phone, t.is_active, t.created_at,
                   s.name AS school_name
            FROM teachers t
            JOIN schools s ON s.id = t.school_id
            WHERE t.id = ? AND t.is_active = 1 AND s.is_active = 1
        """, (teacher_id,))
        return cur.fetchone()

def update_teacher(teacher_id: int, school_id: int, name: str, email: str, phone: str | None):
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE teachers
                SET school_id = ?, name = ?, email = ?, phone = ?
                WHERE id = ? AND is_active = 1
            """, (school_id, name.strip(), email.strip().lower(), phone, teacher_id))
        return True
    except sqlite3.IntegrityError:
        return False

def deactivate_teacher(teacher_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE teachers SET is_active = 0 WHERE id = ?", (teacher_id,))

# ---- Subjects ----
def list_subjects_by_school(school_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT id, school_id, name, is_active, created_at
            FROM subjects
            WHERE school_id = ? AND is_active = 1
            ORDER BY name COLLATE NOCASE
        """, (school_id,))
        return cur.fetchall()

def insert_subject(school_id: int, name: str) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO subjects (school_id, name)
                VALUES (?,?)
            """, (school_id, name.strip()))
        return True
    except sqlite3.IntegrityError:
        return False

def get_subject(subject_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT sub.id, sub.school_id, sub.name, sub.is_active, sub.created_at,
                   s.name AS school_name
            FROM subjects sub
            JOIN schools s ON s.id = sub.school_id
            WHERE sub.id = ? AND sub.is_active = 1 AND s.is_active = 1
        """, (subject_id,))
        return cur.fetchone()

def update_subject(subject_id: int, school_id: int, name: str) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE subjects
                SET school_id = ?, name = ?
                WHERE id = ? AND is_active = 1
            """, (school_id, name.strip(), subject_id))
        return True
    except sqlite3.IntegrityError:
        return False

def deactivate_subject(subject_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE subjects SET is_active = 0 WHERE id = ?", (subject_id,))

# ---- Periods ----
def list_periods_by_school(school_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT id, school_id, name, start_time, end_time, sort_order, is_active, created_at
            FROM periods
            WHERE school_id = ? AND is_active = 1
            ORDER BY sort_order, name COLLATE NOCASE
        """, (school_id,))
        return cur.fetchall()

def insert_period(school_id: int, name: str, start_time: str | None, end_time: str | None, sort_order: int = 0) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO periods (school_id, name, start_time, end_time, sort_order)
                VALUES (?,?,?,?,?)
            """, (school_id, name.strip(), start_time, end_time, sort_order))
        return True
    except sqlite3.IntegrityError:
        return False

def get_period(period_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT p.id, p.school_id, p.name, p.start_time, p.end_time, p.sort_order, p.is_active, p.created_at,
                   s.name AS school_name
            FROM periods p
            JOIN schools s ON s.id = p.school_id
            WHERE p.id = ? AND p.is_active = 1 AND s.is_active = 1
        """, (period_id,))
        return cur.fetchone()

def update_period(period_id: int, school_id: int, name: str, start_time: str | None, end_time: str | None, sort_order: int) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE periods
                SET school_id = ?, name = ?, start_time = ?, end_time = ?, sort_order = ?
                WHERE id = ? AND is_active = 1
            """, (school_id, name.strip(), start_time, end_time, sort_order, period_id))
        return True
    except sqlite3.IntegrityError:
        return False

def deactivate_period(period_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE periods SET is_active = 0 WHERE id = ?", (period_id,))

# ---- Teacher Assignments ----
def list_assignments(school_id: int | None = None):
    with get_conn() as conn:
        base = """
            SELECT ta.id, ta.school_id,
                   t.name AS teacher_name, t.id AS teacher_id,
                   sub.name AS subject_name, sub.id AS subject_id,
                   c.name AS class_name, c.id AS class_id,
                   sec.name AS section_name, sec.id AS section_id,
                   ta.created_at
            FROM teacher_assignments ta
            JOIN teachers t ON t.id = ta.teacher_id
            JOIN subjects sub ON sub.id = ta.subject_id
            JOIN classes c ON c.id = ta.class_id
            JOIN sections sec ON sec.id = ta.section_id
            WHERE ta.is_active = 1 AND t.is_active = 1 AND sub.is_active = 1 AND c.is_active = 1 AND sec.is_active = 1
        """
        if school_id:
            cur = conn.execute(base + " AND ta.school_id = ? ORDER BY teacher_name COLLATE NOCASE", (school_id,))
        else:
            cur = conn.execute(base + " ORDER BY ta.school_id, teacher_name COLLATE NOCASE")
        return cur.fetchall()

def insert_assignment(school_id: int, teacher_id: int, subject_id: int, class_id: int, section_id: int) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO teacher_assignments (school_id, teacher_id, subject_id, class_id, section_id)
                VALUES (?,?,?,?,?)
            """, (school_id, teacher_id, subject_id, class_id, section_id))
        return True
    except sqlite3.IntegrityError:
        return False

def deactivate_assignment(assignment_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE teacher_assignments SET is_active = 0 WHERE id = ?", (assignment_id,))

# ---- Timetable entries (NEW) ----
def insert_timetable_entry(school_id: int, date: str, period_id: int,
                           class_id: int, section_id: int,
                           subject_id: int, teacher_id: int) -> bool:
    """
    Insert one timetable cell. Safe to call repeatedly: UNIQUE constraint avoids duplicates.
    date must be 'YYYY-MM-DD'.
    """
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO timetable_entries
                  (school_id, date, period_id, class_id, section_id, subject_id, teacher_id)
                VALUES (?,?,?,?,?,?,?)
            """, (school_id, date, period_id, class_id, section_id, subject_id, teacher_id))
        return True
    except sqlite3.IntegrityError:
        return False

# ---- Students ----
def list_students_by_section(section_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT st.id, st.school_id, st.class_id, st.section_id,
                   st.name, st.roll_no, st.admission_no, st.dob, st.gender,
                   st.guardian_name, st.guardian_phone, st.address, st.created_at,
                   c.name AS class_name, s.name AS section_name
            FROM students st
            JOIN classes c ON c.id = st.class_id
            JOIN sections s ON s.id = st.section_id
            WHERE st.section_id = ? AND st.is_active = 1
            ORDER BY COALESCE(st.roll_no, 999999), st.name COLLATE NOCASE
        """, (section_id,))
        return cur.fetchall()

def insert_student(school_id: int, class_id: int, section_id: int,
                   name: str, roll_no: int | None, admission_no: str | None,
                   dob: str | None, gender: str | None,
                   guardian_name: str | None, guardian_phone: str | None,
                   address: str | None) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO students
                  (school_id, class_id, section_id, name, roll_no, admission_no, dob, gender,
                   guardian_name, guardian_phone, address)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (school_id, class_id, section_id, name.strip(),
                  roll_no, (admission_no or None), (dob or None), (gender or None),
                  (guardian_name or None), (guardian_phone or None), (address or None)))
        return True
    except sqlite3.IntegrityError:
        return False

def get_student(student_id: int):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT st.*, c.name AS class_name, s.name AS section_name
            FROM students st
            JOIN classes c ON c.id = st.class_id
            JOIN sections s ON s.id = st.section_id
            WHERE st.id = ? AND st.is_active = 1
        """, (student_id,))
        return cur.fetchone()

def update_student(student_id: int,
                   name: str, roll_no: int | None, admission_no: str | None,
                   dob: str | None, gender: str | None,
                   guardian_name: str | None, guardian_phone: str | None,
                   address: str | None) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE students
                SET name = ?, roll_no = ?, admission_no = ?, dob = ?, gender = ?,
                    guardian_name = ?, guardian_phone = ?, address = ?
                WHERE id = ? AND is_active = 1
            """, (name.strip(), roll_no, (admission_no or None), (dob or None), (gender or None),
                  (guardian_name or None), (guardian_phone or None), (address or None),
                  student_id))
        return True
    except sqlite3.IntegrityError:
        return False

def deactivate_student(student_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE students SET is_active = 0 WHERE id = ?", (student_id,))


# ---- Attendance (sessions + marks) ----
def get_or_create_attendance_session(school_id: int, class_id: int, section_id: int,
                                     period_id: int, date_str: str, taken_by: str | None):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT id FROM attendance_sessions
            WHERE school_id=? AND class_id=? AND section_id=? AND period_id=? AND date=?
        """, (school_id, class_id, section_id, period_id, date_str))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur = conn.execute("""
            INSERT INTO attendance_sessions (school_id, class_id, section_id, period_id, date, taken_by)
            VALUES (?,?,?,?,?,?)
        """, (school_id, class_id, section_id, period_id, date_str, taken_by))
        return cur.lastrowid

def list_students_with_mark(session_id: int, section_id: int):
    # Return students of section with joined status if already marked
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT st.id AS student_id, st.name, st.roll_no,
                   am.status
            FROM students st
            LEFT JOIN attendance_marks am
              ON am.student_id = st.id AND am.session_id = ?
            WHERE st.section_id = ? AND st.is_active = 1
            ORDER BY COALESCE(st.roll_no, 999999), st.name COLLATE NOCASE
        """, (session_id, section_id))
        return cur.fetchall()

def upsert_attendance_mark(session_id: int, student_id: int, status: str) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO attendance_marks (session_id, student_id, status)
                VALUES (?,?,?)
                ON CONFLICT(session_id, student_id) DO UPDATE SET status = excluded.status
            """, (session_id, student_id, status))
        return True
    except sqlite3.IntegrityError:
        return False

def summarize_attendance_for_class_date(class_id: int, date_str: str):
    # returns [(section_id, section_name, present, absent, total)]
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT sec.id AS section_id, sec.name AS section_name,
                   SUM(CASE am.status WHEN 'Present' THEN 1 ELSE 0 END) AS present,
                   SUM(CASE am.status WHEN 'Absent' THEN 1 ELSE 0 END)  AS absent,
                   COUNT(am.id) AS total
            FROM sections sec
            JOIN attendance_sessions ses ON ses.section_id = sec.id
            LEFT JOIN attendance_marks am ON am.session_id = ses.id
            WHERE sec.class_id = ? AND ses.date = ?
            GROUP BY sec.id, sec.name
            ORDER BY sec.name COLLATE NOCASE
        """, (class_id, date_str))
        return cur.fetchall()

