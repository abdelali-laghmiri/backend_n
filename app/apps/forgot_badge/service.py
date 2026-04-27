from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.attendance.models import NfcCard, NfcCardStatusEnum, NfcCardTypeEnum
from app.apps.employees.models import Employee
from app.apps.forgot_badge.models import (
    ForgotBadgeRequest,
    ForgotBadgeRequestStatusEnum,
    TemporaryNfcAssignment,
    TemporaryNfcAssignmentStatusEnum,
)
from app.apps.forgot_badge.schemas import (
    ForgotBadgeRequestApproveRequest,
    ForgotBadgeRequestCancelRequest,
    ForgotBadgeRequestCompleteRequest,
    ForgotBadgeRequestCreateRequest,
    ForgotBadgeRequestRejectRequest,
    ForgotBadgeRequestResponse,
    ForgotBadgeRequestWithAssignmentResponse,
    TemporaryNfcAssignmentResponse,
)
from app.apps.users.models import User

class ForgotBadgeConflictError(RuntimeError):
    """Raised when a unique or state conflict prevents the operation."""


class ForgotBadgeNotFoundError(RuntimeError):
    """Raised when a forgot badge related record cannot be found."""


class ForgotBadgeValidationError(RuntimeError):
    """Raised when a forgot badge request is invalid."""


