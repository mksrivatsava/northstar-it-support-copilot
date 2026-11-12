"""Offline regression fixtures. Scores this fixed suite, not general model quality."""
from datetime import datetime, timezone
import json
from pathlib import Path


def evaluate(workflow, cases_path=None):
    cases_path = cases_path or Path(__file__).resolve().parent.parent / 'evals' / 'cases.json'
    cases = json.loads(cases_path.read_text(encoding='utf-8'))
    rows = []
    for case in cases:
        result = workflow.run(case['question'], case.get('role', 'employee'), persist=False)
        web_case = workflow.settings.web_search_enabled and case.get('web_outcomes')
        expected = case['web_outcomes'] if web_case else [case['outcome']]
        checks = {'outcome': result['outcome'] in expected}
        if web_case:
            checks['web_routing'] = result.get('web_searched', False)
            checks['external_boundary'] = result['outcome'] != 'answered' or (
                result.get('source_used') == 'web' and bool(result['citations']) and
                all(c.get('source_type') == 'web' for c in result['citations']))
        if case.get('source'):
            checks['retrieval'] = any(c.get('filename') == case['source'] for c in result['citations'])
        if case.get('contains'):
            checks['answer_content'] = case['contains'].lower() in result['answer'].lower()
        if case.get('rewrite') and workflow.settings.retrieval_mode == 'sqlite':
            checks['rewrite'] = any(t['node'] == 'rewrite' for t in result['trace'])
        rows.append({'name': case['name'], 'question': case['question'], 'passed': all(checks.values()),
                     'checks': checks, 'outcome': result['outcome'], 'latency_ms': result['latency_ms'],
                     'generation_mode': result['generation_mode'], 'warnings': result['warnings']})
    latencies = sorted(r['latency_ms'] for r in rows)
    return {'created_at': datetime.now(timezone.utc).isoformat(), 'mode': workflow.settings.answer_mode,
            'retrieval_mode': workflow.settings.retrieval_mode,
            'web_search_enabled': workflow.settings.web_search_enabled,
            'total': len(rows), 'passed': sum(r['passed'] for r in rows),
            'pass_rate': round(sum(r['passed'] for r in rows) / len(rows), 3),
            'p95_latency_ms': latencies[min(len(latencies) - 1, int(len(latencies) * .95))], 'cases': rows,
            'scope': 'Fixed synthetic retrieval, routing, and source-boundary checks; not a claim of production accuracy or live outage verification.'}
