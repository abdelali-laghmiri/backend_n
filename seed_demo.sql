-- ============================================
-- SEED SCRIPT: Demo Data for Scanner App Testing
-- Run this in Supabase SQL Editor
-- ============================================

-- ============================================
-- 1) CREATE JOB TITLES
-- ============================================

INSERT INTO job_titles (name, code, description, hierarchical_level, is_active, created_at, updated_at)
SELECT 'System Administrator', 'JT001', 'Super admin role', 10, true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM job_titles WHERE code = 'JT001');

INSERT INTO job_titles (name, code, description, hierarchical_level, is_active, created_at, updated_at)
SELECT 'Scanner Operator', 'JT002', 'Limited scanner app access', 1, true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM job_titles WHERE code = 'JT002');

INSERT INTO job_titles (name, code, description, hierarchical_level, is_active, created_at, updated_at)
SELECT 'HR Manager', 'JT003', 'HR department management', 5, true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM job_titles WHERE code = 'JT003');

INSERT INTO job_titles (name, code, description, hierarchical_level, is_active, created_at, updated_at)
SELECT 'Software Engineer', 'JT004', 'IT development', 4, true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM job_titles WHERE code = 'JT004');

INSERT INTO job_titles (name, code, description, hierarchical_level, is_active, created_at, updated_at)
SELECT 'Operations Staff', 'JT005', 'Day-to-day operations', 3, true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM job_titles WHERE code = 'JT005');

INSERT INTO job_titles (name, code, description, hierarchical_level, is_active, created_at, updated_at)
SELECT 'Security Guard', 'JT006', 'Security monitoring', 2, true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM job_titles WHERE code = 'JT006');

INSERT INTO job_titles (name, code, description, hierarchical_level, is_active, created_at, updated_at)
SELECT 'Finance Analyst', 'JT007', 'Financial operations', 4, true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM job_titles WHERE code = 'JT007');

-- ============================================
-- 2) CREATE USERS
-- ============================================

-- Using bcrypt hash for 'SuperDemo123!'
INSERT INTO users (matricule, password_hash, first_name, last_name, email, is_super_admin, is_active, must_change_password, created_at, updated_at)
SELECT 'SUPERADMIN001', '$2b$12$KIXqFxPdjmN0QZ0Z0QZ0ZuZ0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0', 'Super', 'Admin', 'superadmin.demo@example.com', true, true, false, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'superadmin.demo@example.com');

-- Scanner user
INSERT INTO users (matricule, password_hash, first_name, last_name, email, is_super_admin, is_active, must_change_password, created_at, updated_at)
SELECT 'SCANNER001', '$2b$12$KIXqFxPdjmN0QZ0Z0QZ0ZuZ0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0', 'Scanner', 'Device', 'scanner.demo@example.com', false, true, false, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'scanner.demo@example.com');

-- Company Admin
INSERT INTO users (matricule, password_hash, first_name, last_name, email, is_super_admin, is_active, must_change_password, created_at, updated_at)
SELECT 'ADMIN001', '$2b$12$KIXqFxPdjmN0QZ0Z0QZ0ZuZ0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0', 'Company', 'Admin', 'companyadmin.demo@example.com', false, true, false, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'companyadmin.demo@example.com');

-- ============================================
-- 3) CREATE DEPARTMENTS
-- ============================================

INSERT INTO departments (name, code, description, is_active, created_at, updated_at)
SELECT 'Human Resources', 'DEPT-HR', 'HR department', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM departments WHERE code = 'DEPT-HR');

INSERT INTO departments (name, code, description, is_active, created_at, updated_at)
SELECT 'Information Technology', 'DEPT-IT', 'IT department', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM departments WHERE code = 'DEPT-IT');

INSERT INTO departments (name, code, description, is_active, created_at, updated_at)
SELECT 'Operations', 'DEPT-OPS', 'Operations department', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM departments WHERE code = 'DEPT-OPS');

INSERT INTO departments (name, code, description, is_active, created_at, updated_at)
SELECT 'Security', 'DEPT-SEC', 'Security department', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM departments WHERE code = 'DEPT-SEC');

INSERT INTO departments (name, code, description, is_active, created_at, updated_at)
SELECT 'Finance', 'DEPT-FIN', 'Finance department', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM departments WHERE code = 'DEPT-FIN');

-- ============================================
-- 4) CREATE TEAMS
-- ============================================

INSERT INTO teams (name, code, description, department_id, is_active, created_at, updated_at)
SELECT 'Development', 'TEAM-IT-DEV', 'IT Development', (SELECT id FROM departments WHERE code = 'DEPT-IT'), true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM teams WHERE code = 'TEAM-IT-DEV');

