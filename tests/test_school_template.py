"""Blank-school regression tests; live MySQL test is explicitly opt-in."""
import importlib.util
import os
from pathlib import Path
import uuid

import bcrypt
import pymysql
import pytest

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

builder = load('school_template_builder', 'scripts/build_school_template.py')
provisioner = load('school_provisioner', 'app/core/tenant_provisioner.py')


def test_kampul_presets_are_complete_and_branded():
    tables = builder.load_presets()
    assert tables['branch'][0]['branch_name'] == 'Kampul SIS Main Branch'
    assert tables['settings'][0]['enterpriseName'] == 'Kampul SIS'
    assert tables['settings'][0]['system_name'] == 'Kampul SIS'
    assert tables['roles'][0]['role_name'] == 'Super Admin'
    for table in ('settings', 'branch', 'academic', 'attendance_system_settings',
                  'certificate_settings', 'pickup_settings', 'app_branding_settings',
                  'telegram_attendance_settings'):
        assert len(tables[table]) == 1
    assert not set(tables).intersection({'users', 'students', 'parents', 'invoices', 'holidays'})
    assert tables['telegram_attendance_settings'][0]['enabled'] == 0


def test_builder_reads_schema_only():
    source = (ROOT / 'scripts/build_school_template.py').read_text(encoding='utf-8')
    assert 'SELECT *' not in source
    assert 'SELECT id FROM academic' not in source


@pytest.mark.skipif(os.getenv('RUN_MYSQL_TEMPLATE_TESTS') != '1', reason='requires local MySQL CREATE DATABASE privilege')
def test_fresh_school_has_usable_defaults_and_no_orphaned_references():
    slug = 'template_test_' + uuid.uuid4().hex[:12]
    database = 'sis_' + slug
    options = dict(host=os.getenv('DB_HOST', '127.0.0.1'), port=int(os.getenv('DB_PORT', '3306')),
                   user=os.getenv('DB_USER', 'root'), password=os.getenv('DB_PASSWORD', ''))
    conn = pymysql.connect(**options, autocommit=True)
    created = False
    try:
        result = provisioner.provision_tenant_database(slug, 'Test School', admin_username='admin',
            admin_password='TestOnly!42', contact_name='Must Not Become Admin', contact_email='owner@example.test', mysql_host=options['host'], mysql_port=options['port'],
            mysql_user=options['user'], mysql_password=options['password'])
        created = True
        assert result['success'] and result['table_count'] >= 200
        with conn.cursor() as cur:
            cur.execute(f'USE `{database}`')
            for table in ('branch', 'academic', 'settings'):
                cur.execute(f'SELECT id FROM `{table}`')
                assert cur.fetchall() == ((1,),)
            cur.execute('SELECT password,workplace,role FROM users WHERE id=1')
            password, branch, role = cur.fetchone()
            assert bcrypt.checkpw(b'TestOnly!42', password.encode())
            assert (branch, role) == (1, 1)
            cur.execute('SELECT eName,kName,email,phone FROM users WHERE id=1')
            assert cur.fetchone() == ('Super Admin', 'Super Admin', None, None)
            cur.execute('SELECT enterpriseName,ownerEname,system_name FROM settings WHERE id=1')
            assert cur.fetchone() == ('Kampul SIS', 'Super Admin', 'Kampul SIS')
            for table, rows in builder.load_presets().items():
                cur.execute(f'SELECT COUNT(*) FROM `{table}`')
                assert cur.fetchone()[0] == len(rows), table
            for table in ('students', 'parents', 'medal_price', 'leave_type_allocations', 'holidays'):
                cur.execute(f'SELECT COUNT(*) FROM `{table}`')
                assert cur.fetchone()[0] == 0
            cur.execute('SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME '
                        'FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() '
                        'AND REFERENCED_TABLE_NAME IS NOT NULL')
            references = list(cur.fetchall())
            targets = {'academic_id': 'academic', 'academicid': 'academic', 'branch_id': 'branch',
                       'grade_id': 'grade', 'grade_group_id': 'grade_group',
                       'grade_type_id': 'grade_type', 'subject_id': 'subjects'}
            cur.execute('SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()')
            references += [(t, c, targets[c], 'id') for t, c in cur.fetchall() if c in targets]
            for table, column, target, key in references:
                cur.execute(f'SELECT COUNT(*) FROM `{table}` a LEFT JOIN `{target}` b '
                            f'ON a.`{column}`=b.`{key}` WHERE a.`{column}` IS NOT NULL '
                            f'AND a.`{column}` <> 0 AND b.`{key}` IS NULL')
                assert cur.fetchone()[0] == 0, (table, column, target)
            with pytest.raises(RuntimeError, match='refusing to overwrite'):
                provisioner.provision_tenant_database(slug, 'Replacement', mysql_host=options['host'],
                    mysql_port=options['port'], mysql_user=options['user'], mysql_password=options['password'])
    finally:
        if created:
            with conn.cursor() as cur:
                cur.execute(f'DROP DATABASE `{database}`')
        conn.close()

@pytest.mark.parametrize('headers', [
    {'host': 'my-school.sis.kampul.com'},
    {'x-tenant-subdomain': 'my-school'},
    {'x-school-slug': 'MY-SCHOOL'},
])
def test_hyphenated_school_resolves_to_provisioned_database(monkeypatch, headers):
    from app.core import database
    from starlette.requests import Request
    monkeypatch.setattr(database, 'is_valid_database', lambda name: name == 'sis_my_school')
    request = Request({'type': 'http', 'headers': [(k.encode(), v.encode()) for k, v in headers.items()]})
    assert database.resolve_tenant_db_name(request) == 'sis_my_school'


@pytest.mark.skipif(os.getenv('RUN_MYSQL_TEMPLATE_TESTS') != '1', reason='requires local MySQL')
def test_two_schools_get_identical_defaults_and_distinct_credentials():
    conn = pymysql.connect(host=os.getenv('DB_HOST', '127.0.0.1'), port=int(os.getenv('DB_PORT', 3306)),
        user=os.getenv('DB_USER', 'root'), password=os.getenv('DB_PASSWORD', ''), autocommit=True)
    created = []
    try:
        schools = []
        for index in range(2):
            slug = 'preset_test_' + uuid.uuid4().hex[:12]
            result = provisioner.provision_tenant_database(slug, f'Different School {index}',
                contact_name=f'Owner {index}', contact_email=f'owner{index}@example.test')
            created.append(result['database'])
            schools.append(result)
        assert schools[0]['admin_username'] != schools[1]['admin_username']
        assert schools[0]['admin_password'] != schools[1]['admin_password']
        with conn.cursor() as cur:
            for table, rows in builder.load_presets().items():
                columns = ','.join('`' + col + '`' for col in rows[0])
                snapshots = []
                for database in created:
                    cur.execute(f'SELECT {columns} FROM `{database}`.`{table}`')
                    snapshots.append(sorted(cur.fetchall(), key=repr))
                assert snapshots[0] == snapshots[1], table
    finally:
        with conn.cursor() as cur:
            for database in created:
                cur.execute(f'DROP DATABASE `{database}`')
        conn.close()
