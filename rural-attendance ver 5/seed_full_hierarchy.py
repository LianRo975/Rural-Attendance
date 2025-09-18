# seed_full_hierarchy.py
"""
Fast seeder with optional purge + smaller defaults.

Creates (quick defaults):
- 10 schools across India (can change with --schools)
- Classes (LKG, UKG, 1..12) with Section A (only)
- Subjects per school
- 8 named periods with times + order per school (change with --periods)
- 40 teachers total (distributed) (change with --teachers)
- LIMITED students per class in Section A (default 10 via --students-per-section)
- Teacher assignments (teacher ↔ subject ↔ class/section)
- 6 timetable days (Mon–Sat only) using 8 periods/day

Usage:
  python seed_full_hierarchy.py --purge
Options:
  --schools 10 --teachers 40 --periods 8 --days 6 --students-per-section 10
  --create-teacher-logins  (password: Teacher@123)
  --purge                  (deletes all seeded domain tables but keeps users)
  --purge-users            (also deletes users; use with care)
"""

import argparse
import random
from datetime import date, timedelta, datetime
from pathlib import Path
from werkzeug.security import generate_password_hash

from db import (
    DB_PATH, bootstrap, get_conn,
    # schools
    list_schools, insert_school,
    # classes/sections
    list_classes_by_school, insert_class, list_sections_by_class, insert_section, get_class,
    # teachers + users
    list_teachers, insert_teacher, insert_user, get_user_by_login,
    # subjects
    list_subjects_by_school, insert_subject,
    # periods
    list_periods_by_school, insert_period,
    # assignments
    insert_assignment,
    # timetable
    insert_timetable_entry
)

# ---------- Static data ----------
STATE_CITY = [
  ("Karnataka","Bengaluru"), ("Karnataka","Mysuru"), ("Karnataka","Hubballi"),
  ("Maharashtra","Mumbai"), ("Maharashtra","Pune"), ("Maharashtra","Nagpur"),
  ("Tamil Nadu","Chennai"), ("Tamil Nadu","Coimbatore"), ("Tamil Nadu","Madurai"),
  ("Telangana","Hyderabad"), ("Andhra Pradesh","Vijayawada"), ("Kerala","Thiruvananthapuram"),
  ("Gujarat","Ahmedabad"), ("Gujarat","Surat"), ("West Bengal","Kolkata"), ("Odisha","Bhubaneswar"),
  ("Delhi","New Delhi"), ("Haryana","Gurugram"), ("Punjab","Amritsar"), ("Rajasthan","Jaipur"),
  ("Uttar Pradesh","Lucknow"), ("Uttar Pradesh","Kanpur"), ("Bihar","Patna"),
  ("Jharkhand","Ranchi"), ("Chhattisgarh","Raipur"), ("Madhya Pradesh","Bhopal"),
  ("Madhya Pradesh","Indore"), ("Assam","Guwahati"), ("J&K","Srinagar"),
  ("Uttarakhand","Dehradun"), ("Himachal Pradesh","Shimla"), ("Goa","Panaji"),
  ("Meghalaya","Shillong"), ("Tripura","Agartala"), ("Manipur","Imphal"),
  ("Nagaland","Kohima"), ("Sikkim","Gangtok"), ("Arunachal Pradesh","Itanagar"),
  ("Mizoram","Aizawl"), ("Puducherry","Puducherry"), ("Chandigarh","Chandigarh"),
  ("Ladakh","Leh"), ("Dadra & Nagar Haveli","Silvassa"), ("Daman & Diu","Daman"),
  ("Lakshadweep","Kavaratti"), ("Andaman & Nicobar","Port Blair"), ("Haryana","Faridabad"),
  ("Rajasthan","Udaipur"), ("Punjab","Ludhiana"), ("Kerala","Kochi"), ("Tamil Nadu","Trichy"),
]

FIRST_NAMES = [
  "Aarav","Vivaan","Aditya","Vihaan","Arjun","Kabir","Karthik","Rohan","Rahul","Aakash",
  "Ananya","Diya","Isha","Kavya","Mira","Riya","Saanvi","Tanvi","Neha","Pooja",
  "Ishaan","Ritvik","Siddharth","Aman","Nikhil","Rakesh","Varun","Harsh","Suresh","Deepak",
  "Sneha","Pallavi","Asha","Nandini","Meera","Bhavana","Priya","Shreya","Aishwarya","Divya"
]
LAST_NAMES = [
  "Sharma","Verma","Reddy","Iyer","Patel","Naidu","Gowda","Shetty","Singh","Khan",
  "Das","Nair","Kulkarni","Bose","Rao","Gupta","Agarwal","Mishra","Ghosh","Chopra",
  "Banerjee","Chatterjee","Bhattacharya","Tripathi","Yadav","Thakur","Jain","Mehta","Pawar","Kamble"
]

