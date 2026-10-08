import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

CSV_COLUMNS = 'source_name board_id board_name thread_id thread_title thread_url post_kind external_review_id parent_review_id url title review_text published_at published_at_raw published_year collected_at language_code thread_vehicle_name thread_vehicle_assignment_basis body_mentioned_vehicle_name rating rating_scale license_code license_url mapping_status raw_payload'.split()
FIELDS = 'source_name source_url external_post_id external_comment_id parent_post_id parent_comment_id title review_text author_id posted_at collected_at target_vehicle vehicle_match_evidence language target_market_code market_evidence rating_or_reactions collection_status data_type translated_text summary analysis raw_payload'.split()

def now():
    return datetime.now(timezone.utc).isoformat()

def normalize_url(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', p.query, p.fragment))

def validate(row):
    for field in ('source_name', 'source_url', 'review_text', 'collected_at'):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError('Missing required field: ' + field)
    if urlsplit(row['source_url']).scheme != 'https':
        raise ValueError('Expected HTTPS provenance URL')
    if '\ufffd' in row['review_text']:
        raise ValueError('Unicode replacement character: encoding requires review')
    if row.get('target_vehicle') and not row.get('vehicle_match_evidence'):
        raise ValueError('Vehicle evidence required')
    if row.get('target_market_code') and not row.get('market_evidence'):
        raise ValueError('Market evidence required')
    return row

def identity(row):
    # A thread ID alone is insufficient for distinct comments.
    kind = 'comment' if row.get('external_comment_id') else 'post'
    key = row.get('external_comment_id') or row.get('external_post_id') or normalize_url(row['source_url'])
    return hashlib.sha256(json.dumps([row['source_name'], kind, key], ensure_ascii=False).encode()).hexdigest()

def legacy(row):
    raw = row.get('raw_payload', {})
    result = dict.fromkeys(CSV_COLUMNS, '')
    result.update(source_name=row['source_name'], thread_id=row.get('parent_post_id') or row.get('external_post_id',''),
                  thread_title=row['title'], thread_url=raw.get('page_url',''),
                  post_kind='reply' if row.get('external_comment_id') else 'original',
                  external_review_id=row.get('external_comment_id') or row.get('external_post_id',''),
                  parent_review_id=row.get('parent_comment_id') or row.get('parent_post_id',''),
                  url=row['source_url'], title=row['title'], review_text=row['review_text'],
                  published_at=row.get('posted_at',''), published_at_raw=raw.get('posted_at_raw',''),
                  collected_at=row['collected_at'], language_code=row.get('language',''),
                  body_mentioned_vehicle_name=row.get('target_vehicle',''),
                  mapping_status=row['collection_status'], raw_payload=json.dumps(row, ensure_ascii=False))
    if row.get('posted_at'):
        result['published_year'] = row['posted_at'][:4]
    return result
