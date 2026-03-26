from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.employees.models import Employee
from app.apps.notifications.models import Notification, NotificationTypeEnum
from app.apps.notifications.service import NotificationsService
from app.apps.organization.models import Department, JobTitle, Team
from app.apps.permissions.service import PermissionsService
from app.apps.requests.leave_business import (
    LeaveBusinessRuleError,
    evaluate_leave_request,
    is_leave_request_type_code,
    validate_leave_field_definition,
    validate_leave_request_type_fields,
)
from app.apps.requests.models import (
    RequestActionEnum,
    RequestActionHistory,
    RequestFieldTypeEnum,
    RequestFieldValue,
    RequestResolverTypeEnum,
    RequestStatusEnum,
    RequestStepKindEnum,
    RequestType,
    RequestTypeField,
    RequestWorkflowStep,
    WorkflowRequest,
    utcnow,
)
from app.apps.requests.schemas import (
    LeaveRequestDetailsResponse,
    RequestApprovalHistoryResponse,
    RequestActionHistoryResponse,
    RequestCreateRequest,
    RequestCurrentStepResponse,
    RequestDetailResponse,
    RequestFieldValueResponse,
    RequestSummaryResponse,
    RequestTypeCreateRequest,
    RequestTypeFieldCreateRequest,
    RequestTypeFieldUpdateRequest,
    RequestTypeUpdateRequest,
    RequestWorkflowProgressResponse,
    RequestWorkflowStepCreateRequest,
    RequestWorkflowStepUpdateRequest,
)
from app.apps.users.models import User


class RequestsConflictError(RuntimeError):
    """Raised when a unique or state conflict prevents the operation."""


class RequestsNotFoundError(RuntimeError):
    """Raised when a request-engine record cannot be found."""


class RequestsValidationError(RuntimeError):
    """Raised when a request-engine payload or workflow is invalid."""


class RequestsAuthorizationError(RuntimeError):
    """Raised when a user is not allowed to access a request."""