CLASS_NAMES = ["LKG","UKG"] + [str(i) for i in range(1, 13)]
SECTION_NAME = "A"   # only one section to keep data smaller/faster

SUBJECTS_PRIMARY = ["English","Hindi","Mathematics","EVS","General Knowledge","Arts","Physical Education"]
SUBJECTS_MIDDLE  = ["English","Hindi","Mathematics","Science","Social Science","Computer Science","Arts","Physical Education"]
SUBJECTS_HIGH    = ["English","Hindi","Mathematics","Physics","Chemistry","Biology","History","Geography","Civics","Economics","Computer Science","Physical Education"]

def subjects_for_class(cls_name: str):
    if cls_name in ("LKG","UKG","1","2","3","4","5"):
        return SUBJECTS_PRIMARY
    if cls_name in ("6","7","8"):
        return SUBJECTS_MIDDLE
    return SUBJECTS_HIGH

# ---------- Purge (fast reset) ----------
PURGE_ORDER_CHILD_FIRST = [
    "timetable_entries",
    "teacher_assignments",
    "students",
    "periods",
    "subjects",
    "teachers",
    "sections",
    "classes",
    "schools",
    # users optionally
]

def purge_all(purge_users: bool = False):
    with get_conn() as conn:
        conn.execute("PRAGMA foreign_keys=OFF;")
        cur = conn.cursor()
        for t in PURGE_ORDER_CHILD_FIRST:
            cur.execute(f"DELETE FROM {t};")
        if purge_users:
            cur.execute("DELETE FROM users;")
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON;")

# ---------- Helpers ----------
def ensure_school(name: str, state: str, district: str):
    insert_school(name, state=state, district=district, address=None)
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM schools WHERE name = ? AND is_active = 1", (name,))
        return cur.fetchone()

def ensure_classes_sections(school_id: int):
    existing = {c["name"] for c in list_classes_by_school(school_id)}
    for cname in CLASS_NAMES:
        if cname not in existing:
            insert_class(school_id, cname)
    for c in list_classes_by_school(school_id):
        secs = {s["name"] for s in list_sections_by_class(c["id"])}
        if SECTION_NAME not in secs:
            insert_section(c["id"], SECTION_NAME)

def ensure_subjects_for_school(school_id: int):
    current = {s["name"].lower() for s in list_subjects_by_school(school_id)}
    needed = set()
    for cname in CLASS_NAMES:
        for sub in subjects_for_class(cname):
            if sub.lower() not in current:
                needed.add(sub)
    for sub in sorted(needed):
        insert_subject(school_id, sub)

def ensure_periods(school_id: int, total_periods: int):
    have = list_periods_by_school(school_id)
    if len(have) >= total_periods:
        return
    start = datetime.strptime("08:30", "%H:%M")
    for i in range(1, total_periods + 1):
        pstart = start + timedelta(minutes=(i-1)*45)  # 40m + 5m gap
        pend   = pstart + timedelta(minutes=40)
        insert_period(school_id, f"Period {i}", pstart.strftime("%H:%M"), pend.strftime("%H:%M"), i)

def make_email(base: str, idx: int) -> str:
    return f"{base}{idx:03d}@school.in"

def seed_teachers_across_schools(schools: list, total_teachers: int):
    """
    Distribute roughly evenly: >=1 per school, rest round-robin.
    Use lastrowid to avoid extra SELECTs.
    """
    created = []
    idx = 1
    with get_conn() as conn:
        cur = conn.cursor()
        # baseline one per school
        for s in schools:
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            email = make_email("teacher", idx)
            phone = f"+91{random.randint(7000000000, 9999999999)}"
            try:
                cur.execute(
                    "INSERT INTO teachers (school_id, name, email, phone) VALUES (?,?,?,?)",
                    (s["id"], name, email, phone)
                )
                created.append((cur.lastrowid, s["id"]))
            except Exception:
                pass
            idx += 1
        # remaining, round-robin
        remaining = max(0, total_teachers - len(created))
        si = 0
        for _ in range(remaining):
            s = schools[si % len(schools)]
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            email = make_email("teacher", idx)
            phone = f"+91{random.randint(7000000000, 9999999999)}"
            try:
                cur.execute(
                    "INSERT INTO teachers (school_id, name, email, phone) VALUES (?,?,?,?)",
                    (s["id"], name, email, phone)
                )
                created.append((cur.lastrowid, s["id"]))
            except Exception:
                pass
            idx += 1
            si += 1
        conn.commit()
    return created  # [(teacher_id, school_id), ...]

