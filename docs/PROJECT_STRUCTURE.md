# PAMA API - Project Structure

## 📁 **New FastAPI Project Structure**

The project has been reorganized following FastAPI best practices for better maintainability, scalability, and production readiness.

```
pama_api/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application entry point
│   │
│   ├── core/                       # Core configuration and database
│   │   ├── __init__.py
│   │   ├── config.py              # Application settings and environment variables
│   │   └── database.py            # Database connection and session management
│   │
│   ├── models/                     # Database models (SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── base.py               # Base model class
│   │   ├── user.py               # User model (teachers/admins)
│   │   ├── student.py            # Student model
│   │   ├── parent.py             # Parent model
│   │   ├── teacher.py            # Teacher model
│   │   ├── class_model.py        # Class model
│   │   └── enrollment.py         # Enrollment model
│   │
│   ├── schemas/                    # Pydantic schemas for request/response validation
│   │   └── __init__.py           # All Pydantic models
│   │
│   ├── auth/                       # Authentication and authorization
│   │   ├── __init__.py
│   │   ├── dependencies.py       # FastAPI dependencies for auth
│   │   ├── services.py            # Authentication services
│   │   ├── student_auth.py        # Student authentication functions
│   │   └── parent_auth.py        # Parent authentication functions
│   │
│   ├── services/                   # Business logic and CRUD operations
│   │   ├── __init__.py
│   │   ├── crud.py               # Database CRUD operations
│   │   └── utils.py              # Utility functions (JWT, password hashing, etc.)
│   │
│   └── api/                        # API endpoints
│       ├── __init__.py
│       └── v1/                    # API version 1
│           ├── __init__.py        # API router configuration
│           ├── auth.py           # Authentication endpoints
│           ├── users.py          # User management endpoints
│           ├── students.py       # Student management endpoints
│           ├── teachers.py        # Teacher management endpoints
│           └── classes.py         # Class management endpoints
│
├── alembic/                        # Database migrations
├── requirements.txt                # Python dependencies
├── run.py                         # Application runner
├── Dockerfile                      # Docker configuration
├── docker-compose.yml              # Docker Compose configuration
├── nginx.conf                      # Nginx configuration
├── deploy.sh                       # Deployment script
├── PRODUCTION.md                   # Production deployment guide
├── SSL_CONFIG.md                   # SSL configuration guide
└── PROJECT_STRUCTURE.md           # This file
```

## 🎯 **Key Improvements**

### **1. Separation of Concerns**

- **Models**: Database models separated into individual files
- **Schemas**: Pydantic models for request/response validation
- **Auth**: Authentication logic isolated in dedicated package
- **Services**: Business logic and CRUD operations
- **API**: Clean API endpoints with versioning

### **2. Production-Ready Structure**

- **Core**: Configuration and database setup
- **Versioned API**: `/api/v1/` prefix for future API versions
- **Modular Design**: Easy to add new features and maintain
- **Clear Dependencies**: Explicit import structure

### **3. Role-Based Authentication**

- **Teacher Role**: Uses `users` table
- **Student Role**: Uses `students` table
- **Parent Role**: Uses `parents` table
- **Security**: Users can only authenticate with correct role/table combination

## 🚀 **API Endpoints**

### **Authentication**

- `POST /api/v1/auth/login` - Regular login (teacher role)
- `POST /api/v1/auth/login-role` - Role-based login
- `POST /api/v1/auth/register` - User registration
- `GET /api/v1/auth/me` - Get current user info

### **User Management**

- `GET /api/v1/users/me` - Get current user profile
- `GET /api/v1/users/` - List users (admin only)

### **Student Management**

- `POST /api/v1/students/` - Create student
- `GET /api/v1/students/` - List students
- `GET /api/v1/students/{id}` - Get student by ID
- `PUT /api/v1/students/{id}` - Update student
- `DELETE /api/v1/students/{id}` - Delete student

### **Teacher Management**

- `POST /api/v1/teachers/` - Create teacher
- `GET /api/v1/teachers/` - List teachers
- `GET /api/v1/teachers/{id}` - Get teacher by ID
- `PUT /api/v1/teachers/{id}` - Update teacher
- `DELETE /api/v1/teachers/{id}` - Delete teacher

### **Class Management**

- `POST /api/v1/classes/` - Create class
- `GET /api/v1/classes/` - List classes
- `GET /api/v1/classes/{id}` - Get class by ID
- `PUT /api/v1/classes/{id}` - Update class
- `DELETE /api/v1/classes/{id}` - Delete class

## 🔧 **Development Benefits**

1. **Easy to Navigate**: Clear folder structure
2. **Scalable**: Easy to add new features
3. **Maintainable**: Separation of concerns
4. **Testable**: Modular design enables unit testing
5. **Production-Ready**: Follows FastAPI best practices

## 📝 **Next Steps**

1. **Add Tests**: Create test files for each module
2. **Add Logging**: Implement structured logging
3. **Add Monitoring**: Add health checks and metrics
4. **Add Documentation**: Auto-generate API docs
5. **Add CI/CD**: Set up continuous integration

This structure makes the project much more professional and easier to manage for future development! 🎉
