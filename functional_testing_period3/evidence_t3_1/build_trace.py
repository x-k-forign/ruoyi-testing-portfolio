"""Extract existing design references, write Markdown tracking only; never edit XLSX."""
from pathlib import Path
import collections, hashlib, json, re
import openpyxl
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'functional_testing_period3'
source=ROOT/'document_design_period1/测试用例/若依主线测试用例.xlsx'
w=openpyxl.load_workbook(source,read_only=True,data_only=True)
cases=[]; tp_cases={}
for row in w.worksheets[0].values:
    if row and re.fullmatch(r'TP-[A-Z]\d{2}',str(row[0])):
        tp_cases[row[0]]=re.findall(r'TC-[A-Z]\d{2}-\d{2}',str(row[3]))
for s in w.worksheets[1:]:
    for i,row in enumerate(s.values,1):
        if len(row)>=8 and re.fullmatch(r'TC-[A-Z]\d{2}-\d{2}',str(row[0])):
            cases.append({'id':row[0],'title':row[1],'priority':row[3],'pre':row[4],'steps':row[5],'data':row[6],'expected':row[7],'sheet':s.title,'row':i})
assert len(cases)==88 and len({c['id'] for c in cases})==88 and len(tp_cases)==52
assert set(sum(tp_cases.values(),[]))=={c['id'] for c in cases}
risk_tp={}
for line in (ROOT/'document_design_period1/T1_风险评估与优先级.md').read_text(encoding='utf-8-sig').splitlines():
    cols=[x.strip() for x in line.split('|')]
    if len(cols)>3 and re.fullmatch(r'RK\d{2}',cols[1]) and 'TP-' in cols[2]: risk_tp[cols[1]]=re.findall(r'TP-[A-Z]\d{2}',cols[2])
assert len(risk_tp)==12
def refs(text):
    found=set(re.findall(r'E\d{2}',text))
    for a,b in re.findall(r'E(\d{2})[—–-]E?(\d{2})',text): found.update(f'E{i:02}' for i in range(int(a),int(b)+1))
    return '、'.join(sorted(found)) or '需求S07'
scope={'C':'SC01','L':'SC02','A':'SC03','M':'SC05','G':'SC06','E':'SC07','D':'SC08'}
direct={'TC-C05-01','TC-C06-01','TC-C06-02','TC-C07-03','TC-C07-04','TC-M07-01'}
fault={'TC-C08-01','TC-M07-02','TC-G04-03'}
rows=[]
for c in cases:
    cid=c['id']; group=cid[3]; tp=[t for t,ids in tp_cases.items() if cid in ids]
    risks=[r for r,ts in risk_tp.items() if set(tp)&set(ts)]
    if cid.startswith('TC-C07-'):
        risks=['RK07','RK12'] if cid[-2:] in ('01','02') else ['RK04']
    if cid=='TC-M07-01': risks=['RK04']
    if cid=='TC-M07-02': risks=['RK08']
    sc=scope[group]
    if group=='A' and int(cid[4:6])>=5: sc='SC04'
    if cid=='TC-C05-01': sc+='、SC03'
    e=refs(c['pre']+' '+c['expected'])
    if group=='C': action='T3.3：单项输入、提交提示、保存及关联回查'; later='T4同输入服务端校验；T5必要时核对关联/原记录'
    elif group=='L': action='T3.3：隔离登录条件、页面/响应及身份'; later='T4认证及受保护请求；需要时补缓存计数/TTL证据'
    elif group=='A': action='T3.4：页面/获准操作及回查' if sc=='SC03' else 'T3.4：配置回查、新登录、同条件全部分页ID集合'; later='T4身份/请求对照；T5基准集合或关联补证'
    elif group=='M': action='T3.5：专用对象变更、回查与新旧会话实际对照'; later='T4请求完整对照；T5关联/状态补证'
    elif group=='G': action='T3.6：随业务动作关联日志、记录身份/时间/窗口'; later='T4请求和拦截链；T5入库；T6缺失排查'
    elif group=='E': action='T3.3—3.8：复用同一对象的步骤与结果，逐段记录'; later='T4/T5补对应子步骤证据，不能整体覆盖未决'
    else: action='T3.3：专用部门约束及回查'; later='页面不可构造时保留缺口；T4请求、T5组织关系补证'
    if cid in direct:
        action='T3必需准备/页面层：身份、合法请求配方、目标范围/配置及入口观察'; later='T4必测直接请求拒绝；T5核对无未授权写入（按PL04）'
    if cid in fault:
        action='T3必需准备：事务内异常触发点、独立环境、前后基线与恢复方案'; later='T4/T5实际受控异常、回滚及日志；普通error不能替代（按PL08）'
    if cid in {'TC-M02-01','TC-M06-01','TC-M09-02','TC-M03-01','TC-M09-03'}:
        action='T3.5：独立A/B、单一变更、实际请求及时间线；仅页面不能满足'; later='T4扩展请求组合；T5关联补证；缺最小请求条件仍为T3缺口'
    if cid=='TC-L09-05': action+='；5位已有账号待受控准备，不能移除'
    if cid=='TC-L07-01': action+='；保留原验证码请求，自动刷新不等于已测试复用'
    if cid.startswith('TC-L10-'): action+='；独立计数账号与计数/到期证据'
    if cid=='TC-G04-01': action+='；需关联真实授权拒绝，缺事件则不能完成此项'
    q=''
    if cid in {'TC-C07-01','TC-C07-02'}: q='Q03'
    if cid=='TC-L09-05': q='Q02'
    if cid in {'TC-M02-01','TC-M04-01','TC-M06-01','TC-M09-02'}: q='Q04'
    if cid=='TC-G04-02': q='Q06'
    if cid=='TC-E01-01': q='Q04、Q06（及关联步骤）'
    rows.append([cid,c['title'],sc+' / '+'、'.join(risks),'、'.join(tp),e,action,later,q or '—',f"{c['sheet']}!A{c['row']}:H{c['row']}"])