def ensure_teacher_logins():
    with get_conn() as conn:
        rows = conn.execute("SELECT email FROM teachers WHERE is_active = 1").fetchall()
    pwd_hash = generate_password_hash("Teacher@123")
    for r in rows:
        email = r["email"]
        if not get_user_by_login(email):
            insert_user(email, pwd_hash, "Teacher")

def seed_assignments_for_school(school_id: int):
    """
    Round-robin teachers across class/section subjects.
    Uses fewer commits by batching within a connection.
    """
    with get_conn() as conn:
        teacher_rows = conn.execute(
            "SELECT id FROM teachers WHERE school_id = ? AND is_active = 1 ORDER BY id",
            (school_id,)
        ).fetchall()
        if not teacher_rows:
            return 0
        teacher_ids = [r["id"] for r in teacher_rows]

        subs = list_subjects_by_school(school_id)
        subs_by_name = {s["name"]: s["id"] for s in subs}

        classes = list_classes_by_school(school_id)
        assigned = 0
        ti = 0
        cur = conn.cursor()
        for c in classes:
            class_subs = subjects_for_class(c["name"])
            secs = list_sections_by_class(c["id"])
            secA = next((s for s in secs if s["name"] == "A"), None)
            if not secA:
                continue
            for sub_name in class_subs:
                sub_id = subs_by_name.get(sub_name)
                if not sub_id:
                    continue
                teacher_id = teacher_ids[ti % len(teacher_ids)]
                ti += 1
                try:
                    cur.execute("""
                        INSERT INTO teacher_assignments (school_id, teacher_id, subject_id, class_id, section_id)
                        VALUES (?,?,?,?,?)
                    """, (school_id, teacher_id, sub_id, c["id"], secA["id"]))
                    assigned += 1
                except Exception:
                    pass
        conn.commit()
    return assigned

def daterange(start: date, days: int):
    for i in range(days):
        yield start + timedelta(days=i)

def is_sunday(d: date) -> bool:
    return d.weekday() == 6

