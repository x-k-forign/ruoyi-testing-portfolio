from pathlib import Path
from copy import deepcopy
import json,zipfile,uuid,re,hashlib
from lxml import etree as ET

base=Path(__file__).resolve().parents[1]
reference=base/'practice/长度范围功能测试分析.xmind'
output=base/'若依用户权限主线需求分析.xmind'
def uid():return str(uuid.uuid4())
def topic(title,*children,fold=False):
    t={'id':uid(),'class':'topic','title':title}
    if children:t['children']={'attached':[topic(c) if isinstance(c,str) else c for c in children]}
    if fold and children:t['branch']='folded'
    return t

requirements=topic('需求',
 'R01 用户创建：合法资料可创建，账号唯一，部门与角色保存正确',
 'R02 登录认证：正常账号可登录；错误凭据、停用或删除账号被拒绝',
 'R03 操作权限：按有效角色授权；无权限请求被拒绝，不能只看按钮',
 'R04 数据范围：用户列表按角色范围返回允许的数据',
 'R05 变更与禁用：新登录按新配置；旧会话单独观察，时效待确认',
 'R06 日志追溯：登录和管理动作能与账号、对象、时间、结果对应',
 '部门约束：不能以自身为父级；有下级或用户时不能删除')

analysis=topic('分析',
 topic('等价类划分',
  topic('登录',
   topic('有效','正常已存在账号＋匹配密码＋开关所需有效验证码＋未锁定＋来源获准'),
   topic('无效（逐项替换）','账号为空／不存在／停用／删除','密码为空／错误','验证码为空／错误／过期／已消耗','已锁定／来源命中限制')),
  topic('用户创建',
   topic('有效','有新增权限＋唯一登录名＋合法资料＋可分配部门和角色'),
   topic('无效（逐项替换）','登录名为空／全空白／重复','非空手机号重复／非空邮箱重复','无新增权限','有限管理身份：部门或角色越界／编号不存在'),
   topic('待确认','deptId=null是否允许','roleIds=[]是否允许；不等同于null数组')),
  topic('查询','有查询权限＋范围内记录：返回匹配记录','有查询权限＋无匹配或仅范围外匹配：返回空','无查询权限＋合法请求：拒绝访问'),fold=True),
 topic('边界值分析（固定版本依据）',
  topic('登录账号2—20位','上点：2、20','相邻点：1、3、19、21','内点：10；成功样本须真实存在'),
  topic('后端登录密码5—20位','上点：5、20','相邻点：4、6、19、21','内点：10；有效样本须匹配账号'),
  topic('前端创建密码6—20位','上点：6、20','相邻点：5、7、19、21','内点：10；其余字符规则保持有效'),
  topic('失败次数与时间','先核对生效阈值N、锁定时长T','默认N=5、T=10分钟；按N−1、N及自然到期对照','验证码默认TTL=2分钟；按缓存有效／过期状态对照'),
  '5位登录与6位创建是不同入口；统一规则待确认',fold=True),
 topic('判定表：操作授权',
  '共同条件：已正常登录、请求格式及其他输入合法',
  '有操作权限＋目标关联在允许范围 → 允许操作',
  '有操作权限＋目标关联超出范围 → 拒绝（普通有限管理身份）',
  '无操作权限＋目标关联在允许范围 → 拒绝',
  '无操作权限＋目标关联超出范围 → 拒绝；不能据此单独证明范围校验',fold=True),
 topic('数据范围对照',
  '共同条件：普通身份、有效适用角色、有列表权限、相同查询条件',
  '全部 → 全部匹配的有效记录',
  '自定义 → 实际保存的指定部门集合',
  '本部门 → 本部门匹配记录',
  '本部门及以下 → 本部门和下级匹配记录',
  '仅本人 → 本人匹配记录',
  '多角色 → 仅组合有效且匹配目标权限的角色范围',
  '清除非目标搜索和部门树筛选；核对全部分页ID',fold=True),
 topic('状态迁移',
  '账号正常 → 禁用：新登录拒绝；旧会话另测',
  '仅查询 → 增加新增权限 → 撤销新增权限',
  '部门A → 部门B：新登录按B；旧会话比较变更后集合',
  '角色正常 → 停用：新登录核对剩余有效角色',
  'A保留变更前会话；B独立新登录；一次只改一项',fold=True),
 topic('场景法',
  '准备角色与部门 → 创建用户 → 同一用户登录',
  '获准操作及数据查询 → 变更或禁用 → A/B对照 → 核对日志',
  '创建或登录失败 → 停止依赖成功的后续步骤',fold=True))

