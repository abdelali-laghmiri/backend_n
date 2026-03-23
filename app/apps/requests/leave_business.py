from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Sequence

from app.apps.requests.models import RequestFieldTypeEnum, RequestTypeField

LEAVE_REQUEST_TYPE_CODE = "leave"
LEAVE_DATE_START_FIELD_CODE = "date_start"
LEAVE_DATE_END_FIELD_CODE = "date_end"
LEAVE_OPTION_FIELD_CODE = "leave_option"
LEAVE_REQUIRED_FIELD_CODES = (
    LEAVE_DATE_START_FIELD_CODE,
    LEAVE_DATE_END_FIELD_CODE,
    LEAVE_OPTION_FIELD_CODE,
)


class LeaveBusinessRuleError(ValueError):
    """Raised when leave-specific configuration or business validation fails."""


class LeaveOptionEnum(str, Enum):
    """Canonical leave-option codes supported by the backend."""

    PAID_LEAVE = "paid_leave"
    UNPAID_LEAVE = "unpaid_leave"
    CTT = "ctt"


@dataclass(frozen=True)
class LeaveOptionRule:
    """Static behavior attached to a supported leave option."""

    option: LeaveOptionEnum
    label: str
    requires_balance_check: bool


@dataclass(frozen=True)
class LeaveRequestEvaluation:
    """Computed leave request data used by validations and responses."""

    date_start: date
    date_end: date
    leave_option: LeaveOptionEnum
    leave_option_label: str
    requested_duration_days: int
    balance_validation_applied: bool
    available_balance_days: int


LEAVE_OPTION_RULES: dict[LeaveOptionEnum, LeaveOptionRule] = {
    LeaveOptionEnum.PAID_LEAVE: LeaveOptionRule(
        option=LeaveOptionEnum.PAID_LEAVE,
        label="Paid Leave",
        requires_balance_check=True,
    ),
    LeaveOptionEnum.UNPAID_LEAVE: LeaveOptionRule(
        option=LeaveOptionEnum.UNPAID_LEAVE,
        label="Unpaid Leave",
        requires_balance_check=False,
    ),
    LeaveOptionEnum.CTT: LeaveOptionRule(
        option=LeaveOptionEnum.CTT,
        label="CTT",
        requires_balance_check=False,
    ),
}

LEAVE_OPTION_ALIASES: dict[str, LeaveOptionEnum] = {
    "paid": LeaveOptionEnum.PAID_LEAVE,
    "paid leave": LeaveOptionEnum.PAID_LEAVE,
    "paid_leave": LeaveOptionEnum.PAID_LEAVE,
    "paid-leave": LeaveOptionEnum.PAID_LEAVE,
    "unpaid": LeaveOptionEnum.UNPAID_LEAVE,
    "unpaid leave": LeaveOptionEnum.UNPAID_LEAVE,
    "unpaid_leave": LeaveOptionEnum.UNPAID_LEAVE,
    "unpaid-leave": LeaveOptionEnum.UNPAID_LEAVE,
    "ctt": LeaveOptionEnum.CTT,
}

LEAVE_FIELD_ALLOWED_TYPES: dict[str, set[RequestFieldTypeEnum]] = {
    LEAVE_DATE_START_FIELD_CODE: {RequestFieldTypeEnum.DATE},
    LEAVE_DATE_END_FIELD_CODE: {RequestFieldTypeEnum.DATE},
    LEAVE_OPTION_FIELD_CODE: {
        RequestFieldTypeEnum.SELECT,
        RequestFieldTypeEnum.TEXT,
    },
}


def is_leave_request_type_code(request_type_code: str) -> bool:
    """Return whether a request type code uses leave business rules."""

    return request_type_code.strip().lower() == LEAVE_REQUEST_TYPE_CODE


def validate_leave_field_definition(
    field_code: str,
    field_type: RequestFieldTypeEnum,
) -> None:
    """Validate field definitions that use leave-reserved field codes."""

    normalized_code = field_code.strip().lower()
    allowed_types = LEAVE_FIELD_ALLOWED_TYPES.get(normalized_code)
    if allowed_types is None:
        return

    if field_type in allowed_types:
        return

    if normalized_code in {LEAVE_DATE_START_FIELD_CODE, LEAVE_DATE_END_FIELD_CODE}:
        raise LeaveBusinessRuleError(
            f"Leave field '{normalized_code}' must use the DATE field type."
        )

    raise LeaveBusinessRuleError(
        "Leave field 'leave_option' must use the SELECT or TEXT field type."
    )