class RequestsService:
    """Service layer for the dynamic requests engine."""

    RH_MANAGER_JOB_TITLE_CODE = "RH_MANAGER"
    APPROVAL_HISTORY_ACTIONS = (
        RequestActionEnum.APPROVED.value,
        RequestActionEnum.REJECTED.value,
    )

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_request_type(self, payload: RequestTypeCreateRequest) -> RequestType:
        """Create a dynamic request type."""

        self._ensure_unique_request_type_code(payload.code)
        request_type = RequestType(
            code=payload.code,
            name=payload.name,
            description=payload.description,
            is_active=True,
        )
        self.db.add(request_type)
        return self._commit_and_refresh(
            request_type,
            conflict_message="Failed to create the request type.",
        )

    def list_request_types(self, *, include_inactive: bool = False) -> list[RequestType]:
        """List request types."""

        statement: Select[tuple[RequestType]] = select(RequestType)
        if not include_inactive:
            statement = statement.where(RequestType.is_active.is_(True))

        statement = statement.order_by(RequestType.name.asc(), RequestType.id.asc())
        return list(self.db.execute(statement).scalars().all())

    def get_request_type(self, request_type_id: int) -> RequestType:
        """Return a request type by id."""

        request_type = self.db.get(RequestType, request_type_id)
        if request_type is None:
            raise RequestsNotFoundError("Request type not found.")

        return request_type

    def update_request_type(
        self,
        request_type_id: int,
        payload: RequestTypeUpdateRequest,
    ) -> RequestType:
        """Update a request type."""

        request_type = self.get_request_type(request_type_id)
        changes = payload.model_dump(exclude_unset=True)

        if "code" in changes:
            self._ensure_unique_request_type_code(
                changes["code"],
                current_request_type_id=request_type.id,
            )

        for field_name, value in changes.items():
            setattr(request_type, field_name, value)

        self.db.add(request_type)
        return self._commit_and_refresh(
            request_type,
            conflict_message="Failed to update the request type.",
        )

    def create_request_field(
        self,
        request_type_id: int,
        payload: RequestTypeFieldCreateRequest,
    ) -> RequestTypeField:
        """Create a field definition for a request type."""

        request_type = self.get_request_type(request_type_id)
        self._ensure_unique_request_field_code(request_type_id, payload.code)
        self._validate_request_field_business_definition(
            request_type=request_type,
            field_code=payload.code,
            field_type=payload.field_type,
        )
        default_value = self._normalize_value_for_type(
            field_type=payload.field_type.value,
            value=payload.default_value,
            label="Default value",
            required=False,
            allow_none=True,
        )

        request_field = RequestTypeField(
            request_type_id=request_type_id,
            code=payload.code,
            label=payload.label,
            field_type=payload.field_type.value,
            is_required=payload.is_required,
            placeholder=payload.placeholder,
            help_text=payload.help_text,
            default_value=default_value,
            sort_order=payload.sort_order,
            is_active=True,
        )
        self.db.add(request_field)
        return self._commit_and_refresh(
            request_field,
            conflict_message="Failed to create the request field.",
        )

    def list_request_fields(
        self,
        request_type_id: int,
        *,
        include_inactive: bool = False,
    ) -> list[RequestTypeField]:
        """List field definitions for a request type."""

        self.get_request_type(request_type_id)
        statement: Select[tuple[RequestTypeField]] = select(RequestTypeField).where(
            RequestTypeField.request_type_id == request_type_id
        )
        if not include_inactive:
            statement = statement.where(RequestTypeField.is_active.is_(True))

        statement = statement.order_by(
            RequestTypeField.sort_order.asc(),
            RequestTypeField.id.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def get_request_field(self, request_field_id: int) -> RequestTypeField:
        """Return a request field by id."""

        request_field = self.db.get(RequestTypeField, request_field_id)
        if request_field is None:
            raise RequestsNotFoundError("Request field not found.")

        return request_field

    def update_request_field(
        self,
        request_field_id: int,
        payload: RequestTypeFieldUpdateRequest,
    ) -> RequestTypeField:
        """Update a request field definition."""

        request_field = self.get_request_field(request_field_id)
        request_type = self.get_request_type(request_field.request_type_id)
        changes = payload.model_dump(exclude_unset=True)

        final_code = changes.get("code", request_field.code)
        final_field_type = changes.get(
            "field_type",
            RequestFieldTypeEnum(request_field.field_type),
        )
        final_default_value = (
            changes["default_value"]
            if "default_value" in changes
            else request_field.default_value
        )

        if final_code != request_field.code:
            self._ensure_unique_request_field_code(
                request_field.request_type_id,
                final_code,
                current_request_field_id=request_field.id,
            )

        self._validate_request_field_business_definition(
            request_type=request_type,
            field_code=final_code,
            field_type=final_field_type,
        )
        normalized_default_value = self._normalize_value_for_type(
            field_type=final_field_type.value,
            value=final_default_value,
            label="Default value",
            required=False,
            allow_none=True,
        )

        for field_name, value in changes.items():
            if field_name == "field_type":
                setattr(request_field, field_name, value.value)
                continue

            setattr(request_field, field_name, value)

        request_field.default_value = normalized_default_value
        self.db.add(request_field)
        return self._commit_and_refresh(
            request_field,
            conflict_message="Failed to update the request field.",
        )

    def create_workflow_step(
        self,
        request_type_id: int,
        payload: RequestWorkflowStepCreateRequest,
    ) -> RequestWorkflowStep:
        """Create a workflow step definition for a request type."""

        self.get_request_type(request_type_id)
        self._ensure_unique_workflow_step_order(request_type_id, payload.step_order)

        request_step = RequestWorkflowStep(
            request_type_id=request_type_id,
            step_order=payload.step_order,
            name=payload.name,
            step_kind=payload.step_kind.value,
            resolver_type=payload.resolver_type.value if payload.resolver_type else None,
            is_required=payload.is_required,
            is_active=True,
        )
        self.db.add(request_step)
        return self._commit_and_refresh(
            request_step,
            conflict_message="Failed to create the workflow step.",
        )

    def list_workflow_steps(
        self,
        request_type_id: int,
        *,
        include_inactive: bool = False,
    ) -> list[RequestWorkflowStep]:
        """List workflow steps for a request type."""

        self.get_request_type(request_type_id)
        statement: Select[tuple[RequestWorkflowStep]] = select(RequestWorkflowStep).where(
            RequestWorkflowStep.request_type_id == request_type_id
        )
        if not include_inactive:
            statement = statement.where(RequestWorkflowStep.is_active.is_(True))

        statement = statement.order_by(
            RequestWorkflowStep.step_order.asc(),
            RequestWorkflowStep.id.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def get_workflow_step(self, step_id: int) -> RequestWorkflowStep:
        """Return a workflow step by id."""

        step = self.db.get(RequestWorkflowStep, step_id)
        if step is None:
            raise RequestsNotFoundError("Workflow step not found.")

        return step

    def update_workflow_step(
        self,
        step_id: int,
        payload: RequestWorkflowStepUpdateRequest,
    ) -> RequestWorkflowStep:
        """Update a workflow-step definition."""

        step = self.get_workflow_step(step_id)
        changes = payload.model_dump(exclude_unset=True)

        final_step_order = changes.get("step_order", step.step_order)
        final_step_kind = changes.get("step_kind", RequestStepKindEnum(step.step_kind))
        final_resolver_type = (
            changes["resolver_type"]
            if "resolver_type" in changes
            else (
                RequestResolverTypeEnum(step.resolver_type)
                if step.resolver_type is not None
                else None
            )
        )
        self._validate_step_configuration(
            step_kind=final_step_kind,
            resolver_type=final_resolver_type,
        )

        if final_step_order != step.step_order:
            self._ensure_unique_workflow_step_order(
                step.request_type_id,
                final_step_order,
                current_step_id=step.id,
            )

        for field_name, value in changes.items():
            if field_name == "step_kind":
                setattr(step, field_name, value.value)
                continue

            if field_name == "resolver_type":
                setattr(step, field_name, value.value if value is not None else None)
                continue

            setattr(step, field_name, value)

        self.db.add(step)
        return self._commit_and_refresh(
            step,
            conflict_message="Failed to update the workflow step.",
        )

    def create_request(
        self,
        current_user: User,
        payload: RequestCreateRequest,
    ) -> WorkflowRequest:
        """Create a request instance and place it on the first effective workflow step."""

        requester_employee = self._get_active_employee_by_user_id(current_user.id)
        request_type = self.get_request_type(payload.request_type_id)
        if not request_type.is_active:
            raise RequestsValidationError("Request type must be active.")

        active_fields = self._get_request_type_fields(
            request_type.id,
            active_only=True,
        )
        active_steps = self._get_request_workflow_steps(
            request_type.id,
            active_only=True,
        )
        self._validate_request_type_business_configuration(request_type, active_fields)
        self._validate_required_steps_resolvable(requester_employee, active_steps)
        normalized_values = self._normalize_submitted_values(active_fields, payload.values)
        self._validate_request_business_rules(
            request_type=request_type,
            requester_employee=requester_employee,
            normalized_values=normalized_values,
        )

        workflow_request = WorkflowRequest(
            request_type_id=request_type.id,
            requester_user_id=current_user.id,
            requester_employee_id=requester_employee.id,
            status=RequestStatusEnum.IN_PROGRESS.value,
            current_step_id=None,
            current_approver_user_id=None,
            submitted_at=utcnow(),
            completed_at=None,
            rejection_reason=None,
        )
        self.db.add(workflow_request)
        notifications_service = NotificationsService(self.db)
        pending_notifications: list[Notification] = []

        try:
            self.db.flush()
            self._persist_request_values(workflow_request, active_fields, normalized_values)
            self._record_history(
                workflow_request=workflow_request,
                step=None,
                actor_user_id=current_user.id,
                action=RequestActionEnum.SUBMITTED,
                comment=None,
            )
            self._advance_request_workflow(
                workflow_request=workflow_request,
                requester_employee=requester_employee,
                start_after_order=None,
            )
            self._queue_submission_notifications(
                notifications_service=notifications_service,
                pending_notifications=pending_notifications,
                workflow_request=workflow_request,
                request_type=request_type,
                requester_employee=requester_employee,
            )
            self.db.add(workflow_request)
            self.db.commit()
        except (RequestsValidationError, RequestsNotFoundError, RequestsAuthorizationError):
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            raise RequestsConflictError("Failed to create the request.") from exc

        self.db.refresh(workflow_request)
        self._publish_pending_notifications(
            notifications_service=notifications_service,
            notifications=pending_notifications,
        )
        return workflow_request

    def list_requests_for_user(self, current_user: User) -> list[WorkflowRequest]:
        """List requests submitted by the current authenticated user."""

        statement = (
            select(WorkflowRequest)
            .where(WorkflowRequest.requester_user_id == current_user.id)
            .order_by(WorkflowRequest.created_at.desc(), WorkflowRequest.id.desc())
        )
        return list(self.db.execute(statement).scalars().all())

    def list_pending_approvals_for_user(self, current_user: User) -> list[WorkflowRequest]:
        """List in-progress requests currently assigned to the authenticated approver."""

        statement = (
            select(WorkflowRequest)
            .join(RequestWorkflowStep, RequestWorkflowStep.id == WorkflowRequest.current_step_id)
            .where(
                WorkflowRequest.status == RequestStatusEnum.IN_PROGRESS.value,
                WorkflowRequest.current_step_id.is_not(None),
                WorkflowRequest.current_approver_user_id == current_user.id,
                RequestWorkflowStep.step_kind == RequestStepKindEnum.APPROVER.value,
            )
            .order_by(
                WorkflowRequest.submitted_at.desc(),
                WorkflowRequest.created_at.desc(),
                WorkflowRequest.id.desc(),
            )
        )
        return list(self.db.execute(statement).scalars().all())

    def list_approval_history_for_user(
        self,
        current_user: User,
    ) -> list[RequestApprovalHistoryResponse]:
        """List approval or rejection actions personally performed by the user."""

        statement = (
            select(
                RequestActionHistory.id.label("action_history_id"),
                RequestActionHistory.request_id,
                RequestActionHistory.step_id,
                RequestActionHistory.step_name,
                RequestActionHistory.step_order,
                RequestActionHistory.step_kind,
                RequestActionHistory.resolver_type,
                RequestActionHistory.action,
                RequestActionHistory.comment,
                RequestActionHistory.created_at.label("acted_at"),
                WorkflowRequest.request_type_id,
                WorkflowRequest.requester_user_id,
                WorkflowRequest.requester_employee_id,
                WorkflowRequest.status.label("request_status"),
                WorkflowRequest.submitted_at,
                WorkflowRequest.completed_at,
                RequestType.code.label("request_type_code"),
                RequestType.name.label("request_type_name"),
                Employee.matricule.label("requester_matricule"),
                Employee.first_name.label("requester_first_name"),
                Employee.last_name.label("requester_last_name"),
            )
            .select_from(RequestActionHistory)
            .join(WorkflowRequest, WorkflowRequest.id == RequestActionHistory.request_id)
            .join(RequestType, RequestType.id == WorkflowRequest.request_type_id)
            .join(Employee, Employee.id == WorkflowRequest.requester_employee_id)
            .where(
                RequestActionHistory.actor_user_id == current_user.id,
                RequestActionHistory.action.in_(self.APPROVAL_HISTORY_ACTIONS),
                RequestActionHistory.step_kind == RequestStepKindEnum.APPROVER.value,
            )
            .order_by(RequestActionHistory.created_at.desc(), RequestActionHistory.id.desc())
        )
        rows = self.db.execute(statement).all()

        return [
            RequestApprovalHistoryResponse(
                action_history_id=row.action_history_id,
                request_id=row.request_id,
                request_type_id=row.request_type_id,
                request_type_code=row.request_type_code,
                request_type_name=row.request_type_name,
                requester_user_id=row.requester_user_id,
                requester_employee_id=row.requester_employee_id,
                requester_name=(
                    f"{row.requester_first_name} {row.requester_last_name}"
                ),
                requester_matricule=row.requester_matricule,
                request_status=RequestStatusEnum(row.request_status),
                submitted_at=row.submitted_at,
                completed_at=row.completed_at,
                acted_at=row.acted_at,
                action=RequestActionEnum(row.action),
                step_id=row.step_id,
                step_name=row.step_name,
                step_order=row.step_order,
                step_kind=(
                    RequestStepKindEnum(row.step_kind)
                    if row.step_kind is not None
                    else None
                ),
                resolver_type=(
                    RequestResolverTypeEnum(row.resolver_type)
                    if row.resolver_type is not None
                    else None
                ),
                comment=row.comment,
            )
            for row in rows
        ]

    def get_request_for_user(
        self,
        request_id: int,
        current_user: User,
    ) -> WorkflowRequest:
        """Return a request if the user is allowed to access it."""

        workflow_request = self._get_request(request_id)
        self._authorize_request_access(workflow_request, current_user)
        return workflow_request

    def approve_current_step(
        self,
        request_id: int,
        current_user: User,
        *,
        comment: str | None,
    ) -> WorkflowRequest:
        """Approve the current workflow step and advance the request."""

        workflow_request = self._get_request(request_id)
        self._ensure_request_actionable_by_user(workflow_request, current_user)
        requester_employee = self._get_requester_employee(workflow_request.requester_employee_id)
        current_step = self.get_workflow_step(workflow_request.current_step_id)
        request_type = self.get_request_type(workflow_request.request_type_id)
        notifications_service = NotificationsService(self.db)
        pending_notifications: list[Notification] = []

        try:
            self._record_history(
                workflow_request=workflow_request,
                step=current_step,
                actor_user_id=current_user.id,
                action=RequestActionEnum.APPROVED,
                comment=comment,
            )
            self._advance_request_workflow(
                workflow_request=workflow_request,
                requester_employee=requester_employee,
                start_after_order=current_step.step_order,
            )
            self._queue_post_approval_notifications(
                notifications_service=notifications_service,
                pending_notifications=pending_notifications,
                workflow_request=workflow_request,
                request_type=request_type,
                requester_employee=requester_employee,
            )
            self.db.add(workflow_request)
            self.db.commit()
        except (RequestsValidationError, RequestsNotFoundError, RequestsAuthorizationError):
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            raise RequestsConflictError("Failed to approve the request step.") from exc

        self.db.refresh(workflow_request)
        self._publish_pending_notifications(
            notifications_service=notifications_service,
            notifications=pending_notifications,
        )
        return workflow_request

    def reject_current_step(
        self,
        request_id: int,
        current_user: User,
        *,
        comment: str | None,
    ) -> WorkflowRequest:
        """Reject the current workflow step and finish the request as rejected."""

        workflow_request = self._get_request(request_id)
        self._ensure_request_actionable_by_user(workflow_request, current_user)
        current_step = self.get_workflow_step(workflow_request.current_step_id)
        request_type = self.get_request_type(workflow_request.request_type_id)
        notifications_service = NotificationsService(self.db)
        pending_notifications: list[Notification] = []

        try:
            self._record_history(
                workflow_request=workflow_request,
                step=current_step,
                actor_user_id=current_user.id,
                action=RequestActionEnum.REJECTED,
                comment=comment,
            )
            workflow_request.status = RequestStatusEnum.REJECTED.value
            workflow_request.current_step_id = None
            workflow_request.current_approver_user_id = None
            workflow_request.completed_at = utcnow()
            workflow_request.rejection_reason = comment
            self._queue_rejection_notifications(
                notifications_service=notifications_service,
                pending_notifications=pending_notifications,
                workflow_request=workflow_request,
                request_type=request_type,
            )
            self.db.add(workflow_request)
            self.db.commit()
        except (RequestsValidationError, RequestsNotFoundError, RequestsAuthorizationError):
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            raise RequestsConflictError("Failed to reject the request step.") from exc

        self.db.refresh(workflow_request)
        self._publish_pending_notifications(
            notifications_service=notifications_service,
            notifications=pending_notifications,
        )
        return workflow_request

    def build_request_summaries(
        self,
        workflow_requests: list[WorkflowRequest],
    ) -> list[RequestSummaryResponse]:
        """Build summary responses for a request collection."""

        if not workflow_requests:
            return []

        (
            request_types_by_id,
            steps_by_id,
            users_by_id,
            employees_by_id,
        ) = self._load_summary_maps(workflow_requests)
        return [
            self._build_request_summary(
                workflow_request,
                request_types_by_id=request_types_by_id,
                steps_by_id=steps_by_id,
                users_by_id=users_by_id,
                employees_by_id=employees_by_id,
            )
            for workflow_request in workflow_requests
        ]

    def build_request_detail(self, workflow_request: WorkflowRequest) -> RequestDetailResponse:
        """Build a detailed response for a single request."""

        request_type = self.get_request_type(workflow_request.request_type_id)
        requester_employee = self._get_requester_employee(workflow_request.requester_employee_id)
        current_step = (
            self.get_workflow_step(workflow_request.current_step_id)
            if workflow_request.current_step_id is not None
            else None
        )
        current_approver = (
            self.db.get(User, workflow_request.current_approver_user_id)
            if workflow_request.current_approver_user_id is not None
            else None
        )

        field_values = list(
            self.db.execute(
                select(RequestFieldValue)
                .where(RequestFieldValue.request_id == workflow_request.id)
                .order_by(
                    RequestFieldValue.sort_order.asc(),
                    RequestFieldValue.field_code.asc(),
                    RequestFieldValue.id.asc(),
                )
            )
            .scalars()
            .all()
        )

        action_history = list(
            self.db.execute(
                select(RequestActionHistory)
                .where(RequestActionHistory.request_id == workflow_request.id)
                .order_by(
                    RequestActionHistory.created_at.asc(),
                    RequestActionHistory.id.asc(),
                )
            )
            .scalars()
            .all()
        )

        actor_user_ids = {
            action.actor_user_id
            for action in action_history
            if action.actor_user_id is not None
        }
        actor_users = self._get_users_by_ids(actor_user_ids)

        workflow_steps = self._get_request_progress_steps(
            workflow_request.request_type_id,
            action_history,
            workflow_request.current_step_id,
        )

        return RequestDetailResponse(
            **self._build_request_summary(
                workflow_request,
                request_types_by_id={request_type.id: request_type},
                steps_by_id={current_step.id: current_step} if current_step is not None else {},
                users_by_id=(
                    {current_approver.id: current_approver}
                    if current_approver is not None
                    else {}
                ),
                employees_by_id={requester_employee.id: requester_employee},
            ).model_dump(),
            submitted_values=[
                RequestFieldValueResponse.model_validate(field_value)
                for field_value in field_values
            ],
            action_history=[
                self._build_request_action_history_response(action, actor_users)
                for action in action_history
            ],
            leave_details=self._build_leave_request_details(
                request_type=request_type,
                requester_employee_id=workflow_request.requester_employee_id,
                field_values=field_values,
            ),
            workflow_progress=self._build_workflow_progress(
                workflow_request=workflow_request,
                workflow_steps=workflow_steps,
                action_history=action_history,
                actor_users=actor_users,
            ),
        )

    def _build_leave_request_details(
        self,
        *,
        request_type: RequestType,
        requester_employee_id: int,
        field_values: list[RequestFieldValue],
    ) -> LeaveRequestDetailsResponse | None:
        """Build computed leave metadata for leave request details."""

        if not is_leave_request_type_code(request_type.code):
            return None

        requester_employee = self._get_requester_employee(requester_employee_id)
        persisted_values = {
            field_value.field_code: field_value.value for field_value in field_values
        }
        try:
            leave_evaluation = evaluate_leave_request(
                persisted_values,
                requester_employee.available_leave_balance_days,
                enforce_balance_check=False,
            )
        except LeaveBusinessRuleError:
            return None

        return LeaveRequestDetailsResponse(
            date_start=leave_evaluation.date_start,
            date_end=leave_evaluation.date_end,
            requested_duration_days=leave_evaluation.requested_duration_days,
            leave_option=leave_evaluation.leave_option.value,
            leave_option_label=leave_evaluation.leave_option_label,
            balance_validation_applied=leave_evaluation.balance_validation_applied,
            requester_available_balance_days=leave_evaluation.available_balance_days,
        )

    def _build_request_summary(
        self,
        workflow_request: WorkflowRequest,
        *,
        request_types_by_id: dict[int, RequestType],
        steps_by_id: dict[int, RequestWorkflowStep],
        users_by_id: dict[int, User],
        employees_by_id: dict[int, Employee],
    ) -> RequestSummaryResponse:
        """Build a summary response for a request instance."""

        request_type = request_types_by_id[workflow_request.request_type_id]
        requester_employee = employees_by_id.get(workflow_request.requester_employee_id)
        if requester_employee is None:
            requester_employee = self._get_requester_employee(workflow_request.requester_employee_id)

        current_step = (
            steps_by_id.get(workflow_request.current_step_id)
            if workflow_request.current_step_id is not None
            else None
        )
        current_approver = (
            users_by_id.get(workflow_request.current_approver_user_id)
            if workflow_request.current_approver_user_id is not None
            else None
        )

        return RequestSummaryResponse(
            id=workflow_request.id,
            request_type_id=request_type.id,
            request_type_code=request_type.code,
            request_type_name=request_type.name,
            requester_user_id=workflow_request.requester_user_id,
            requester_employee_id=workflow_request.requester_employee_id,
            requester_name=(
                f"{requester_employee.first_name} {requester_employee.last_name}"
            ),
            requester_matricule=requester_employee.matricule,
            status=RequestStatusEnum(workflow_request.status),
            current_step=(
                self._build_current_step_response(current_step, current_approver)
                if current_step is not None
                else None
            ),
            submitted_at=workflow_request.submitted_at,
            completed_at=workflow_request.completed_at,
            rejection_reason=workflow_request.rejection_reason,
            created_at=workflow_request.created_at,
            updated_at=workflow_request.updated_at,
        )

    def _build_current_step_response(
        self,
        current_step: RequestWorkflowStep,
        current_approver: User | None,
    ) -> RequestCurrentStepResponse:
        """Build the current-step summary payload."""

        approver_name = None
        if current_approver is not None:
            approver_name = f"{current_approver.first_name} {current_approver.last_name}"

        return RequestCurrentStepResponse(
            id=current_step.id,
            step_order=current_step.step_order,
            name=current_step.name,
            step_kind=RequestStepKindEnum(current_step.step_kind),
            resolver_type=(
                RequestResolverTypeEnum(current_step.resolver_type)
                if current_step.resolver_type is not None
                else None
            ),
            is_required=current_step.is_required,
            current_approver_user_id=(
                current_approver.id if current_approver is not None else None
            ),
            current_approver_matricule=(
                current_approver.matricule if current_approver is not None else None
            ),
            current_approver_name=approver_name,
        )

    def _build_request_action_history_response(
        self,
        action: RequestActionHistory,
        actor_users: dict[int, User],
    ) -> RequestActionHistoryResponse:
        """Build a workflow action-history response entry."""

        actor = actor_users.get(action.actor_user_id) if action.actor_user_id is not None else None
        actor_name = None
        if actor is not None:
            actor_name = f"{actor.first_name} {actor.last_name}"

        return RequestActionHistoryResponse(
            id=action.id,
            step_id=action.step_id,
            step_name=action.step_name,
            step_order=action.step_order,
            step_kind=(
                RequestStepKindEnum(action.step_kind)
                if action.step_kind is not None
                else None
            ),
            resolver_type=(
                RequestResolverTypeEnum(action.resolver_type)
                if action.resolver_type is not None
                else None
            ),
            actor_user_id=action.actor_user_id,
            actor_matricule=actor.matricule if actor is not None else None,
            actor_name=actor_name,
            action=RequestActionEnum(action.action),
            comment=action.comment,
            created_at=action.created_at,
        )

    def _build_workflow_progress(
        self,
        *,
        workflow_request: WorkflowRequest,
        workflow_steps: list[RequestWorkflowStep],
        action_history: list[RequestActionHistory],
        actor_users: dict[int, User],
    ) -> list[RequestWorkflowProgressResponse]:
        """Build workflow progress states for each effective step."""

        latest_action_by_step_id: dict[int, RequestActionHistory] = {}
        for action in action_history:
            if action.step_id is None:
                continue

            latest_action_by_step_id[action.step_id] = action

        progress_entries: list[RequestWorkflowProgressResponse] = []
        for step in workflow_steps:
            latest_action = latest_action_by_step_id.get(step.id)
            actor = (
                actor_users.get(latest_action.actor_user_id)
                if latest_action is not None and latest_action.actor_user_id is not None
                else None
            )
            actor_name = None
            if actor is not None:
                actor_name = f"{actor.first_name} {actor.last_name}"

            if latest_action is not None:
                state = latest_action.action
                acted_at = latest_action.created_at
                comment = latest_action.comment
            elif workflow_request.current_step_id == step.id:
                state = "pending"
                acted_at = None
                comment = None
            else:
                state = "waiting"
                acted_at = None
                comment = None

            progress_entries.append(
                RequestWorkflowProgressResponse(
                    step_id=step.id,
                    step_order=step.step_order,
                    name=step.name,
                    step_kind=RequestStepKindEnum(step.step_kind),
                    resolver_type=(
                        RequestResolverTypeEnum(step.resolver_type)
                        if step.resolver_type is not None
                        else None
                    ),
                    is_required=step.is_required,
                    state=state,
                    actor_user_id=actor.id if actor is not None else None,
                    actor_matricule=actor.matricule if actor is not None else None,
                    actor_name=actor_name,
                    comment=comment,
                    acted_at=acted_at,
                )
            )

        return progress_entries

    def _persist_request_values(
        self,
        workflow_request: WorkflowRequest,
        active_fields: list[RequestTypeField],
        normalized_values: dict[str, Any],
    ) -> None:
        """Persist normalized request values as immutable field snapshots."""

        fields_by_code = {request_field.code: request_field for request_field in active_fields}
        for field_code, value in normalized_values.items():
            request_field = fields_by_code[field_code]
            request_value = RequestFieldValue(
                request_id=workflow_request.id,
                request_field_id=request_field.id,
                field_code=request_field.code,
                field_label=request_field.label,
                field_type=request_field.field_type,
                sort_order=request_field.sort_order,
                value=value,
            )
            self.db.add(request_value)

    def _normalize_submitted_values(
        self,
        active_fields: list[RequestTypeField],
        submitted_values: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate submitted request values against configured field definitions."""

        active_fields_by_code = {request_field.code: request_field for request_field in active_fields}
        unknown_codes = sorted(set(submitted_values) - set(active_fields_by_code))
        if unknown_codes:
            unknown_list = ", ".join(unknown_codes)
            raise RequestsValidationError(f"Unknown request field codes: {unknown_list}.")

        normalized_values: dict[str, Any] = {}
        for request_field in active_fields:
            raw_value = (
                submitted_values[request_field.code]
                if request_field.code in submitted_values
                else request_field.default_value
            )
            normalized_value = self._normalize_value_for_type(
                field_type=request_field.field_type,
                value=raw_value,
                label=request_field.label,
                required=request_field.is_required,
                allow_none=not request_field.is_required,
            )
            if normalized_value is not None or request_field.code in submitted_values:
                normalized_values[request_field.code] = normalized_value
                continue

            if request_field.default_value is not None:
                normalized_values[request_field.code] = normalized_value

        return normalized_values

    def _normalize_value_for_type(
        self,
        *,
        field_type: str,
        value: Any,
        label: str,
        required: bool,
        allow_none: bool,
    ) -> Any:
        """Normalize and validate a dynamic field value."""

        if value is None:
            if allow_none:
                return None

            raise RequestsValidationError(f"{label} is required.")

        normalized_type = RequestFieldTypeEnum(field_type)
        if normalized_type in {
            RequestFieldTypeEnum.TEXT,
            RequestFieldTypeEnum.TEXTAREA,
            RequestFieldTypeEnum.SELECT,
        }:
            if not isinstance(value, str):
                raise RequestsValidationError(f"{label} must be a string.")

            normalized_value = value.strip()
            if not normalized_value:
                if required:
                    raise RequestsValidationError(f"{label} cannot be blank.")

                return None

            return normalized_value

        if normalized_type == RequestFieldTypeEnum.NUMBER:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RequestsValidationError(f"{label} must be a number.")

            return value

        if normalized_type == RequestFieldTypeEnum.BOOLEAN:
            if not isinstance(value, bool):
                raise RequestsValidationError(f"{label} must be a boolean.")

            return value

        if normalized_type == RequestFieldTypeEnum.DATE:
            return self._normalize_date_value(value, label)

        if normalized_type == RequestFieldTypeEnum.DATETIME:
            return self._normalize_datetime_value(value, label)

        raise RequestsValidationError(f"{label} uses an unsupported field type.")

    def _normalize_date_value(self, value: Any, label: str) -> str:
        """Normalize a date input value to ISO format."""

        if isinstance(value, datetime):
            return value.date().isoformat()

        if isinstance(value, date):
            return value.isoformat()

        if isinstance(value, str):
            normalized_value = value.strip()
            if not normalized_value:
                raise RequestsValidationError(f"{label} cannot be blank.")

            try:
                return date.fromisoformat(normalized_value).isoformat()
            except ValueError as exc:
                raise RequestsValidationError(
                    f"{label} must be a valid ISO date."
                ) from exc

        raise RequestsValidationError(f"{label} must be a valid date.")

    def _normalize_datetime_value(self, value: Any, label: str) -> str:
        """Normalize a datetime input value to ISO format."""

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, str):
            normalized_value = value.strip()
            if not normalized_value:
                raise RequestsValidationError(f"{label} cannot be blank.")

            candidate = normalized_value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(candidate).isoformat()
            except ValueError as exc:
                raise RequestsValidationError(
                    f"{label} must be a valid ISO datetime."
                ) from exc

        raise RequestsValidationError(f"{label} must be a valid datetime.")

    def _validate_request_type_business_configuration(
        self,
        request_type: RequestType,
        active_fields: list[RequestTypeField],
    ) -> None:
        """Validate request-type configuration required by business-specific rules."""

        if not is_leave_request_type_code(request_type.code):
            return

        try:
            validate_leave_request_type_fields(active_fields)
        except LeaveBusinessRuleError as exc:
            raise RequestsValidationError(str(exc)) from exc

    def _validate_request_business_rules(
        self,
        *,
        request_type: RequestType,
        requester_employee: Employee,
        normalized_values: dict[str, Any],
    ) -> None:
        """Run type-specific business validation before request creation."""

        if not is_leave_request_type_code(request_type.code):
            return

        try:
            evaluate_leave_request(
                normalized_values,
                requester_employee.available_leave_balance_days,
                enforce_balance_check=True,
            )
        except LeaveBusinessRuleError as exc:
            raise RequestsValidationError(str(exc)) from exc

    def _validate_request_field_business_definition(
        self,
        *,
        request_type: RequestType,
        field_code: str,
        field_type: RequestFieldTypeEnum,
    ) -> None:
        """Validate business-specific field-definition constraints."""

        if not is_leave_request_type_code(request_type.code):
            return

        try:
            validate_leave_field_definition(
                field_code=field_code,
                field_type=field_type,
            )
        except LeaveBusinessRuleError as exc:
            raise RequestsValidationError(str(exc)) from exc

    def _validate_required_steps_resolvable(
        self,
        requester_employee: Employee,
        workflow_steps: list[RequestWorkflowStep],
    ) -> None:
        """Ensure every required approver step can be resolved before creation."""

        for step in workflow_steps:
            if step.step_kind != RequestStepKindEnum.APPROVER.value:
                continue

            resolved_user = self._resolve_approver_for_step(step, requester_employee)
            if resolved_user is None and step.is_required:
                raise RequestsValidationError(
                    f"Workflow step '{step.name}' requires a resolvable approver."
                )

    def _advance_request_workflow(
        self,
        *,
        workflow_request: WorkflowRequest,
        requester_employee: Employee,
        start_after_order: int | None,
    ) -> None:
        """Advance a request to the next effective workflow step or final state."""

        workflow_request.status = RequestStatusEnum.IN_PROGRESS.value
        workflow_request.current_step_id = None
        workflow_request.current_approver_user_id = None

        workflow_steps = self._get_request_workflow_steps(
            workflow_request.request_type_id,
            active_only=True,
        )
        for step in workflow_steps:
            if start_after_order is not None and step.step_order <= start_after_order:
                continue

            if step.step_kind == RequestStepKindEnum.CONCEPTION.value:
                self._record_history(
                    workflow_request=workflow_request,
                    step=step,
                    actor_user_id=None,
                    action=RequestActionEnum.COMPLETED,
                    comment="Completed automatically by the workflow engine.",
                )
                continue

            approver = self._resolve_approver_for_step(step, requester_employee)
            if approver is None:
                if step.is_required:
                    raise RequestsValidationError(
                        f"Workflow step '{step.name}' requires a resolvable approver."
                    )

                self._record_history(
                    workflow_request=workflow_request,
                    step=step,
                    actor_user_id=None,
                    action=RequestActionEnum.SKIPPED,
                    comment="Skipped because no approver could be resolved.",
                )
                continue

            workflow_request.current_step_id = step.id
            workflow_request.current_approver_user_id = approver.id
            return

        workflow_request.status = RequestStatusEnum.APPROVED.value
        workflow_request.current_step_id = None
        workflow_request.current_approver_user_id = None
        workflow_request.completed_at = utcnow()
        workflow_request.rejection_reason = None

    def _resolve_approver_for_step(
        self,
        step: RequestWorkflowStep,
        requester_employee: Employee,
    ) -> User | None:
        """Resolve the user account responsible for an approver step."""

        if step.step_kind != RequestStepKindEnum.APPROVER.value:
            return None

        if step.resolver_type == RequestResolverTypeEnum.TEAM_LEADER.value:
            return self._resolve_team_leader(requester_employee)

        if step.resolver_type == RequestResolverTypeEnum.DEPARTMENT_MANAGER.value:
            return self._resolve_department_manager(requester_employee)

        if step.resolver_type == RequestResolverTypeEnum.RH_MANAGER.value:
            return self._resolve_rh_manager()

        raise RequestsValidationError(
            f"Unsupported resolver type '{step.resolver_type}'."
        )

    def _resolve_team_leader(self, requester_employee: Employee) -> User | None:
        """Resolve the team leader of the requester's current team."""

        if requester_employee.team_id is None:
            return None

        team = self.db.get(Team, requester_employee.team_id)
        if team is None or not team.is_active or team.leader_user_id is None:
            return None

        return self._get_active_user(team.leader_user_id)

    def _resolve_department_manager(self, requester_employee: Employee) -> User | None:
        """Resolve the manager of the requester's current department."""

        if requester_employee.department_id is None:
            return None

        department = self.db.get(Department, requester_employee.department_id)
        if department is None or not department.is_active or department.manager_user_id is None:
            return None

        return self._get_active_user(department.manager_user_id)

    def _resolve_rh_manager(self) -> User | None:
        """Resolve the active RH manager user using the RH_MANAGER job-title code."""

        statement = (
            select(User)
            .join(Employee, Employee.user_id == User.id)
            .join(JobTitle, JobTitle.id == Employee.job_title_id)
            .where(
                User.is_active.is_(True),
                Employee.is_active.is_(True),
                JobTitle.is_active.is_(True),
                JobTitle.code == self.RH_MANAGER_JOB_TITLE_CODE,
            )
            .order_by(Employee.id.asc(), User.id.asc())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def _queue_submission_notifications(
        self,
        *,
        notifications_service: NotificationsService,
        pending_notifications: list[Notification],
        workflow_request: WorkflowRequest,
        request_type: RequestType,
        requester_employee: Employee,
    ) -> None:
        """Queue notifications triggered when a request is first submitted."""

        if workflow_request.current_approver_user_id is not None:
            self._queue_request_notification(
                notifications_service=notifications_service,
                pending_notifications=pending_notifications,
                recipient_user_id=workflow_request.current_approver_user_id,
                notification_type=NotificationTypeEnum.REQUEST_ASSIGNED,
                title="Nouvelle demande a traiter",
                message=(
                    f"La demande '{request_type.name}' de "
                    f"{requester_employee.first_name} {requester_employee.last_name} "
                    "necessite votre decision."
                ),
                request_id=workflow_request.id,
            )
            return

        if workflow_request.status == RequestStatusEnum.APPROVED.value:
            self._queue_request_notification(
                notifications_service=notifications_service,
                pending_notifications=pending_notifications,
                recipient_user_id=workflow_request.requester_user_id,
                notification_type=NotificationTypeEnum.REQUEST_APPROVED,
                title="Demande approuvee",
                message=f"Votre demande '{request_type.name}' a ete approuvee.",
                request_id=workflow_request.id,
            )

    def _queue_post_approval_notifications(
        self,
        *,
        notifications_service: NotificationsService,
        pending_notifications: list[Notification],
        workflow_request: WorkflowRequest,
        request_type: RequestType,
        requester_employee: Employee,
    ) -> None:
        """Queue notifications triggered after an approval action."""

        if workflow_request.current_approver_user_id is not None:
            self._queue_request_notification(
                notifications_service=notifications_service,
                pending_notifications=pending_notifications,
                recipient_user_id=workflow_request.current_approver_user_id,
                notification_type=NotificationTypeEnum.REQUEST_ASSIGNED,
                title="Nouvelle demande a traiter",
                message=(
                    f"La demande '{request_type.name}' de "
                    f"{requester_employee.first_name} {requester_employee.last_name} "
                    "necessite votre decision."
                ),
                request_id=workflow_request.id,
            )
            self._queue_request_notification(
                notifications_service=notifications_service,
                pending_notifications=pending_notifications,
                recipient_user_id=workflow_request.requester_user_id,
                notification_type=NotificationTypeEnum.REQUEST_STEP_UPDATED,
                title="Demande transmise a l'etape suivante",
                message=(
                    f"Votre demande '{request_type.name}' a ete approuvee "
                    "et transmise a l'etape suivante."
                ),
                request_id=workflow_request.id,
            )
            return

        if workflow_request.status == RequestStatusEnum.APPROVED.value:
            self._queue_request_notification(
                notifications_service=notifications_service,
                pending_notifications=pending_notifications,
                recipient_user_id=workflow_request.requester_user_id,
                notification_type=NotificationTypeEnum.REQUEST_APPROVED,
                title="Demande approuvee",
                message=f"Votre demande '{request_type.name}' a ete approuvee.",
                request_id=workflow_request.id,
            )

    def _queue_rejection_notifications(
        self,
        *,
        notifications_service: NotificationsService,
        pending_notifications: list[Notification],
        workflow_request: WorkflowRequest,
        request_type: RequestType,
    ) -> None:
        """Queue notifications triggered after a rejection action."""

        self._queue_request_notification(
            notifications_service=notifications_service,
            pending_notifications=pending_notifications,
            recipient_user_id=workflow_request.requester_user_id,
            notification_type=NotificationTypeEnum.REQUEST_REJECTED,
            title="Demande rejetee",
            message=f"Votre demande '{request_type.name}' a ete rejetee.",
            request_id=workflow_request.id,
        )

    def _queue_request_notification(
        self,
        *,
        notifications_service: NotificationsService,
        pending_notifications: list[Notification],
        recipient_user_id: int | None,
        notification_type: NotificationTypeEnum,
        title: str,
        message: str,
        request_id: int,
    ) -> None:
        """Queue a request-related notification inside the current transaction."""

        if recipient_user_id is None:
            return

        notification = notifications_service.create_notification(
            recipient_user_id=recipient_user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            target_url=f"/requests/{request_id}",
            commit=False,
            publish_realtime=False,
        )
        pending_notifications.append(notification)

    def _publish_pending_notifications(
        self,
        *,
        notifications_service: NotificationsService,
        notifications: list[Notification],
    ) -> None:
        """Publish committed notifications to connected websocket clients."""

        for notification in notifications:
            notifications_service.publish_realtime_notification(notification)

    def _record_history(
        self,
        *,
        workflow_request: WorkflowRequest,
        step: RequestWorkflowStep | None,
        actor_user_id: int | None,
        action: RequestActionEnum,
        comment: str | None,
    ) -> None:
        """Persist a workflow action-history entry."""

        history_entry = RequestActionHistory(
            request_id=workflow_request.id,
            step_id=step.id if step is not None else None,
            step_name=step.name if step is not None else None,
            step_order=step.step_order if step is not None else None,
            step_kind=step.step_kind if step is not None else None,
            resolver_type=step.resolver_type if step is not None else None,
            actor_user_id=actor_user_id,
            action=action.value,
            comment=comment,
        )
        self.db.add(history_entry)

    def _authorize_request_access(
        self,
        workflow_request: WorkflowRequest,
        current_user: User,
    ) -> None:
        """Authorize read access to a request instance."""

        if current_user.is_super_admin:
            return

        if workflow_request.requester_user_id == current_user.id:
            return

        if workflow_request.current_approver_user_id == current_user.id:
            return

        permissions_service = PermissionsService(self.db)
        if permissions_service.user_has_permission(current_user, "requests.read_all"):
            return

        raise RequestsAuthorizationError("You are not allowed to access this request.")

    def _ensure_request_actionable_by_user(
        self,
        workflow_request: WorkflowRequest,
        current_user: User,
    ) -> None:
        """Require the current user to be the exact pending approver."""

        if workflow_request.status != RequestStatusEnum.IN_PROGRESS.value:
            raise RequestsValidationError("Only in-progress requests can be processed.")

        if workflow_request.current_step_id is None or workflow_request.current_approver_user_id is None:
            raise RequestsValidationError("This request does not have a pending approver step.")

        if workflow_request.current_approver_user_id != current_user.id:
            raise RequestsAuthorizationError(
                "Only the current resolved approver can process this request."
            )

    def _get_request(self, request_id: int) -> WorkflowRequest:
        """Return a request instance by id."""

        workflow_request = self.db.get(WorkflowRequest, request_id)
        if workflow_request is None:
            raise RequestsNotFoundError("Request not found.")

        return workflow_request

    def _get_requester_employee(self, requester_employee_id: int) -> Employee:
        """Return the employee profile linked to the request requester."""

        requester_employee = self.db.get(Employee, requester_employee_id)
        if requester_employee is None:
            raise RequestsValidationError("Requester employee record no longer exists.")

        return requester_employee

    def _get_active_employee_by_user_id(self, user_id: int) -> Employee:
        """Return the active employee profile linked to a user."""

        statement = (
            select(Employee)
            .where(Employee.user_id == user_id, Employee.is_active.is_(True))
            .limit(1)
        )
        employee = self.db.execute(statement).scalar_one_or_none()
        if employee is None:
            raise RequestsValidationError(
                "The authenticated user must be linked to an active employee profile."
            )

        return employee

    def _get_active_user(self, user_id: int) -> User | None:
        """Return an active user by id."""

        user = self.db.get(User, user_id)
        if user is None or not user.is_active:
            return None

        return user

    def _get_request_type_fields(
        self,
        request_type_id: int,
        *,
        active_only: bool,
    ) -> list[RequestTypeField]:
        """Return field definitions for a request type."""

        statement = select(RequestTypeField).where(
            RequestTypeField.request_type_id == request_type_id
        )
        if active_only:
            statement = statement.where(RequestTypeField.is_active.is_(True))

        statement = statement.order_by(
            RequestTypeField.sort_order.asc(),
            RequestTypeField.id.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def _get_request_workflow_steps(
        self,
        request_type_id: int,
        *,
        active_only: bool,
    ) -> list[RequestWorkflowStep]:
        """Return workflow-step definitions for a request type."""

        statement = select(RequestWorkflowStep).where(
            RequestWorkflowStep.request_type_id == request_type_id
        )
        if active_only:
            statement = statement.where(RequestWorkflowStep.is_active.is_(True))

        statement = statement.order_by(
            RequestWorkflowStep.step_order.asc(),
            RequestWorkflowStep.id.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def _get_request_progress_steps(
        self,
        request_type_id: int,
        action_history: list[RequestActionHistory],
        current_step_id: int | None,
    ) -> list[RequestWorkflowStep]:
        """Return effective workflow steps used to build progress details."""

        history_step_ids = {action.step_id for action in action_history if action.step_id is not None}
        if current_step_id is not None:
            history_step_ids.add(current_step_id)

        active_steps = self._get_request_workflow_steps(request_type_id, active_only=True)
        active_step_ids = {step.id for step in active_steps}
        missing_ids = history_step_ids - active_step_ids
        if not missing_ids:
            return active_steps

        historical_steps = list(
            self.db.execute(
                select(RequestWorkflowStep).where(RequestWorkflowStep.id.in_(missing_ids))
            )
            .scalars()
            .all()
        )
        steps_by_id = {step.id: step for step in active_steps}
        for step in historical_steps:
            steps_by_id[step.id] = step

        return sorted(steps_by_id.values(), key=lambda item: (item.step_order, item.id))

    def _load_summary_maps(
        self,
        workflow_requests: list[WorkflowRequest],
    ) -> tuple[
        dict[int, RequestType],
        dict[int, RequestWorkflowStep],
        dict[int, User],
        dict[int, Employee],
    ]:
        """Load the supporting request-type, step, user, and employee maps for summaries."""

        request_type_ids = {workflow_request.request_type_id for workflow_request in workflow_requests}
        requester_employee_ids = {
            workflow_request.requester_employee_id for workflow_request in workflow_requests
        }
        step_ids = {
            workflow_request.current_step_id
            for workflow_request in workflow_requests
            if workflow_request.current_step_id is not None
        }
        user_ids = {
            workflow_request.current_approver_user_id
            for workflow_request in workflow_requests
            if workflow_request.current_approver_user_id is not None
        }

        request_types = list(
            self.db.execute(
                select(RequestType).where(RequestType.id.in_(request_type_ids))
            )
            .scalars()
            .all()
        )
        steps = (
            list(
                self.db.execute(
                    select(RequestWorkflowStep).where(RequestWorkflowStep.id.in_(step_ids))
                )
                .scalars()
                .all()
            )
            if step_ids
            else []
        )
        users = self._get_users_by_ids(user_ids)
        employees = self._get_employees_by_ids(requester_employee_ids)

        return (
            {request_type.id: request_type for request_type in request_types},
            {step.id: step for step in steps},
            users,
            employees,
        )

    def _get_users_by_ids(self, user_ids: set[int]) -> dict[int, User]:
        """Load users in bulk by id."""

        if not user_ids:
            return {}

        users = list(
            self.db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
        )
        return {user.id: user for user in users}

    def _get_employees_by_ids(self, employee_ids: set[int]) -> dict[int, Employee]:
        """Load employees in bulk by id."""

        if not employee_ids:
            return {}

        employees = list(
            self.db.execute(select(Employee).where(Employee.id.in_(employee_ids)))
            .scalars()
            .all()
        )
        return {employee.id: employee for employee in employees}

    def _validate_step_configuration(
        self,
        *,
        step_kind: RequestStepKindEnum,
        resolver_type: RequestResolverTypeEnum | None,
    ) -> None:
        """Validate the step-kind and resolver configuration."""

        if step_kind == RequestStepKindEnum.APPROVER and resolver_type is None:
            raise RequestsValidationError("Approver steps must define a resolver type.")

        if step_kind == RequestStepKindEnum.CONCEPTION and resolver_type is not None:
            raise RequestsValidationError("Conception steps cannot define a resolver type.")

    def _ensure_unique_request_type_code(
        self,
        code: str,
        *,
        current_request_type_id: int | None = None,
    ) -> None:
        """Validate request-type code uniqueness."""

        statement = select(RequestType).where(RequestType.code == code)
        if current_request_type_id is not None:
            statement = statement.where(RequestType.id != current_request_type_id)

        existing_record = self.db.execute(statement.limit(1)).scalar_one_or_none()
        if existing_record is not None:
            raise RequestsConflictError("Request type code already exists.")

    def _ensure_unique_request_field_code(
        self,
        request_type_id: int,
        code: str,
        *,
        current_request_field_id: int | None = None,
    ) -> None:
        """Validate request-field code uniqueness inside a request type."""

        statement = select(RequestTypeField).where(
            RequestTypeField.request_type_id == request_type_id,
            RequestTypeField.code == code,
        )
        if current_request_field_id is not None:
            statement = statement.where(RequestTypeField.id != current_request_field_id)

        existing_record = self.db.execute(statement.limit(1)).scalar_one_or_none()
        if existing_record is not None:
            raise RequestsConflictError("Request field code already exists for this request type.")

    def _ensure_unique_workflow_step_order(
        self,
        request_type_id: int,
        step_order: int,
        *,
        current_step_id: int | None = None,
    ) -> None:
        """Validate workflow-step order uniqueness inside a request type."""

        statement = select(RequestWorkflowStep).where(
            RequestWorkflowStep.request_type_id == request_type_id,
            RequestWorkflowStep.step_order == step_order,
        )
        if current_step_id is not None:
            statement = statement.where(RequestWorkflowStep.id != current_step_id)

        existing_record = self.db.execute(statement.limit(1)).scalar_one_or_none()
        if existing_record is not None:
            raise RequestsConflictError(
                "Workflow step order already exists for this request type."
            )

    def _commit_and_refresh(self, instance, *, conflict_message: str):
        """Commit the current transaction and refresh the target instance."""

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise RequestsConflictError(conflict_message) from exc

        self.db.refresh(instance)
        return instance
