"""One small public search to verify Tavily; never prints credentials or errors bodies."""
from pathlib import Path
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import httpx
from app.config import load_env

if __name__=='__main__':
    load_env()
    key=os.getenv('TAVILY_API_KEY','')
    if not key:sys.exit('TAVILY_API_KEY is not configured.')
    try:
        with httpx.Client(timeout=25,trust_env=False) as client:
            response=client.post('https://api.tavily.com/search',headers={'Authorization':'Bearer '+key},json={
                'query':'Microsoft Teams microphone troubleshooting official support',
                'search_depth':'basic','max_results':3,'include_domains':['support.microsoft.com','learn.microsoft.com'],
                'include_answer':False,'include_raw_content':False})
        print('Tavily HTTP',response.status_code)
        if response.is_success:
            data=response.json()
            print('Results:',len(data.get('results',[])))
            for item in data.get('results',[])[:3]:print(item.get('title'),item.get('url'))
        sys.exit(0 if response.is_success else 1)
    except (httpx.HTTPError,ValueError):
        sys.exit('Tavily connection or response failed. Credentials and response details suppressed.')
