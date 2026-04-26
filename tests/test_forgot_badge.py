from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

from app.apps.forgot_badge.models import (
    ForgotBadgeRequest,
    ForgotBadgeRequestStatusEnum,
    TemporaryNfcAssignment,
    TemporaryNfcAssignmentStatusEnum,
)
from app.apps.forgot_badge.schemas import (
    ForgotBadgeRequestCreateRequest,
    ForgotBadgeRequestApproveRequest,
    ForgotBadgeRequestRejectRequest,
    ForgotBadgeRequestCancelRequest,
    ForgotBadgeRequestCompleteRequest,
)
from app.apps.forgot_badge.service import (
    ForgotBadgeService,
    ForgotBadgeConflictError,
    ForgotBadgeNotFoundError,
    ForgotBadgeValidationError,
)


class ForgotBadgeSchemaValidationTests(unittest.TestCase):
    """Tests for forgot badge request schema validation."""

    def test_create_request_with_optional_reason(self) -> None:
        payload = ForgotBadgeRequestCreateRequest(reason="Forgot my badge at home")
        self.assertEqual(payload.reason, "Forgot my badge at home")

    def test_create_request_without_reason(self) -> None:
        payload = ForgotBadgeRequestCreateRequest()
        self.assertIsNone(payload.reason)

    def test_create_request_trims_reason(self) -> None:
        payload = ForgotBadgeRequestCreateRequest(reason="  Forgot badge  ")
        self.assertEqual(payload.reason, "Forgot badge")

    def test_approve_request_requires_nfc_card_and_date(self) -> None:
        payload = ForgotBadgeRequestApproveRequest(
            nfc_card_id=1,
            valid_for_date=date.today(),
        )
        self.assertEqual(payload.nfc_card_id, 1)
        self.assertEqual(payload.valid_for_date, date.today())

    def test_reject_request_with_notes(self) -> None:
        payload = ForgotBadgeRequestRejectRequest(notes="Card not available today")
        self.assertEqual(payload.notes, "Card not available today")

    def test_cancel_request_with_reason(self) -> None:
        payload = ForgotBadgeRequestCancelRequest(reason="Found my badge")
        self.assertEqual(payload.reason, "Found my badge")


class ForgotBadgeModelTests(unittest.TestCase):
    """Tests for forgot badge model enums."""

    def test_request_status_values(self) -> None:
        values = [e.value for e in ForgotBadgeRequestStatusEnum]
        self.assertIn("PENDING", values)
        self.assertIn("APPROVED", values)
        self.assertIn("REJECTED", values)
        self.assertIn("COMPLETED", values)
        self.assertIn("CANCELLED", values)

    def test_assignment_status_values(self) -> None:
        values = [e.value for e in TemporaryNfcAssignmentStatusEnum]
        self.assertIn("ACTIVE", values)
        self.assertIn("USED", values)
        self.assertIn("RELEASED", values)
        self.assertIn("EXPIRED", values)