counts=collections.Counter(c['priority'] for c in cases)
meta={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'cases':len(cases),'points':len(tp_cases),'priority':dict(counts),'business_pending':[r[0] for r in rows if r[7]!='—'],'unmapped_cases':[],'missing_points':[],'t3_executed':0}
assert len(meta['business_pending'])==9 and counts=={'P0':51,'P1':37}
(OUT/'evidence_t3_1/design_inventory.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
head='''# T3.1 用例追踪索引

日期：2026-10-10。AI依据既有资料整理；本次仅接手与设计核查，88条用例均未执行。表格是原设计的索引，不是第二套用例；原步骤、输入与完整预期仍以原Excel为准，当前映射补充见[T3.1追踪记录](T3.1_追踪记录.md)。

## 读取与统计

来源：[若依主线测试用例](../document_design_period1/测试用例/若依主线测试用例.xlsx)，8张表，其中7张业务表共88条；P0为51条、P1为37条；52个TP均有TC，无重复TC或游离TC。表中保留9条业务疑问，其他准备缺口见追踪记录。

依据E为固定源码/默认配置推断；部门约束引用原需求S07。SC取原范围，RK取风险文档测试点映射，并细分C07空/非法关联、M07拒绝/回滚。原用例前置条件及预期在最后一列定位。全量跨阶段用例状态均为“未执行”，实际结果、执行时间、证据、产品问题号均未产生；接手核查证据不得填入用例实际结果。

## T3必需任务与后续补证

本表逐行列明T3任务，88条均保留追踪。6条直接越权用例在T3落实准备及页面层，服务端拒绝按原PL04留到T4；3条事务异常用例在T3落实方案与恢复准备，实际故障/回滚按PL08留到T4/T5。其余79条的T3功能、观察或执行管理层需真实执行。此处是按原计划拆分断言，不是删除9条用例；任何准备任务也不能仅列“待准备”就验收。T3.5必需的实际请求对照不能整体延期成T4。

页面不能构造的原定T3输入、未完成的日志观察或缺失A/B条件，仍是T3缺口：先补条件；若确需调整范围，记录影响并由用户明确确认。T3层完成不自动使整条跨阶段TC通过。

| 原TC | 检查行为 | 范围 / 风险 | 原TP | 预期索引 | T3必需层次 | 后续补证/边界 | 业务疑问 | 原表定位 |
|---|---|---|---|---|---|---|---|---|
'''
text=head+'\n'.join('| '+' | '.join(str(v).replace('|','／').replace('\n',' ') for v in r)+' |' for r in rows)+'\n'
text+='\n## 从风险反查\n\n| 风险 | 原测试点 | 原用例（去重） |\n|---|---|---|\n'
for risk,tps in risk_tp.items():
    matching=[r[0] for r in rows if risk in r[2]]
    assert matching
    text+='| '+risk+' | '+'、'.join(tps)+' | '+'、'.join(matching)+' |\n'
(OUT/'T3.1_用例追踪索引.md').write_text(text,encoding='utf-8')
print(json.dumps(meta,ensure_ascii=False,indent=2))
