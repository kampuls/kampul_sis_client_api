"""Build the shared Kampul SIS template from versioned presets and a schema source.

The source database supplies DDL only. No school rows or registration values are
read. Edit defaults/kampul_sis.json to change the common starter data.
"""
import argparse
import json
import os
from pathlib import Path
import re

import pymysql

ROOT = Path(__file__).resolve().parents[1]
PRESET_PATH = ROOT / 'defaults' / 'kampul_sis.json'


def load_presets(path=PRESET_PATH):
    preset = json.loads(Path(path).read_text(encoding='utf-8'))
    if preset.get('product') != 'Kampul SIS' or preset.get('version') != 1:
        raise ValueError('Unsupported Kampul SIS preset version')
    tables = preset['tables']
    for table in ('branch', 'academic', 'settings'):
        if len(tables.get(table, [])) != 1 or tables[table][0]['id'] != 1:
            raise ValueError(f'Preset requires exactly one {table} with id 1')
    if any(tables.get(t) for t in ('users', 'app_admins', 'students', 'parents', 'invoices')):
        raise ValueError('Preset cannot contain accounts or operational records')
    return tables


def identifier(value):
    return '`' + value.replace('`', '``') + '`'


def insert_sql(conn, table, rows, batch=100):
    columns = list(rows[0])
    if any(set(row) != set(columns) for row in rows):
        raise ValueError(f'Inconsistent preset columns: {table}')
    out = []
    for offset in range(0, len(rows), batch):
        values = ',\n'.join('(' + ', '.join(conn.escape(row[c]) for c in columns) + ')'
                            for row in rows[offset:offset + batch])
        out.append(f'INSERT INTO {identifier(table)} (' + ', '.join(map(identifier, columns))
                   + ') VALUES\n' + values + ';\n')
    return ''.join(out)


def build(conn, source, preset_path=PRESET_PATH):
    presets = load_presets(preset_path)
    with conn.cursor() as cur:
        cur.execute('USE ' + identifier(source))
        for catalog, column in (('views', 'table_schema'), ('triggers', 'trigger_schema')):
            cur.execute(f'SELECT COUNT(*) FROM information_schema.{catalog} WHERE {column}=%s', (source,))
            if cur.fetchone()[0]:
                raise ValueError(f'Schema source has {catalog}; explicit support is required')
        cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
        tables = sorted(row[0] for row in cur.fetchall())
        missing = set(presets) - set(tables)
        if missing:
            raise ValueError(f'Preset tables missing from schema: {sorted(missing)}')
        parts = ['-- Kampul SIS default school template; generated, do not edit.\n'
                 '-- All starter rows come from defaults/kampul_sis.json (version 1).\n'
                 '-- One branch and academic year; unique Super Admin created at provisioning.\n'
                 'SET NAMES utf8mb4;\nSET SQL_MODE = \'NO_AUTO_VALUE_ON_ZERO\';\n'
                 'SET FOREIGN_KEY_CHECKS = 0;\n\n']
        for table in tables:
            cur.execute('SHOW CREATE TABLE ' + identifier(table))
            ddl = re.sub(r' AUTO_INCREMENT=\d+', '', cur.fetchone()[1])
            if table == 'app_branding_settings':
                ddl = ddl.replace("DEFAULT 'PAMA'", "DEFAULT 'KAMPUL'").replace("DEFAULT 'INTERNATIONAL SCHOOL'", "DEFAULT 'SIS'")
            parts.append(f'DROP TABLE IF EXISTS {identifier(table)};\n{ddl};\n\n')
        for table, rows in presets.items():
            if not rows:
                continue
            cur.execute('SHOW COLUMNS FROM ' + identifier(table))
            schema = {row[0]: row for row in cur.fetchall()}
            unknown = set(rows[0]) - set(schema)
            required = {name for name, col in schema.items()
                        if col[2] == 'NO' and col[4] is None and 'auto_increment' not in col[5]}
            if unknown or required - set(rows[0]):
                raise ValueError(f'{table}: unknown columns {sorted(unknown)}, missing required {sorted(required - set(rows[0]))}')
            parts.append(f'-- {table}: {len(rows)} rows\n' + insert_sql(conn, table, rows) + '\n')
        parts.append('SET FOREIGN_KEY_CHECKS = 1;\n')
    return ''.join(parts), {table: len(rows) for table, rows in presets.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='schema-only source database; no rows are copied')
    parser.add_argument('--presets', type=Path, default=PRESET_PATH)
    parser.add_argument('--out', type=Path, default=ROOT / 'template_school_db.sql')
    args = parser.parse_args()
    conn = pymysql.connect(host=os.getenv('DB_HOST', '127.0.0.1'), port=int(os.getenv('DB_PORT', 3306)),
                           user=os.getenv('DB_USER', 'root'), password=os.getenv('DB_PASSWORD', ''), charset='utf8mb4')
    try:
        sql, counts = build(conn, args.source, args.presets)
    finally:
        conn.close()
    args.out.write_text(sql, encoding='utf-8', newline='\n')
    print(f'Wrote Kampul SIS template: {len(counts)} preset tables, {sum(counts.values())} starter rows')


if __name__ == '__main__':
    main()