groups=[]
def group(name,valid=(),invalid=(),observe=()):
    branches=[]
    for title,entries in [('有效',valid),('无效（各条件分别测试）',invalid),('异常与待确认',observe)]:
        if entries:branches.append(topic(title,*entries))
    groups.append(topic(name,*branches,fold=True))

group('用户创建',[
 'TP-C01 创建成功：新增权限＋唯一账号＋合法资料＋可分配关联 → 保存并回查一致'],[
 'TP-C02 创建拒绝：仅登录名为空／全空白＋其余有效 → 不新增',
 'TP-C03 创建拒绝：仅登录名重复＋其余有效 → 不新增，不覆盖旧账号',
 'TP-C04 创建拒绝：仅手机号重复／仅邮箱重复＋其余有效 → 不新增',
 'TP-C05 新增拒绝：仅缺新增权限＋其余有效 → 服务端拒绝，不产生新用户',
 'TP-C06 关联拒绝：仅部门越界／仅角色越界＋其余有效 → 有限管理身份被拒'],[
 topic('TP-C07 空关联与非法编号',
  'deptId=null＋其余有效 → 观察保存结果；业务允许性待确认',
  'roleIds=[]＋其余有效 → 观察无角色关联；业务允许性待确认',
  '有限管理身份＋仅部门编号不存在／仅角色编号不存在 → 拒绝'),
 'TP-C08 事务内可回滚异常＋其余有效 → 核对用户和关联无部分写入（条件待准备）'])

group('登录认证',[
 'TP-L01 登录成功：正常新用户＋匹配密码＋有效验证码等条件 → 身份一致',
 'TP-L08 登录成功：关闭验证码＋正常账号＋正确密码 → 可登录；完成后恢复开关'],[
 'TP-L02 登录拒绝：仅账号为空／不存在＋合规非空密码＋有效验证码 → 无新会话',
 'TP-L03 登录拒绝：正常账号＋仅密码为空／错误＋有效验证码 → 无新会话',
 'TP-L04 登录拒绝：仅账号停用／删除＋原正确密码＋有效验证码 → 拒绝新登录',
 'TP-L05 登录拒绝：仅验证码为空／错误＋其余有效 → 验证码校验失败',
 'TP-L06 登录拒绝：仅验证码已过期＋其余有效 → 拒绝',
 'TP-L07 登录拒绝：复用已消耗验证码＋其余有效 → 拒绝；新码作正常对照',
 'TP-L12 登录失败＋无残留会话 → 不能访问受保护功能'],[
 topic('TP-L09 长度边界',
  '账号2／20位，密码5／20位＋真实匹配凭据＋其余有效 → 按登录规则核对',
  '仅账号1／21位，或仅密码4／21位＋其余有效 → 拒绝',
  '5位密码已有账号待准备；与创建6位下限的差异待确认'),
 topic('TP-L10 密码失败限制',
  '失败计数未达阈值＋正确密码＋新有效码 → 可登录并清计数',
  '失败计数已达阈值＋正确密码＋新有效码 → 锁定期拒绝',
  '计数自然过期＋正确密码＋新有效码 → 可重试'),
 'TP-L11 IP限制：获准来源＋其余有效 → 可登录；仅来源受限 → 拒绝'])

