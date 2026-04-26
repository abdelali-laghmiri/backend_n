from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from app.apps.employees.schemas import EmployeeCreateRequest, EmployeeUpdateRequest
from app.apps.employees.models import ContractTypeEnum, Employee
from app.apps.employees.service import EmployeesService, EmployeesValidationError


class ContractTypeValidationTests(unittest.TestCase):
    """Tests for employee contract type schema validation."""

    def test_create_internal_employee_without_external_company(self) -> None:
        payload = EmployeeCreateRequest(
            matricule="EMP-001",
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hire_date=date(2024, 1, 1),
            job_title_id=1,
            contract_type="INTERNAL",
        )
        self.assertEqual(payload.contract_type, "INTERNAL")
        self.assertIsNone(payload.external_company_name)

    def test_create_external_employee_requires_company_name(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            EmployeeCreateRequest(
                matricule="EMP-002",
                first_name="Test",
                last_name="User",
                email="test@example.com",
                hire_date=date(2024, 1, 1),
                job_title_id=1,
                contract_type="EXTERNAL",
            )
        self.assertIn("External company name is required", str(ctx.exception))

    def test_create_external_employee_with_company_name(self) -> None:
        payload = EmployeeCreateRequest(
            matricule="EMP-003",
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hire_date=date(2024, 1, 1),
            job_title_id=1,
            contract_type="EXTERNAL",
            external_company_name="TechSolutions SARL",
        )
        self.assertEqual(payload.contract_type, "EXTERNAL")
        self.assertEqual(payload.external_company_name, "TechSolutions SARL")

    def test_create_external_employee_trims_company_name(self) -> None:
        payload = EmployeeCreateRequest(
            matricule="EMP-004",
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hire_date=date(2024, 1, 1),
            job_title_id=1,
            contract_type="EXTERNAL",
            external_company_name="  Global Services Inc  ",
        )
        self.assertEqual(payload.external_company_name, "Global Services Inc")

    def test_update_to_external_requires_company(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            EmployeeUpdateRequest(
                contract_type="EXTERNAL",
            )
        self.assertIn("External company name is required", str(ctx.exception))

    def test_update_to_internal_clears_company(self) -> None:
        payload = EmployeeUpdateRequest(
            contract_type="INTERNAL",
            external_company_name="Some Company",
        )
        self.assertEqual(payload.contract_type, "INTERNAL")
        self.assertIsNone(payload.external_company_name)

    def test_update_internal_to_external_with_company(self) -> None:
        payload = EmployeeUpdateRequest(
            contract_type="EXTERNAL",
            external_company_name="New Contractor Ltd",
        )
        self.assertEqual(payload.contract_type, "EXTERNAL")
        self.assertEqual(payload.external_company_name, "New Contractor Ltd")


class ContractTypeModelTests(unittest.TestCase):
    """Tests for ContractTypeEnum."""

    def test_contract_type_values(self) -> None:
        self.assertEqual(ContractTypeEnum.INTERNAL.value, "INTERNAL")
        self.assertEqual(ContractTypeEnum.EXTERNAL.value, "EXTERNAL")

    def test_contract_type_count(self) -> None:
        values = [e.value for e in ContractTypeEnum]
        self.assertEqual(len(values), 2)
        self.assertIn("INTERNAL", values)
        self.assertIn("EXTERNAL", values)


class ContractTypeServiceValidationTests(unittest.TestCase):
    """Tests for employee service contract type validation."""

    def test_update_contract_type_validation_external_without_company(self) -> None:
        db = MagicMock()
        service = EmployeesService(db)

        changes = {
            "contract_type": "EXTERNAL",
            "external_company_name": None,
        }

        with self.assertRaises(EmployeesValidationError) as ctx:
            service._validate_required_update_fields(changes)
        self.assertIn("External company name is required", str(ctx.exception))

    def test_update_contract_type_validation_external_with_empty_company(self) -> None:
        db = MagicMock()
        service = EmployeesService(db)

        changes = {
            "contract_type": "EXTERNAL",
            "external_company_name": "",
        }

        with self.assertRaises(EmployeesValidationError) as ctx:
            service._validate_required_update_fields(changes)
        self.assertIn("External company name is required", str(ctx.exception))

    def test_update_contract_type_validation_external_with_whitespace_company(self) -> None:
        db = MagicMock()
        service = EmployeesService(db)

        changes = {
            "contract_type": "EXTERNAL",
            "external_company_name": "   ",
        }

        with self.assertRaises(EmployeesValidationError) as ctx:
            service._validate_required_update_fields(changes)
        self.assertIn("External company name is required", str(ctx.exception))

    def test_update_contract_type_validation_internal_allows_no_company(self) -> None:
        db = MagicMock()
        service = EmployeesService(db)

        changes = {
            "contract_type": "INTERNAL",
        }
        service._validate_required_update_fields(changes)


if __name__ == "__main__":
    unittest.main()