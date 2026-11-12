"""Privacy-preserving vendor search. No raw user query or private evidence leaves
the application for Tavily: only fixed product/topic templates are submitted.
"""
from datetime import datetime, timezone
import math
import re
from urllib.parse import urlsplit

from app.cloud import ProviderError, request_json

PRODUCTS = [
    (r'\b(?:microsoft\s+)?teams\b', 'Microsoft Teams', ['support.microsoft.com', 'learn.microsoft.com', 'status.cloud.microsoft']),
    (r'\boutlook\b', 'Microsoft Outlook', ['support.microsoft.com', 'learn.microsoft.com', 'status.cloud.microsoft']),
    (r'\b(?:microsoft|office)\s*365\b', 'Microsoft 365', ['support.microsoft.com', 'learn.microsoft.com', 'status.cloud.microsoft']),
    (r'\bwindows\b', 'Microsoft Windows', ['support.microsoft.com', 'learn.microsoft.com']),
    (r'\bzoom\b', 'Zoom', ['support.zoom.com', 'status.zoom.us']),
    (r'\bslack\b', 'Slack', ['slack.com', 'slack-status.com']),
    (r'\bokta\b', 'Okta', ['help.okta.com', 'status.okta.com']),
]
FRESH = r'\b(latest|current|today|right now|live|newest|recent|outage|service status)\b'
PRIVATE = r'\b(company|corporate|internal|northstar|our|policy|policies|payroll|salary|leave|password|mfa|2fa|secret|token|credentials|vpn|break[ -]?glass|priority|sla|retention|approval|approvals|onboarding|offboarding|administrator)\b'


def public_search_plan(question):
    if re.search(PRIVATE, question, re.I):
        return None
    for pattern, product, domains in PRODUCTS:
        if not re.search(pattern, question, re.I):
            continue
        q = question.lower()
        if re.search(r'\b(outage|down|status|availability|incident)\b', q):
            topic = 'service status outage official guidance'
        elif re.search(r'\b(microphone|mic|audio|headset|speaker)\b', q):
            topic = 'microphone audio troubleshooting official support'
        elif re.search(r'\b(update|updates|release|version|features)\b', q):
            topic = 'release notes latest updates official documentation'
        elif re.search(r'\b(install|installation|download)\b', q):
            topic = 'installation requirements official support documentation'
        else:
            topic = 'troubleshooting official support documentation'
        return {'query': f'{product} {topic}', 'domains': domains,
                'fresh': bool(re.search(FRESH, question, re.I)) or topic == 'service status outage official guidance'}
    return None


def approved_url(url, domains):
    if not isinstance(url, str) or len(url) > 2048:
        return False
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in {None, 443}:
            return False
        if not any(host == domain or host.endswith('.' + domain) for domain in domains):
            return False
        # Official domains also host user-written Q&A. Exclude that material.
        if host.endswith('learn.microsoft.com') and '/answers/' in parsed.path.lower():
            return False
        return True
    except ValueError:
        return False


class TavilySearch:
    def __init__(self, settings):
        self.settings = settings

    def search(self, plan):
        s = self.settings
        if not s.web_search_enabled or not s.tavily_api_key:
            raise ProviderError('Web search is not configured.', provider='Tavily', code='not_configured')
        data = request_json('Tavily', 'POST', s.tavily_url + '/search',
            {'Authorization': 'Bearer ' + s.tavily_api_key}, s.web_request_timeout,
            {'query': plan['query'], 'topic': 'general', 'search_depth': 'basic', 'max_results': 5,
             'include_domains': plan['domains'], 'include_answer': False, 'include_raw_content': False,
             'include_images': False, 'include_usage': True, 'include_published_date': True},
            max_attempts=2, total_timeout=s.web_total_timeout, retry_timeouts=True, retry_server_errors=True)
        if not isinstance(data.get('results'), list):
            raise ProviderError('Tavily returned invalid search results.', provider='Tavily')
        retrieved_at = datetime.now(timezone.utc).isoformat()
        sources, seen = [], set()
        for item in data['results'][:10]:
            if not isinstance(item, dict):
                continue
            url, content, title = item.get('url'), item.get('content'), item.get('title')
            score = item.get('score')
            if not approved_url(url, plan['domains']) or url in seen or not isinstance(content, str) or not content.strip():
                continue
            if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score) or score < .45:
                continue
            title = title[:200] if isinstance(title, str) and title.strip() else urlsplit(url).hostname
            published = item.get('published_date')
            sources.append({'source_type': 'web', 'heading': title, 'title': title, 'url': url,
                'content': content.strip()[:2200], 'published_at': published[:100] if isinstance(published, str) else None,
                'retrieved_at': retrieved_at, 'search_score': round(score, 4)})
            seen.add(url)
            if len(sources) == 3:
                break
        return sources