def validate_leave_request_type_fields(fields: Sequence[RequestTypeField]) -> None:
    """Validate that a leave request type exposes the required active fields."""

    fields_by_code = {field.code: field for field in fields}
    missing_codes = [
        field_code
        for field_code in LEAVE_REQUIRED_FIELD_CODES
        if field_code not in fields_by_code
    ]
    if missing_codes:
        missing_list = ", ".join(missing_codes)
        raise LeaveBusinessRuleError(
            "Leave request types must define the active fields "
            f"{missing_list}."
        )

    for field_code, request_field in fields_by_code.items():
        validate_leave_field_definition(
            field_code=field_code,
            field_type=RequestFieldTypeEnum(request_field.field_type),
        )


def calculate_leave_duration_days(date_start: date, date_end: date) -> int:
    """Return the inclusive number of calendar days between two leave dates."""

    if date_start > date_end:
        raise LeaveBusinessRuleError("date_start must be on or before date_end.")

    return (date_end - date_start).days + 1


def evaluate_leave_request(
    values: Mapping[str, Any],
    available_balance_days: int,
    *,
    enforce_balance_check: bool,
) -> LeaveRequestEvaluation:
    """Validate and compute the leave business payload from submitted values."""

    if available_balance_days < 0:
        raise LeaveBusinessRuleError(
            "Available leave balance days cannot be negative."
        )

    date_start = _coerce_date(
        _require_leave_value(values, LEAVE_DATE_START_FIELD_CODE),
        LEAVE_DATE_START_FIELD_CODE,
    )
    date_end = _coerce_date(
        _require_leave_value(values, LEAVE_DATE_END_FIELD_CODE),
        LEAVE_DATE_END_FIELD_CODE,
    )
    leave_rule = _resolve_leave_option(
        _require_leave_value(values, LEAVE_OPTION_FIELD_CODE)
    )
    requested_duration_days = calculate_leave_duration_days(date_start, date_end)

    if (
        enforce_balance_check
        and leave_rule.requires_balance_check
        and requested_duration_days > available_balance_days
    ):
        raise LeaveBusinessRuleError(
            f"{leave_rule.label} requires {requested_duration_days} day(s) but "
            f"only {available_balance_days} day(s) are available."
        )

    return LeaveRequestEvaluation(
        date_start=date_start,
        date_end=date_end,
        leave_option=leave_rule.option,
        leave_option_label=leave_rule.label,
        requested_duration_days=requested_duration_days,
        balance_validation_applied=leave_rule.requires_balance_check,
        available_balance_days=available_balance_days,
    )


def _require_leave_value(values: Mapping[str, Any], field_code: str) -> Any:
    """Return a leave value and reject blank or missing required inputs."""

    if field_code not in values:
        raise LeaveBusinessRuleError(
            f"{field_code} is required for leave requests."
        )

    value = values[field_code]
    if value is None:
        raise LeaveBusinessRuleError(
            f"{field_code} is required for leave requests."
        )

    if isinstance(value, str) and not value.strip():
        raise LeaveBusinessRuleError(
            f"{field_code} is required for leave requests."
        )

    return value


def _coerce_date(value: Any, field_code: str) -> date:
    """Convert a leave value to a date."""

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise LeaveBusinessRuleError(
                f"{field_code} must be a valid ISO date."
            ) from exc

    raise LeaveBusinessRuleError(f"{field_code} must be a valid date.")


def _resolve_leave_option(value: Any) -> LeaveOptionRule:
    """Normalize a leave option value and return its static rule mapping."""

    if not isinstance(value, str):
        raise LeaveBusinessRuleError(
            "leave_option must be one of: paid leave, unpaid leave, CTT."
        )

    normalized_value = " ".join(
        value.strip().lower().replace("-", " ").replace("_", " ").split()
    )
    option = LEAVE_OPTION_ALIASES.get(normalized_value)
    if option is None:
        raise LeaveBusinessRuleError(
            "leave_option must be one of: paid leave, unpaid leave, CTT."
        )

    return LEAVE_OPTION_RULES[option]


__all__ = [
    "LEAVE_DATE_END_FIELD_CODE",
    "LEAVE_DATE_START_FIELD_CODE",
    "LEAVE_OPTION_FIELD_CODE",
    "LEAVE_REQUEST_TYPE_CODE",
    "LeaveBusinessRuleError",
    "LeaveRequestEvaluation",
    "calculate_leave_duration_days",
    "evaluate_leave_request",
    "is_leave_request_type_code",
    "validate_leave_field_definition",
    "validate_leave_request_type_fields",
]