class ForgotBadgeServiceTests(unittest.TestCase):
    """Tests for forgot badge service."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.service = ForgotBadgeService(self.db)

    def test_create_request_requires_employee(self) -> None:
        mock_user = MagicMock()
        mock_user.id = 1

        self.db.execute.return_value.scalar_one_or_none.return_value = None

        payload = ForgotBadgeRequestCreateRequest()
        with self.assertRaises(ForgotBadgeValidationError) as ctx:
            self.service.create_request(payload, mock_user)
        self.assertIn("No active employee profile", str(ctx.exception))

    def test_validate_temporary_card_available_rejects_active_for_other(self) -> None:
        mock_card = MagicMock()
        mock_card.id = 1

        mock_assignment = MagicMock()
        mock_assignment.employee_id = 99
        mock_assignment.status = TemporaryNfcAssignmentStatusEnum.ACTIVE.value

        self.db.execute.return_value.scalar_one_or_none.return_value = mock_assignment

        with self.assertRaises(ForgotBadgeConflictError) as ctx:
            self.service._validate_temporary_card_available(
                nfc_card_id=1,
                employee_id=1,
                valid_for_date=date.today(),
            )
        self.assertIn("already assigned to another employee", str(ctx.exception))

    def test_validate_temporary_card_available_rejects_active_for_same(self) -> None:
        mock_card = MagicMock()
        mock_card.id = 1

        mock_assignment = MagicMock()
        mock_assignment.employee_id = 1
        mock_assignment.status = TemporaryNfcAssignmentStatusEnum.ACTIVE.value

        self.db.execute.return_value.scalar_one_or_none.return_value = mock_assignment

        with self.assertRaises(ForgotBadgeConflictError) as ctx:
            self.service._validate_temporary_card_available(
                nfc_card_id=1,
                employee_id=1,
                valid_for_date=date.today(),
            )
        self.assertIn("already has an active temporary NFC card", str(ctx.exception))

    def test_validate_temporary_card_available_rejects_used_today(self) -> None:
        mock_assignment = MagicMock()
        mock_assignment.employee_id = 99
        mock_assignment.status = TemporaryNfcAssignmentStatusEnum.USED.value

        self.db.execute.return_value.scalar_one_or_none.return_value = mock_assignment

        with self.assertRaises(ForgotBadgeConflictError) as ctx:
            self.service._validate_temporary_card_available(
                nfc_card_id=1,
                employee_id=1,
                valid_for_date=date.today(),
            )
        self.assertIn("already used for a forgot badge session", str(ctx.exception))

    def test_reject_request_wrong_status(self) -> None:
        mock_request = MagicMock()
        mock_request.id = 1
        mock_request.status = ForgotBadgeRequestStatusEnum.APPROVED.value

        self.db.get.return_value = mock_request

        payload = ForgotBadgeRequestRejectRequest()
        mock_user = MagicMock()

        with self.assertRaises(ForgotBadgeValidationError) as ctx:
            self.service.reject_request(1, payload, mock_user)
        self.assertIn("Only PENDING requests can be rejected", str(ctx.exception))

    def test_approve_request_wrong_status(self) -> None:
        mock_request = MagicMock()
        mock_request.id = 1
        mock_request.status = ForgotBadgeRequestStatusEnum.REJECTED.value

        self.db.get.return_value = mock_request

        payload = ForgotBadgeRequestApproveRequest(
            nfc_card_id=1,
            valid_for_date=date.today(),
        )
        mock_user = MagicMock()

        with self.assertRaises(ForgotBadgeValidationError) as ctx:
            self.service.approve_request(1, payload, mock_user)
        self.assertIn("Only PENDING requests can be approved", str(ctx.exception))

    def test_cancel_request_wrong_user(self) -> None:
        mock_request = MagicMock()
        mock_request.id = 1
        mock_request.user_id = 99
        mock_request.status = ForgotBadgeRequestStatusEnum.PENDING.value

        self.db.get.return_value = mock_request

        payload = ForgotBadgeRequestCancelRequest()
        mock_user = MagicMock()
        mock_user.id = 1

        with self.assertRaises(ForgotBadgeValidationError) as ctx:
            self.service.cancel_request(1, payload, mock_user)
        self.assertIn("only cancel your own requests", str(ctx.exception))

    def test_resolve_employee_by_temporary_card_returns_none_when_no_assignment(self) -> None:
        self.db.execute.return_value.scalar_one_or_none.return_value = None

        result = self.service.resolve_employee_by_temporary_card(
            nfc_card_id=1,
            valid_for_date=date.today(),
        )
        self.assertIsNone(result)

    def test_get_active_temporary_assignment_returns_none(self) -> None:
        self.db.execute.return_value.scalar_one_or_none.return_value = None

        result = self.service.get_active_temporary_assignment(
            employee_id=1,
            valid_for_date=date.today(),
        )
        self.assertIsNone(result)


class ForgotBadgeRequestWorkflowTests(unittest.TestCase):
    """Tests for forgot badge request workflow states."""

    def test_workflow_states_complete(self) -> None:
        states = [e.value for e in ForgotBadgeRequestStatusEnum]
        self.assertEqual(len(states), 5)
        self.assertCountEqual(
            states,
            ["PENDING", "APPROVED", "REJECTED", "COMPLETED", "CANCELLED"],
        )

    def test_temporary_assignment_workflow_states_complete(self) -> None:
        states = [e.value for e in TemporaryNfcAssignmentStatusEnum]
        self.assertEqual(len(states), 4)
        self.assertCountEqual(
            states,
            ["ACTIVE", "USED", "RELEASED", "EXPIRED"],
        )


if __name__ == "__main__":
    unittest.main()