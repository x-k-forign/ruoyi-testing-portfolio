# T6.3 diagnostic helper, Python standard library only; not a testing framework.
import sys,json,hashlib,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime
cfg=json.loads(Path(sys.argv[1]).read_text('utf-8'))
expected=Path(sys.argv[2]).read_bytes()
path=sys.argv[3] if len(sys.argv)>3 else cfg['path']
url=f"http://{cfg['host']}:{cfg['port']}{path}"
r={'at':datetime.now().astimezone().isoformat(),'method':'GET','url':url,'http_status':None,'proxy_used':False}
try:
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url,timeout=3) as response:
        body=response.read();r.update(http_status=response.status,body_sha256=hashlib.sha256(body).hexdigest(),body_utf8=body.decode('utf-8'),exact_expected_body=body==expected)
    code=0 if r['http_status']==200 and r['exact_expected_body'] else 11
except urllib.error.HTTPError as exc:
    r.update(http_status=exc.code,error_type='HTTPError',error=str(exc));code=11
except urllib.error.URLError as exc:
    reason=exc.reason;r.update(error_type=type(reason).__name__,os_errno=getattr(reason,'errno',None),error=str(reason));code=10
r['probe_exit_code']=code
print(json.dumps(r,ensure_ascii=False));sys.exit(code)