group('菜单与操作权限',[
 'TP-A04 操作成功：普通账号有目标权限＋合法对象和输入 → 返回或保存正确结果'],[
 'TP-A03 操作拒绝：普通账号无目标权限＋合法直接请求 → 拒绝且无未授权变更'],[
 'TP-A01 菜单对照：已分配／未分配／已授权但隐藏 → 分别核对侧栏与路由',
 'TP-A02 同部门甲乙对照：甲仅查询、乙可新增＋各自合法输入 → 核对按钮及真实请求'])

group('部门数据范围',[
 'TP-A05 本部门：同角色甲属A、丙属B＋同条件查询 → 各见本部门、不互见',
 'TP-A06 本部门及以下：A身份＋A/子部门/B对照 → 返回A及子部门，排除B',
 'TP-A07 仅本人：本人＋同部门其他人对照 → 仅返回本人匹配记录',
 'TP-A08 自定义：回查仅选B＋A/子部门/B对照 → 仅返回B匹配记录',
 'TP-A09 全部：普通身份＋全部范围＋同条件 → 与有效记录基准集合一致',
 'TP-A10 空结果：获准查询＋无匹配／仅范围外匹配 → 返回空，不泄漏'],observe=[
 'TP-A11 多角色：正常适用角色组合 → 核对授权与范围；停用其中一个后新登录再对照'])

group('关联变更与账号禁用',[
 'TP-M01 保存成功：有修改权限＋合法角色关联变更 → 同一用户回查一致',
 'TP-M08 正常角色／部门变更＋有效凭据 → 新登录成功并按新配置使用',
 'TP-M09 增加正常角色：新登录取得该角色有效授权；无目标授权角色不放开操作，旧会话另观察'],[
 'TP-M03 撤销新增权限＋无其他角色补授＋新登录合法新增 → 服务端拒绝',
 'TP-M05 禁用账号＋正确凭据＋新有效码 → 新登录拒绝'],[
 'TP-M02 仅撤销用户角色关联＋旧会话未刷新 → 观察原请求；即时撤权要求待确认',
 'TP-M04 仅A部门改B部门 → 新登录查B；旧会话比较变更后集合，时效待确认',
 'TP-M06 仅禁用账号＋旧会话保持 → 观察真实访问；是否立即失效待确认',
 'TP-M07 变更失败：无修改权限应拒绝；事务内异常另查回滚，不按新配置继续'])

group('日志关联',[
 'TP-G01 成功登录＋日志读取权限＋对应时间窗口 → 账号、时间和成功结果可关联',
 'TP-G03 创建／编辑／授权／禁用 → 按入口核对操作者、对象线索、类型及响应'],[
 'TP-G02 账号／密码／验证码单项无效且请求进入服务 → 分别关联失败日志'],[
 'TP-G04 拒绝或保存失败 → 区分方法前拦截、正常error和抛异常；SUCCESS语义待确认',
 'TP-G05 未匹配日志 → 复查权限、筛选、时区及异步观察窗口后分类'])

group('部门配置约束',[
 'TP-D03 删除成功：专用部门无下级＋无用户＋有权限 → 查询不再返回'],[
 'TP-D01 修改拒绝：仅将父级设为自身＋其余有效 → 原层级不变',
 'TP-D02 删除拒绝：仅有下级／仅有关联用户＋其余有效 → 部门及关系保留'])

group('整条业务主线',observe=[
 'TP-E01 同一用户：创建→登录→获准使用→变更对照→日志；未决步骤单独记录',
 'TP-E02 创建失败 → 停止新用户链路，不拿旧同名账号替代',
 'TP-E03 登录失败 → 不继续成功访问链；保留拒绝及关联日志',
 'TP-E04 规则未定／缺执行条件 → 记录待确认／阻塞，不填写通过'])

points=topic('提取测试点',topic('规则',
 '有效：同一场景各输入均有效，使用多个有效条件组合',
 '无效：只替换一个无效数据项或条件，其余全部有效',
 '判定表组合、状态迁移与受控异常按各自场景对照'),*groups)