def build_timetable_fast(school_id: int, days: int, periods_per_day: int = 8):
    """
    For next `days` (Mon–Sat only), create entries for Section A of each class
    using first N periods/day. Batches inserts for speed.
    """
    periods = sorted(list_periods_by_school(school_id), key=lambda p: (p["sort_order"], p["name"]))[:periods_per_day]
    if not periods:
        return 0
    classes = list_classes_by_school(school_id)

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT ta.class_id, ta.section_id, ta.subject_id, ta.teacher_id
            FROM teacher_assignments ta
            WHERE ta.school_id = ? AND ta.is_active = 1
            ORDER BY ta.class_id, ta.section_id, ta.subject_id
        """, (school_id,)).fetchall()
        teachers = [r["id"] for r in conn.execute(
            "SELECT id FROM teachers WHERE school_id = ? AND is_active = 1 ORDER BY id", (school_id,)
        ).fetchall()]
        subjects = [r["id"] for r in conn.execute(
            "SELECT id FROM subjects WHERE school_id = ? AND is_active = 1 ORDER BY name", (school_id,)
        ).fetchall()]

        assignment_map = {}
        for r in rows:
            key = (r["class_id"], r["section_id"])
            assignment_map.setdefault(key, []).append((r["subject_id"], r["teacher_id"]))

        cur = conn.cursor()
        created = 0
        today = date.today()
        for d in daterange(today, days):
            if is_sunday(d):
                continue
            di = d.isoformat()
            for c in classes:
                secs = list_sections_by_class(c["id"])
                secA = next((s for s in secs if s["name"] == "A"), None)
                if not secA:
                    continue
                key = (c["id"], secA["id"])
                rotation = assignment_map.get(key, [])
                rot_len = len(rotation) if rotation else 0
                for pi, p in enumerate(periods):
                    if rotation:
                        subj_id, teach_id = rotation[(pi) % rot_len]
                    else:
                        subj_id = subjects[(c["id"] + pi) % len(subjects)]
                        teach_id = teachers[(c["id"] + pi) % len(teachers)]
                    try:
                        cur.execute("""
                            INSERT INTO timetable_entries
                              (school_id, date, period_id, class_id, section_id, subject_id, teacher_id)
                            VALUES (?,?,?,?,?,?,?)
                        """, (school_id, di, p["id"], c["id"], secA["id"], subj_id, teach_id))
                        created += 1
                    except Exception:
                        pass
        conn.commit()
    return created

def seed_students_one_section_per_class(school_id: int, students_per_section: int):
    """
    Create limited students for Section A of each class. Names are synthetic.
    Roll numbers auto 1..N; admission_no = S<school>-C<class>-<roll>.
    """
    created = 0
    with get_conn() as conn:
        cur = conn.cursor()
        classes = list_classes_by_school(school_id)
        for c in classes:
            secs = list_sections_by_class(c["id"])
            secA = next((s for s in secs if s["name"] == "A"), None)
            if not secA:
                continue
            for rn in range(1, students_per_section + 1):
                name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                admission_no = f"S{school_id}-C{c['id']}-{rn:03d}"
                try:
                    cur.execute("""
                        INSERT INTO students
                          (school_id, class_id, section_id, name, roll_no, admission_no)
                        VALUES (?,?,?,?,?,?)
                    """, (school_id, c["id"], secA["id"], name, rn, admission_no))
                    created += 1
                except Exception:
                    pass
        conn.commit()
    return created

# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schools", type=int, default=10, help="Number of schools (fast default: 10)")
    ap.add_argument("--teachers", type=int, default=40, help="Total teachers across all schools (fast default: 40)")
    ap.add_argument("--periods", type=int, default=8, help="Number of period definitions per school (fast default: 8)")
    ap.add_argument("--days", type=int, default=6, help="Days of timetable (Mon–Sat only, fast default: 6)")
    ap.add_argument("--students-per-section", type=int, default=10, help="Students per class (Section A only)")
    ap.add_argument("--create-teacher-logins", action="store_true", help="Also create user logins (Teacher@123)")
    ap.add_argument("--purge", action="store_true", help="Delete existing data before seeding (keeps users)")
    ap.add_argument("--purge-users", action="store_true", help="Also delete users (use with care)")
    args = ap.parse_args()

    print(f"→ Using database: {Path(DB_PATH).resolve()}")
    print("→ Bootstrapping schema (if needed)…")
    bootstrap()

    if args.purge or args.purge_users:
        print("⚠ Purging existing data…")
        purge_all(purge_users=args.purge_users)
        print("✔ Purge complete.")

    # 1) Create up to N schools
    print("→ Creating schools…")
    schools = []
    for i in range(args.schools):
        state, city = STATE_CITY[i % len(STATE_CITY)]
        name = f"Government High School, {city} #{(i//len(STATE_CITY))+1}"
        srow = ensure_school(name, state, city)
        schools.append(srow)
    print(f"✔ Schools ready: {len(schools)}")

    # 2) Per school: classes/section A, subjects, periods (batched)
    print("→ Ensuring classes, sections, subjects, periods…")
    for s in schools:
        ensure_classes_sections(s["id"])
        ensure_subjects_for_school(s["id"])
        ensure_periods(s["id"], args.periods)
    print("✔ Structure ensured per school.")

    # 3) Teachers (distributed)
    print("→ Seeding teachers across schools…")
    created_teachers = seed_teachers_across_schools(schools, args.teachers)
    print(f"✔ Teachers distributed: target={args.teachers}, created_at_least={len(created_teachers)}")

    if args.create_teacher_logins:
        ensure_teacher_logins()
        print("✔ Teacher logins created where missing (password: Teacher@123)")

    # 4) Assignments per school
    print("→ Creating teacher assignments…")
    total_assigned = 0
    for s in schools:
        total_assigned += seed_assignments_for_school(s["id"])
    print(f"✔ Teacher assignments created: ~{total_assigned}")

    # 5) Students (limited, Section A only)
    print(f"→ Creating students (Section A only, {args.students_per_section} per class)…")
    total_students = 0
    for s in schools:
        total_students += seed_students_one_section_per_class(s["id"], args.students_per_section)
    print(f"✔ Students created: {total_students}")

    # 6) Timetable (Mon–Sat, limited days + periods)
    print(f"→ Building {args.days}-day timetable (Mon–Sat) with {args.periods} periods/day…")
    total_tt = 0
    for s in schools:
        total_tt += build_timetable_fast(s["id"], days=args.days, periods_per_day=args.periods)
    print(f"✔ Timetable entries created: {total_tt}")

    print("✅ Done.")

if __name__ == "__main__":
    main()
