"""Read-only handoff checks; credentials stay in memory and are never reported."""
from pathlib import Path
import datetime, json, os, re, subprocess, urllib.request
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
now = lambda: datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
report = {'checked_at': now(), 'operator': 'AI', 'purpose': 'T3接手核查，不是功能用例执行'}
# Read only scalar fields needed for this check, never serialize configuration.
cfg = {}; stack = []
for line in (ROOT/'sources/backend/.local/application-local.yml').read_text(encoding='utf-8-sig').splitlines():
    m = re.match(r'^(\s*)([\w-]+):\s*(.*?)\s*$', line)
    if not m: continue
    indent, key, value = len(m[1]), m[2], m[3]
    while stack and stack[-1][0] >= indent: stack.pop()
    path = '.'.join([x[1] for x in stack]+[key])
    if value: cfg[path] = value.strip('\"\'')
    else: stack.append((indent,key))
url = cfg.get('spring.datasource.druid.master.url', '')
m = re.match(r'jdbc:mysql://([^:/]+):(\d+)/([^?]+)', url)
if not m or (m[1],m[2],m[3]) != ('127.0.0.1','3306','ruoyi_t2_lab'):
    raise SystemExit('Unexpected database target; no connection attempted')
report['configured_target'] = {'mysql_host':m[1], 'mysql_port':int(m[2]), 'database':m[3], 'redis_host':cfg.get('spring.data.redis.host'), 'redis_port':cfg.get('spring.data.redis.port'), 'redis_database':cfg.get('spring.data.redis.database')}
queries = {
 'instance': 'SELECT DATABASE() AS db, VERSION() AS version, @@port AS port;',
 'users': "SELECT u.user_id,u.user_name,u.dept_id,u.status,u.del_flag,GROUP_CONCAT(ur.role_id ORDER BY ur.role_id) AS roles FROM sys_user u LEFT JOIN sys_user_role ur ON ur.user_id=u.user_id WHERE u.user_id IN (1,101,103,104,105,106,107,108,109) GROUP BY u.user_id,u.user_name,u.dept_id,u.status,u.del_flag ORDER BY u.user_id;",
 'roles': "SELECT r.role_id,r.role_key,r.data_scope,r.status,r.del_flag,GROUP_CONCAT(DISTINCT NULLIF(m.perms,'') ORDER BY m.perms) AS perms FROM sys_role r LEFT JOIN sys_role_menu rm ON rm.role_id=r.role_id LEFT JOIN sys_menu m ON m.menu_id=rm.menu_id WHERE r.role_id IN (101,102,103) GROUP BY r.role_id,r.role_key,r.data_scope,r.status,r.del_flag ORDER BY r.role_id;",
 'departments': 'SELECT dept_id,parent_id,dept_name,status,del_flag FROM sys_dept WHERE dept_id IN (201,202,203,204) ORDER BY dept_id;',
 'auth_config': "SELECT config_key,config_value FROM sys_config WHERE config_key IN ('sys.account.captchaEnabled','sys.login.blackIPList');"
}
env = os.environ.copy(); env['MYSQL_PWD'] = cfg['spring.datasource.druid.master.password']
args = ['E:/software/Mysql-8.4/bin/mysql.exe','--default-character-set=utf8mb4','--batch','--raw','--connect-timeout=5','-h',m[1],'-P',m[2],'-u',cfg['spring.datasource.druid.master.username'],m[3]]
report['database'] = {}
for name,sql in queries.items():
    p = subprocess.run(args+['-e','START TRANSACTION READ ONLY; '+sql+' ROLLBACK;'],env=env,capture_output=True,timeout=15)
    report['database'][name] = {'exit_code':p.returncode,'result':p.stdout.decode('utf-8',errors='replace') if p.returncode==0 else '连接或查询失败；未输出原始错误以避免泄露配置'}
for name,endpoint in [('frontend','http://127.0.0.1/'),('captcha_proxy','http://127.0.0.1/dev-api/captchaImage')]:
    try:
        with urllib.request.urlopen(endpoint,timeout=10) as r:
            body=r.read(); item={'http_status':r.status,'checked_at':now()}
            if name=='frontend': item['html_present']=b'<html' in body.lower()
            else:
                data=json.loads(body); item.update({k:data.get(k) for k in ['code','msg','captchaEnabled']}); item['uuid_present']=bool(data.get('uuid')); item['image_present']=bool(data.get('img'))
            report[name]=item
    except Exception as e: report[name]={'error_type':type(e).__name__}
report['boundary']='No login attempts or business data writes. Captcha GET may create one short-lived Redis captcha key; no token, password, UUID or image is saved.'
(OUT/'current_environment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