INSERT INTO teams (name, code, description, department_id, is_active, created_at, updated_at)
SELECT 'IT Support', 'TEAM-IT-SUPPORT', 'IT Support', (SELECT id FROM departments WHERE code = 'DEPT-IT'), true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM teams WHERE code = 'TEAM-IT-SUPPORT');

INSERT INTO teams (name, code, description, department_id, is_active, created_at, updated_at)
SELECT 'Recruitment', 'TEAM-HR-RECRUIT', 'HR Recruitment', (SELECT id FROM departments WHERE code = 'DEPT-HR'), true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM teams WHERE code = 'TEAM-HR-RECRUIT');

INSERT INTO teams (name, code, description, department_id, is_active, created_at, updated_at)
SELECT 'Front Desk', 'TEAM-OPS-FRONT', 'Front Desk Operations', (SELECT id FROM departments WHERE code = 'DEPT-OPS'), true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM teams WHERE code = 'TEAM-OPS-FRONT');

INSERT INTO teams (name, code, description, department_id, is_active, created_at, updated_at)
SELECT 'Morning Shift', 'TEAM-SEC-MORNING', 'Security Morning Shift', (SELECT id FROM departments WHERE code = 'DEPT-SEC'), true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM teams WHERE code = 'TEAM-SEC-MORNING');

-- ============================================
-- 5) CREATE PERMISSIONS
-- ============================================

INSERT INTO permissions (code, name, description, module, is_active, created_at, updated_at)
SELECT 'attendance.nfc.ingest', 'Ingest NFC attendance events', 'Submit NFC scan events from the dedicated scanner application.', 'attendance', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'attendance.nfc.ingest');

INSERT INTO permissions (code, name, description, module, is_active, created_at, updated_at)
SELECT 'attendance.read', 'View attendance records', 'View attendance records', 'attendance', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'attendance.read');

INSERT INTO permissions (code, name, description, module, is_active, created_at, updated_at)
SELECT 'announcements.read', 'View announcements', 'View announcements', 'announcements', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'announcements.read');

INSERT INTO permissions (code, name, description, module, is_active, created_at, updated_at)
SELECT 'messages.read', 'View messages', 'View messages', 'messages', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'messages.read');

INSERT INTO permissions (code, name, description, module, is_active, created_at, updated_at)
SELECT 'dashboard.read', 'View dashboard', 'View dashboard', 'dashboard', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'dashboard.read');

INSERT INTO permissions (code, name, description, module, is_active, created_at, updated_at)
SELECT 'profile.view', 'View profile', 'View profile', 'profile', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'profile.view');

INSERT INTO permissions (code, name, description, module, is_active, created_at, updated_at)
SELECT 'requests.view', 'View requests', 'View requests', 'requests', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'requests.view');

INSERT INTO permissions (code, name, description, module, is_active, created_at, updated_at)
SELECT 'requests.create', 'Create requests', 'Create requests', 'requests', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'requests.create');

INSERT INTO permissions (code, name, description, module, is_active, created_at, updated_at)
SELECT 'organization.read_company_hierarchy', 'View company hierarchy', 'View company hierarchy', 'organization', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'organization.read_company_hierarchy');

INSERT INTO permissions (code, name, description, module, is_active, created_at, updated_at)
SELECT 'permissions.read', 'View permissions', 'View permissions', 'permissions', true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'permissions.read');

-- ============================================
-- 6) CREATE EMPLOYEES
-- ============================================

-- First, get the super admin user ID
DO $$
DECLARE
    super_admin_id INTEGER;
    scanner_user_id INTEGER;
    company_admin_id INTEGER;
    dept_it INTEGER;
    dept_hr INTEGER;
    dept_ops INTEGER;
    dept_sec INTEGER;
    dept_fin INTEGER;
    team_it_dev INTEGER;
    team_it_support INTEGER;
    team_hr_recruit INTEGER;
    team_ops_front INTEGER;
    team_sec_morning INTEGER;
    jt_it INTEGER;
    jt_hr INTEGER;
    jt_ops INTEGER;
    jt_sec INTEGER;
    jt_fin INTEGER;
    jt_scanner INTEGER;
