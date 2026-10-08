import csv
import json
import sqlite3
from pathlib import Path
from .model import CSV_COLUMNS, FIELDS, identity, legacy, validate

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, day TEXT, payload TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT)')
        self.db.commit()

    def load(self, job_id):
        r = self.db.execute('SELECT payload FROM jobs WHERE id=?', (job_id,)).fetchone()
        return json.loads(r[0]) if r else None

    def save(self, job):
        self.db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?)', (job['job_id'], json.dumps(job,ensure_ascii=False)))
        self.db.commit()

    def add(self, row, day):
        validate(row)
        c = self.db.execute('INSERT OR IGNORE INTO records VALUES (?,?,?)', (identity(row), day, json.dumps(row,ensure_ascii=False)))
        self.db.commit()
        return bool(c.rowcount)

    def contains(self, row):
        return bool(self.db.execute('SELECT 1 FROM records WHERE key=?',(identity(row),)).fetchone())

    def daily(self, day):
        return self.db.execute('SELECT COUNT(*) FROM records WHERE day=?',(day,)).fetchone()[0]

    def rows(self):
        return [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM records ORDER BY rowid')]

    def export(self, directory, legacy_columns=None, common_columns=None):
        p = Path(directory); p.mkdir(parents=True, exist_ok=True)
        rows = self.rows()
        # BOM enables Excel to recognize UTF-8; JSONL preserves the common schema.
        for filename, fields, values in [('reviews.csv',legacy_columns or CSV_COLUMNS,map(legacy,rows)), ('common.csv',common_columns or FIELDS,iter(rows))]:
            allowed = CSV_COLUMNS if filename == 'reviews.csv' else FIELDS
            if len(set(fields)) != len(fields) or any(k not in allowed for k in fields):
                raise ValueError('Invalid export columns')
            tmp = p / (filename + '.tmp')
            with tmp.open('w',encoding='utf-8-sig',newline='') as f:
                writer = csv.DictWriter(f,fieldnames=fields); writer.writeheader()
                for row in values:
                    writer.writerow({k:json.dumps(row[k],ensure_ascii=False) if isinstance(row[k],(dict,list)) else row[k] for k in fields})
            tmp.replace(p / filename)
        tmp = p / 'reviews.jsonl.tmp'
        with tmp.open('w',encoding='utf-8',newline='') as f:
            for row in rows:
                f.write(json.dumps(row,ensure_ascii=False)+'\n')
        tmp.replace(p / 'reviews.jsonl')
