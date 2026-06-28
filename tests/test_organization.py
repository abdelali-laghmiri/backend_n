from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_organization_bootstrap.db"

from app.apps.auth.dependencies import get_current_active_user
from app.apps.organization.dependencies import get_organization_service
from app.apps.organization.models import Department, JobTitle, Team
from app.apps.organization.router import router as organization_router
from app.apps.organization.service import OrganizationService
from app.apps.permissions.dependencies import get_permissions_service
from app.apps.users.models import User
from app.db.base import Base


def _make_user(user_id: int) -> User:
    return User(
        id=user_id,
        matricule=f"USR-{user_id}",
        password_hash="hash",
        first_name="Test",
        last_name=f"User{user_id}",
        email=f"user{user_id}@example.com",
        is_super_admin=False,
        is_active=True,
        must_change_password=False,
    )


ADMIN_USER_ID = 999


class OrganizationCRUDTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "organization.db"
        self.engine = create_engine(
            f"sqlite:///{database_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        self.db: Session = self.session_factory()
        self.admin_user = _make_user(ADMIN_USER_ID)
        self.db.add(self.admin_user)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    # ----- Departments -----

    def test_create_department(self) -> None:
        client = self._build_test_client()

        response = client.post(
            "/organization/departments",
            json={
                "name": "Engineering",
                "code": "ENG",
                "description": "Engineering department",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["name"], "Engineering")
        self.assertEqual(payload["code"], "ENG")
        self.assertEqual(payload["description"], "Engineering department")
        self.assertTrue(payload["is_active"])
        self.assertIn("id", payload)

    def test_get_department(self) -> None:
        client = self._build_test_client()
        created = client.post(
            "/organization/departments",
            json={"name": "HR", "code": "HR", "description": "Human Resources"},
        ).json()

        response = client.get(f"/organization/departments/{created['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "HR")

    def test_list_departments(self) -> None:
        client = self._build_test_client()
        client.post("/organization/departments", json={"name": "A", "code": "A"})
        client.post("/organization/departments", json={"name": "B", "code": "B"})

        response = client.get("/organization/departments")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()), 2)

    def test_update_department(self) -> None:
        client = self._build_test_client()
        created = client.post(
            "/organization/departments",
            json={"name": "Old Name", "code": "OLD"},
        ).json()

        response = client.patch(
            f"/organization/departments/{created['id']}",
            json={"name": "New Name"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "New Name")

    def test_deactivate_department(self) -> None:
        client = self._build_test_client()
        created = client.post(
            "/organization/departments",
            json={"name": "To Deactivate", "code": "DEACT"},
        ).json()

        response = client.post(
            f"/organization/departments/{created['id']}/deactivate"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_active"])

    # ----- Teams -----

    def test_create_team(self) -> None:
        client = self._build_test_client()
        dept = client.post(
            "/organization/departments",
            json={"name": "IT", "code": "IT"},
        ).json()

        response = client.post(
            "/organization/teams",
            json={
                "name": "Backend",
                "code": "BE",
                "department_id": dept["id"],
                "description": "Backend team",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["name"], "Backend")
        self.assertEqual(payload["code"], "BE")
        self.assertEqual(payload["department_id"], dept["id"])
        self.assertTrue(payload["is_active"])
        self.assertIn("id", payload)

    def test_get_team(self) -> None:
        client = self._build_test_client()
        dept = client.post(
            "/organization/departments", json={"name": "Dept", "code": "DEPT"}
        ).json()
        created = client.post(
            "/organization/teams",
            json={"name": "Team X", "code": "TX", "department_id": dept["id"]},
        ).json()

        response = client.get(f"/organization/teams/{created['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Team X")

    def test_list_teams(self) -> None:
        client = self._build_test_client()
        dept = client.post(
            "/organization/departments", json={"name": "Dept", "code": "DPT"}
        ).json()
        client.post(
            "/organization/teams",
            json={"name": "T1", "code": "T1", "department_id": dept["id"]},
        )
        client.post(
            "/organization/teams",
            json={"name": "T2", "code": "T2", "department_id": dept["id"]},
        )

        response = client.get("/organization/teams")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()), 2)

    def test_update_team(self) -> None:
        client = self._build_test_client()
        dept = client.post(
            "/organization/departments", json={"name": "Dept", "code": "DPT2"}
        ).json()
        created = client.post(
            "/organization/teams",
            json={"name": "Old Team", "code": "OLD", "department_id": dept["id"]},
        ).json()

        response = client.patch(
            f"/organization/teams/{created['id']}",
            json={"name": "New Team"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "New Team")

    def test_deactivate_team(self) -> None:
        client = self._build_test_client()
        dept = client.post(
            "/organization/departments", json={"name": "Dept", "code": "DPT3"}
        ).json()
        created = client.post(
            "/organization/teams",
            json={
                "name": "To Deactivate",
                "code": "TDEACT",
                "department_id": dept["id"],
            },
        ).json()

        response = client.post(f"/organization/teams/{created['id']}/deactivate")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_active"])

    # ----- Job Titles -----

    def test_create_job_title(self) -> None:
        client = self._build_test_client()

        response = client.post(
            "/organization/job-titles",
            json={
                "name": "Senior Engineer",
                "code": "SR_ENG",
                "hierarchical_level": 3,
                "description": "Senior engineering role",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["name"], "Senior Engineer")
        self.assertEqual(payload["code"], "SR_ENG")
        self.assertEqual(payload["hierarchical_level"], 3)
        self.assertTrue(payload["is_active"])
        self.assertIn("id", payload)

    def test_get_job_title(self) -> None:
        client = self._build_test_client()
        created = client.post(
            "/organization/job-titles",
            json={"name": "Junior", "code": "JR", "hierarchical_level": 1},
        ).json()

        response = client.get(f"/organization/job-titles/{created['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Junior")

    def test_list_job_titles(self) -> None:
        client = self._build_test_client()
        client.post(
            "/organization/job-titles",
            json={"name": "Role A", "code": "RA", "hierarchical_level": 1},
        )
        client.post(
            "/organization/job-titles",
            json={"name": "Role B", "code": "RB", "hierarchical_level": 2},
        )

        response = client.get("/organization/job-titles")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()), 2)

    def test_update_job_title(self) -> None:
        client = self._build_test_client()
        created = client.post(
            "/organization/job-titles",
            json={"name": "Old Role", "code": "OR", "hierarchical_level": 1},
        ).json()

        response = client.patch(
            f"/organization/job-titles/{created['id']}",
            json={"name": "New Role"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "New Role")

    def test_deactivate_job_title(self) -> None:
        client = self._build_test_client()
        created = client.post(
            "/organization/job-titles",
            json={"name": "Temp Role", "code": "TR", "hierarchical_level": 1},
        ).json()

        response = client.post(
            f"/organization/job-titles/{created['id']}/deactivate"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_active"])

    # ----- Pagination -----

    def test_department_pagination(self) -> None:
        client = self._build_test_client()
        for i in range(5):
            client.post(
                "/organization/departments",
                json={"name": f"Dept {i}", "code": f"DPT{i:02d}"},
            )

        page_one = client.get("/organization/departments?limit=2")
        self.assertEqual(len(page_one.json()), 2)

        page_two = client.get("/organization/departments?limit=2&offset=2")
        self.assertEqual(len(page_two.json()), 2)

        ids_page_one = [item["id"] for item in page_one.json()]
        ids_page_two = [item["id"] for item in page_two.json()]
        self.assertNotEqual(ids_page_one, ids_page_two)

    def test_team_pagination(self) -> None:
        client = self._build_test_client()
        dept = client.post(
            "/organization/departments", json={"name": "Root", "code": "ROOT"}
        ).json()
        for i in range(5):
            client.post(
                "/organization/teams",
                json={
                    "name": f"Team {i}",
                    "code": f"TM{i:02d}",
                    "department_id": dept["id"],
                },
            )

        page_one = client.get("/organization/teams?limit=2")
        self.assertEqual(len(page_one.json()), 2)

        page_two = client.get("/organization/teams?limit=2&offset=2")
        self.assertEqual(len(page_two.json()), 2)

        ids_page_one = [item["id"] for item in page_one.json()]
        ids_page_two = [item["id"] for item in page_two.json()]
        self.assertNotEqual(ids_page_one, ids_page_two)

    def test_job_title_pagination(self) -> None:
        client = self._build_test_client()
        for i in range(5):
            client.post(
                "/organization/job-titles",
                json={
                    "name": f"Level {i}",
                    "code": f"LV{i:02d}",
                    "hierarchical_level": i,
                },
            )

        page_one = client.get("/organization/job-titles?limit=2")
        self.assertEqual(len(page_one.json()), 2)

        page_two = client.get("/organization/job-titles?limit=2&offset=2")
        self.assertEqual(len(page_two.json()), 2)

        ids_page_one = [item["id"] for item in page_one.json()]
        ids_page_two = [item["id"] for item in page_two.json()]
        self.assertNotEqual(ids_page_one, ids_page_two)

    # ----- Helpers -----

    def _build_test_client(self) -> TestClient:
        app = FastAPI()
        app.include_router(organization_router)

        class StubPermissionsService:
            def user_has_permission(self, _user: User, permission_code: str) -> bool:
                return True

        def override_org_service():
            db = self.session_factory()
            try:
                yield OrganizationService(db=db)
            finally:
                db.close()

        app.dependency_overrides[get_organization_service] = override_org_service
        app.dependency_overrides[get_current_active_user] = lambda: self.admin_user
        app.dependency_overrides[get_permissions_service] = lambda: StubPermissionsService()
        return TestClient(app)


if __name__ == "__main__":
    unittest.main()
