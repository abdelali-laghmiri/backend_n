"""
Idempotent seed script for demo data.
Run this to populate the database with test data for the scanner app demo.
"""

from datetime import date, datetime, timezone
from passlib.context import CryptContext
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import Base
from app.apps.users.models import User
from app.apps.organization.models import Department, Team, JobTitle
from app.apps.employees.models import Employee
from app.apps.permissions.models import Permission, JobTitlePermissionAssignment
from app.apps.attendance.models import NfcCard
from app.apps.scanner_app.models import AllowedOrigin, ScannerAppBuild

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def utcnow():
    return datetime.now(timezone.utc)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def get_or_create_user(session: Session, email: str, defaults: dict) -> User:
    """Get existing user or create new one."""
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user:
        print(f"  ↳ User {email} already exists, reusing")
        return user
    
    user = User(**defaults)
    session.add(user)
    session.flush()
    print(f"  ↳ Created user: {email}")
    return user

def get_or_create_job_title(session: Session, code: str, defaults: dict) -> JobTitle:
    """Get existing job title or create new one."""
    job_title = session.execute(select(JobTitle).where(JobTitle.code == code)).scalar_one_or_none()
    if job_title:
        return job_title
    
    job_title = JobTitle(**defaults)
    session.add(job_title)
    session.flush()
    print(f"  ↳ Created job title: {code}")
    return job_title

def get_or_create_department(session: Session, code: str, defaults: dict) -> Department:
    """Get existing department or create new one."""
    dept = session.execute(select(Department).where(Department.code == code)).scalar_one_or_none()
    if dept:
        return dept
    
    dept = Department(**defaults)
    session.add(dept)
    session.flush()
    print(f"  ↳ Created department: {code}")
    return dept

def get_or_create_team(session: Session, code: str, defaults: dict) -> Team:
    """Get existing team or create new one."""
    team = session.execute(select(Team).where(Team.code == code)).scalar_one_or_none()
    if team:
        return team
    
    team = Team(**defaults)
    session.add(team)
    session.flush()
    print(f"  ↳ Created team: {code}")
    return team

def get_or_create_permission(session: Session, code: str, defaults: dict) -> Permission:
    """Get existing permission or create new one."""
    perm = session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
    if perm:
        return perm
    
    perm = Permission(**defaults)
    session.add(perm)
    session.flush()
    print(f"  ↳ Created permission: {code}")
    return perm

