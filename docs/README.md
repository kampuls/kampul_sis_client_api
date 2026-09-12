# PAMA API Documentation

Welcome to the PAMA API documentation. This folder contains comprehensive documentation for the API system.

## 📚 Documentation Index

### Core Documentation

1. **[Attendance System — End-to-End Developer Guide](./attendance_dev_guide.md)**

   - Complete mobile-to-API attendance flow
   - Security, schedules, multi-session rollover, leave, devices, and reporting
   - Implementation checklist and regression matrix

2. **[Leave Management — End-to-End Developer Guide](./leave_dev_guide.md)**

   - Employee, approver, and manual staff-leave flows
   - Dynamic balances, policy deductions, proof, privacy, and attendance integration
   - Complete endpoint contracts and web implementation checklist

3. **[Marking System Overview](./MARKING_SYSTEM_OVERVIEW.md)**

   - Complete guide to the marking system
   - Data flow and architecture
   - Calculation processes
   - Developer guide

4. **[Deep Verification Report](./DEEP_VERIFICATION_REPORT.md)**

   - Detailed comparison with Telegram bot implementation
   - Line-by-line verification
   - Column names and schema verification
   - Transaction safety analysis

5. **[Google Login Backend](./GOOGLE_LOGIN_BACKEND.md)**
   - Backend implementation for Google Sign-In
   - Firebase configuration requirements
   - API endpoint details

### Quick Start

**For New Developers:**

1. For attendance work, start with the [Attendance System Guide](./attendance_dev_guide.md)
2. For leave work, start with the [Leave Management Guide](./leave_dev_guide.md)
3. For marking work, start with [Marking System Overview](./MARKING_SYSTEM_OVERVIEW.md)
4. Review the relevant implementation and regression tests linked from each guide

**For API Integration:**

1. Use the endpoint contracts in the relevant attendance, leave, or marking guide
2. Review request/response formats and permission rules
3. Understand transaction safety and retry behavior

**For Database Setup:**

1. See [Marking System Overview - Database Schema](./MARKING_SYSTEM_OVERVIEW.md#database-schema)
2. Verify column names match exactly
3. Ensure `divide_by_multiplier` column exists

## 🔑 Key Concepts

### Marking Process

- **Monthly:** Calculated from subject marks
- **Semester:** Calculated from monthly averages (different logic for Khmer vs English/IEP)
- **Yearly:** Calculated from semester averages

### Transaction Safety

- All operations in single transaction
- Single commit at the end
- Automatic rollback on errors

### Column Names (Critical!)

- `marks_semester.marks_imonthly_ids` (with "i")
- `marks_yearly.marks_isemester_ids` (with "i")
- `exam_calculate_sign.divide_by_multiplier`

## 📁 File Structure

```
docs/
├── README.md (this file)
├── attendance_dev_guide.md
├── leave_dev_guide.md
├── MARKING_SYSTEM_OVERVIEW.md
└── DEEP_VERIFICATION_REPORT.md
```

## 🚀 Getting Started

1. **Read the Overview:** Start with [MARKING_SYSTEM_OVERVIEW.md](./MARKING_SYSTEM_OVERVIEW.md)
2. **Understand the Flow:** Review the data flow diagrams
3. **Check Implementation:** See [DEEP_VERIFICATION_REPORT.md](./DEEP_VERIFICATION_REPORT.md) for details
4. **Test:** Use the testing checklist in the overview

## 📝 Contributing

When updating documentation:

1. Keep it clear and concise
2. Include code examples
3. Update the version and date
4. Add to this README if creating new docs

## 🔍 Finding Information

- **How does marking work?** → [Marking System Overview](./MARKING_SYSTEM_OVERVIEW.md)
- **How does attendance work?** → [Attendance System Guide](./attendance_dev_guide.md)
- **How does leave work?** → [Leave Management Guide](./leave_dev_guide.md)
- **Is it safe?** → [Deep Verification Report - Transaction Safety](./DEEP_VERIFICATION_REPORT.md#7-transaction-safety-verified)
- **What are the calculations?** → [Marking System Overview - Calculation Process](./MARKING_SYSTEM_OVERVIEW.md#calculation-process)
- **Database schema?** → [Marking System Overview - Database Schema](./MARKING_SYSTEM_OVERVIEW.md#database-schema)
- **API endpoints?** → [Marking System Overview - API Endpoints](./MARKING_SYSTEM_OVERVIEW.md#api-endpoints)

---

**Last Updated:** 2026-08-04
**Maintained by:** Development Team
