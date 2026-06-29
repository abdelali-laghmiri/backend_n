from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.attendance.models import AttendanceDailySummary, AttendanceStatusEnum
from app.apps.employees.models import Employee
from app.apps.tasks.models import EmployeeTask, TaskPriorityEnum, TaskStatusEnum, utcnow
from app.apps.tasks.schemas import (
    MobileAttendanceStatusResponse,
    MobileEmployeeSummaryResponse,
    MobileTaskStatsResponse,
    MobileTaskSummaryResponse,
    TaskCreateRequest,
    TaskResponse,
)
from app.apps.users.models import User


class TasksConflictError(RuntimeError):
    """Raised when a persistence conflict prevents a task operation."""


class TasksNotFoundError(RuntimeError):
    """Raised when a task or employee record cannot be found."""


class TasksValidationError(RuntimeError):
    """Raised when a task operation is invalid."""


class TasksService:
    """Small employee task manager used by the mobile dashboard."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_my_tasks(
        self,
        current_user: User,
        *,
        include_done: bool = True,
        limit: int = 20,
    ) -> list[EmployeeTask]:
        employee = self._get_employee_for_user(current_user)
        statement: Select[tuple[EmployeeTask]] = (
            select(EmployeeTask)
            .where(EmployeeTask.employee_id == employee.id)
            .order_by(
                EmployeeTask.status.asc(),
                EmployeeTask.due_date.asc().nulls_last(),
                EmployeeTask.priority.desc(),
                EmployeeTask.id.desc(),
            )
            .limit(limit)
        )
        if not include_done:
            statement = statement.where(EmployeeTask.status != TaskStatusEnum.DONE.value)

        return list(self.db.execute(statement).scalars().all())

    def list_tasks(
        self,
        *,
        employee_id: int | None = None,
        status: TaskStatusEnum | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EmployeeTask]:
        statement: Select[tuple[EmployeeTask]] = select(EmployeeTask)
        if employee_id is not None:
            self._get_employee(employee_id)
            statement = statement.where(EmployeeTask.employee_id == employee_id)
        if status is not None:
            statement = statement.where(EmployeeTask.status == status.value)

        statement = (
            statement.order_by(
                EmployeeTask.status.asc(),
                EmployeeTask.due_date.asc().nulls_last(),
                EmployeeTask.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(statement).scalars().all())

    def create_task(
        self,
        payload: TaskCreateRequest,
        current_user: User,
    ) -> EmployeeTask:
        self._get_employee(payload.employee_id)
        task = EmployeeTask(
            employee_id=payload.employee_id,
            created_by_user_id=current_user.id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority.value,
            status=TaskStatusEnum.TODO.value,
            due_date=payload.due_date,
        )
        self.db.add(task)
        return self._commit_and_refresh(task, "Failed to create the task.")

    def complete_my_task(
        self,
        task_id: int,
        current_user: User,
    ) -> EmployeeTask:
        employee = self._get_employee_for_user(current_user)
        task = self.db.get(EmployeeTask, task_id)
        if task is None or task.employee_id != employee.id:
            raise TasksNotFoundError("Task not found.")

        task.status = TaskStatusEnum.DONE.value
        task.completed_at = utcnow()
        self.db.add(task)
        return self._commit_and_refresh(task, "Failed to complete the task.")

    def get_mobile_summary(
        self,
        current_user: User,
        *,
        target_date: date | None = None,
        task_limit: int = 8,
    ) -> MobileTaskSummaryResponse:
        employee = self._get_employee_for_user(current_user)
        resolved_date = target_date or date.today()
        attendance = self._get_attendance_for_employee(employee.id, resolved_date)
        tasks = self.list_my_tasks(current_user, include_done=True, limit=task_limit)
        task_stats = self._build_task_stats(employee.id, resolved_date)

        return MobileTaskSummaryResponse(
            employee=MobileEmployeeSummaryResponse(
                employee_id=employee.id,
                matricule=employee.matricule,
                full_name=f"{employee.first_name} {employee.last_name}".strip(),
            ),
            attendance=self._build_attendance_response(attendance, resolved_date),
            task_stats=task_stats,
            tasks=self.build_task_responses(tasks),
        )

    def build_task_response(self, task: EmployeeTask) -> TaskResponse:
        return TaskResponse(
            id=task.id,
            employee_id=task.employee_id,
            title=task.title,
            description=task.description,
            status=TaskStatusEnum(task.status),
            priority=TaskPriorityEnum(task.priority),
            due_date=task.due_date,
            completed_at=self._normalize_datetime(task.completed_at),
            created_at=self._normalize_datetime(task.created_at),
            updated_at=self._normalize_datetime(task.updated_at),
        )

    def build_task_responses(self, tasks: list[EmployeeTask]) -> list[TaskResponse]:
        return [self.build_task_response(task) for task in tasks]

    def _get_employee_for_user(self, current_user: User) -> Employee:
        employee = self.db.execute(
            select(Employee).where(Employee.user_id == current_user.id).limit(1)
        ).scalar_one_or_none()
        if employee is None:
            raise TasksNotFoundError("No employee profile is linked to this user.")

        return employee

    def _get_employee(self, employee_id: int) -> Employee:
        employee = self.db.get(Employee, employee_id)
        if employee is None:
            raise TasksNotFoundError("Employee not found.")

        return employee

    def _get_attendance_for_employee(
        self,
        employee_id: int,
        target_date: date,
    ) -> AttendanceDailySummary | None:
        return self.db.execute(
            select(AttendanceDailySummary)
            .where(
                AttendanceDailySummary.employee_id == employee_id,
                AttendanceDailySummary.attendance_date == target_date,
            )
            .limit(1)
        ).scalar_one_or_none()

    def _build_attendance_response(
        self,
        attendance: AttendanceDailySummary | None,
        target_date: date,
    ) -> MobileAttendanceStatusResponse:
        if attendance is None:
            return MobileAttendanceStatusResponse(
                attendance_date=target_date,
                status=AttendanceStatusEnum.ABSENT,
                first_check_in_at=None,
                last_check_out_at=None,
                worked_duration_minutes=0,
            )

        return MobileAttendanceStatusResponse(
            attendance_date=attendance.attendance_date,
            status=AttendanceStatusEnum(attendance.status),
            first_check_in_at=self._normalize_datetime(attendance.first_check_in_at),
            last_check_out_at=self._normalize_datetime(attendance.last_check_out_at),
            worked_duration_minutes=attendance.worked_duration_minutes,
        )

    def _build_task_stats(
        self,
        employee_id: int,
        target_date: date,
    ) -> MobileTaskStatsResponse:
        tasks = list(
            self.db.execute(
                select(EmployeeTask).where(EmployeeTask.employee_id == employee_id)
            )
            .scalars()
            .all()
        )
        done = sum(1 for task in tasks if task.status == TaskStatusEnum.DONE.value)
        open_count = len(tasks) - done
        overdue = sum(
            1
            for task in tasks
            if task.status != TaskStatusEnum.DONE.value
            and task.due_date is not None
            and task.due_date < target_date
        )
        return MobileTaskStatsResponse(
            total=len(tasks),
            open=open_count,
            done=done,
            overdue=overdue,
        )

    def _commit_and_refresh(
        self,
        task: EmployeeTask,
        conflict_message: str,
    ) -> EmployeeTask:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise TasksConflictError(conflict_message) from exc

        self.db.refresh(task)
        return task

    def _normalize_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)
