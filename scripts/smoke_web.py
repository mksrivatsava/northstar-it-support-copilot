"""Small live Tavily/Gemini acceptance check using only synthetic questions."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.main import create_app

if __name__=='__main__':
    app=create_app()
    if not app.state.settings.web_search_enabled:sys.exit('Enable WEB_SEARCH_ENABLED first.')
    cases=[('Public vendor guidance','What is the latest official Microsoft Teams microphone troubleshooting guidance?'),
           ('Private policy boundary','What is the latest company Teams MFA policy?')]
    records=[]
    for name,question in cases:
        result=app.state.workflow.run(question,persist=False)
        if name=='Public vendor guidance':
            passed=result['outcome']=='answered' and result['generation_mode']=='gemini' and result['source_used']=='web' and bool(result['citations'])
        else:
            passed=not result['web_searched'] and result['source_used']=='none' and result['outcome']=='abstained'
        print(f"{'PASS' if passed else 'FAIL'} {name}: {result['outcome']}, source={result['source_used']}, searched={result['web_searched']}, {result['latency_ms']} ms",flush=True)
        for source in result['citations']:
            if source.get('source_type')=='web':print('  external source:',source['url'],flush=True)
        if result['outcome']=='error':print('  error:',result['failure'],flush=True)
        records.append({'name':name,'passed':bool(passed),'result':result})
    path=Path(__file__).resolve().parent.parent/'.runtime'/'web-smoke.json'
    path.write_text(json.dumps(records,indent=2),encoding='utf8')
    print('Report:',path)
    sys.exit(0 if all(r['passed'] for r in records) else 1)
