# Justice – Backend (Flask + SQLite)

## Run
    pip install -r requirements.txt
    python app.py            # http://localhost:5000

Environment variables (optional): JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, DB_PATH, UPLOAD_DIR, PORT.
Default admin: admin@justice.local / Admin@12345  (change before deployment)

## Main endpoints
| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | /api/auth/register | public | register client or advocate |
| POST | /api/auth/login | public | get JWT |
| GET | /api/meta | public | courts and practice areas |
| GET | /api/advocates?court=&area=&language=&sort= | public | search approved advocates |
| GET | /api/advocates/<id> | public | profile with reviews |
| POST | /api/chat | public | legal assistant + suggested advocates |
| POST | /api/advocates/enroll | advocate | multipart form + Bar Council letter |
| GET | /api/me/advocate | advocate | own enrollment status |
| POST | /api/advocates/<id>/reviews | client | rating + comment |
| POST | /api/advocates/<id>/consult | client | consultation request |
| GET/PATCH | /api/consultations | client/advocate | list / accept, decline, close |
| GET | /api/admin/pending | admin | pending enrollments |
| POST | /api/admin/advocates/<id>/verify | admin | {"approve": true/false} |
| GET | /api/admin/audit | admin | audit log |

Send the token as `Authorization: Bearer <token>`.
