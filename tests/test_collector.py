import copy
import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from pbv_collector.adapter import Stop
from pbv_collector.model import validate, identity, CSV_COLUMNS
from pbv_collector.runner import run, handle_response, check_window
from pbv_collector.store import Store
from pbv_collector.locking import job_lock

ROOT = Path(__file__).resolve().parents[1]

class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = json.loads((ROOT/'config/local.json').read_text())
        self.c['storage'] = {'database':self.tmp.name+'/state.sqlite3','export_directory':self.tmp.name+'/out'}
        self.c['fixture_pages'] = {k:str(ROOT/v) for k,v in self.c['fixture_pages'].items()}
        self.c['limits']['page_interval_seconds'] = 0
        self.c['schedule']['interval_seconds'] = 0

    def rows(self):
        s = Store(self.c['storage']['database']); rows = s.rows(); s.db.close(); return rows

    def test_dom_schema_unicode_dedup_and_csv(self):
        result = run(self.c)
        self.assertEqual(result['state'],'completed')
        self.assertEqual(result['last_run']['saved_records'],3)
        self.assertEqual(result['last_run']['duplicate_records'],1)
        self.assertEqual(result['last_run']['network_requests'],0)
        rows = self.rows()
        self.assertIn('Größe', rows[0]['review_text'])
        self.assertIn('한글 원문 테스트.',rows[0]['review_text'])
        self.assertNotIn('DO NOT COLLECT',rows[0]['review_text'])
        self.assertEqual(rows[1]['posted_at'],'')
        self.assertEqual(rows[1]['data_type'],'unclassified')
        self.assertEqual(rows[1]['parent_post_id'],'100')
        self.assertEqual(rows[0]['translated_text'],'')
        with open(self.tmp.name+'/out/reviews.csv',encoding='utf-8-sig',newline='') as f:
            reader = csv.DictReader(f)
            with (ROOT/'tests/fixtures/reviews.header.csv').open(encoding='utf-8',newline='') as header:
                expected=next(csv.reader(header))
            self.assertEqual(reader.fieldnames,expected)
            self.assertEqual(next(reader)['review_text'],rows[0]['review_text'])
        self.assertTrue(Path(self.tmp.name+'/out/reviews.csv').read_bytes().startswith(b'\xef\xbb\xbf'))
        repeated = run(self.c,True)
        self.assertEqual(repeated['last_run']['saved_records'],0)
        self.assertEqual(len(self.rows()),3)

    def test_midpage_resume_no_loss(self):
        self.c['limits']['max_records']=1
        self.assertEqual(run(self.c)['state'],'paused')
        self.assertEqual(len(self.rows()),1)
        self.c['limits']['max_records']=10
        result=run(self.c)
        self.assertEqual(result['state'],'completed')
        self.assertEqual(len(self.rows()),3)
        self.assertEqual(len({identity(r) for r in self.rows()}),3)

    def test_page_budget_resume(self):
        self.c['limits']['max_pages']=1
        result=run(self.c)
        self.assertEqual(result['state'],'paused')
        self.assertEqual(result['last_run']['page_accesses'],1)
        self.assertEqual(len(self.rows()),2)
        self.assertEqual(run(self.c)['state'],'completed')
        self.assertEqual(len(self.rows()),3)

    def test_barrier_and_changed_layout(self):
        for fixture in ['blocked.html','changed.html']:
            with self.subTest(fixture=fixture):
                c=copy.deepcopy(self.c); c['job_id']=fixture
                c['fixture_pages'][c['seed_urls'][0]]=str(ROOT/'tests/fixtures'/fixture)
                result=run(c)
                self.assertEqual(result['state'],'needs_review')
                self.assertEqual(result['last_run']['saved_records'],0)

    def test_live_policy_blocks_without_requests(self):
        c=copy.deepcopy(self.c); c['mode']='live'; c['policy']={}
        result=run(c)
        self.assertEqual(result['state'],'needs_review')
        self.assertEqual(result['last_run']['network_requests'],0)

    def test_required_fields_and_distinct_comment_ids(self):
        run(self.c); row=self.rows()[0]
        for field in ['source_name','source_url','review_text','collected_at']:
            bad=dict(row); bad[field]=''
            with self.assertRaises(ValueError):validate(bad)
        a=dict(row,external_comment_id='1'); b=dict(row,external_comment_id='2')
        self.assertNotEqual(identity(a),identity(b))
        bad=dict(row,review_text='broken\ufffd')
        with self.assertRaises(ValueError):validate(bad)

    def test_http_states_retry_after(self):
        for status,state in [(403,'needs_review'),(401,'needs_review'),(429,'paused')]:
            with self.assertRaises(Stop) as raised:handle_response(status,{'retry-after':'7200'})
            self.assertEqual(raised.exception.state,state)
            if status==429:self.assertEqual(raised.exception.retry_after,7200)
        with self.assertRaises(Stop) as raised:
            handle_response(429,{'retry-after':'Wed, 07 Oct 2099 09:49:00 GMT'})
        self.assertGreater(raised.exception.retry_after,3600)
        with self.assertRaises(OSError):handle_response(503,{})

    def test_daily_budget_and_window(self):
        self.c['limits']['daily_records']=1
        result=run(self.c)
        self.assertEqual(result['state'],'paused')
        self.assertEqual(len(self.rows()),1)
        self.assertTrue(result['next_allowed_at'])
        s={'timezone':'Europe/Zurich','start':'22:00','end':'06:00'}
        self.assertTrue(check_window(s,datetime(2026,1,1,22,tzinfo=timezone.utc)))
        self.assertFalse(check_window(s,datetime(2026,1,1,12,tzinfo=timezone.utc)))

    def test_completed_cycle_cooldown_and_lock(self):
        self.c['schedule']['interval_seconds']=1800
        self.assertEqual(run(self.c)['state'],'completed')
        result=run(self.c,True)
        self.assertEqual(result['state'],'paused')
        self.assertEqual(result['last_run']['page_accesses'],0)
        with job_lock(self.c['storage']['database']):
            with self.assertRaises(BlockingIOError):
                with job_lock(self.c['storage']['database']):pass

    def test_time_limit_pauses_and_changed_search_rejected(self):
        self.c['limits']['max_seconds']=0.00001
        result=run(self.c)
        self.assertEqual(result['state'],'paused')
        self.assertEqual(result['last_run']['saved_records'],0)
        self.c['search']['keywords']=['different']
        with self.assertRaises(ValueError):run(self.c)

if __name__=='__main__':unittest.main()
