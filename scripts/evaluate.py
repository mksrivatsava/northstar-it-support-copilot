import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.main import create_app
from app.evaluation import evaluate

if __name__ == '__main__':
    app = create_app()
    report = evaluate(app.state.workflow)
    app.state.store.save_evaluation(report)
    output = Path(__file__).resolve().parent.parent / '.runtime' / 'evaluation.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    for case in report['cases']:
        print(f"{'PASS' if case['passed'] else 'FAIL'}  {case['name']}: {case['checks']}")
    print(f"\n{report['passed']}/{report['total']} passed; p95 {report['p95_latency_ms']} ms. Report: {output}")
    sys.exit(0 if report['passed'] == report['total'] else 1)
