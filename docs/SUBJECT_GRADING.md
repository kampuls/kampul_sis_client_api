# Subject grading composition

Teachers can compose one subject mark from any number of weighted components.
Each plan belongs to a class, shift, subject, exam, and academic year. Component
weights must total exactly 100%; the computed percentage is then scaled to the
`subjects_group.full_marks` value for that subject.

The built-in presets include attendance/homework/test (10/10/80),
attendance/activity/exam (10/20/70), coursework/midterm/final (40/20/40), and
final-only (100). Teachers can rename, add, remove, or reweight components.

`subject_attendance` is separate from general `daily_attendance`. Its automatic
component awards:

```text
attendance points = component weight × (present + late days) / subject study days
```

A subject study day is a distinct date with at least one subject-attendance
record for the class context inside the plan's saved attendance period.
Permission and absence do not add attended days. By default, the period is the
full calendar month containing `marks_system.for_month` (the exam opening
date). Teachers can replace it with a custom inclusive date range. If an exam
has no opening date, the default is the current Cambodia calendar month. If no
subject study days exist inside the selected period, the attendance component
is incomplete and the plan cannot be applied to final marks.

`POST /api/v1/marks/composition/apply` reuses the canonical `/marks/save`
implementation, including exam windows, mark locks, audit logging, and the
monthly/semester/yearly calculation cascade.

Final marks can be managed per student. A class-wide apply publishes only
students whose component inputs are complete and skips unfinished students. An
explicit per-student apply may publish the student's current partial total;
blank components contribute zero and the teacher is warned before publishing.
The component scores remain editable, and applying the same student again
updates the canonical final mark through the normal audited mark writer.
