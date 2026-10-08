import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo
from .adapter import DOMAdapter, Stop
from .model import now, normalize_url
from .store import Store

def signature(config):
    return hashlib.sha256(json.dumps({k:v for k,v in config.items() if k not in ('limits','storage','schedule')},sort_keys=True).encode()).hexdigest()

def check_window(schedule, instant):
    local = instant.astimezone(ZoneInfo(schedule['timezone']))
    start, end = schedule['start'], schedule['end']
    clock = local.strftime('%H:%M')
    return start == end or (start <= clock < end if start < end else clock >= start or clock < end)

def policy_gate(config):
    if config['mode'] == 'fixture':
        return
    policy = config.get('policy',{})
    if not all(policy.get(k) for k in ('automation_allowed','terms_url','reviewed_at','review_note','selectors_verified')):
        raise Stop('needs_review','Policy permission and live selectors require documented human review')
    if not config.get('market_evidence'):
        raise Stop('needs_review','Swiss community classification requires evidence')
    if not config.get('allowed_path_prefixes'):
        raise Stop('needs_review','Approved public path scope requires review')

def run(config, new_cycle=False):
    cache = Path(__file__).resolve().parent.parent / '.browser-cache'
    if cache.exists():
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(cache))
    from playwright.sync_api import sync_playwright, Error as BrowserError
    storage = config['storage']; store = Store(storage['database'])
    job = store.load(config['job_id'])
    fresh = dict(job_id=config['job_id'], signature=signature(config), state='queued',
                 search_conditions=config.get('search',{}), queue=list(config['seed_urls']),
                 processed_urls=[], last_cursor='', total_saved=0, error='', failures=0,
                 next_allowed_at='', created_at=now())
    if job is None:
        job = fresh
    elif job['signature'] != fresh['signature']:
        raise ValueError('Search/site configuration changed; use a new job_id')
    if new_cycle and job['state'] == 'completed':
        fresh['total_saved'] = job['total_saved']
        fresh['next_allowed_at'] = job['next_allowed_at']
        job = fresh
    stats = dict(search_candidates=0, pages_checked=0, page_accesses=0, network_requests=0,
                 saved_records=0, duplicate_records=0, review_pending=0, filtered_records=0)
    job['last_run'] = stats
    limits = config['limits']
    for k in ('max_records','max_pages','max_seconds','daily_records'):
        if limits[k] <= 0:
            raise ValueError(k + ' must be positive')
    start = time.monotonic()
    instant = datetime.now(timezone.utc)
    day = instant.astimezone(ZoneInfo(config['schedule']['timezone'])).date().isoformat()
    def pause(reason, seconds=0):
        raise Stop('paused', reason, seconds)
    def budget():
        if time.monotonic()-start >= limits['max_seconds']:
            pause('Run time limit reached')
        if stats['saved_records'] >= limits['max_records']:
            pause('Record limit reached')
        if store.daily(day) >= limits['daily_records']:
            # Next midnight in the configured timezone (including DST).
            zone = ZoneInfo(config['schedule']['timezone'])
            local = datetime.now(zone)
            midnight = datetime.combine(local.date()+timedelta(days=1),datetime.min.time(),zone)
            pause('Daily record limit reached', (midnight-datetime.now(zone)).total_seconds())
    def accept_url(url):
        p = urlsplit(url)
        if p.scheme != 'https' or p.hostname != config['host'] or p.username or p.password or p.port not in (None,443):
            raise Stop('needs_review','URL outside approved HTTPS host')
        prefixes=config.get('allowed_path_prefixes',[])
        if config['mode']=='live' and not any(p.path == prefix.rstrip('/') or p.path.startswith(prefix.rstrip('/')+'/') for prefix in prefixes):
            raise Stop('needs_review','URL outside approved public path scope')
    try:
        policy_gate(config)
        if job['next_allowed_at'] and datetime.fromisoformat(job['next_allowed_at']) > instant:
            pause('Waiting for next allowed run', (datetime.fromisoformat(job['next_allowed_at'])-instant).total_seconds())
        if not check_window(config['schedule'], instant):
            pause('Outside execution window', config['schedule']['interval_seconds'])
        budget()
        job.update(state='running',error=''); store.save(job)
        with sync_playwright() as pw:
            budget()
            executable = os.environ.get('PBV_BROWSER_EXECUTABLE') or shutil.which('chromium') or shutil.which('google-chrome')
            browser = pw.chromium.launch(headless=True, executable_path=executable,
                timeout=max(1,min(30000,int((limits['max_seconds']-(time.monotonic()-start))*1000))))
            budget()
            context = browser.new_context(user_agent=config['user_agent'], service_workers='block')
            deadline_error = []
            robots = None
            def route_handler(route):
                request = route.request
                if request.resource_type != 'document':
                    route.abort(); return
                try:
                    budget(); accept_url(request.url)
                    if robots and not robots.can_fetch(config['user_agent'],request.url):
                        raise Stop('needs_review','robots.txt disallows navigation or redirect')
                    if stats['page_accesses'] >= limits['max_pages']:
                        pause('Page access limit reached')
                    stats['page_accesses'] += 1; stats['network_requests'] += 1
                    route.continue_()
                except Stop as exc:
                    deadline_error.append(exc); route.abort()
            # Fixture files are local only; rendered by the same browser/parser.
            if config['mode'] != 'fixture':
                context.route('**/*',route_handler)
                robots_url = 'https://' + config['host'] + '/robots.txt'
                if stats['page_accesses'] >= limits['max_pages']:
                    pause('Page access limit reached')
                stats['page_accesses'] += 1; stats['network_requests'] += 1
                budget()
                response = context.request.get(robots_url, timeout=max(1,min(30000,int((limits['max_seconds']-(time.monotonic()-start))*1000))),max_redirects=0)
                handle_response(response.status, response.headers)
                if response.status != 200:
                    raise Stop('needs_review','robots.txt unavailable; manual review required')
                robots = RobotFileParser(); robots.parse(response.text().splitlines())
                crawl_delay = robots.crawl_delay(config['user_agent']) or robots.crawl_delay('*') or 0
            else:
                robots = None; crawl_delay = 0
                context.route('**/*',lambda route: route.continue_() if route.request.url.startswith('file:') else route.abort())
            page = context.new_page(); adapter = DOMAdapter(config)
            page.set_default_timeout(min(5000,limits['max_seconds']*1000))
            while job['queue']:
                budget()
                source_url = job['queue'][0]; accept_url(source_url)
                job['last_cursor'] = source_url; store.save(job)
                if robots and not robots.can_fetch(config['user_agent'],source_url):
                    raise Stop('needs_review','robots.txt disallows this page')
                if config['mode'] == 'fixture':
                    if stats['page_accesses'] >= limits['max_pages']:
                        pause('Page access limit reached')
                    stats['page_accesses'] += 1
                    sample = config['fixture_pages'].get(source_url)
                    if not sample:
                        raise Stop('needs_review','Fixture page not mapped')
                    page.set_content(Path(sample).read_text(encoding='utf-8'),wait_until='domcontentloaded')
                else:
                    try:
                        response = page.goto(source_url,wait_until='domcontentloaded',timeout=max(1,min(30000,int((limits['max_seconds']-(time.monotonic()-start))*1000))))
                    except BrowserError:
                        if deadline_error:
                            raise deadline_error[0]
                        raise
                    if deadline_error:
                        raise deadline_error[0]
                    if response is None:
                        raise Stop('needs_review','No navigation response')
                    handle_response(response.status,response.headers)
                    accept_url(page.url)
                    source_url = page.url
                stats['pages_checked'] += 1
                rows, links = adapter.extract(page,source_url)
                stats['search_candidates'] += len(rows)
                for row in rows:
                    budget()
                    accept_url(row['source_url'])
                    if store.contains(row):
                        stats['duplicate_records'] += 1; continue
                    search = config.get('search',{})
                    if search.get('keywords') and not any(k.casefold() in (row['title']+' '+row['review_text']).casefold() for k in search['keywords']):
                        stats['filtered_records'] += 1; continue
                    date = row['posted_at'][:10]
                    if date and ((search.get('from') and date < search['from']) or (search.get('to') and date > search['to'])):
                        stats['filtered_records'] += 1; continue
                    # Unknown dates are retained for review, never assigned a year.
                    if store.add(row,day):
                        stats['saved_records'] += 1; stats['review_pending'] += 1
                        job['total_saved'] += 1
                        store.save(job)
                job['processed_urls'].append(normalize_url(job['queue'].pop(0)))
                for url in links:
                    accept_url(url)
                    if normalize_url(url) not in job['processed_urls'] and url not in job['queue']:
                        job['queue'].append(url)
                store.save(job)
                if job['queue']:
                    delay = max(limits['page_interval_seconds'],crawl_delay)
                    if time.monotonic()-start+delay >= limits['max_seconds']:
                        pause('Insufficient time for next page')
                    time.sleep(delay)
            job.update(state='completed',error='',failures=0,
                       next_allowed_at=(datetime.now(timezone.utc)+timedelta(seconds=config['schedule']['interval_seconds'])).isoformat())
            browser.close()
    except Stop as exc:
        if exc.reason.startswith('HTTP 429'):
            job['failures'] += 1
            if job['failures'] > limits['retry_count']:
                exc.state = 'failed'
        job.update(state=exc.state,error=exc.reason,
                   next_allowed_at=(datetime.now(timezone.utc)+timedelta(seconds=max(exc.retry_after,config['schedule']['interval_seconds']))).isoformat())
    except KeyboardInterrupt:
        job.update(state='paused',error='Interrupted by operator',next_allowed_at='')
    except (BrowserError,OSError) as exc:
        job['failures'] += 1
        job.update(state='failed' if job['failures'] > limits['retry_count'] else 'paused',
                   error=type(exc).__name__ + ': ' + str(exc)[:300],
                   next_allowed_at=(datetime.now(timezone.utc)+timedelta(seconds=max(limits['retry_wait_seconds'],config['schedule']['interval_seconds']))).isoformat())
    finally:
        job['updated_at'] = now()
        # Reconcile commits if a process exited after a record commit but before job.save.
        job['total_saved'] = len(store.rows())
        store.save(job); store.export(storage['export_directory'],storage.get('legacy_columns'),storage.get('common_columns')); store.db.close()
    return job

def handle_response(status, headers):
    if status == 429:
        value = headers.get('retry-after','')
        try:
            wait = max(0,float(value))
        except ValueError:
            from email.utils import parsedate_to_datetime
            try:
                wait = max(0,(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
            except (ValueError,TypeError):
                wait = 3600
        raise Stop('paused','HTTP 429 rate limited',wait)
    if status in (401,403):
        raise Stop('needs_review','HTTP access denied: '+str(status))
    if status >= 500:
        raise OSError('HTTP server error: '+str(status))
    if status >= 300:
        raise Stop('needs_review','Unexpected HTTP response: '+str(status))