def seed_demo_data():
    """Seed all demo data."""
    print("\n" + "="*60)
    print("SEEDING DEMO DATA")
    print("="*60 + "\n")
    
    # Connect to database
    database_url = settings.get_database_url()
    engine = create_engine(database_url, echo=False)
    
    with Session(engine) as session:
        # ============================================
        # 1) CREATE JOB TITLES
        # ============================================
        print("\n[1] Creating job titles...")
        
        job_titles_data = [
            ("JT001", "System Administrator", "Super admin role", 10),
            ("JT002", "Scanner Operator", "Limited scanner app access", 1),
            ("JT003", "HR Manager", "HR department management", 5),
            ("JT004", "Software Engineer", "IT development", 4),
            ("JT005", "Operations Staff", "Day-to-day operations", 3),
            ("JT006", "Security Guard", "Security monitoring", 2),
            ("JT007", "Finance Analyst", "Financial operations", 4),
        ]
        
        job_titles = {}
        for code, name, desc, level in job_titles_data:
            job_titles[code] = get_or_create_job_title(
                session, code,
                {"name": name, "code": code, "description": desc, "hierarchical_level": level, "is_active": True}
            )
        
        # ============================================
        # 2) CREATE USERS
        # ============================================
        print("\n[2] Creating users...")
        
        # Super Admin
        super_admin = get_or_create_user(
            session, "superadmin.demo@example.com",
            {
                "matricule": "SUPERADMIN001",
                "password_hash": hash_password("SuperDemo123!"),
                "first_name": "Super",
                "last_name": "Admin",
                "email": "superadmin.demo@example.com",
                "is_super_admin": True,
                "is_active": True,
                "must_change_password": False,
            }
        )
        super_admin.is_super_admin = True
        super_admin.must_change_password = False
        
        # Scanner User
        scanner_user = get_or_create_user(
            session, "scanner.demo@example.com",
            {
                "matricule": "SCANNER001",
                "password_hash": hash_password("ScannerDemo123!"),
                "first_name": "Scanner",
                "last_name": "Device",
                "email": "scanner.demo@example.com",
                "is_super_admin": False,
                "is_active": True,
                "must_change_password": False,
            }
        )
        
        # Company Admin
        company_admin = get_or_create_user(
            session, "companyadmin.demo@example.com",
            {
                "matricule": "ADMIN001",
                "password_hash": hash_password("AdminDemo123!"),
                "first_name": "Company",
                "last_name": "Admin",
                "email": "companyadmin.demo@example.com",
                "is_super_admin": False,
                "is_active": True,
                "must_change_password": False,
            }
        )
        
        # ============================================
        # 3) CREATE DEPARTMENTS
        # ============================================
        print("\n[3] Creating departments...")
        
        departments_data = [
            ("DEPT-HR", "Human Resources", "HR department"),
            ("DEPT-IT", "Information Technology", "IT department"),
            ("DEPT-OPS", "Operations", "Operations department"),
            ("DEPT-SEC", "Security", "Security department"),
            ("DEPT-FIN", "Finance", "Finance department"),
        ]
        
        departments = {}
        for code, name, desc in departments_data:
            departments[code] = get_or_create_department(
                session, code,
                {"name": name, "code": code, "description": desc, "is_active": True}
            )
        
        # ============================================
        # 4) CREATE TEAMS
        # ============================================
        print("\n[4] Creating teams...")
        
        teams_data = [
            ("TEAM-IT-DEV", "Development", departments["DEPT-IT"].id),
            ("TEAM-IT-SUPPORT", "IT Support", departments["DEPT-IT"].id),
            ("TEAM-HR-RECRUIT", "Recruitment", departments["DEPT-HR"].id),
            ("TEAM-OPS-FRONT", "Front Desk", departments["DEPT-OPS"].id),
            ("TEAM-SEC-MORNING", "Morning Shift", departments["DEPT-SEC"].id),
        ]
        
        teams = {}
        for code, name, dept_id in teams_data:
            teams[code] = get_or_create_team(
                session, code,
                {"name": name, "code": code, "department_id": dept_id, "is_active": True}
            )
        
        # ============================================
        # 5) CREATE EMPLOYEES
        # ============================================
        print("\n[5] Creating employees...")
        
        employees_data = [
            ("EMP001", "Ahmed", "Bensalah", "ahmed.bensalah@example.com", "+212600000001", departments["DEPT-IT"].id, teams["TEAM-IT-DEV"].id, job_titles["JT004"].id),
            ("EMP002", "Fatima", "Zahra", "fatima.zahra@example.com", "+212600000002", departments["DEPT-HR"].id, teams["TEAM-HR-RECRUIT"].id, job_titles["JT003"].id),
            ("EMP003", "Youssef", "Amrani", "youssef.amrani@example.com", "+212600000003", departments["DEPT-OPS"].id, teams["TEAM-OPS-FRONT"].id, job_titles["JT005"].id),
            ("EMP004", "Aicha", "Benhama", "aicha.benhama@example.com", "+212600000004", departments["DEPT-SEC"].id, teams["TEAM-SEC-MORNING"].id, job_titles["JT006"].id),
            ("EMP005", "Omar", "Kadiri", "omar.kadiri@example.com", "+212600000005", departments["DEPT-FIN"].id, None, job_titles["JT007"].id),
            ("EMP006", "Nadia", "Elmostafa", "nadia.elmostafa@example.com", "+212600000006", departments["DEPT-IT"].id, teams["TEAM-IT-SUPPORT"].id, job_titles["JT004"].id),
            ("EMP007", "Rachid", "Bousbia", "rachid.bousbia@example.com", "+212600000007", departments["DEPT-OPS"].id, teams["TEAM-OPS-FRONT"].id, job_titles["JT005"].id),
            ("EMP008", "Samira", "Talbi", "samira.talbi@example.com", "+212600000008", departments["DEPT-HR"].id, teams["TEAM-HR-RECRUIT"].id, job_titles["JT003"].id),
        ]
        
        employees = []
        for matricule, first_name, last_name, email, phone, dept_id, team_id, job_title_id in employees_data:
            # Check if employee already exists
            existing = session.execute(select(Employee).where(Employee.matricule == matricule)).scalar_one_or_none()
            if existing:
                print(f"  ↳ Employee {matricule} already exists, reusing")
                employees.append(existing)
                continue
            
            employee = Employee(
                user_id=super_admin.id,  # Using super admin as placeholder user
                matricule=matricule,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                hire_date=date(2024, 1, 15),
                department_id=dept_id,
                team_id=team_id,
                job_title_id=job_title_id,
                is_active=True,
            )
            session.add(employee)
            session.flush()
            print(f"  ↳ Created employee: {matricule} - {first_name} {last_name}")
            employees.append(employee)
        
        # ============================================
        # 6) CREATE PERMISSIONS
        # ============================================
        print("\n[6] Creating/verifying permissions...")
        
        permissions_data = [
            ("attendance.nfc.ingest", "Ingest NFC attendance events", "attendance"),
            ("attendance.read", "View attendance records", "attendance"),
            ("announcements.read", "View announcements", "announcements"),
            ("messages.read", "View messages", "messages"),
            ("dashboard.read", "View dashboard", "dashboard"),
            ("profile.view", "View profile", "profile"),
            ("requests.view", "View requests", "requests"),
            ("requests.create", "Create requests", "requests"),
            ("organization.read_company_hierarchy", "View company hierarchy", "organization"),
            ("permissions.read", "View permissions", "permissions"),
        ]
        
        permissions = {}
        for code, name, module in permissions_data:
            permissions[code] = get_or_create_permission(
                session, code,
                {"name": name, "code": code, "description": f"{name} permission", "module": module, "is_active": True}
            )
        
        # ============================================
        # 7) ASSIGN PERMISSIONS TO JOB TITLES
        # ============================================
        print("\n[7] Assigning permissions to job titles...")
        
        # Scanner Operator gets attendance.nfc.ingest only
        scanner_perms = ["attendance.nfc.ingest"]
        for perm_code in scanner_perms:
            # Check if assignment already exists
            existing_assignment = session.execute(
                select(JobTitlePermissionAssignment).where(
                    JobTitlePermissionAssignment.job_title_id == job_titles["JT002"].id,
                    JobTitlePermissionAssignment.permission_id == permissions[perm_code].id
                )
            ).scalar_one_or_none()
            
            if not existing_assignment:
                assignment = JobTitlePermissionAssignment(
                    job_title_id=job_titles["JT002"].id,
                    permission_id=permissions[perm_code].id,
                )
                session.add(assignment)
                print(f"  ↳ Assigned {perm_code} to Scanner Operator")
        
        # Update scanner user to have Scanner Operator job title
        # (We need to create an employee for scanner user too)
        scanner_employee = session.execute(select(Employee).where(Employee.matricule == "EMP-SCAN")).scalar_one_or_none()
        if not scanner_employee:
            scanner_employee = Employee(
                user_id=scanner_user.id,
                matricule="EMP-SCAN",
                first_name="Scanner",
                last_name="Device",
                email="scanner.demo@example.com",
                hire_date=date(2024, 1, 1),
                job_title_id=job_titles["JT002"].id,  # Scanner Operator
                is_active=True,
            )
            session.add(scanner_employee)
            session.flush()
            print(f"  ↳ Created employee for scanner user")
        
        # ============================================
        # 8) CREATE SCANNER-RELATED DATA
        # ============================================
        print("\n[8] Creating scanner-related data...")
        
        # Allowed origin (demo)
        allowed_origin = session.execute(select(AllowedOrigin).where(AllowedOrigin.origin == "https://nfc-selector-app.vercel.app")).scalar_one_or_none()
        if not allowed_origin:
            allowed_origin = AllowedOrigin(
                origin="https://nfc-selector-app.vercel.app",
                source="generated",
                is_active=True,
                created_by_user_id=super_admin.id,
            )
            session.add(allowed_origin)
            session.flush()
            print(f"  ↳ Created allowed origin: https://nfc-selector-app.vercel.app")
        
        # Scanner app build (demo)
        scanner_build = session.execute(select(ScannerAppBuild).where(ScannerAppBuild.target_name == "Demo Build")).scalar_one_or_none()
        if not scanner_build:
            scanner_build = ScannerAppBuild(
                target_name="Demo Build",
                backend_base_url="https://backend-n-lac.vercel.app",
                allowed_origin="https://nfc-selector-app.vercel.app",
                generated_by_user_id=super_admin.id,
                is_active=True,
            )
            session.add(scanner_build)
            session.flush()
            print(f"  ↳ Created scanner app build: Demo Build")
        
        # ============================================
        # 9) COMMIT
        # ============================================
        print("\n[9] Committing changes...")
        session.commit()
        
        print("\n" + "="*60)
        print("SEED COMPLETE!")
        print("="*60 + "\n")
        
        # Print summary
        print("SUMMARY:")
        print("-" * 40)
        print(f"Users created/reused: 3")
        print(f"  - superadmin.demo@example.com / SuperDemo123!")
        print(f"  - scanner.demo@example.com / ScannerDemo123!")
        print(f"  - companyadmin.demo@example.com / AdminDemo123!")
        print(f"Employees: {len(employees)}")
        print(f"Departments: {len(departments)}")
        print(f"Teams: {len(teams)}")
        print(f"Job Titles: {len(job_titles)}")
        print(f"Permissions: {len(permissions)}")
        print("-" * 40)
        print("\nIMPORTANT:")
        print("- Scanner user has job title 'Scanner Operator' with attendance.nfc.ingest")
        print("- Employees are ready for NFC UID attachment in frontend")
        print("- Demo scanner app build is active")
        print("-" * 40)

if __name__ == "__main__":
    seed_demo_data()
