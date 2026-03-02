# Data migration: seed Role, Permission, RolePermission for RBAC.

from django.db import migrations


def seed_rbac(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    RolePermission = apps.get_model('core', 'RolePermission')

    roles_data = [
        ('super_admin', 'Super Admin'),
        ('owner', 'Owner'),
        ('manager', 'Manager'),
        ('waiter', 'Waiter'),
        ('kitchen', 'Kitchen'),
        ('customer', 'Customer'),
    ]
    permissions_data = [
        ('manage_restaurants', 'Manage Restaurants'),
        ('manage_owners', 'Manage Owners'),
        ('manage_kyc', 'Manage KYC Verifications'),
        ('manage_shareholders', 'Manage Shareholders'),
        ('manage_transactions', 'Manage Transactions'),
        ('manage_withdrawals', 'Manage Shareholder Withdrawals'),
        ('manage_dues', 'Manage Dues'),
        ('manage_qr_orders', 'Manage QR Stand Orders'),
        ('manage_notifications', 'Manage Notifications'),
        ('view_reports', 'View Reports'),
        ('manage_super_settings', 'Manage System Settings'),
        ('manage_menu', 'Manage Menu'),
        ('manage_units', 'Manage Units'),
        ('manage_categories', 'Manage Categories'),
        ('manage_products', 'Manage Products'),
        ('manage_combo_sets', 'Manage Combo Sets'),
        ('manage_customers', 'Manage Customers'),
        ('manage_vendors', 'Manage Vendors'),
        ('manage_inventory', 'Manage Inventory'),
        ('manage_purchases', 'Manage Purchases'),
        ('manage_tables', 'Manage Tables'),
        ('manage_orders', 'Manage Orders'),
        ('manage_finance', 'Manage Finance'),
        ('manage_finance_records', 'Manage Finance Records'),
        ('manage_expenses', 'Manage Expenses'),
        ('manage_staff', 'Manage Staff'),
        ('manage_attendance', 'Manage Attendance'),
        ('manage_payroll', 'Manage Payroll'),
        ('manage_feedback', 'Manage Feedback'),
        ('view_live_orders', 'View Live Orders'),
        ('view_salary', 'View Salary'),
        ('view_my_performance', 'View My Performance'),
        ('customer_orders', 'Customer: My Orders'),
        ('customer_credits', 'Customer: Credits'),
        ('customer_feedback', 'Customer: Feedback'),
        ('customer_profile', 'Customer: Profile'),
    ]

    for code, name in roles_data:
        Role.objects.get_or_create(code=code, defaults={'name': name})

    for code, name in permissions_data:
        Permission.objects.get_or_create(code=code, defaults={'name': name})

    role_perms = {
        'super_admin': [
            'manage_restaurants', 'manage_owners', 'manage_kyc', 'manage_shareholders',
            'manage_transactions', 'manage_withdrawals', 'manage_dues', 'manage_qr_orders',
            'manage_notifications', 'view_reports', 'manage_super_settings',
        ],
        'owner': [
            'manage_restaurants', 'manage_menu', 'manage_units', 'manage_categories', 'manage_products',
            'manage_combo_sets', 'manage_customers', 'manage_vendors', 'manage_qr_orders',
            'manage_orders', 'manage_finance', 'manage_staff', 'manage_payroll',
            'manage_notifications', 'view_reports', 'manage_feedback',
        ],
        'manager': [
            'manage_menu', 'manage_units', 'manage_categories', 'manage_products', 'manage_combo_sets',
            'manage_vendors', 'manage_inventory', 'manage_purchases', 'manage_tables',
            'manage_qr_orders', 'manage_orders', 'manage_finance', 'manage_finance_records',
            'manage_expenses', 'manage_staff', 'manage_attendance', 'manage_payroll',
            'manage_customers', 'manage_notifications', 'manage_feedback', 'view_reports',
        ],
        'waiter': [
            'manage_orders', 'view_salary', 'view_my_performance', 'manage_attendance', 'manage_feedback',
        ],
        'kitchen': [
            'view_live_orders',
        ],
        'customer': [
            'customer_orders', 'customer_credits', 'customer_feedback', 'customer_profile',
        ],
    }

    role_objs = {r.code: r for r in Role.objects.all()}
    perm_objs = {p.code: p for p in Permission.objects.all()}

    for role_code, perm_codes in role_perms.items():
        role = role_objs.get(role_code)
        if not role:
            continue
        for perm_code in perm_codes:
            perm = perm_objs.get(perm_code)
            if perm:
                RolePermission.objects.get_or_create(role=role, permission=perm)


def reverse_seed_rbac(apps, schema_editor):
    RolePermission = apps.get_model('core', 'RolePermission')
    RolePermission.objects.all().delete()
    apps.get_model('core', 'Permission').objects.all().delete()
    apps.get_model('core', 'Role').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0029_rbac_roles_permissions'),
    ]

    operations = [
        migrations.RunPython(seed_rbac, reverse_seed_rbac),
    ]
