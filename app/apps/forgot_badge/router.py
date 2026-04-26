from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.apps.attendance.dependencies import get_attendance_service
from app.apps.attendance.service import AttendanceService
from app.apps.forgot_badge.dependencies import get_forgot_badge_service
from app.apps.forgot_badge.models import ForgotBadgeRequestStatusEnum
from app.apps.forgot_badge.schemas import (
    ForgotBadgeRequestApproveRequest,
    ForgotBadgeRequestCancelRequest,
    ForgotBadgeRequestCompleteRequest,
    ForgotBadgeRequestCreateRequest,
    ForgotBadgeRequestRejectRequest,
    ForgotBadgeRequestResponse,
    ForgotBadgeRequestWithAssignmentResponse,
    ForgotBadgeRequestWithEmployeeResponse,
    TemporaryNfcAssignmentResponse,
)
from app.apps.forgot_badge.service import (
    ForgotBadgeConflictError,
    ForgotBadgeNotFoundError,
    ForgotBadgeService,
    ForgotBadgeValidationError,
)
from app.apps.permissions.dependencies import require_any_permission, require_permission
from app.apps.users.models import User

router = APIRouter(prefix="/forgot-badge", tags=["Forgot Badge"])


def raise_forgot_badge_http_error(exc: Exception) -> None:
    """Map forgot badge service errors to HTTP exceptions."""

    if isinstance(exc, ForgotBadgeNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, ForgotBadgeValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if isinstance(exc, ForgotBadgeConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise exc


@router.post(
    "/requests",
    response_model=ForgotBadgeRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a forgot badge request",
)
def create_forgot_badge_request(
    payload: ForgotBadgeRequestCreateRequest,
    service: ForgotBadgeService = Depends(get_forgot_badge_service),
    current_user: User = Depends(require_permission("forgot_badge.create")),
) -> ForgotBadgeRequestResponse:
    try:
        request = service.create_request(payload=payload, current_user=current_user)
    except (ForgotBadgeConflictError, ForgotBadgeValidationError) as exc:
        raise_forgot_badge_http_error(exc)

    return service.build_request_response(request)


@router.get(
    "/requests/me",
    response_model=list[ForgotBadgeRequestResponse],
    status_code=status.HTTP_200_OK,
    summary="List my forgot badge requests",
)
def list_my_forgot_badge_requests(
    service: ForgotBadgeService = Depends(get_forgot_badge_service),
    current_user: User = Depends(require_permission("forgot_badge.view_own")),
) -> list[ForgotBadgeRequestResponse]:
    requests = service.list_own_requests(current_user=current_user)
    return [service.build_request_response(r) for r in requests]


@router.get(
    "/requests",
    response_model=list[ForgotBadgeRequestWithEmployeeResponse],
    status_code=status.HTTP_200_OK,
    summary="List all forgot badge requests",
)
def list_forgot_badge_requests(
    employee_id: int | None = Query(default=None, ge=1),
    status_filter: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    service: ForgotBadgeService = Depends(get_forgot_badge_service),
    current_user: User = Depends(require_permission("forgot_badge.view_all")),
) -> list[ForgotBadgeRequestWithEmployeeResponse]:
    try:
        requests = service.list_all_requests(
            employee_id=employee_id,
            status=status_filter,
            date_from=date_from,
            date_to=date_to,
        )
    except ForgotBadgeValidationError as exc:
        raise_forgot_badge_http_error(exc)

    return [_build_request_with_employee_response(r, service) for r in requests]


@router.get(
    "/requests/{request_id}",
    response_model=ForgotBadgeRequestWithEmployeeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get one forgot badge request",
)
def get_forgot_badge_request(
    request_id: int = Path(ge=1),
    service: ForgotBadgeService = Depends(get_forgot_badge_service),
    current_user: User = Depends(require_permission("forgot_badge.view_all")),
) -> ForgotBadgeRequestWithEmployeeResponse:
    try:
        request = service.get_request(request_id)
    except ForgotBadgeNotFoundError as exc:
        raise_forgot_badge_http_error(exc)

    return _build_request_with_employee_response(request, service)


@router.post(
    "/requests/{request_id}/approve",
    response_model=ForgotBadgeRequestWithAssignmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve a forgot badge request and attach temporary NFC card",
)
def approve_forgot_badge_request(
    request_id: int = Path(ge=1),
    payload: ForgotBadgeRequestApproveRequest = None,
    service: ForgotBadgeService = Depends(get_forgot_badge_service),
    current_user: User = Depends(require_permission("forgot_badge.manage")),
    attendance_service: AttendanceService = Depends(get_attendance_service),
) -> ForgotBadgeRequestWithAssignmentResponse:
    if payload is None:
        payload = ForgotBadgeRequestApproveRequest(
            nfc_card_id=1,
            valid_for_date=date.today(),
        )

    try:
        result = service.approve_request(
            request_id=request_id,
            payload=payload,
            current_user=current_user,
        )
    except (
        ForgotBadgeConflictError,
        ForgotBadgeNotFoundError,
        ForgotBadgeValidationError,
    ) as exc:
        raise_forgot_badge_http_error(exc)

    return result


@router.post(
    "/requests/{request_id}/reject",
    response_model=ForgotBadgeRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject a forgot badge request",
)
def reject_forgot_badge_request(
    request_id: int = Path(ge=1),
    payload: ForgotBadgeRequestRejectRequest = None,
    service: ForgotBadgeService = Depends(get_forgot_badge_service),
    current_user: User = Depends(require_permission("forgot_badge.manage")),
) -> ForgotBadgeRequestResponse:
    if payload is None:
        payload = ForgotBadgeRequestRejectRequest()

    try:
        request = service.reject_request(
            request_id=request_id,
            payload=payload,
            current_user=current_user,
        )
    except (
        ForgotBadgeConflictError,
        ForgotBadgeNotFoundError,
        ForgotBadgeValidationError,
    ) as exc:
        raise_forgot_badge_http_error(exc)

    return service.build_request_response(request)


@router.post(
    "/requests/{request_id}/cancel",
    response_model=ForgotBadgeRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel my forgot badge request",
)
def cancel_forgot_badge_request(
    request_id: int = Path(ge=1),
    payload: ForgotBadgeRequestCancelRequest = None,
    service: ForgotBadgeService = Depends(get_forgot_badge_service),
    current_user: User = Depends(require_permission("forgot_badge.create")),
) -> ForgotBadgeRequestResponse:
    if payload is None:
        payload = ForgotBadgeRequestCancelRequest()

    try:
        request = service.cancel_request(
            request_id=request_id,
            payload=payload,
            current_user=current_user,
        )
    except (
        ForgotBadgeConflictError,
        ForgotBadgeNotFoundError,
        ForgotBadgeValidationError,
    ) as exc:
        raise_forgot_badge_http_error(exc)

    return service.build_request_response(request)


@router.post(
    "/requests/{request_id}/complete",
    response_model=ForgotBadgeRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark forgot badge request as completed",
)
def complete_forgot_badge_request(
    request_id: int = Path(ge=1),
    payload: ForgotBadgeRequestCompleteRequest = None,
    service: ForgotBadgeService = Depends(get_forgot_badge_service),
    current_user: User = Depends(require_permission("forgot_badge.manage")),
) -> ForgotBadgeRequestResponse:
    if payload is None:
        payload = ForgotBadgeRequestCompleteRequest()

    try:
        request = service.complete_request(
            request_id=request_id,
            payload=payload,
            current_user=current_user,
        )
    except (
        ForgotBadgeConflictError,
        ForgotBadgeNotFoundError,
        ForgotBadgeValidationError,
    ) as exc:
        raise_forgot_badge_http_error(exc)

    return service.build_request_response(request)


@router.post(
    "/temporary-cards/release",
    response_model=TemporaryNfcAssignmentResponse | None,
    status_code=status.HTTP_200_OK,
    summary="Manually release a temporary NFC card",
)
def release_temporary_nfc_card(
    employee_id: int = Query(ge=1),
    valid_for_date: date = Query(),
    service: ForgotBadgeService = Depends(get_forgot_badge_service),
    current_user: User = Depends(require_permission("attendance.nfc.release_temporary_card")),
) -> TemporaryNfcAssignmentResponse | None:
    try:
        assignment = service.release_temporary_card(
            employee_id=employee_id,
            valid_for_date=valid_for_date,
            current_user=current_user,
        )
    except (ForgotBadgeConflictError, ForgotBadgeValidationError) as exc:
        raise_forgot_badge_http_error(exc)

    if assignment is None:
        return None

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


def _build_request_with_employee_response(
    request: ForgotBadgeRequest,
    service: ForgotBadgeService,
) -> ForgotBadgeRequestWithEmployeeResponse:
    """Build a request response with employee details embedded."""

    from app.apps.employees.models import Employee

    employee = service.db.get(Employee, request.employee_id)
    employee_name = (
        f"{employee.first_name} {employee.last_name}" if employee else "Unknown"
    )
    employee_matricule = employee.matricule if employee else "Unknown"

    return ForgotBadgeRequestWithEmployeeResponse(
        id=request.id,
        employee_id=request.employee_id,
        employee_matricule=employee_matricule,
        employee_name=employee_name,
        user_id=request.user_id,
        status=request.status,
        reason=request.reason,
        requested_at=request.requested_at,
        handled_by_user_id=request.handled_by_user_id,
        handled_at=request.handled_at,
        nfc_card_id=request.nfc_card_id,
        valid_for_date=request.valid_for_date,
        notes=request.notes,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )