"""
Telegram Analytics Service for Attendance.
Provides statistics, reports, and analytics.
"""
from sqlalchemy import text, func, extract
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class TelegramAnalyticsService:
    """Service for generating attendance analytics."""

    @staticmethod
    def get_today_summary(db: Session) -> Dict:
        """Get today's attendance summary."""
        today = datetime.now().date()
        
        result = db.execute(text("""
            SELECT 
                COUNT(DISTINCT user_id) as total_users,
                SUM(CASE WHEN status IN ('present', 'late') THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) as late,
                SUM(CASE WHEN status = 'absent' THEN 1 ELSE 0 END) as absent,
                AVG(work_hours) as avg_hours
            FROM attendance_records
            WHERE attendance_date = :today
        """), {"today": today})
        
        row = result.fetchone()
        
        return {
            "date": today.isoformat(),
            "total_employees": row[0] or 0,
            "present": row[1] or 0,
            "late": row[2] or 0,
            "absent": row[3] or 0,
            "avg_hours": round(row[4] or 0, 1),
            "attendance_rate": round((row[1] or 0) / max(1, row[0] or 1) * 100, 1) if row else 0
        }

    @staticmethod
    def get_monthly_summary(db: Session, year: int, month: int) -> Dict:
        """Get monthly attendance summary."""
        result = db.execute(text("""
            SELECT 
                COUNT(DISTINCT user_id) as total_users,
                COUNT(DISTINCT DATE(attendance_date)) as working_days,
                SUM(CASE WHEN status IN ('present', 'late') THEN 1 ELSE 0 END) as total_present,
                SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) as total_late,
                SUM(CASE WHEN status = 'absent' THEN 1 ELSE 0 END) as total_absent,
                AVG(work_hours) as avg_hours
            FROM attendance_records
            WHERE YEAR(attendance_date) = :year 
            AND MONTH(attendance_date) = :month
        """), {"year": year, "month": month})
        
        row = result.fetchone()
        
        return {
            "year": year,
            "month": month,
            "total_employees": row[0] or 0,
            "working_days": row[1] or 0,
            "total_present": row[2] or 0,
            "total_late": row[3] or 0,
            "total_absent": row[4] or 0,
            "avg_hours": round(row[5] or 0, 1)
        }

    @staticmethod
    def get_top_performers(db: Session, limit: int = 10) -> List[Dict]:
        """Get top performers by attendance."""
        result = db.execute(text("""
            SELECT 
                u.username,
                u.full_name,
                COUNT(ar.id) as days_present,
                AVG(ar.work_hours) as avg_hours,
                SUM(CASE WHEN ar.status = 'late' THEN 1 ELSE 0 END) as late_count
            FROM attendance_records ar
            JOIN users u ON ar.user_id = u.id
            WHERE ar.status IN ('present', 'late')
            GROUP BY u.id, u.username, u.full_name
            ORDER BY days_present DESC, avg_hours DESC
            LIMIT :limit
        """), {"limit": limit})
        
        performers = []
        for row in result:
            performers.append({
                "username": row[0],
                "full_name": row[1],
                "days_present": row[2],
                "avg_hours": round(row[3] or 0, 1),
                "late_count": row[4] or 0
            })
        
        return performers

    @staticmethod
    def get_late_arrivals_today(db: Session) -> List[Dict]:
        """Get employees who arrived late today."""
        today = datetime.now().date()
        
        result = db.execute(text("""
            SELECT 
                u.username,
                u.full_name,
                ar.check_in_time,
                ar.work_hours
            FROM attendance_records ar
            JOIN users u ON ar.user_id = u.id
            WHERE ar.attendance_date = :today
            AND ar.status = 'late'
            ORDER BY ar.check_in_time DESC
        """), {"today": today})
        
        late_arrivals = []
        for row in result:
            late_arrivals.append({
                "username": row[0],
                "full_name": row[1],
                "check_in_time": row[2].strftime("%H:%M") if row[2] else "N/A",
                "work_hours": round(row[3] or 0, 1)
            })
        
        return late_arrivals

    @staticmethod
    def get_absent_today(db: Session) -> List[Dict]:
        """Get employees absent today."""
        today = datetime.now().date()
        
        result = db.execute(text("""
            SELECT 
                u.username,
                u.full_name,
                u.department_id
            FROM users u
            WHERE u.id NOT IN (
                SELECT user_id FROM attendance_records 
                WHERE attendance_date = :today
                AND status IN ('present', 'late')
            )
            AND u.is_active = 1
        """), {"today": today})
        
        absent = []
        for row in result:
            absent.append({
                "username": row[0],
                "full_name": row[1],
                "department_id": row[2]
            })
        
        return absent

    @staticmethod
    def get_attendance_trend(db: Session, days: int = 30) -> List[Dict]:
        """Get attendance trend for the last N days."""
        start_date = datetime.now().date() - timedelta(days=days)
        
        result = db.execute(text("""
            SELECT 
                attendance_date,
                COUNT(DISTINCT user_id) as total_users,
                SUM(CASE WHEN status IN ('present', 'late') THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) as late,
                AVG(work_hours) as avg_hours
            FROM attendance_records
            WHERE attendance_date >= :start_date
            GROUP BY attendance_date
            ORDER BY attendance_date DESC
        """), {"start_date": start_date})
        
        trend = []
        for row in result:
            trend.append({
                "date": row[0].isoformat(),
                "total_users": row[1],
                "present": row[2],
                "late": row[3],
                "avg_hours": round(row[4] or 0, 1)
            })
        
        return trend
