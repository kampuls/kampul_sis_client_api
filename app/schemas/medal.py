from pydantic import BaseModel, Field
from typing import Optional, List

class StudentMedalSummary(BaseModel):
    national_gold: int = 0
    national_silver: int = 0
    national_bronze: int = 0
    national_diamond: int = 0

    international_gold: int = 0
    international_silver: int = 0
    international_bronze: int = 0
    international_diamond: int = 0

    school_gold: int = 0
    school_silver: int = 0
    school_bronze: int = 0
    school_diamond: int = 0

    total_gold: int = 0
    total_silver: int = 0
    total_bronze: int = 0
    total_diamond: int = 0
    total_medals: int = 0

class StudentMedalResponse(BaseModel):
    student_id: int
    student_ename: str
    student_kname: Optional[str] = None
    student_gender: Optional[str] = None
    student_image: Optional[str] = None
    rank: int
    medals_summary: StudentMedalSummary

    class Config:
        from_attributes = True

class AcademicYearOption(BaseModel):
    id: int
    name_kh: str
    name_en: str
    is_active: bool

class StudentMedalDetail(BaseModel):
    medal_name: str
    medal_type: str
    price_name_kh: str
    price_name_us: str
    academic_kh: str
    academic_en: str
    created_at: Optional[str] = None


# Admin Report Schemas
class GradeProgramMedalReport(BaseModel):
    """Medal statistics grouped by grade and program"""
    grade_name: str
    program_name: str
    total_gold: int = 0
    total_silver: int = 0
    total_bronze: int = 0
    total_diamond: int = 0
    total_medals: int = 0
    top_students: Optional[List[dict]] = None

    class Config:
        from_attributes = True


class StudentCompetitionMedalRow(BaseModel):
    """Per-student medal counts for one competition (medals.medal_name), for matrix exports."""

    student_id: int
    student_name: str
    student_name_kh: str
    student_name_en: str
    gender: str
    grade_name: str
    grade_type_name: str = ""
    medal_type: str
    program_name: str
    total_gold: int = 0
    total_silver: int = 0
    total_bronze: int = 0
    total_diamond: int = 0
    total_medals: int = 0

    class Config:
        from_attributes = True


class OverallMedalSummary(BaseModel):
    """Overall medal summary across all grades/programs"""
    total_gold: int = 0
    total_silver: int = 0
    total_bronze: int = 0
    total_diamond: int = 0
    total_medals: int = 0
    total_grades: int = 0
    total_programs: int = 0

    class Config:
        from_attributes = True


class EnrollmentProgramOption(BaseModel):
    """Curriculum program (learning.programid → program.id) for medal report filters."""
    id: int
    program_name: str

    class Config:
        from_attributes = True
