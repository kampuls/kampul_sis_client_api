# Kampul SIS Client API (`kampul_sis_client_api`)

Dedicated tenant & school management API backend for the **Kampul SIS** ecosystem and the **AD School C# Desktop Application**. Built with FastAPI, SQLAlchemy (supporting MySQL & PostgreSQL), PyJWT, and Redis.

## Features

- **Authentication & Authorization**: JWT-based authentication with user roles
- **Student Management**: CRUD operations for student records
- **Teacher Management**: CRUD operations for teacher records
- **Class Management**: CRUD operations for class records
- **Enrollment System**: Manage student enrollments in classes
- **Search Functionality**: Search across students, teachers, and classes
- **Data Validation**: Pydantic schemas for request/response validation
- **Database Relationships**: Proper foreign key relationships between entities

## API Endpoints

### Authentication

- `POST /auth/register` - Register a new user
- `POST /auth/login` - Login and get access token
- `GET /auth/me` - Get current user information
- `GET /auth/users` - Get list of users (admin only)

### Students

- `POST /students/` - Create a new student
- `GET /students/` - Get list of students (with pagination and filtering)
- `GET /students/{student_id}` - Get student by ID
- `GET /students/by-student-id/{student_id}` - Get student by student ID
- `GET /students/{student_id}/enrollments` - Get student with enrollments
- `PUT /students/{student_id}` - Update student information
- `DELETE /students/{student_id}` - Delete student (soft delete)
- `GET /students/search/{search_term}` - Search students

### Teachers

- `POST /teachers/` - Create a new teacher
- `GET /teachers/` - Get list of teachers (with pagination and filtering)
- `GET /teachers/{teacher_id}` - Get teacher by ID
- `GET /teachers/by-teacher-id/{teacher_id}` - Get teacher by teacher ID
- `GET /teachers/{teacher_id}/classes` - Get teacher with classes
- `PUT /teachers/{teacher_id}` - Update teacher information
- `DELETE /teachers/{teacher_id}` - Delete teacher (soft delete)
- `GET /teachers/search/{search_term}` - Search teachers
- `GET /teachers/by-subject/{subject}` - Get teachers by subject
- `GET /teachers/by-department/{department}` - Get teachers by department

### Classes

- `POST /classes/` - Create a new class
- `GET /classes/` - Get list of classes (with pagination and filtering)
- `GET /classes/{class_id}` - Get class by ID
- `GET /classes/by-code/{class_code}` - Get class by class code
- `GET /classes/{class_id}/with-teacher` - Get class with teacher information
- `GET /classes/{class_id}/enrollments` - Get class enrollments
- `PUT /classes/{class_id}` - Update class information
- `DELETE /classes/{class_id}` - Delete class (soft delete)
- `GET /classes/search/{search_term}` - Search classes
- `GET /classes/by-subject/{subject}` - Get classes by subject
- `GET /classes/by-semester/{semester}` - Get classes by semester
- `GET /classes/by-academic-year/{academic_year}` - Get classes by academic year
- `GET /classes/by-teacher/{teacher_id}` - Get classes by teacher

## Installation & Setup

1. **Create a virtual environment:**

   ```bash
   python -m venv venv

   # On Windows
   venv\\Scripts\\activate

   # On macOS/Linux
   source venv/bin/activate
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Set up the database and create admin user:**

   ```bash
   python setup.py
   ```

4. **Run the application:**

   ```bash
   # Development server
   python run.py

   # Or directly with uvicorn
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. **Access the API:**
   - API: http://localhost:8000
   - Interactive API docs (Swagger): http://localhost:8000/docs
   - Alternative API docs (ReDoc): http://localhost:8000/redoc

## Database Schema

### Users

- `id`: Primary key
- `email`: Unique email address
- `username`: Unique username
- `hashed_password`: Hashed password
- `is_active`: Active status
- `is_admin`: Admin privileges
- `created_at`, `updated_at`: Timestamps

### Students

- `id`: Primary key
- `student_id`: Unique student identifier (e.g., STU0001)
- `first_name`, `last_name`: Student name
- `email`: Unique email address
- `phone`: Phone number
- `date_of_birth`: Date of birth
- `address`: Address
- `enrollment_date`: Date of enrollment
- `graduation_date`: Expected graduation date
- `is_active`: Active status
- `created_at`, `updated_at`: Timestamps

### Teachers

- `id`: Primary key
- `teacher_id`: Unique teacher identifier (e.g., TCH0001)
- `first_name`, `last_name`: Teacher name
- `email`: Unique email address
- `phone`: Phone number
- `subject`: Teaching subject
- `department`: Department
- `hire_date`: Date of hire
- `salary`: Salary information
- `is_active`: Active status
- `created_at`, `updated_at`: Timestamps