class ForgotBadgeService:
    """Service layer for forgot badge requests and temporary NFC assignments."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_request(
        self,
        payload: ForgotBadgeRequestCreateRequest,
        current_user: User,
    ) -> ForgotBadgeRequest:
        """Create a forgot badge request for the current user."""

        employee = self._get_employee_for_user(current_user.id)
        self._ensure_no_pending_request_for_today(employee.id)

        request = ForgotBadgeRequest(
            employee_id=employee.id,
            user_id=current_user.id,
            status=ForgotBadgeRequestStatusEnum.PENDING.value,
            reason=payload.reason,
            requested_at=datetime.now(timezone.utc),
        )
        self.db.add(request)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ForgotBadgeConflictError("Failed to create forgot badge request.") from exc

        self.db.refresh(request)
        return request

    def list_own_requests(
        self,
        current_user: User,
    ) -> list[ForgotBadgeRequest]:
        """List forgot badge requests for the current user."""

        employee = self._get_employee_for_user(current_user.id)
        statement = (
            select(ForgotBadgeRequest)
            .where(ForgotBadgeRequest.employee_id == employee.id)
            .order_by(ForgotBadgeRequest.requested_at.desc())
        )
        return list(self.db.execute(statement).scalars().all())

    def list_all_requests(
        self,
        employee_id: int | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[ForgotBadgeRequest]:
        """List all forgot badge requests with optional filters."""

        statement: Select[tuple[ForgotBadgeRequest]] = select(ForgotBadgeRequest)
        if employee_id is not None:
            statement = statement.where(ForgotBadgeRequest.employee_id == employee_id)

        if status is not None:
            statement = statement.where(ForgotBadgeRequest.status == status)

        if date_from is not None:
            statement = statement.where(ForgotBadgeRequest.requested_at >= date_from)

        if date_to is not None:
            statement = statement.where(ForgotBadgeRequest.requested_at <= date_to)

        statement = statement.order_by(ForgotBadgeRequest.requested_at.desc())
        return list(self.db.execute(statement).scalars().all())

    def get_request(self, request_id: int) -> ForgotBadgeRequest:
        """Return a forgot badge request by id."""

        request = self.db.get(ForgotBadgeRequest, request_id)
        if request is None:
            raise ForgotBadgeNotFoundError("Forgot badge request not found.")

        return request

    def approve_request(
        self,
        request_id: int,
        payload: ForgotBadgeRequestApproveRequest,
        current_user: User,
    ) -> ForgotBadgeRequestWithAssignmentResponse:
        """Approve a forgot badge request and attach a temporary NFC card."""

        request = self.get_request(request_id)
        if request.status != ForgotBadgeRequestStatusEnum.PENDING.value:
            raise ForgotBadgeValidationError(
                f"Cannot approve request with status '{request.status}'. Only PENDING requests can be approved."
            )

        nfc_card = self._resolve_temporary_nfc_card(payload)
        self._validate_temporary_card_available(
            nfc_card=nfc_card,
            employee_id=request.employee_id,
            valid_for_date=payload.valid_for_date,
        )

        self._close_active_temporary_assignments(
            nfc_card_id=nfc_card.id,
            valid_for_date=payload.valid_for_date,
        )

        request.status = ForgotBadgeRequestStatusEnum.APPROVED.value
        request.handled_by_user_id = current_user.id
        request.handled_at = datetime.now(timezone.utc)
        request.nfc_card_id = nfc_card.id
        request.valid_for_date = payload.valid_for_date
        if payload.notes:
            request.notes = payload.notes

        temporary_assignment = TemporaryNfcAssignment(
            employee_id=request.employee_id,
            nfc_card_id=nfc_card.id,
            forgot_badge_request_id=request.id,
            assigned_by_user_id=current_user.id,
            assigned_at=datetime.now(timezone.utc),
            valid_for_date=payload.valid_for_date,
            status=TemporaryNfcAssignmentStatusEnum.ACTIVE.value,
        )
        nfc_card.status = NfcCardStatusEnum.ASSIGNED.value
        self.db.add(nfc_card)
        self.db.add(temporary_assignment)
        self.db.add(request)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ForgotBadgeConflictError("Failed to approve forgot badge request.") from exc

        self.db.refresh(request)
        self.db.refresh(temporary_assignment)

        return ForgotBadgeRequestWithAssignmentResponse(
            request=self._build_request_response(request),
            temporary_assignment=self._build_temporary_assignment_response(temporary_assignment),
        )

    def reject_request(
        self,
        request_id: int,
        payload: ForgotBadgeRequestRejectRequest,
        current_user: User,
    ) -> ForgotBadgeRequest:
        """Reject a forgot badge request."""

        request = self.get_request(request_id)
        if request.status != ForgotBadgeRequestStatusEnum.PENDING.value:
            raise ForgotBadgeValidationError(
                f"Cannot reject request with status '{request.status}'. Only PENDING requests can be rejected."
            )

        request.status = ForgotBadgeRequestStatusEnum.REJECTED.value
        request.handled_by_user_id = current_user.id
        request.handled_at = datetime.now(timezone.utc)
        if payload.notes:
            request.notes = payload.notes

        self.db.add(request)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ForgotBadgeConflictError("Failed to reject forgot badge request.") from exc

        self.db.refresh(request)
        return request

    def cancel_request(
        self,
        request_id: int,
        payload: ForgotBadgeRequestCancelRequest,
        current_user: User,
    ) -> ForgotBadgeRequest:
        """Cancel a forgot badge request (by the requester)."""

        request = self.get_request(request_id)
        if request.user_id != current_user.id:
            raise ForgotBadgeValidationError("You can only cancel your own requests.")

        if request.status not in [
            ForgotBadgeRequestStatusEnum.PENDING.value,
            ForgotBadgeRequestStatusEnum.APPROVED.value,
        ]:
            raise ForgotBadgeValidationError(
                f"Cannot cancel request with status '{request.status}'."
            )

        if request.status == ForgotBadgeRequestStatusEnum.APPROVED.value:
            self._release_temporary_assignment_if_exists(request.id)

        request.status = ForgotBadgeRequestStatusEnum.CANCELLED.value
        if payload.reason:
            request.notes = payload.reason

        self.db.add(request)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ForgotBadgeConflictError("Failed to cancel forgot badge request.") from exc

        self.db.refresh(request)
        return request

    def complete_request(
        self,
        request_id: int,
        payload: ForgotBadgeRequestCompleteRequest,
        current_user: User,
    ) -> ForgotBadgeRequest:
        """Mark a forgot badge request as completed after attendance is done."""

        request = self.get_request(request_id)
        if request.status != ForgotBadgeRequestStatusEnum.APPROVED.value:
            raise ForgotBadgeValidationError(
                f"Cannot complete request with status '{request.status}'. Only APPROVED requests can be completed."
            )

        self._release_temporary_assignment_if_exists(request.id)

        request.status = ForgotBadgeRequestStatusEnum.COMPLETED.value
        request.handled_by_user_id = current_user.id
        request.handled_at = datetime.now(timezone.utc)
        if payload.notes:
            request.notes = payload.notes

        self.db.add(request)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ForgotBadgeConflictError("Failed to complete forgot badge request.") from exc

        self.db.refresh(request)
        return request

    def release_temporary_card(
        self,
        employee_id: int,
        valid_for_date: date,
        current_user: User,
    ) -> TemporaryNfcAssignment | None:
        """Manually release an active temporary NFC assignment."""

        assignment = self._get_active_temporary_assignment(employee_id, valid_for_date)
        if assignment is None:
            return None

        self._release_temporary_assignment(assignment, current_user.id)
        return assignment

    def on_check_out(
        self,
        employee_id: int,
        nfc_card_id: int,
        valid_for_date: date,
    ) -> None:
        """Called after CHECK_OUT to release the temporary assignment."""

        assignment = self._get_active_temporary_assignment(employee_id, valid_for_date)
        if assignment is None:
            return

        if assignment.nfc_card_id != nfc_card_id:
            return

        assignment.status = TemporaryNfcAssignmentStatusEnum.USED.value
        assignment.released_at = datetime.now(timezone.utc)
        nfc_card = self.db.get(NfcCard, nfc_card_id)
        if nfc_card is not None and nfc_card.card_type == NfcCardTypeEnum.TEMPORARY.value:
            nfc_card.status = NfcCardStatusEnum.AVAILABLE.value
            self.db.add(nfc_card)
        self.db.add(assignment)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

    def on_check_out_with_assignment_id(
        self,
        assignment_id: int,
        check_out_attendance_id: int,
    ) -> None:
        """Called after CHECK_OUT to finalize the temporary assignment."""

        assignment = self.db.get(TemporaryNfcAssignment, assignment_id)
        if assignment is None:
            return

        if assignment.status != TemporaryNfcAssignmentStatusEnum.ACTIVE.value:
            return

        assignment.status = TemporaryNfcAssignmentStatusEnum.USED.value
        assignment.check_out_attendance_id = check_out_attendance_id
        assignment.released_at = datetime.now(timezone.utc)
        nfc_card = self.db.get(NfcCard, assignment.nfc_card_id)
        if nfc_card is not None and nfc_card.card_type == NfcCardTypeEnum.TEMPORARY.value:
            nfc_card.status = NfcCardStatusEnum.AVAILABLE.value
            self.db.add(nfc_card)
        self.db.add(assignment)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

    def on_check_in_with_assignment_id(
        self,
        assignment_id: int,
        check_in_attendance_id: int,
    ) -> None:
        """Called after CHECK_IN to record the attendance ID."""

        assignment = self.db.get(TemporaryNfcAssignment, assignment_id)
        if assignment is None:
            return

        if assignment.status != TemporaryNfcAssignmentStatusEnum.ACTIVE.value:
            return

        assignment.check_in_attendance_id = check_in_attendance_id
        self.db.add(assignment)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

    def resolve_employee_by_temporary_card(
        self,
        nfc_card_id: int,
        valid_for_date: date,
    ) -> Employee | None:
        """Resolve employee for an active temporary NFC assignment."""

        assignment = self._get_temporary_assignment_by_card(nfc_card_id, valid_for_date)
        if assignment is None:
            return None

        if assignment.status != TemporaryNfcAssignmentStatusEnum.ACTIVE.value:
            return None

        employee = self.db.get(Employee, assignment.employee_id)
        return employee

    def get_active_temporary_assignment(
        self,
        employee_id: int,
        valid_for_date: date,
    ) -> TemporaryNfcAssignment | None:
        """Get active temporary assignment for employee and date."""

        return self._get_active_temporary_assignment(employee_id, valid_for_date)

    def build_request_response(
        self,
        request: ForgotBadgeRequest,
    ) -> ForgotBadgeRequestResponse:
        """Build a request response with employee details."""

        employee = self.db.get(Employee, request.employee_id)
        card_metadata = self._get_request_card_metadata(request)
        return ForgotBadgeRequestResponse(
            id=request.id,
            employee_id=request.employee_id,
            user_id=request.user_id,
            status=request.status,
            reason=request.reason,
            requested_at=request.requested_at,
            handled_by_user_id=request.handled_by_user_id,
            handled_at=request.handled_at,
            nfc_card_id=request.nfc_card_id,
            temporary_card_id=card_metadata["temporary_card_id"],
            temporary_card_label=card_metadata["temporary_card_label"],
            temporary_card_nfc_uid=card_metadata["temporary_card_nfc_uid"],
            valid_for_date=request.valid_for_date,
            assignment_status=card_metadata["assignment_status"],
            notes=request.notes,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )

    def _build_request_response(
        self,
        request: ForgotBadgeRequest,
    ) -> ForgotBadgeRequestResponse:
        """Build a request response."""

        card_metadata = self._get_request_card_metadata(request)
        return ForgotBadgeRequestResponse(
            id=request.id,
            employee_id=request.employee_id,
            user_id=request.user_id,
            status=request.status,
            reason=request.reason,
            requested_at=request.requested_at,
            handled_by_user_id=request.handled_by_user_id,
            handled_at=request.handled_at,
            nfc_card_id=request.nfc_card_id,
            temporary_card_id=card_metadata["temporary_card_id"],
            temporary_card_label=card_metadata["temporary_card_label"],
            temporary_card_nfc_uid=card_metadata["temporary_card_nfc_uid"],
            valid_for_date=request.valid_for_date,
            assignment_status=card_metadata["assignment_status"],
            notes=request.notes,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )

    def _build_temporary_assignment_response(
        self,
        assignment: TemporaryNfcAssignment,
    ) -> TemporaryNfcAssignmentResponse:
        """Build a temporary assignment response."""

        return TemporaryNfcAssignmentResponse(
            id=assignment.id,
            employee_id=assignment.employee_id,
            nfc_card_id=assignment.nfc_card_id,
            forgot_badge_request_id=assignment.forgot_badge_request_id,
            assigned_by_user_id=assignment.assigned_by_user_id,
            assigned_at=assignment.assigned_at,
            valid_for_date=assignment.valid_for_date,
            status=assignment.status,
            check_in_attendance_id=assignment.check_in_attendance_id,
            check_out_attendance_id=assignment.check_out_attendance_id,
            released_at=assignment.released_at,
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
        )

    def _get_employee_for_user(self, user_id: int) -> Employee:
        """Return the active employee linked to a user."""

        employee = self.db.execute(
            select(Employee)
            .where(Employee.user_id == user_id, Employee.is_active.is_(True))
            .limit(1)
        ).scalar_one_or_none()
        if employee is None:
            raise ForgotBadgeValidationError("No active employee profile found for the current user.")

        return employee

    def _ensure_no_pending_request_for_today(self, employee_id: int) -> None:
        """Reject if a PENDING or APPROVED request already exists for today."""

        today = datetime.now(timezone.utc).date()
        statement = (
            select(ForgotBadgeRequest)
            .where(
                ForgotBadgeRequest.employee_id == employee_id,
                ForgotBadgeRequest.status.in_([
                    ForgotBadgeRequestStatusEnum.PENDING.value,
                    ForgotBadgeRequestStatusEnum.APPROVED.value,
                ]),
            )
        )
        requests = list(self.db.execute(statement).scalars().all())
        for req in requests:
            if req.valid_for_date == today or req.requested_at.date() == today:
                raise ForgotBadgeValidationError(
                    "A pending or approved forgot badge request already exists for today."
                )

    def _get_nfc_card(self, card_id: int) -> NfcCard:
        """Return an NFC card by id."""

        card = self.db.get(NfcCard, card_id)
        if card is None:
            raise ForgotBadgeNotFoundError("NFC card not found.")

        return card

    def _resolve_temporary_nfc_card(
        self,
        payload: ForgotBadgeRequestApproveRequest,
    ) -> NfcCard:
        """Resolve the selected temporary NFC card from id or UID."""

        if payload.nfc_card_id is not None:
            return self._get_nfc_card(payload.nfc_card_id)

        return self._get_nfc_card_by_uid(payload.nfc_uid or "")

    def _get_nfc_card_by_uid(self, nfc_uid: str) -> NfcCard:
        """Return an NFC card by normalized UID."""

        normalized_nfc_uid = nfc_uid.strip().upper()
        card = self.db.execute(
            select(NfcCard)
            .where(NfcCard.nfc_uid == normalized_nfc_uid)
            .limit(1)
        ).scalar_one_or_none()
        if card is None:
            raise ForgotBadgeNotFoundError("NFC card not found.")

        return card

    def _validate_temporary_card_available(
        self,
        nfc_card: NfcCard,
        employee_id: int,
        valid_for_date: date,
    ) -> None:
        """Validate that the NFC card is available for temporary assignment."""

        if nfc_card.card_type != NfcCardTypeEnum.TEMPORARY.value:
            raise ForgotBadgeValidationError(
                "Only TEMPORARY NFC cards can be used for forgot badge assignments."
            )

        if not nfc_card.is_active or nfc_card.status == NfcCardStatusEnum.DISABLED.value:
            raise ForgotBadgeConflictError("This NFC card is disabled or inactive.")

        if nfc_card.employee_id is not None:
            raise ForgotBadgeConflictError(
                "Temporary NFC cards must not be permanently assigned to an employee."
            )

        if nfc_card.status != NfcCardStatusEnum.AVAILABLE.value:
            raise ForgotBadgeConflictError("This NFC card is not currently available.")

        existing = self._get_temporary_assignment_by_card(nfc_card.id, valid_for_date)
        if existing is not None and existing.status == TemporaryNfcAssignmentStatusEnum.ACTIVE.value:
            if existing.employee_id != employee_id:
                raise ForgotBadgeConflictError(
                    "This NFC card is already assigned to another employee for today."
                )
            if existing.employee_id == employee_id:
                raise ForgotBadgeConflictError(
                    "This employee already has an active temporary NFC card for today."
                )

        if existing is not None and existing.status == TemporaryNfcAssignmentStatusEnum.USED.value:
            raise ForgotBadgeConflictError(
                "This NFC card was already used for a forgot badge session today."
            )

    def _close_active_temporary_assignments(
        self,
        nfc_card_id: int,
        valid_for_date: date,
    ) -> None:
        """Close any ACTIVE assignments for the card and date."""

        statement = (
            select(TemporaryNfcAssignment)
            .where(
                TemporaryNfcAssignment.nfc_card_id == nfc_card_id,
                TemporaryNfcAssignment.valid_for_date == valid_for_date,
                TemporaryNfcAssignment.status == TemporaryNfcAssignmentStatusEnum.ACTIVE.value,
            )
        )
        assignments = list(self.db.execute(statement).scalars().all())
        for assignment in assignments:
            assignment.status = TemporaryNfcAssignmentStatusEnum.EXPIRED.value
            assignment.released_at = datetime.now(timezone.utc)
            self.db.add(assignment)

        nfc_card = self.db.get(NfcCard, nfc_card_id)
        if nfc_card is not None and nfc_card.card_type == NfcCardTypeEnum.TEMPORARY.value:
            nfc_card.status = NfcCardStatusEnum.AVAILABLE.value
            self.db.add(nfc_card)

    def _get_temporary_assignment_by_card(
        self,
        nfc_card_id: int,
        valid_for_date: date,
    ) -> TemporaryNfcAssignment | None:
        """Return temporary assignment by card and date."""

        return self.db.execute(
            select(TemporaryNfcAssignment)
            .where(
                TemporaryNfcAssignment.nfc_card_id == nfc_card_id,
                TemporaryNfcAssignment.valid_for_date == valid_for_date,
            )
            .order_by(TemporaryNfcAssignment.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _get_active_temporary_assignment(
        self,
        employee_id: int,
        valid_for_date: date,
    ) -> TemporaryNfcAssignment | None:
        """Return active temporary assignment for employee and date."""

        return self.db.execute(
            select(TemporaryNfcAssignment)
            .where(
                TemporaryNfcAssignment.employee_id == employee_id,
                TemporaryNfcAssignment.valid_for_date == valid_for_date,
                TemporaryNfcAssignment.status == TemporaryNfcAssignmentStatusEnum.ACTIVE.value,
            )
            .limit(1)
        ).scalar_one_or_none()

    def _release_temporary_assignment(
        self,
        assignment: TemporaryNfcAssignment,
        released_by_user_id: int,
    ) -> None:
        """Release a temporary NFC assignment."""

        assignment.status = TemporaryNfcAssignmentStatusEnum.RELEASED.value
        assignment.released_at = datetime.now(timezone.utc)
        nfc_card = self.db.get(NfcCard, assignment.nfc_card_id)
        if nfc_card is not None and nfc_card.card_type == NfcCardTypeEnum.TEMPORARY.value:
            nfc_card.status = NfcCardStatusEnum.AVAILABLE.value
            self.db.add(nfc_card)
        self.db.add(assignment)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ForgotBadgeConflictError("Failed to release temporary NFC assignment.")

    def _release_temporary_assignment_if_exists(
        self,
        forgot_badge_request_id: int,
    ) -> None:
        """Release temporary assignment linked to a forgot badge request."""

        assignment = self.db.execute(
            select(TemporaryNfcAssignment)
            .where(
                TemporaryNfcAssignment.forgot_badge_request_id == forgot_badge_request_id,
                TemporaryNfcAssignment.status == TemporaryNfcAssignmentStatusEnum.ACTIVE.value,
            )
            .limit(1)
        ).scalar_one_or_none()

        if assignment is not None:
            assignment.status = TemporaryNfcAssignmentStatusEnum.RELEASED.value
            assignment.released_at = datetime.now(timezone.utc)
            nfc_card = self.db.get(NfcCard, assignment.nfc_card_id)
            if nfc_card is not None and nfc_card.card_type == NfcCardTypeEnum.TEMPORARY.value:
                nfc_card.status = NfcCardStatusEnum.AVAILABLE.value
                self.db.add(nfc_card)
            self.db.add(assignment)

    def _get_request_card_metadata(self, request: ForgotBadgeRequest) -> dict[str, str | int | None]:
        """Return display metadata for the temporary card linked to a request."""

        card = self.db.get(NfcCard, request.nfc_card_id) if request.nfc_card_id is not None else None
        assignment = self.db.execute(
            select(TemporaryNfcAssignment)
            .where(TemporaryNfcAssignment.forgot_badge_request_id == request.id)
            .order_by(TemporaryNfcAssignment.id.desc())
            .limit(1)
        ).scalar_one_or_none()

        return {
            "temporary_card_id": card.id if card is not None else None,
            "temporary_card_label": card.label if card is not None else None,
            "temporary_card_nfc_uid": card.nfc_uid if card is not None else None,
            "assignment_status": assignment.status if assignment is not None else None,
        }
