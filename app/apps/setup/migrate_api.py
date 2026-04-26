"""
Migration API endpoint - run this to apply canonical permissions.
Access: POST /api/v1/setup/migrate-permissions
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import require_superadmin
from app.apps.users.models import User

router = APIRouter()


@router.post("/setup/migrate-permissions")
async def migrate_permissions(
    response: Response,
    current_user: User = Depends(require_superadmin),
    db=Depends(get_db),
):
    """
    Apply canonical permission migration.
    Run this once after deployment to update permissions.
    """
    results = {"status": "pending", "inserted": 0, "updated": 0, "assigned": 0}
    
    # 1. Insert canonical permissions (ignore duplicates)
    canonical_perms = [
        ("organization.view", "View organization", "View departments, teams, and job titles.", "organization"),
        ("organization.hierarchy.view", "View organization hierarchy", "View hierarchy for current user.", "organization"),
        ("organization.hierarchy.view_all", "View full company hierarchy", "View full company organigram.", "organization"),
        ("employees.view", "View employees", "View employee profiles.", "employees"),
        ("permissions.view", "View permissions", "View permission catalog.", "permissions"),
        ("announcements.view", "View announcements", "View announcements.", "announcements"),
        ("messages.view", "View messages", "View inbox and sent.", "messages"),
        ("messages.recipients.view", "View recipients", "List users for messaging.", "messages"),
        ("messages.templates.manage", "Manage templates", "Manage templates.", "messages"),
        ("requests.view", "View requests", "View requests.", "requests"),
        ("requests.approvals.view", "View approvals", "View personal approvals.", "requests"),
        ("requests.view_all", "View all requests", "View all requests.", "requests"),
        ("attendance.view", "View attendance", "View attendance.", "attendance"),
        ("performance.view", "View performance", "View performance.", "performance"),
        ("dashboard.view", "View dashboard", "View dashboard.", "dashboard"),
        ("dashboard.analytics.view", "View analytics", "View analytics.", "dashboard"),
    ]
    
    for code, name, desc, module in canonical_perms:
        try:
            result = db.execute(text("""
                INSERT INTO permissions (code, name, description, module, is_active, created_at, updated_at)
                VALUES (:code, :name, :desc, :module, true, NOW(), NOW())
                ON CONFLICT (code) DO NOTHING
            """), {"code": code, "name": name, "desc": desc, "module": module})
            if result.rowcount:
                results["inserted"] += 1
        except Exception as e:
            pass
    
    # 2. Update legacy to canonical
    updates = [
        ("organization.read", "organization.view", "View organization"),
        ("organization.read_hierarchy", "organization.hierarchy.view", "View hierarchy"),
        ("organization.company_hierarchy", "organization.hierarchy.view_all", "View full hierarchy"),
        ("employees.read", "employees.view", "View employees"),
        ("permissions.read", "permissions.view", "View permissions"),
        ("announcements.read", "announcements.view", "View announcements"),
        ("messages.read", "messages.view", "View messages"),
        ("messages.read_users", "messages.recipients.view", "View recipients"),
        ("messages.templates", "messages.templates.manage", "Manage templates"),
        ("requests.read", "requests.view", "View requests"),
        ("requests.read_all", "requests.view_all", "View all"),
        ("requests.read_my_approvals", "requests.approvals.view", "View approvals"),
        ("attendance.read", "attendance.view", "View attendance"),
        ("performance.read", "performance.view", "View performance"),
        ("dashboard.read", "dashboard.view", "View dashboard"),
        ("dashboard.analytics.read", "dashboard.analytics.view", "View analytics"),
    ]
    
    for old_code, new_code, name in updates:
        try:
            result = db.execute(text("""
                UPDATE permissions 
                SET code = :new, name = :name, updated_at = NOW()
                WHERE code = :old
            """), {"old": old_code, "new": new_code, "name": name})
            results["updated"] += result.rowcount
        except Exception as e:
            pass
    
    # 3. Reassign job title permissions
    db.execute(text("DELETE FROM job_title_permissions"))
    
    job_title_perms = {
        "RH_MANAGER": [
            "organization.view", "organization.hierarchy.view", "organization.create", "organization.update",
            "employees.view", "employees.create", "employees.update",
            "permissions.view", "permissions.assign",
            "announcements.view", "announcements.create", "announcements.update", "announcements.delete",
            "messages.view", "messages.recipients.view", "messages.send_all", "messages.reply", "messages.templates.manage",
            "requests.view", "requests.create", "requests.approve", "requests.approvals.view", "requests.manage", "requests.view_all",
            "attendance.view", "attendance.ingest", "attendance.nfc.ingest", "attendance.nfc.assign_card", "attendance.reports.generate",
            "performance.view", "performance.manage",
            "dashboard.view",
        ],
        "DEPARTMENT_MANAGER": [
            "organization.view", "organization.hierarchy.view",
            "employees.view",
            "announcements.view", "announcements.create", "announcements.update", "announcements.delete",
            "messages.view", "messages.recipients.view", "messages.send_same_or_down", "messages.reply",
            "requests.view", "requests.approve", "requests.approvals.view",
            "attendance.view", "performance.view", "dashboard.view",
        ],
        "TEAM_LEADER": [
            "organization.hierarchy.view", "announcements.view",
            "messages.view", "messages.recipients.view", "messages.send_same_or_down", "messages.reply",
            "requests.view", "requests.create", "requests.approve", "requests.approvals.view",
            "attendance.view", "performance.create", "performance.view", "dashboard.view",
        ],
        "EMPLOYEE": [
            "announcements.view", "messages.view", "messages.recipients.view", "messages.send_same_or_down", "messages.reply",
            "requests.create", "requests.view",
        ],
    }
    
    for jt_code, perm_codes in job_title_perms.items():
        jt = db.execute(text("SELECT id FROM job_titles WHERE code = :code"), {"code": jt_code}).fetchone()
        if jt:
            for p_code in perm_codes:
                p = db.execute(text("SELECT id FROM permissions WHERE code = :code"), {"code": p_code}).fetchone()
                if p:
                    try:
                        db.execute(text("""
                            INSERT INTO job_title_permissions (job_title_id, permission_id, created_at)
                            VALUES (:jt_id, :p_id, NOW())
                        """), {"jt_id": jt[0], "p_id": p[0]})
                        results["assigned"] += 1
                    except Exception:
                        pass
    
    db.commit()
    results["status"] = "complete"
    
    # Get final count
    count = db.execute(text("SELECT COUNT(*) FROM permissions WHERE is_active = true")).fetchone()
    results["total_permissions"] = count[0] if count else 0
    
    return results