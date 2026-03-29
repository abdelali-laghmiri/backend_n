from __future__ import annotations

import os
from datetime import date
import unittest

os.environ["DATABASE_URL"] = "sqlite:///./hr_management.db"

from app.apps.employees.models import Employee
from app.apps.organization.models import Department, JobTitle, Team
from app.apps.organization.service import (
    OrganizationService,
    _HierarchyPersonRecord,
    _HierarchySnapshot,
)
from app.apps.users.models import User


def _make_user(user_id: int, first_name: str, last_name: str) -> User:
    return User(
        id=user_id,
        matricule=f"USR-{user_id}",
        password_hash="hash",
        first_name=first_name,
        last_name=last_name,
        email=f"user{user_id}@example.com",
        is_super_admin=False,
        is_active=True,
        must_change_password=False,
    )


def _make_job_title(job_title_id: int, level: int) -> JobTitle:
    return JobTitle(
        id=job_title_id,
        name=f"Level {level}",
        code=f"LEVEL_{level}_{job_title_id}",
        description=None,
        hierarchical_level=level,
        is_active=True,
    )


def _make_department(
    department_id: int,
    name: str,
    manager_user_id: int | None,
) -> Department:
    return Department(
        id=department_id,
        name=name,
        code=f"DEPT_{department_id}",
        description=None,
        manager_user_id=manager_user_id,
        is_active=True,
    )


def _make_team(
    team_id: int,
    department_id: int,
    name: str,
    leader_user_id: int | None,
) -> Team:
    return Team(
        id=team_id,
        name=name,
        code=f"TEAM_{team_id}",
        description=None,
        department_id=department_id,
        leader_user_id=leader_user_id,
        is_active=True,
    )


def _make_record(
    *,
    user_id: int,
    first_name: str,
    last_name: str,
    level: int,
    department: Department | None = None,
    team: Team | None = None,
) -> _HierarchyPersonRecord:
    user = _make_user(user_id, first_name, last_name)
    job_title = _make_job_title(user_id, level)
    employee = Employee(
        id=user_id,
        user_id=user_id,
        matricule=f"EMP-{user_id}",
        first_name=first_name,
        last_name=last_name,
        email=f"employee{user_id}@example.com",
        phone=None,
        image=None,
        hire_date=date(2024, 1, 1),
        available_leave_balance_days=0,
        department_id=department.id if department is not None else None,
        team_id=team.id if team is not None else None,
        job_title_id=job_title.id,
        is_active=True,
    )
    return _HierarchyPersonRecord(
        user=user,
        employee=employee,
        job_title=job_title,
        department=department,
        team=team,
    )


class OrganizationHierarchyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = OrganizationService(db=None)

    def test_company_hierarchy_enforces_strict_descending_levels(self) -> None:
        department_a = _make_department(1, "Department A", manager_user_id=70)
        department_b = _make_department(2, "Department B", manager_user_id=40)
        team_a = _make_team(1, department_a.id, "Team A", leader_user_id=50)
        team_b = _make_team(2, department_b.id, "Team B", leader_user_id=60)

        records = {
            record.user.id: record
            for record in [
                _make_record(
                    user_id=10,
                    first_name="Aline",
                    last_name="Root",
                    level=5,
                    department=department_a,
                ),
                _make_record(
                    user_id=20,
                    first_name="Basil",
                    last_name="Root",
                    level=5,
                    department=department_b,
                ),
                _make_record(
                    user_id=30,
                    first_name="Claire",
                    last_name="Manager",
                    level=4,
                    department=department_a,
                ),
                _make_record(
                    user_id=40,
                    first_name="Dario",
                    last_name="Manager",
                    level=4,
                    department=department_b,
                ),
                _make_record(
                    user_id=50,
                    first_name="Elena",
                    last_name="Lead",
                    level=3,
                    department=department_a,
                    team=team_a,
                ),
                _make_record(
                    user_id=60,
                    first_name="Farid",
                    last_name="Lead",
                    level=3,
                    department=department_b,
                    team=team_b,
                ),
                _make_record(
                    user_id=70,
                    first_name="Gina",
                    last_name="Analyst",
                    level=2,
                    department=department_a,
                    team=team_a,
                ),
                _make_record(
                    user_id=80,
                    first_name="Hugo",
                    last_name="Analyst",
                    level=2,
                    department=department_b,
                    team=team_b,
                ),
                _make_record(
                    user_id=90,
                    first_name="Ines",
                    last_name="Associate",
                    level=1,
                    department=department_a,
                    team=team_a,
                ),
            ]
        }
        snapshot = _HierarchySnapshot(
            records_by_user_id=records,
            departments_by_id={
                department_a.id: department_a,
                department_b.id: department_b,
            },
            teams_by_id={team_a.id: team_a, team_b.id: team_b},
            department_ids_by_manager_user_id={
                department_a.manager_user_id: [department_a.id],
                department_b.manager_user_id: [department_b.id],
            },
            team_ids_by_leader_user_id={
                team_a.leader_user_id: [team_a.id],
                team_b.leader_user_id: [team_b.id],
            },
        )

        roots = self.service._build_company_roots(snapshot)
        levels = {user_id: record.hierarchical_level for user_id, record in records.items()}
        parent_by_user_id = self._collect_parent_by_user_id(roots)

        self.assertEqual({node["user_id"] for node in roots}, {10, 20})
        self.assertEqual(parent_by_user_id[30], 10)
        self.assertEqual(parent_by_user_id[40], 20)
        self.assertEqual(parent_by_user_id[50], 30)
        self.assertEqual(parent_by_user_id[60], 40)
        self.assertEqual(parent_by_user_id[70], 50)
        self.assertEqual(parent_by_user_id[80], 60)
        self.assertEqual(parent_by_user_id[90], 70)
        self.assertNotIn(70, {node["user_id"] for node in roots})

        self._assert_descending_tree(roots, levels)

    def test_company_hierarchy_falls_back_to_nearest_available_higher_level(self) -> None:
        department = _make_department(1, "Operations", manager_user_id=None)
        team = _make_team(1, department.id, "Ops Team", leader_user_id=20)

        records = {
            record.user.id: record
            for record in [
                _make_record(
                    user_id=10,
                    first_name="Amina",
                    last_name="Director",
                    level=5,
                    department=department,
                ),
                _make_record(
                    user_id=20,
                    first_name="Bilal",
                    last_name="Lead",
                    level=3,
                    department=department,
                    team=team,
                ),
                _make_record(
                    user_id=30,
                    first_name="Chaymae",
                    last_name="Coordinator",
                    level=1,
                    department=department,
                    team=team,
                ),
            ]
        }
        snapshot = _HierarchySnapshot(
            records_by_user_id=records,
            departments_by_id={department.id: department},
            teams_by_id={team.id: team},
            department_ids_by_manager_user_id={},
            team_ids_by_leader_user_id={team.leader_user_id: [team.id]},
        )

        roots = self.service._build_company_roots(snapshot)
        levels = {user_id: record.hierarchical_level for user_id, record in records.items()}
        parent_by_user_id = self._collect_parent_by_user_id(roots)

        self.assertEqual([node["user_id"] for node in roots], [10])
        self.assertEqual(parent_by_user_id[20], 10)
        self.assertEqual(parent_by_user_id[30], 20)

        self._assert_descending_tree(roots, levels)

    def _collect_parent_by_user_id(
        self,
        roots: list[dict[str, object]],
    ) -> dict[int, int]:
        parent_by_user_id: dict[int, int] = {}

        def visit(node: dict[str, object]) -> None:
            for child in node["children"]:
                parent_by_user_id[child["user_id"]] = node["user_id"]
                visit(child)

        for root in roots:
            visit(root)

        return parent_by_user_id

    def _assert_descending_tree(
        self,
        roots: list[dict[str, object]],
        levels: dict[int, int],
    ) -> None:
        all_levels = set(levels.values())
        highest_level = max(all_levels)

        def visit(node: dict[str, object]) -> None:
            node_level = levels[node["user_id"]]
            child_levels = [levels[child["user_id"]] for child in node["children"]]

            if child_levels:
                self.assertEqual(
                    len(set(child_levels)),
                    1,
                    f"Children of user {node['user_id']} mix hierarchy levels: {child_levels}",
                )
                expected_child_level = max(
                    level for level in all_levels if level < node_level
                )
                self.assertTrue(
                    all(level == expected_child_level for level in child_levels),
                    f"User {node['user_id']} has children on the wrong structural level: {child_levels}",
                )

            for child in node["children"]:
                self.assertLess(levels[child["user_id"]], node_level)
                visit(child)

        self.assertTrue(all(levels[root["user_id"]] == highest_level for root in roots))
        for root in roots:
            visit(root)


if __name__ == "__main__":
    unittest.main()