root=topic('若依用户权限主线需求分析',requirements,analysis,points)
root['structureClass']='org.xmind.ui.logic.right'
root['customWidth']=300
root['notes']={'plain':{'content':'依据：T1_若依需求分析.md、T1_预期依据清单.md、测试用例/测试点.md。后端13db1fcef36bee9ce45d2d636a1d4e8f5ed5bbc3；前端838965c5a18d2c61b73ec30c6e288057aaa08b63。设计视图，未执行；标注默认值须核对生效配置。保留52个原TP编号。'}}
with zipfile.ZipFile(reference) as z:sheet=deepcopy(json.loads(z.read('content.json'))[0])
sheet.update({'id':uid(),'revisionId':uid(),'title':'需求与测试分析','rootTopic':root,'arrangeableLayerOrder':[root['id']]})
for key in ['zones']:sheet[key]=[]
for key,style in sheet.get('theme',{}).items():
 if isinstance(style,dict):
  if 'id' in style:style['id']=uid()
  props=style.get('properties',{})
  if 'fo:font-family' in props:props['fo:font-family']='Microsoft YaHei'

# Matching XML content supplies a consistent fallback instead of stale template content.
NS='urn:xmind:xmap:xmlns:content:2.0'
xroot=ET.Element('{'+NS+'}xmap-content',nsmap={None:NS},version='2.0')
xsheet=ET.SubElement(xroot,'{'+NS+'}sheet',id=sheet['id'])
ET.SubElement(xsheet,'{'+NS+'}title').text=sheet['title']
def xml_topic(parent,t):
 x=ET.SubElement(parent,'{'+NS+'}topic',id=t['id'])
 if 'structureClass' in t:x.set('structure-class',t['structureClass'])
 if t.get('branch')=='folded':x.set('branch','folded')
 ET.SubElement(x,'{'+NS+'}title').text=t['title']
 kids=t.get('children',{}).get('attached',[])
 if kids:
  children=ET.SubElement(x,'{'+NS+'}children');topics=ET.SubElement(children,'{'+NS+'}topics',type='attached')
  for c in kids:xml_topic(topics,c)
xml_topic(xsheet,root)
payload={'content.json':json.dumps([sheet],ensure_ascii=False).encode(),
 'content.xml':ET.tostring(xroot,encoding='UTF-8',xml_declaration=True),
 'metadata.json':json.dumps({'dataStructureVersion':'3','creator':{'name':'XMind'},'layoutEngineVersion':'5'}).encode()}
payload['manifest.json']=json.dumps({'file-entries':{k:{} for k in payload}}).encode()
titles=[];ids=[]
def walk(t):
 titles.append(t['title']);ids.append(t['id'])
 for c in t.get('children',{}).get('attached',[]):walk(c)
walk(root)
assert len(ids)==len(set(ids))
assert [x['title'] for x in root['children']['attached']]==['需求','分析','提取测试点']
tp=re.findall(r'TP-[A-Z]\d{2}','\n'.join(titles))
source=base.parent/'document_design_period1/测试用例/测试点.md'
expected=set(re.findall(r'^\| (TP-[A-Z]\d{2}) \|',source.read_text(encoding='utf-8-sig'),flags=re.M))
assert len(tp)==52 and set(tp)==expected
assert not output.exists(),'Output already exists; inspect before replacing'
with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for name,data in payload.items():z.writestr(name,data)
with zipfile.ZipFile(output) as z:
 assert z.testzip() is None
 assert json.loads(z.read('content.json'))[0]['rootTopic']==root
 assert len(ET.fromstring(z.read('content.xml')).xpath('//*[local-name()="topic"]'))==len(ids)
print(json.dumps({'output':str(output),'top_topics':['需求','分析','提取测试点'],'retained_test_points':len(tp),'topics':len(ids),'checks':'ZIP/JSON/XML一致，节点ID唯一，原52个TP全部保留'},ensure_ascii=False))
