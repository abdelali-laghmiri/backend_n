from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.apps.auth.dependencies import get_current_active_user
from app.apps.permissions.dependencies import require_permission
from app.apps.requests.dependencies import get_requests_service
from app.apps.requests.schemas import (
    RequestCreateRequest,
    RequestDetailResponse,
    RequestStepActionRequest,
    RequestSummaryResponse,
    RequestTypeCreateRequest,
    RequestTypeFieldCreateRequest,
    RequestTypeFieldResponse,
    RequestTypeFieldUpdateRequest,
    RequestTypeResponse,
    RequestTypeUpdateRequest,
    RequestWorkflowStepCreateRequest,
    RequestWorkflowStepResponse,
    RequestWorkflowStepUpdateRequest,
)
from app.apps.requests.service import (
    RequestsAuthorizationError,
    RequestsConflictError,
    RequestsNotFoundError,
    RequestsService,
    RequestsValidationError,
)
from app.apps.users.models import User

router = APIRouter(prefix="/requests", tags=["Requests"])


def raise_requests_http_error(exc: Exception) -> None:
    """Map request-engine service errors to HTTP exceptions."""

    if isinstance(exc, RequestsNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if isinstance(exc, RequestsValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if isinstance(exc, RequestsConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if isinstance(exc, RequestsAuthorizationError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    raise exc


@router.post(
    "/types",
    response_model=RequestTypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a request type",
)
def create_request_type(
    payload: RequestTypeCreateRequest,
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> RequestTypeResponse:
    try:
        request_type = service.create_request_type(payload)
    except RequestsConflictError as exc:
        raise_requests_http_error(exc)

    return RequestTypeResponse.model_validate(request_type)


@router.get(
    "/types",
    response_model=list[RequestTypeResponse],
    status_code=status.HTTP_200_OK,
    summary="List request types",
)
def list_request_types(
    include_inactive: bool = Query(default=False),
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> list[RequestTypeResponse]:
    request_types = service.list_request_types(include_inactive=include_inactive)
    return [RequestTypeResponse.model_validate(item) for item in request_types]


@router.get(
    "/types/{request_type_id}",
    response_model=RequestTypeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a request type by id",
)
def get_request_type(
    request_type_id: int,
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> RequestTypeResponse:
    try:
        request_type = service.get_request_type(request_type_id)
    except RequestsNotFoundError as exc:
        raise_requests_http_error(exc)

    return RequestTypeResponse.model_validate(request_type)


@router.patch(
    "/types/{request_type_id}",
    response_model=RequestTypeResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a request type",
)
def update_request_type(
    request_type_id: int,
    payload: RequestTypeUpdateRequest,
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> RequestTypeResponse:
    try:
        request_type = service.update_request_type(request_type_id, payload)
    except (RequestsConflictError, RequestsNotFoundError) as exc:
        raise_requests_http_error(exc)

    return RequestTypeResponse.model_validate(request_type)


@router.post(
    "/types/{request_type_id}/fields",
    response_model=RequestTypeFieldResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a field definition for a request type",
)
def create_request_field(
    request_type_id: int,
    payload: RequestTypeFieldCreateRequest,
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> RequestTypeFieldResponse:
    try:
        request_field = service.create_request_field(request_type_id, payload)
    except (RequestsConflictError, RequestsNotFoundError, RequestsValidationError) as exc:
        raise_requests_http_error(exc)

    return RequestTypeFieldResponse.model_validate(request_field)


@router.get(
    "/types/{request_type_id}/fields",
    response_model=list[RequestTypeFieldResponse],
    status_code=status.HTTP_200_OK,
    summary="List field definitions for a request type",
)
def list_request_fields(
    request_type_id: int,
    include_inactive: bool = Query(default=False),
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> list[RequestTypeFieldResponse]:
    try:
        request_fields = service.list_request_fields(
            request_type_id,
            include_inactive=include_inactive,
        )
    except RequestsNotFoundError as exc:
        raise_requests_http_error(exc)

    return [RequestTypeFieldResponse.model_validate(item) for item in request_fields]


@router.get(
    "/fields/{request_field_id}",
    response_model=RequestTypeFieldResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a request field by id",
)
def get_request_field(
    request_field_id: int,
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> RequestTypeFieldResponse:
    try:
        request_field = service.get_request_field(request_field_id)
    except RequestsNotFoundError as exc:
        raise_requests_http_error(exc)

    return RequestTypeFieldResponse.model_validate(request_field)


@router.patch(
    "/fields/{request_field_id}",
    response_model=RequestTypeFieldResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a request field definition",
)
def update_request_field(
    request_field_id: int,
    payload: RequestTypeFieldUpdateRequest,
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> RequestTypeFieldResponse:
    try:
        request_field = service.update_request_field(request_field_id, payload)
    except (RequestsConflictError, RequestsNotFoundError, RequestsValidationError) as exc:
        raise_requests_http_error(exc)

    return RequestTypeFieldResponse.model_validate(request_field)


@router.post(
    "/types/{request_type_id}/workflow-steps",
    response_model=RequestWorkflowStepResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workflow step for a request type",
)
def create_workflow_step(
    request_type_id: int,
    payload: RequestWorkflowStepCreateRequest,
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> RequestWorkflowStepResponse:
    try:
        step = service.create_workflow_step(request_type_id, payload)
    except (RequestsConflictError, RequestsNotFoundError, RequestsValidationError) as exc:
        raise_requests_http_error(exc)

    return RequestWorkflowStepResponse.model_validate(step)


@router.get(
    "/types/{request_type_id}/workflow-steps",
    response_model=list[RequestWorkflowStepResponse],
    status_code=status.HTTP_200_OK,
    summary="List workflow steps for a request type",
)
def list_workflow_steps(
    request_type_id: int,
    include_inactive: bool = Query(default=False),
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> list[RequestWorkflowStepResponse]:
    try:
        workflow_steps = service.list_workflow_steps(
            request_type_id,
            include_inactive=include_inactive,
        )
    except RequestsNotFoundError as exc:
        raise_requests_http_error(exc)

    return [RequestWorkflowStepResponse.model_validate(item) for item in workflow_steps]


@router.get(
    "/workflow-steps/{step_id}",
    response_model=RequestWorkflowStepResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a workflow step by id",
)
def get_workflow_step(
    step_id: int,
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> RequestWorkflowStepResponse:
    try:
        workflow_step = service.get_workflow_step(step_id)
    except RequestsNotFoundError as exc:
        raise_requests_http_error(exc)

    return RequestWorkflowStepResponse.model_validate(workflow_step)


@router.patch(
    "/workflow-steps/{step_id}",
    response_model=RequestWorkflowStepResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a workflow step",
)
def update_workflow_step(
    step_id: int,
    payload: RequestWorkflowStepUpdateRequest,
    service: RequestsService = Depends(get_requests_service),
    _current_user: User = Depends(require_permission("requests.manage")),
) -> RequestWorkflowStepResponse:
    try:
        workflow_step = service.update_workflow_step(step_id, payload)
    except (RequestsConflictError, RequestsNotFoundError, RequestsValidationError) as exc:
        raise_requests_http_error(exc)

    return RequestWorkflowStepResponse.model_validate(workflow_step)


@router.post(
    "",
    response_model=RequestDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a dynamic request instance",
)
def create_request(
    payload: RequestCreateRequest,
    service: RequestsService = Depends(get_requests_service),
    current_user: User = Depends(get_current_active_user),
) -> RequestDetailResponse:
    try:
        workflow_request = service.create_request(current_user, payload)
    except (RequestsConflictError, RequestsNotFoundError, RequestsValidationError) as exc:
        raise_requests_http_error(exc)

    return service.build_request_detail(workflow_request)


@router.get(
    "",
    response_model=list[RequestSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List the current authenticated user's requests",
)
def list_my_requests(
    service: RequestsService = Depends(get_requests_service),
    current_user: User = Depends(get_current_active_user),
) -> list[RequestSummaryResponse]:
    workflow_requests = service.list_requests_for_user(current_user)
    return service.build_request_summaries(workflow_requests)


@router.get(
    "/{request_id}",
    response_model=RequestDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get request details",
)
def get_request(
    request_id: int,
    service: RequestsService = Depends(get_requests_service),
    current_user: User = Depends(get_current_active_user),
) -> RequestDetailResponse:
    try:
        workflow_request = service.get_request_for_user(request_id, current_user)
    except (RequestsAuthorizationError, RequestsNotFoundError) as exc:
        raise_requests_http_error(exc)

    return service.build_request_detail(workflow_request)


@router.post(
    "/{request_id}/approve",
    response_model=RequestDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve the current request step",
)
def approve_request_step(
    request_id: int,
    payload: RequestStepActionRequest,
    service: RequestsService = Depends(get_requests_service),
    current_user: User = Depends(get_current_active_user),
) -> RequestDetailResponse:
    try:
        workflow_request = service.approve_current_step(
            request_id,
            current_user,
            comment=payload.comment,
        )
    except (
        RequestsAuthorizationError,
        RequestsConflictError,
        RequestsNotFoundError,
        RequestsValidationError,
    ) as exc:
        raise_requests_http_error(exc)

    return service.build_request_detail(workflow_request)


@router.post(
    "/{request_id}/reject",
    response_model=RequestDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject the current request step",
)
def reject_request_step(
    request_id: int,
    payload: RequestStepActionRequest,
    service: RequestsService = Depends(get_requests_service),
    current_user: User = Depends(get_current_active_user),
) -> RequestDetailResponse:
    try:
        workflow_request = service.reject_current_step(
            request_id,
            current_user,
            comment=payload.comment,
        )
    except (
        RequestsAuthorizationError,
        RequestsConflictError,
        RequestsNotFoundError,
        RequestsValidationError,
    ) as exc:
        raise_requests_http_error(exc)

    return service.build_request_detail(workflow_request)
