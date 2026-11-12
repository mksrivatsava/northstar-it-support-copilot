"""A small live-cloud acceptance run; stores sanitized results, never keys."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.main import create_app

CASES = [
    ('VPN supported answer', 'How do I connect to the company VPN from home?', 'employee', 'answered'),
    ('Semantic paraphrase', 'I am away from the office and need secure access to our internal apps. What steps should I follow?', 'employee', 'answered'),
    ('Unknown HR policy', 'What is the parental leave allowance?', 'employee', 'abstained'),
    ('Restricted employee boundary', 'break glass account review', 'employee', 'abstained'),
    ('Authorized administrator answer', 'break glass account review', 'it_admin', 'answered'),
]

if __name__ == '__main__':
    app = create_app()
    if app.state.settings.retrieval_mode != 'pinecone' or app.state.settings.answer_mode != 'gemini':
        sys.exit('This check requires Pinecone retrieval and Gemini answer mode.')
    results = []
    for name, question, role, outcome in CASES:
        result = app.state.workflow.run(question, role=role, persist=False)
        passed = result['outcome'] == outcome
        if outcome == 'answered':
            passed = passed and result['generation_mode'] == 'gemini' and bool(result['citations'])
        results.append({'name': name, 'passed': bool(passed), 'result': result})
        scores = [c.get('similarity') for c in result['citations']]
        print(f"{'PASS' if passed else 'FAIL'} {name}: {result['outcome']}; {result['generation_mode']}; cosine={scores}; {result['latency_ms']} ms", flush=True)
        if result['warnings']:
            print('  warnings:', ' | '.join(result['warnings']), flush=True)
    path = Path(__file__).resolve().parent.parent / '.runtime' / 'cloud-smoke.json'
    path.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(f'Sanitized report: {path}')
    sys.exit(0 if all(r['passed'] for r in results) else 1)