BEGIN
    -- Get user IDs
    SELECT id INTO super_admin_id FROM users WHERE email = 'superadmin.demo@example.com';
    SELECT id INTO scanner_user_id FROM users WHERE email = 'scanner.demo@example.com';
    SELECT id INTO company_admin_id FROM users WHERE email = 'companyadmin.demo@example.com';
    
    -- Get department IDs
    SELECT id INTO dept_it FROM departments WHERE code = 'DEPT-IT';
    SELECT id INTO dept_hr FROM departments WHERE code = 'DEPT-HR';
    SELECT id INTO dept_ops FROM departments WHERE code = 'DEPT-OPS';
    SELECT id INTO dept_sec FROM departments WHERE code = 'DEPT-SEC';
    SELECT id INTO dept_fin FROM departments WHERE code = 'DEPT-FIN';
    
    -- Get team IDs
    SELECT id INTO team_it_dev FROM teams WHERE code = 'TEAM-IT-DEV';
    SELECT id INTO team_it_support FROM teams WHERE code = 'TEAM-IT-SUPPORT';
    SELECT id INTO team_hr_recruit FROM teams WHERE code = 'TEAM-HR-RECRUIT';
    SELECT id INTO team_ops_front FROM teams WHERE code = 'TEAM-OPS-FRONT';
    SELECT id INTO team_sec_morning FROM teams WHERE code = 'TEAM-SEC-MORNING';
    
    -- Get job title IDs
    SELECT id INTO jt_it FROM job_titles WHERE code = 'JT004';
    SELECT id INTO jt_hr FROM job_titles WHERE code = 'JT003';
    SELECT id INTO jt_ops FROM job_titles WHERE code = 'JT005';
    SELECT id INTO jt_sec FROM job_titles WHERE code = 'JT006';
    SELECT id INTO jt_fin FROM job_titles WHERE code = 'JT007';
    SELECT id INTO jt_scanner FROM job_titles WHERE code = 'JT002';
    
    -- Create employees
    -- EMP001 - IT Developer
    INSERT INTO employees (user_id, matricule, first_name, last_name, email, phone, hire_date, department_id, team_id, job_title_id, is_active, created_at, updated_at)
    SELECT super_admin_id, 'EMP001', 'Ahmed', 'Bensalah', 'ahmed.bensalah@example.com', '+212600000001', '2024-01-15', dept_it, team_it_dev, jt_it, true, NOW(), NOW()
    WHERE NOT EXISTS (SELECT 1 FROM employees WHERE matricule = 'EMP001');
    
    -- EMP002 - HR Manager
    INSERT INTO employees (user_id, matricule, first_name, last_name, email, phone, hire_date, department_id, team_id, job_title_id, is_active, created_at, updated_at)
    SELECT super_admin_id, 'EMP002', 'Fatima', 'Zahra', 'fatima.zahra@example.com', '+212600000002', '2024-01-15', dept_hr, team_hr_recruit, jt_hr, true, NOW(), NOW()
    WHERE NOT EXISTS (SELECT 1 FROM employees WHERE matricule = 'EMP002');
    
    -- EMP003 - Operations
    INSERT INTO employees (user_id, matricule, first_name, last_name, email, phone, hire_date, department_id, team_id, job_title_id, is_active, created_at, updated_at)
    SELECT super_admin_id, 'EMP003', 'Youssef', 'Amrani', 'youssef.amrani@example.com', '+212600000003', '2024-01-15', dept_ops, team_ops_front, jt_ops, true, NOW(), NOW()
    WHERE NOT EXISTS (SELECT 1 FROM employees WHERE matricule = 'EMP003');
    
    -- EMP004 - Security
    INSERT INTO employees (user_id, matricule, first_name, last_name, email, phone, hire_date, department_id, team_id, job_title_id, is_active, created_at, updated_at)
    SELECT super_admin_id, 'EMP004', 'Aicha', 'Benhama', 'aicha.benhama@example.com', '+212600000004', '2024-01-15', dept_sec, team_sec_morning, jt_sec, true, NOW(), NOW()
    WHERE NOT EXISTS (SELECT 1 FROM employees WHERE matricule = 'EMP004');
    
    -- EMP005 - Finance
    INSERT INTO employees (user_id, matricule, first_name, last_name, email, phone, hire_date, department_id, team_id, job_title_id, is_active, created_at, updated_at)
    SELECT super_admin_id, 'EMP005', 'Omar', 'Kadiri', 'omar.kadiri@example.com', '+212600000005', '2024-01-15', dept_fin, NULL, jt_fin, true, NOW(), NOW()
    WHERE NOT EXISTS (SELECT 1 FROM employees WHERE matricule = 'EMP005');
    
    -- EMP006 - IT Support
    INSERT INTO employees (user_id, matricule, first_name, last_name, email, phone, hire_date, department_id, team_id, job_title_id, is_active, created_at, updated_at)
    SELECT super_admin_id, 'EMP006', 'Nadia', 'Elmostafa', 'nadia.elmostafa@example.com', '+212600000006', '2024-01-15', dept_it, team_it_support, jt_it, true, NOW(), NOW()
    WHERE NOT EXISTS (SELECT 1 FROM employees WHERE matricule = 'EMP006');
    
    -- EMP007 - Operations
    INSERT INTO employees (user_id, matricule, first_name, last_name, email, phone, hire_date, department_id, team_id, job_title_id, is_active, created_at, updated_at)
    SELECT super_admin_id, 'EMP007', 'Rachid', 'Bousbia', 'rachid.bousbia@example.com', '+212600000007', '2024-01-15', dept_ops, team_ops_front, jt_ops, true, NOW(), NOW()
    WHERE NOT EXISTS (SELECT 1 FROM employees WHERE matricule = 'EMP007');
    
    -- EMP008 - HR
    INSERT INTO employees (user_id, matricule, first_name, last_name, email, phone, hire_date, department_id, team_id, job_title_id, is_active, created_at, updated_at)
    SELECT super_admin_id, 'EMP008', 'Samira', 'Talbi', 'samira.talbi@example.com', '+212600000008', '2024-01-15', dept_hr, team_hr_recruit, jt_hr, true, NOW(), NOW()
    WHERE NOT EXISTS (SELECT 1 FROM employees WHERE matricule = 'EMP008');
    
    -- Scanner employee
    INSERT INTO employees (user_id, matricule, first_name, last_name, email, phone, hire_date, department_id, team_id, job_title_id, is_active, created_at, updated_at)
    SELECT scanner_user_id, 'EMP-SCAN', 'Scanner', 'Device', 'scanner.demo@example.com', '+212600000000', '2024-01-01', dept_it, team_it_dev, jt_scanner, true, NOW(), NOW()
    WHERE NOT EXISTS (SELECT 1 FROM employees WHERE matricule = 'EMP-SCAN');
    
    -- ============================================
    -- 7) ASSIGN PERMISSIONS TO JOB TITLES
    -- ============================================
    
    -- Scanner Operator (JT002) gets attendance.nfc.ingest
    INSERT INTO job_title_permissions (job_title_id, permission_id, created_at)
    SELECT jt_scanner, (SELECT id FROM permissions WHERE code = 'attendance.nfc.ingest'), NOW()
    WHERE NOT EXISTS (
        SELECT 1 FROM job_title_permissions 
        WHERE job_title_id = jt_scanner 
        AND permission_id = (SELECT id FROM permissions WHERE code = 'attendance.nfc.ingest')
    );
    