### Classes

- `id`: Primary key
- `class_code`: Unique class code (e.g., MATH2024001)
- `class_name`: Class name
- `subject`: Subject
- `description`: Class description
- `credits`: Number of credits
- `max_students`: Maximum number of students
- `teacher_id`: Foreign key to teachers table
- `semester`: Semester (e.g., Fall 2024)
- `academic_year`: Academic year
- `is_active`: Active status
- `created_at`, `updated_at`: Timestamps

### Enrollments

- `id`: Primary key
- `student_id`: Foreign key to students table
- `class_id`: Foreign key to classes table
- `enrollment_date`: Date of enrollment
- `grade`: Grade (A, B, C, D, F)
- `status`: Enrollment status (enrolled, completed, dropped)
- `created_at`, `updated_at`: Timestamps

## Authentication

The API uses JWT (JSON Web Tokens) for authentication. To access protected endpoints:

1. Register a user at `POST /auth/register`
2. Login at `POST /auth/login` to get an access token
3. Include the token in the Authorization header: `Bearer <your-token>`

## Usage Examples

### Register a User

```bash
curl -X POST "http://localhost:8000/auth/register" \
     -H "Content-Type: application/json" \
     -d '{
       "username": "admin",
       "email": "admin@school.com",
       "password": "admin123"
     }'
```

### Login

```bash
curl -X POST "http://localhost:8000/auth/login" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin&password=admin123"
```

### Create a Student

```bash
curl -X POST "http://localhost:8000/students/" \
     -H "Authorization: Bearer <your-token>" \
     -H "Content-Type: application/json" \
     -d '{
       "student_id": "STU0001",
       "first_name": "John",
       "last_name": "Doe",
       "email": "john.doe@student.com"
     }'
```

### Create a Teacher

```bash
curl -X POST "http://localhost:8000/teachers/" \
     -H "Authorization: Bearer <your-token>" \
     -H "Content-Type: application/json" \
     -d '{
       "teacher_id": "TCH0001",
       "first_name": "Jane",
       "last_name": "Smith",
       "email": "jane.smith@teacher.com",
       "subject": "Mathematics",
       "department": "STEM"
     }'
```

### Create a Class

```bash
curl -X POST "http://localhost:8000/classes/" \
     -H "Authorization: Bearer <your-token>" \
     -H "Content-Type: application/json" \
     -d '{
       "class_code": "MATH101",
       "class_name": "Introduction to Mathematics",
       "subject": "Mathematics",
       "credits": 3,
       "teacher_id": 1,
       "semester": "Fall 2024",
       "academic_year": "2024"
     }'
```

## Development

### Project Structure

```
school_management_api/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration settings
│   ├── database.py          # Database connection and session
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas for validation
│   ├── crud.py              # Database CRUD operations
│   ├── utils.py             # Utility functions (auth, password hashing)
│   └── routes/              # API route handlers
│       ├── __init__.py
│       ├── auth.py          # Authentication routes
│       ├── students.py      # Student management routes
│       ├── teachers.py      # Teacher management routes
│       └── classes.py       # Class management routes
├── requirements.txt         # Python dependencies
├── run.py                  # Simple run script
├── setup.py                # Database setup script
└── README.md               # This file
```

### Adding New Features

1. **Models**: Add new SQLAlchemy models in `models.py`
2. **Schemas**: Add Pydantic schemas in `schemas.py`
3. **CRUD**: Add database operations in `crud.py`
4. **Routes**: Add API endpoints in appropriate route files
5. **Update**: Update this README with new endpoints

## Documentation

Comprehensive documentation is available in the [`docs/`](./docs/) folder:

- **[Documentation Index](./docs/README.md)** - Start here for all documentation
- **[Marking System Overview](./docs/MARKING_SYSTEM_OVERVIEW.md)** - Complete guide to the marking system
- **[Deep Verification Report](./docs/DEEP_VERIFICATION_REPORT.md)** - Implementation verification
- **[Full Documentation Index](./docs/INDEX.md)** - Complete list of all documentation

### Quick Links

- **New Developers:** Start with [Marking System Overview](./docs/MARKING_SYSTEM_OVERVIEW.md)
- **API Integration:** See [API Endpoints](./docs/MARKING_SYSTEM_OVERVIEW.md#api-endpoints)
- **Database Setup:** See [Database Schema](./docs/MARKING_SYSTEM_OVERVIEW.md#database-schema)
- **Troubleshooting:** See [Developer Guide](./docs/MARKING_SYSTEM_OVERVIEW.md#developer-guide)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is open source and available under the [MIT License](LICENSE).
