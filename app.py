import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://neondb_owner:npg_bUg8iSfMDax6@ep-quiet-hat-bdkta2rf-pooler.c-8.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

def get_conn():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS teachers (id SERIAL PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS students (id SERIAL PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS courses (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            hours INT,
            teacher_id INT REFERENCES teachers(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS enrollments (
            id SERIAL PRIMARY KEY,
            student_id INT REFERENCES students(id) ON DELETE CASCADE,
            course_id INT REFERENCES courses(id) ON DELETE CASCADE,
            grade INT,
            UNIQUE(student_id, course_id)
        );
        INSERT INTO teachers (id, name) VALUES (1, 'Иван Петров'), (2, 'Анна Смирнова') ON CONFLICT (id) DO NOTHING;
        INSERT INTO students (id, name) VALUES (1, 'Студент 1'), (2, 'Студент 2'), (3, 'Студент 3'), (4, 'Студент 4'), (5, 'Студент 5') ON CONFLICT (id) DO NOTHING;
    """)
    conn.commit()
    cur.close()
    conn.close()

class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        if data is not None:
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        parts = [p for p in self.path.split("/") if p]
        conn = get_conn()
        cur = conn.cursor()
        try:
            if not parts:
                self.send_json(200, {"status": "Работает"})
            elif parts == ["courses"]:
                cur.execute('SELECT id, title, description, hours, teacher_id AS "teacherId" FROM courses ORDER BY id')
                self.send_json(200, cur.fetchall())
            elif len(parts) == 2 and parts[0] == "courses":
                cur.execute('SELECT id, title, description, hours, teacher_id AS "teacherId" FROM courses WHERE id = %s', (parts[1],))
                row = cur.fetchone()
                self.send_json(200, row) if row else self.send_json(404, {"error": "Не найдено"})
            elif len(parts) == 3 and parts[0] == "students" and parts[2] == "courses":
                cur.execute("""
                    SELECT c.id, c.title, c.description, c.hours, c.teacher_id AS "teacherId", e.grade
                    FROM courses c JOIN enrollments e ON c.id = e.course_id
                    WHERE e.student_id = %s
                """, (parts[1],))
                self.send_json(200, cur.fetchall())
            else:
                self.send_json(404, {"error": "Неизвестный маршрут"})
        finally:
            cur.close()
            conn.close()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        parts = [p for p in self.path.split("/") if p]
        conn = get_conn()
        cur = conn.cursor()
        try:
            if parts == ["courses"]:
                cur.execute(
                    'INSERT INTO courses (title, description, hours, teacher_id) VALUES (%s, %s, %s, %s) RETURNING id, title, description, hours, teacher_id AS "teacherId"',
                    (body.get("title"), body.get("description"), body.get("hours"), body.get("teacherId"))
                )
                conn.commit()
                self.send_json(201, cur.fetchone())
            elif parts == ["enrollments"]:
                try:
                    cur.execute(
                        'INSERT INTO enrollments (student_id, course_id, grade) VALUES (%s, %s, %s) RETURNING id, student_id AS "studentId", course_id AS "courseId", grade',
                        (body.get("studentId"), body.get("courseId"), body.get("grade"))
                    )
                    conn.commit()
                    self.send_json(201, cur.fetchone())
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    self.send_json(409, {"error": "Студент уже записан на этот курс"})
            else:
                self.send_json(404, {"error": "Неизвестный маршрут"})
        finally:
            cur.close()
            conn.close()

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        parts = [p for p in self.path.split("/") if p]
        if len(parts) == 2 and parts[0] == "courses":
            conn = get_conn()
            cur = conn.cursor()
            try:
                cur.execute(
                    'UPDATE courses SET title=%s, description=%s, hours=%s, teacher_id=%s WHERE id=%s RETURNING id, title, description, hours, teacher_id AS "teacherId"',
                    (body.get("title"), body.get("description"), body.get("hours"), body.get("teacherId"), parts[1])
                )
                row = cur.fetchone()
                conn.commit()
                self.send_json(200, row) if row else self.send_json(404, {"error": "Курс не найден"})
            finally:
                cur.close()
                conn.close()

    def do_DELETE(self):
        parts = [p for p in self.path.split("/") if p]
        if len(parts) == 2 and parts[0] == "courses":
            conn = get_conn()
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM courses WHERE id = %s", (parts[1],))
                deleted = cur.rowcount
                conn.commit()
                self.send_json(204, None) if deleted else self.send_json(404, {"error": "Курс не найден"})
            finally:
                cur.close()
                conn.close()

if __name__ == "__main__":
    init_db()
    print("Сервер запущен на http://localhost:3000")
    HTTPServer(("0.0.0.0", 3000), Handler).serve_forever()
