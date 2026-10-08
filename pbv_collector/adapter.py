from datetime import datetime
from urllib.parse import urljoin
from typing import Protocol
from .model import FIELDS, now, validate

class Stop(Exception):
    def __init__(self, state, reason, retry_after=0):
        self.state, self.reason, self.retry_after = state, reason, retry_after
        super().__init__(reason)

class SiteAdapter(Protocol):
    def extract(self, page, source_url: str) -> tuple[list[dict], list[str]]:
        """Return displayed records and permitted next-page URLs."""
        ...

class DOMAdapter:
    """CSS rules are site-specific; only visible DOM text is extracted."""
    def __init__(self, config):
        self.config = config
        self.rules = config['selectors']

    def extract(self, page, source_url):
        for selector in self.rules.get('access_barriers', []):
            if page.locator(selector).filter(visible=True).count():
                raise Stop('needs_review', 'Login, CAPTCHA or access barrier detected')
        if not page.locator(self.rules['ready']).filter(visible=True).count():
            raise Stop('needs_review', 'Expected page structure missing')
        posts = page.locator(self.rules['record']).filter(visible=True)
        if not posts.count() and not (self.rules.get('empty') and page.locator(self.rules['empty']).filter(visible=True).count()):
            raise Stop('needs_review', 'No records and no explicit empty-result marker')
        rows = []
        for item in posts.all():
            def text(key):
                selector = self.rules.get(key)
                if not selector:
                    return ''
                nodes = item.locator(selector).filter(visible=True)
                return nodes.first.inner_text() if nodes.count() else ''
            def attr(key, name):
                selector = self.rules.get(key)
                if not selector:
                    return ''
                nodes = item.locator(selector).filter(visible=True)
                return (nodes.first.get_attribute(name) or '') if nodes.count() else ''
            row = dict.fromkeys(FIELDS, '')
            permalink = attr('permalink', 'href')
            row.update(source_name=self.config['source_name'], source_url=urljoin(source_url, permalink) if permalink else '',
                       external_post_id=item.get_attribute('data-post-id') or '',
                       external_comment_id=item.get_attribute('data-comment-id') or '',
                       parent_post_id=item.get_attribute('data-parent-post-id') or '',
                       parent_comment_id=item.get_attribute('data-parent-comment-id') or '',
                       title=text('title'), review_text=text('body'), author_id=text('author'),
                       collected_at=now(), rating_or_reactions=text('reactions'),
                       collection_status='needs_review', data_type='unclassified')
            # No inferred dates, language, ownership or author nationality.
            date_raw = text('time')
            date_value = attr('time', 'datetime')
            if date_value:
                try:
                    d = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                    if d.tzinfo:
                        row['posted_at'] = d.isoformat()
                except ValueError:
                    pass
            language = item.get_attribute('lang') or ''
            row['language'] = language
            evidence = self.config.get('market_evidence','')
            if evidence:
                row.update(target_market_code='CH', market_evidence=evidence)
            matches = [v for v in self.config.get('vehicles', []) if v.casefold() in row['review_text'].casefold()]
            if matches:
                row.update(target_vehicle='; '.join(matches), vehicle_match_evidence='Literal body mentions: ' + '; '.join(matches))
            row['raw_payload'] = {'page_url': source_url, 'posted_at_raw': date_raw,
                                  'synthetic': self.config['mode'] == 'fixture',
                                  'market_scope': 'community scope only; author country unknown'}
            try:
                validate(row)
            except ValueError as exc:
                raise Stop('needs_review', str(exc)) from exc
            rows.append(row)
        links = []
        if self.rules.get('next'):
            for node in page.locator(self.rules['next']).filter(visible=True).all():
                href = node.get_attribute('href')
                if href:
                    links.append(urljoin(source_url, href))
        return rows, links
