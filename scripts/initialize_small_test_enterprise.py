from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.apps.employees.schemas import EmployeeCreateRequest
from app.apps.employees.service import EmployeesService
from app.apps.organization.models import JobTitle
from app.apps.setup.service import SetupService
from app.core.config import get_settings
from app.core.database import SessionLocal


def main() -> None:
    settings = get_settings()
    session = SessionLocal()

    try:
        setup_service = SetupService(db=session, settings=settings)
        if setup_service.is_initialized():
            print("Initialization already completed. Skipping.")
            return

        super_admin = setup_service.get_super_admin()
        if super_admin is None:
            super_admin = setup_service.initialize_system()

        setup_service.save_readiness_step()
        setup_service.save_organization_step(
            {
                "department_name": "Operations",
                "department_code": "OPS",
                "department_description": "Initial operational department for pilot usage.",
                "team_one_name": "Administration Team",
                "team_one_code": "OPS-ADMIN",
                "team_one_description": "Administrative operations and HR coordination.",
                "team_two_name": "Field Team",
                "team_two_code": "OPS-FIELD",
                "team_two_description": "Field operations and execution.",
            }
        )
        setup_service.save_job_titles_step({})
        setup_service.ensure_permission_catalog()
        setup_service.ensure_job_title_permission_assignments()

        today = date.today().isoformat()
        setup_service.save_operational_users_step(
            {
                "rh_manager": {
                    "matricule": "RHM001",
                    "first_name": "Sara",
                    "last_name": "Amrani",
                    "email": "sara.amrani@smalltest.local",
                    "hire_date": today,
                    "password": "Rhm@12345",
                },
                "department_manager": {
                    "matricule": "DPM001",
                    "first_name": "Youssef",
                    "last_name": "Bennani",
                    "email": "youssef.bennani@smalltest.local",
                    "hire_date": today,
                    "password": "Dpm@12345",
                },
                "team_leader_one": {
                    "matricule": "TLD001",
                    "first_name": "Nadia",
                    "last_name": "El Idrissi",
                    "email": "nadia.idrissi@smalltest.local",
                    "hire_date": today,
                    "password": "Tld1@12345",
                },
                "team_leader_two": {
                    "matricule": "TLD002",
                    "first_name": "Karim",
                    "last_name": "Alaoui",
                    "email": "karim.alaoui@smalltest.local",
                    "hire_date": today,
                    "password": "Tld2@12345",
                },
            }
        )

        setup_service.complete_installation(super_admin)

        organization_summary = setup_service.get_organization_summary()
        department = organization_summary["department"]
        teams = organization_summary["teams"]
        employee_job_title = session.execute(
            select(JobTitle).where(JobTitle.code == "EMPLOYEE").limit(1)
        ).scalar_one()

        employees_service = EmployeesService(db=session)
        extra_employees = [
            {
                "matricule": "EMP001",
                "first_name": "Omar",
                "last_name": "Ziani",
                "email": "omar.ziani@smalltest.local",
                "team_id": teams[0].id,
            },
            {
                "matricule": "EMP002",
                "first_name": "Salma",
                "last_name": "Belkadi",
                "email": "salma.belkadi@smalltest.local",
                "team_id": teams[1].id,
            },
        ]

        print("Created enterprise small-test initialization.")
        print("Operational login accounts (must change password on first login):")
        print("- RHM001 / Rhm@12345")
        print("- DPM001 / Dpm@12345")
        print("- TLD001 / Tld1@12345")
        print("- TLD002 / Tld2@12345")

        print("Additional employee accounts:")
        for employee_data in extra_employees:
            employee, temporary_password = employees_service.create_employee(
                EmployeeCreateRequest(
                    matricule=employee_data["matricule"],
                    first_name=employee_data["first_name"],
                    last_name=employee_data["last_name"],
                    email=employee_data["email"],
                    phone=None,
                    image=None,
                    hire_date=today,
                    available_leave_balance_days=18,
                    department_id=department.id,
                    team_id=employee_data["team_id"],
                    job_title_id=employee_job_title.id,
                )
            )
            print(f"- {employee.matricule} / {temporary_password}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
