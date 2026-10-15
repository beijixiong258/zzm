"""Browse saved real Stage15 results only. No new inference is permitted here."""
from pathlib import Path
import argparse,os,sys
APP=Path(__file__).resolve().parents[2];sys.path.insert(0,str(APP))
p=argparse.ArgumentParser();p.add_argument('--qa',required=True);p.add_argument('--port',type=int,default=18775);a=p.parse_args();qa=Path(a.qa).resolve()
os.environ.update(AICADEMIYA_DATA_DIR=str(qa/'browser-import-data'),AICADEMIYA_AI_MODE='openai',AICADEMIYA_AI_BASE_URL='',AICADEMIYA_AI_MODEL='',AICADEMIYA_WEB_SEARCH_ENABLED='false')
import httpx,uvicorn
from backend.aicademiya.main import create_app
class NoInference(httpx.BaseTransport):
 def handle_request(self,request):raise httpx.ConnectError('Read-only visual QA: inference disabled',request=request)
app=create_app(data_dir=qa/'data',catalog_path=qa/'fixture/catalog.json',frontend_dir=APP/'frontend/dist',demo_enabled=True,ai_transport=NoInference())
uvicorn.run(app,host='127.0.0.1',port=a.port,log_level='warning')