END $$;

-- ============================================
-- 8) CREATE SCANNER-RELATED DATA
-- ============================================

-- Allowed origin
INSERT INTO allowed_origins (origin, source, is_active, created_by_user_id, created_at, updated_at)
SELECT 'https://nfc-selector-app.vercel.app', 'generated', true, (SELECT id FROM users WHERE email = 'superadmin.demo@example.com'), NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM allowed_origins WHERE origin = 'https://nfc-selector-app.vercel.app');

-- Scanner app build
INSERT INTO scanner_app_builds (target_name, backend_base_url, allowed_origin, generated_by_user_id, is_active, created_at, updated_at)
SELECT 'Demo Build', 'https://backend-n-lac.vercel.app', 'https://nfc-selector-app.vercel.app', (SELECT id FROM users WHERE email = 'superadmin.demo@example.com'), true, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM scanner_app_builds WHERE target_name = 'Demo Build');

-- ============================================
-- VERIFICATION
-- ============================================

SELECT 'Users created:' as info, COUNT(*)::text as count FROM users WHERE email LIKE '%demo@example.com'
UNION ALL
SELECT 'Employees created:', COUNT(*)::text FROM employees WHERE matricule LIKE 'EMP%'
UNION ALL
SELECT 'Departments created:', COUNT(*)::text FROM departments
UNION ALL
SELECT 'Teams created:', COUNT(*)::text FROM teams
UNION ALL
SELECT 'Job titles created:', COUNT(*)::text FROM job_titles
UNION ALL
SELECT 'Permissions created:', COUNT(*)::text FROM permissions
UNION ALL
SELECT 'Scanner app builds:', COUNT(*)::text FROM scanner_app_builds WHERE target_name = 'Demo Build'
UNION ALL
SELECT 'Allowed origins:', COUNT(*)::text FROM allowed_origins;

-- List demo users
SELECT matricule, first_name, last_name, email, is_super_admin FROM users WHERE email LIKE '%demo@example.com';

-- List employees
SELECT matricule, first_name, last_name, email, is_active FROM employees WHERE matricule LIKE 'EMP%' ORDER BY matricule;
