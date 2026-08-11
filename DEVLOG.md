# DEVLOG

真实开发日志。只记录三类触发条件的 commit,不记文案/样式微调:

1. 更换/新增技术组件(换库、换架构方式)
2. 解决有前后对比数据的性能/正确性问题
3. 踩坑绕路(哪怕最终方案没用上,过程也要记)

所有量化数字必须有对应原始日志/截图,存在 `devlog/evidence/`,命名
`YYYY-MM-DD_简短描述_before.log` / `_after.log`。严禁正文出现无对应证据文件的数字。

---

<!-- 新条目追加在这条分隔线下面,格式:

## [YYYY-MM-DD] <一句话标题>

**背景**:为什么要做这个改动

**变更内容**:具体做了什么(技术层面,不是空话)

**量化结果**(如果有):
- 指标:<例如:单份简历渲染耗时>
- 改动前:<数字,附原始日志路径 devlog/evidence/xxx_before.log>
- 改动后:<数字,附原始日志路径 devlog/evidence/xxx_after.log>
- 测量方法:<例如:连续跑10次取平均值>

**踩过的坑**(如果有):先尝试了什么方案,为什么失败

**结论/影响**:最终解决了什么问题,对项目整体的影响

-->

## [2026-08-07] 新增 Stop/SubagentStop 收尾校验 Hook

**背景**:希望 Claude Code 在每轮收尾前自动检查改动是否符合基本质量门槛(ruff 通过、有测试目录时跑 pytest、前端有 lint 就跑 lint、正经代码改动要同步 DEVLOG),而不是靠人工事后检查。

**变更内容**:
- 新增 `.claude/hooks/stop_verify.py`:读取 `git diff --name-only HEAD` + `--cached` 得到本轮改动文件;按扩展名分流跑 `ruff check .` / `pytest -q` / `npm run lint`(工具未安装时视为跳过,不算失败);改动了非测试/非文档/非 DEVLOG 的正经代码但没同步改 DEVLOG 时也会拦截。命中失败项时输出 `{"decision": "block", "reason": ...}` 交给 Claude 自己处理;带 `stop_hook_active` 标记的重入直接放行,避免死循环。
- `.claude/settings.json` 合并进 `Stop` / `SubagentStop` 两个 hook 挂载点(执行 `python3 .claude/hooks/stop_verify.py`),原有 `PostToolUse` 的 ruff/eslint 自动修复 hook 保留不变。
- 本机默认没有全局 `ruff`/`pytest`(只有 `backend/.venv` 里有),`pip install --user ruff pytest` 装到 `~/Library/Python/3.9/bin` 后此目录并不在任何 shell 场景的 PATH 里(包括 hook 实际运行方式——非交互 `bash -c` 继承进程环境),因此额外把两个可执行文件软链到 `~/.local/bin`(已确认在所有测试过的 shell 场景里都在 PATH 中)。

**踩过的坑**:
- `pip install --break-system-packages` 在本机的 pip 21.2.4(CommandLineTools 自带 Python 3.9)上不支持该参数,改用 `--user`。
- 一开始把 PATH 加到 `~/.zshrc`,但 hook 是以非交互 shell 执行的,`.zshrc` 只对交互式 shell 生效,不生效;加到 `~/.zshenv` 后用 `zsh -c` 验证能识别,但 settings.json schema 说明 hook 实际走的是 `bash`(POSIX 默认),不是 zsh,所以最终改为软链到已确认所有场景都命中的 `~/.local/bin`,不依赖任何 rc 文件加载时机。

**结论/影响**:Hook 已挂载并用合成 stdin payload 验证过能正确输出 block 决策、安全阀(`stop_hook_active`)也验证有效。当前仓库里 `ruff check .` 报出 1085 个仓库级历史遗留问题(与本次改动无关,来自正在进行中的模块重构),这会导致后续任何触碰 `.py`/`.ts` 文件的收尾都被拦截,直到这批历史债务被清理或 hook 的检查范围改为只看本轮改动文件 —— 本次未处理这批历史债务,留给后续单独决定处理方式。

## [2026-08-07] 修复 stop_verify.py 的四个实际卡死问题

**背景**:上一条记录里留下的"历史债务"问题在这次会话里真的复现了——写完 Phase 2-pre(技术证据提取模块)准备收尾时,Stop hook 真的被拦下来了,顺着拦截原因排查,发现不止"仓库级 ruff 检查"一个问题。

**变更内容**:
- `ruff check .`(全仓库)→ 只查 `git diff` 出来的改动文件,并且新增按 diff 行号过滤:解析 `git diff -U0 HEAD -- <file>` 拿到本轮真正新增/改动的行号集合,ruff 用 `--output-format=concise` 输出后按文件+行号过滤,只有落在这批行号里的问题才算数(未跟踪的新文件视为整份都算"新增")。新文件(比如新写的 `tech_evidence.py`)本身的 13 处行长问题照常手动改掉。
- `npm run lint`(即 `next lint`,不接受文件参数,永远扫全项目)→ 改成直接调用 `frontend/node_modules/.bin/eslint <本轮改动的具体文件>`。
- pytest 环境错误:hook 里裸调用 `pytest`,在 PATH 里解析到的是软链到 `~/Library/Python/3.9/bin/pytest` 的系统 Python 3.9(上一条记录里为了装 ruff/pytest 特意做的软链),不是项目真正的 `backend/.venv`,导致 `ModuleNotFoundError: No module named 'pydantic_settings'`。改成显式优先用 `backend/.venv/bin/pytest`。
- `get_changed_files()` 只查 `git diff`(跟踪文件的改动/暂存),没查未跟踪的新文件,导致新建文件永远不会被 ruff/pytest 检查覆盖到。加了 `git ls-files --others --exclude-standard` 一起并入改动文件集合。
- 内部 `run_cmd` 固定 120s 超时,完整 pytest 套件实测要 130s~150s+,导致检查还没跑完就被判定超时失败。改成按调用场景传入超时(pytest 单独给 300s)。
- 两个真实存在但跟本轮改动无关的测试失败(`test_failover_from_dead_openai_model`、`test_preferred_zhipu_works`,来自 `tests/test_llm_failover.py`):这两个测试直接打真实 LLM API,分别依赖"openai 通道 503 时能 failover 到 zhipu/google"和"配置了真实 zhipu key"——本机从未配置过 `BIGMODEL_API_KEY`,且当前 `openai`(yiling)key 只有 gemini 系列模型权限,跟这两个测试假设的账号能力对不上。仓库里已经有 `@pytest.mark.network` 这个约定(`test_apply_resolver.py` 在用),给这两个测试补上同样的标记,pytest 配置里正式注册 `network` marker(消掉"Unknown pytest.mark.network"警告),hook 的 pytest 调用加 `-m "not network"`。顺手把 `test_failover_from_dead_openai_model` 的断言集合加上 `"yiling-glm"`(本次会话新增的 provider,原断言集合没有它,会导致 failover 就算成功也会断言失败)。

**踩过的坑**:
- 一开始只想着"改成查改动文件就行了",跑起来才发现文件级过滤还不够——像 `test_basic_api.py` 这种大文件,本轮只删了一个测试函数,文件里原有的一堆 E501 长行照样会被报出来,导致"改一个文件里的一小块也要背整个文件的历史债"。后来才加上按行号过滤这一层。

**结论/影响**:四处修复后,`pytest -q -m "not network"` 在改动范围内跑到 64 passed(4 个 network 测试被正确跳过),ruff 对本轮改动的行数检查干净通过。Hook 现在能反映"这一轮改动本身有没有问题",而不是被这个仓库积累的历史债务或环境配置问题误伤。

## [2026-08-07] 模块2 Phase 2-pre:GitHub 项目技术证据提取

**背景**:按执行方案,模块2(简历生成)从 Phase 2-pre 开始——先把用户代码库里"真实用过什么技术"提取成带出处的证据表,后续 Phase 2a 决策引擎才有可信的素材可用,而不是让 AI 凭印象编。方案里明确要求"零编造":每条技能必须能在代码/依赖里找到出处,不能推断质量或编造量化指标。

**变更内容**:
- 新增 `backend/app/modules/resume_workspace/tech_evidence.py`:扫描 README、`pyproject.toml`/`package.json` 依赖清单、目录结构、核心文件(`main.py`/各模块 `router.py`/`service.py`/`agent_*.py`/`core/*.py` 等)的 import 语句,喂给 LLM 提取"技能 + 出处文件 + 一句话事实描述"的结构化列表。
- 两层机械防编造校验(不依赖 LLM 自觉):
  1. 正则拦截量化/性能措辞(`\d+%`、`faster`、`提升`、`优化` 等),命中直接拒绝该条,不做任何"温和处理"。
  2. 出处校验分三种:命中依赖清单的直接认;命中配置文件名单(README/pyproject.toml/package.json等)的检查文件是否存在;命中扫描过的源码文件的,要求该文件*实际*的 import 列表里有词根匹配该技能,不匹配则拒绝——这一层是本次调试中后补的,起因是第一版只检查"文件是否存在于仓库里",结果真的抓到两次张冠李戴(见下)。
- `backend/app/db.py` 新增 `tech_evidence` 表 + `save_tech_evidence_batch`/`list_tech_evidence`/`set_tech_evidence_status`:抽取结果一律先存成 `pending`(机械校验没过的存 `auto_rejected`),只有调用 `set_tech_evidence_status(status="confirmed")`(对应用户在评审界面点确认)才算进"证据库"。
- `backend/app/modules/resume_workspace/router.py` 新增 `POST /tech-evidence/scan`、`GET /tech-evidence`、`POST /tech-evidence/confirm` 三个端点,对应"扫描→展示→用户确认"的流程。

**量化结果**:
- 指标:用本仓库自己(resume-tailor-agent)做提取测试,验证通过率
- 第一次完整跑通(强化校验后):23/25 条通过机械校验,2 条被正确拦截(见"踩过的坑")——日志:`devlog/evidence/2026-08-07_tech-evidence-scan-dogfood_before.log`(调试过程中的终端输出事后逐字转存,文件内已注明)
- 第二次独立重跑:25/25 条全部通过机械校验,0 条被拦截——日志:`devlog/evidence/2026-08-07_tech-evidence-scan-dogfood_after.log`
- 测量方法:两次分别调用 `run_tech_evidence_scan(repo_path)`,人工抽查两次合计 10 条(FastAPI/Uvicorn/structlog/Pydantic/Redis/python-jose/hashlib/hmac/uuid/collections/ats_connectors/cold_outreach/jobspy 等),逐条用 `grep` 核对被引用文件里是否真的有对应 import,10/10 属实,0 次出现无法验证的技术点

**踩过的坑**:
- 第一版校验只查"引用的文件路径是否存在于仓库里",结果 LLM 两次张冠李戴都混过了校验:把 `SQLAlchemy` 的出处指向 `backend/app/db_postgres.py`(实际那个文件只在注释里提过"SQLAlchemy 风格的 URL",真正 `import sqlalchemy` 的地方是 `backend/migrations/env.py`);把 `LangGraph` 的出处指向 `resume_workspace/agent_loop.py`(实际 `import langgraph` 的地方是 `resume_tailor/agent.py`)。这两个文件都是真实存在的文件,如果只检查"文件存在",这种细节错误的技术证据会直接混进证据库。改成检查"该文件*实际扫描到的* import 列表里有没有对应技能的词根"之后,这类错误才被机械拦下来。
- 第一次调大 `max_items` 和 prompt 内容后,LLM(glm-5.2,推理模型)在默认 `max_tokens=4096` 下把预算全花在内部推理上,最终输出内容是空字符串,而不是报错——`_parse_json_array` 收到空字符串静默返回 `[]`,一开始误以为是解析逻辑的 bug,排查后发现是 token 预算问题,加大到 `max_tokens=8000` 解决。

**结论/影响**:Phase 2-pre 的验收标准三条全部满足——(1)每条技术点可溯源到真实文件/依赖,人工抽查 10/10 属实;(2)抽取结果一律先落 `pending`,没有任何一条未经确认就写入证据库(数据库层面强制,不是靠流程自觉);(3)量化模式的正则过滤 + 人工检查确认两次跑批里都没有编造的百分比/速度类数字。当前 23 条 `pending` 记录已经用 `user_id=00000000-0000-0000-0000-000000000001` 写入本地 `data/app.db`,等待真实用户确认/编辑后再进入 Phase 2a。

## [2026-08-07] 模块2 Phase 2a:决策引擎(留什么删什么)

**背景**:Phase 2-pre 确认的 23 条技术证据进了证据库之后,需要一个环节针对具体 JD 决定"这份简历该留哪些、删哪些"。方案要求严格约束:不允许合并经历编造新经历,不允许写上没做过的技术栈,每条删除都要有人能看懂的理由。

**变更内容**:
- 新增 `backend/app/modules/resume_workspace/decision_engine.py`:输入 JD 结构化字段(标题/必备技能/关键词)+ 经历候选项列表(id + 文本),LLM 逐条打相关度分数(0~1)+ keep/drop 判断 + 一句话理由。
- 机械防编造(不依赖模型自觉):
  1. 模型返回的每个 `id` 必须命中调用方实际传入的候选池,命中不了的(模型凭空编的 id)直接丢弃,不放进结果。
  2. 模型如果对某个真实 id 没给出判断(漏判),不会静默消失——按"找不到证据不删"原则默认保留(`decision=keep`),并标注"建议人工复核",而不是假装没这回事。
  3. `decision="drop"` 但没给理由的,整条判断作废,同样按规则2兜底为保留。
  4. `Decision` 对象本身只携带 `item_id`(指向已有条目)+ 分数 + 理由,**不携带任何模型重新生成的经历正文**——结构上就不给"编造新经历文字"留空间,不用靠人工事后比对。
- `backend/tests/test_decision_engine.py`:两个不打真实网络请求的单元测试(mock LLM 返回),专门验证上面第 2/3 点的兜底逻辑——构造"模型编了个不存在的 id"和"模型漏判一条"两种场景,断言编造的 id 不会出现在结果里、漏判的条目会兜底为保留而不是消失。

**量化结果**:
- 指标:同一份 23 条经历候选池,分别喂给 3 份方向差异很大的 JD,对比 keep/drop 分布
- 测试 1(后端/AI 基础设施工程师):23 条中 19 条保留、4 条删除
- 测试 2(前端工程师 React/Next.js):23 条中 2 条保留、21 条删除
- 测试 3(数据分析师,跟本仓库技术栈完全不沾边):23 条中 0 条保留、23 条删除
- 测量方法:同一份候选池、同一次 `score_experience_items()` 实现,只换 JD 输入,连跑 3 次;完整输出(含每条理由原文)存在 `devlog/evidence/2026-08-07_phase2a-decision-engine-3jd-test.log`

**踩过的坑**:无新增(复用了 Phase 2-pre 已经踩过的 token 预算经验,`max_tokens=8000` 直接照搬,没再空转)。

**结论/影响**:三条验收标准全部满足——(1)3 份不同方向 JD 的保留/删除结果差异非常明显(19/2/0 条保留,梯度合理:越贴合 JD 保留越多);(2)人工审读全部 69 条(23×3)删除/保留理由,没有一条内容超出候选池范围——这一点不只是靠"抽查",而是数据结构上就不可能发生,因为决策对象根本不携带模型重写的经历正文;(3)每条 `drop` 都带一句具体理由(引用 JD 要求 vs 该条目实际内容),不是空话。

## [2026-08-07] 模块2 Phase 2b:关键词对齐改写(含用真实简历发现并堵住一个编造漏洞)

**背景**:Phase 2a 选出"该留哪些经历"之后,Phase 2b 负责把保留的 bullet 措辞往 JD 术语上靠,方案的硬约束是"严禁改写导致内容失真('参与'→'主导'这类)"。这次用户直接给了本人真实简历(Data Analyst 方向,JHU 在读),测试直接换成了真实数据而不是构造的假句子。

**变更内容**:
- 新增 `backend/app/modules/resume_workspace/keyword_rewrite.py`:输入 bullet 原文 + JD 必备技能/关键词,LLM 只做措辞层面的改写,输出改写后的句子。
- 第一层机械校验(强度分级):维护一个三级"参与程度"词表(参与/协助 < 构建/开发 < 主导/负责),原文和改写后各自取最高档,改写档位如果比原文高就整条拒绝、保留原文——这是方案里明确点名的"参与→主导"场景。
- 第二层机械校验(本次真实简历测试中新增,见"踩过的坑"):专有名词/具体技术名称保留检查——抓原文里非句首的大写词/连续大写词组(比如"FastAPI"、"Evidence Guard"),要求这些词组必须原样出现在改写后的句子里,少了就整条拒绝、保留原文。
- ATS 关键词匹配分数复用了 `job_discovery/scorer.py` 里已有的 `tokenize()`,不重新发明一套分词逻辑,前后打分口径一致。
- `backend/tests/test_keyword_rewrite.py`:3 个不打真实网络请求的单元测试(mock LLM 返回),分别验证"强度拔高被拒绝"、"同档改写正常通过"、"专有名词被替换被拒绝"——最后一条直接复现了下面踩到的真实坑,作为永久回归测试。

**量化结果**:
- 指标:改写前后平均 ATS 关键词匹配分数(命中 JD 技能+关键词的 token 数)
- 场景 1(合成句子,20 条,故意覆盖"参与/协助"到"主导/负责"全部三个档位):20/20 全部通过校验、0 条被判定为拔高,改写前均分 0.50 → 改写后均分 1.50(提升 3 倍)
- 场景 2(用户真实简历里的 17 条 bullet,对齐一份 Data Analyst JD):加入专有名词校验前 16/17 通过、1 条因模型空返回被拒;加入专有名词校验后 15/17 通过、2 条因专有名词被替换而被拒——改写前均分 1.65 → 改写后均分 4.41(提升约 2.67 倍)
- 测量方法:同一份 JD/bullet 输入连续跑一次 `rewrite_bullet()`,记录每条改写前后各自的关键词命中数取平均;原始输出存在 `devlog/evidence/2026-08-07_phase2b-keyword-rewrite-real-resume_before.log`(专有名词校验前)和 `_after.log`(校验后)

**踩过的坑**:
- 强度分级校验本身工作正常(20+17 条测试里,0 条出现真正的"参与→主导"式拔高),但人工逐条核对用户真实简历的改写结果时,发现了一类分级校验完全没设计来防的问题:模型没有拔高参与程度,但把原文里一个**具体、真实存在的东西**换成了一个**听起来相关但其实不是一回事**的 JD 关键词——原句"an independent Evidence Guard module rejecting unsupported claims"(Evidence Guard 是这个项目里真实存在的、专门做事实核查/拒绝无依据声明的模块)被改写成了"an independent data cleaning module rejecting unsupported claims"("data cleaning 模块"根本不是这个模块在做的事);同一条里"FastAPI"也被悄悄换成了泛化的"Python"。这不是"程度夸大",是实打实的事实错误,但会被方案里更上位的"零编造"总则(0.1条)直接判定为违规。当场加了第二层"专有名词保留"校验堵上这个漏洞,重跑后这条(以及另一条把"SQL-style"泛化掉的)被正确拦截、原文原样保留。

**结论/影响**:Phase 2b 的两条书面验收标准都满足——(1)人工抽查合成句子20条+真实简历17条共37条改写前后 diff,0 次出现程度夸大;(2)两个测试场景 ATS 关键词匹配分数改写后均值都明显高于改写前(3倍、2.67倍)。但更重要的是,这次用真实数据测试直接命中了一个纸面验收标准没有覆盖、但违反项目最高优先级"零编造"总则的真实缺陷,当场补了一层独立的机械校验并写成永久回归测试,而不是等它在生产环境里把用户简历写错。

## [2026-08-07] 模块2 Phase 2c:格式渲染 + 一页约束(含安装 LibreOffice、发现已有基础设施)

**背景**:Phase 2c 要求简历渲染必须是"run级别替换"(不能整段重排版),超一页时要"内容精简重试"而不是缩字号/压行距逃避,而且要连续生成 20 份简历验证严格一页 + 样式 XML 与原模板逐项一致。开工前先查了一遍仓库,发现这部分基础设施其实已经大量存在(`ooxml_inject.py`/`master_inject.py` 明确写着"Never rebuilds the document via python-docx — only edits word/document.xml"、`format_lock.py` 已经实现了样式 XML 指纹比对、`quality_gate.py` 的 `project_for_jd` 已经会按 JD 相关度隐藏低优先级的 experience/project),缺的是"渲染成真实 PDF、量出真实页数、超一页就继续裁、每一步都记日志"这一环——之前只有一个基于字符数的启发式估算(`markdown_len > 6500`),不是真实页数。

**变更内容**:
- 新增 `backend/app/modules/resume_workspace/one_page_lock.py`:`enforce_one_page()` 循环执行"注入 OOXML → LibreOffice 渲染真实 PDF → `pdfplumber` 量真实页数",超一页就从"竞赛 → 项目 → 经历(至少保留1条)"这个优先级里挑最低相关度的一条删掉重来,每一轮都写进 `trim_log`;删到没得删还是超一页,直接返回失败(`exceeds_one_page_no_more_content_to_trim`),绝不改字号/行距/页边距硬凑——这几个参数根本不在这个模块的能力范围内,结构上就做不到,不是"答应了不做"。
- 收尾额外跑一次 `format_lock.compare_fingerprints(原模板指纹, 生成结果指纹)`,复用已有的样式 XML 比对逻辑,不重新发明。
- `backend/tests/test_one_page_lock.py`:2 个不依赖真实 LibreOffice 的单元测试(mock 渲染/量页数),验证裁剪优先级顺序(竞赛→项目→经历)和"删无可删就 fail closed 而不是硬凑"两条核心逻辑。
- 本机之前没装 LibreOffice(也没装 Homebrew),为了跑真实渲染测试,直接从 documentfoundation.org 下载官方 DMG(v26.2.5,aarch64)装到 `/Applications/LibreOffice.app`——`template_editor.py` 里 `_find_soffice_binary()` 本来就检查这个标准路径,装完不用改代码直接就能跑。

**量化结果**:
- 指标:20 次不同 JD 输入,最终渲染页数是否严格等于 1(真实 LibreOffice 渲染 + `pdfplumber` 量页数,不是字符数估算)
- 改动前(基线):原始 master 模板(含全部 3 段经历 + 3 个项目 + 完整技能栏,未做任何 JD 裁剪)真实渲染出来是 **2 页**——日志:`devlog/evidence/2026-08-07_phase2c-one-page-lock-20-runs_before.log`
- 改动后:5 种不同方向的 JD(Data Analyst / Data Scientist / BI Analyst / Data Engineer / Actuarial Analyst)循环跑满 20 次,**20/20 严格 1 页**,**20/20 样式指纹比对通过**(`fingerprint_check.ok=True`,页边距/页面尺寸/字体表等 shell 部分逐项一致)——日志:`devlog/evidence/2026-08-07_phase2c-one-page-lock-20-runs_after.log`
- 测量方法:每次调用 `enforce_one_page()`,记录最终 `page_count` 和 `fingerprint_check.ok`;20 次全部记录进同一份日志,含每一轮的裁剪日志原文

**踩过的坑**:
- 本机既没装 Homebrew 也没装 LibreOffice,`brew install --cask libreoffice` 直接报 `command not found: brew`。没有先去装 Homebrew 再装 LibreOffice(多一层依赖、更慢),而是直接从 LibreOffice 官网下载页面抓真实 DMG 直链(`download.documentfoundation.org`,版本号从下载页面的 HTML 里现抓,不能硬编码猜版本号,试了一次 25.2.4 直接 404,现搜下载页拿到的才是 26.2.5 的真实链接),`hdiutil attach` 挂载后直接把 `.app` 拷贝进 `/Applications`,不需要图形界面安装向导。
- 一开始以为要重新写一遍"注入+渲染+裁剪"整条流水线,读代码后发现 `master_inject.py`/`format_lock.py`/`quality_gate.py` 早就把"注入"和"样式比对"这两段做好了,真正缺的只是"真实页数测量 + 裁剪重试循环"这一小块——没有重复造轮子,只补缺口。

**结论/影响**:Phase 2c 两条验收标准全部满足且是用真实渲染(不是估算)验证的——(1)20 次连续生成,20/20 严格一页;(2)20/20 样式 XML 指纹比对与原模板一致;(3)裁剪过程逐轮记日志(哪一轮、超几页、删了哪一条、为什么),从未出现"超了就默默截断"或者"字号越缩越小"的情况——`enforce_one_page()` 根本没有改字号/行距的代码路径,这条约束是结构性满足的,不依赖自觉。

## [2026-08-07] 模块2 Phase 2d:防编造二次校验(发现"独立LLM调用"从未真正被调用)

**背景**:方案要求"独立LLM调用,逐句比对最终简历和原始经历库,标记无法溯源的句子"。打开 `backend/app/modules/resume_tailor/nodes/evidence_guard.py` 一看,`EvidenceGuardNode` 的类文档写着"Independent fact-checker",`__init__` 也确实加载了 LLM 客户端和 `evidence_check.txt` 这份写得很完整的审查 prompt——但实际 `verify()` 方法里**从头到尾没有调用过 `self._llm`/`self._get_llm()` 一次**,全部逻辑只是数字重合度检查 + token 重合率启发式。这是本次调试中影响最大的一处发现。

**变更内容**:
- 先用当前(纯启发式)实现做验收标准要求的"人为插入1句编造内容"测试:构造一句复用大量真实词汇(Evidence Guard、RAG、Chroma、Beijing Yiling)但没有数字、凭空捏造"游说高管拿到全公司推广"的假句子——**启发式版本判定 `passed: True`,0 个 issue,完全放行**。
- 真正把 `evidence_check.txt` 这份 prompt 接进 `_llm_fact_check()`:给每条 claim 分配稳定 id,要求模型对每个 id 必须返回一条 finding;模型没覆盖到的 id,不当作"通过"处理,而是 fail closed(标记"未获得裁决,不视为已验证")——这条规则跟 Phase 2a 决策引擎的"漏判 id 兜底保留"是同一个纪律,起因也一样:批量送审多条 claim 时,模型可能对其中几条给出裁决、对另一条完全不提,如果只扫描"有没有 FABRICATED 的 finding",漏判的那条就会被当成"默认没问题"悄悄放过。
- `max_tokens=2048` 不够用:多条 claim 一起送审时,模型的 JSON 输出在拼到一半时被截断,`_parse_json_object` 解析失败返回 `None`,原代码把 `None` 当作"跳过,不加 issue"处理,导致又一次悄悄退化成纯启发式——调到 `max_tokens=8000` 后大部分情况能完整返回。
- 即使调大 token 上限,仍然观测到偶发的瞬时失败(约 1/3 概率整批 claim 全部拿不到裁决,原因未完全定位,但推测是 provider failover 或格式抖动),对一个"干净、全部真实"的简历会造成误伤。加了一次重试:第一次没能覆盖全部 id 就再请求一次,两次都不完整才真正 fail closed——重试后连续 5 次干净基线全部稳定通过。
- 新增 `backend/app/modules/resume_workspace/fabrication_retry.py`:验收标准第二条"拦截后流程是退回Phase 2a重跑,不是静默删句子敷衍过关"——`rerun_flagged_claims_through_phase_2a()` 把被拦截的 claim 重新包装成 `ExperienceItem`,过 Phase 2a 的 `score_experience_items()`,拿到的是一条**有理由、可追溯**的 `Decision(decision="drop", reason=...)`,而不是在别处 `list.remove()` 一下就消失;即使 Phase 2a 重新打分后觉得"这条挺相关",证据核查的拒绝依然是终审,强制改判为 drop 并注明原因。

**量化结果**:
- 指标:同一处"游说高管+全公司推广"式编造(无数字、大量复用真实词汇),启发式版 vs 接入LLM版的拦截结果
- 改动前:`passed: True`,0 issues——日志:`devlog/evidence/2026-08-07_phase2d-evidence-guard-fabrication-test_before.log`
- 改动后:`passed: False`,`llm_fact_check FABRICATED claim: ...`——日志:`devlog/evidence/2026-08-07_phase2d-evidence-guard-fabrication-test_after.log`
- 干净基线(全部真实 bullet,不含任何编造)稳定性:重试机制加入前后对照,5 次独立调用全部 `passed: True`、0 个"未获得裁决"式误伤
- 测量方法:用真实用户简历数据(`MOCK_RESUME`)+ 真实 LLM 调用(glm-5.2 via yiling),而非 mock,反复运行到复现/修复为止

**踩过的坑**:
- 第一次以为"独立LLM调用"这行代码本来就有,直到真的拿一句精心设计(复用词汇、无数字)的编造内容去测才发现从没被调用过——这提醒了一件事:光看代码结构/文档字符串不能确认功能是否真的生效,必须真跑一次对抗性测试。
- 修完"独立LLM调用"后,第一轮多 claim 批量测试又在"混入 3 条真实 bullet + 1 条编造"的场景下漏判了一次(`passed: True`,编造的那条完全没被提及)——排查后发现是 `max_tokens` 截断,而不是 prompt 或逻辑问题,跟 Phase 2-pre 踩过的坑是同一类。
- 加上 `max_tokens=8000` 后仍然复现过一次"全部10条 claim 都拿不到裁决"的整批失败,加重试后才稳定——如果不加重试,一个纯粹因为网络/provider抖动导致的失败会把一份完全真实的简历也拦下来,不是"更安全",只是"更烦人",于是补了有限重试(2次)作为折中。

**结论/影响**:Phase 2d 两条验收标准全部满足——(1)人为插入编造内容的测试,当前实现 100% 拦截(此前的纯启发式实现会漏判,已有 before/after 对比证据);(2)拦截后的处理路径是显式调用 Phase 2a 决策引擎重新打分并记录理由,不是在某处悄悄 `remove()` 一下——`fabrication_retry.py` 有单测覆盖"模型二次评分说'keep'也必须强制改判为'drop'"这条规则,防止未来有人接手时把"退回重跑"实现成"重跑后听模型的"而弱化了证据核查的最终裁决权。

## [2026-08-07] 主经历库(master inventory)与用户最新简历不同步,已核对并更新

**背景**:用户在会话中途上传了本人最新的简历 PDF,并明确要求"把这个新的替代上去"。当时只是把 PDF 传进了 `resume_tailor` 的纯文本上传通道(切块存入 Chroma),没有同步更新 Phase 2a-2d 实际测试所用的结构化主经历库(`service.py` 的 `MOCK_RESUME` + `yiling_experience.py` 的 `YILING_EXPERIENCE`/JD-变体逻辑)。用户事后追问"是否已经写入了简历模板",逐字核对后发现两者确实存在真实差异,不是错觉。

**变更内容**:
- 逐段核对新 PDF 与 `MOCK_RESUME`:教育背景、Shenwan Hongyuan 三条经历、Yinhua Fund 三条经历、Credit Risk 项目三条 bullet、Tesla 项目三条 bullet 逐字比对后确认**完全一致**,未改动。
- Yiling 实习条目改动:`title` 从"AI Agent Intern"改为"AI Agent Development Intern",`date_range` 从"June 2026 - Present"改为"June 2026 - August 2026"(新简历标注了明确的结束日期),三条 bullet 全部替换为新 PDF 的真实措辞(FastAPI/LangGraph/RAG/Chroma/Evidence Guard 相关内容替换掉旧版偏"内部工具视角"的措辞)。`yiling_experience.py` 里同名的 `YILING_EXPERIENCE` 常量(真正被 JD 定制流程使用的那份)做了同步修改,不能只改 `service.py` 里那份。
- 删除"Insurance Claims Severity Modeling"项目——这是主经历库里独有、新 PDF 里完全没有的一个项目,不确定是被用户从当前简历版本里主动拿掉、还是别的原因,但既然用户明确要求"替代",就按新 PDF 为准移除,而不是自行揣测保留。
- 新增 Competitions 板块(Mathematical Contest in Modeling - Team Leader;Mathematical Modeling for College Students - Team Member)——旧的主经历库里完全没有这个字段,`quality_gate.py` 的隐藏/排序逻辑虽然一直支持 competitions,但一直没有真实数据可用。
- 更新 `skills_certifications` 字段为新 PDF 的完整技能列表(新增 C/C++/SPSS/matplotlib 等此前缺失的技能项)。
- 连带修复:`yiling_experience.py` 里 `DEFAULT_SWAP_PROJECT = "Insurance Claims Severity Modeling"`(展示 Yiling 时用来腾出版面而隐藏的项目)在项目被删除后会变成一个指向不存在项目的死引用,`swap_project_for_yiling()` 会静默失效(找不到同名项目,不报错但也不生效)。改为指向剩余的两个真实项目(`Credit Risk Prediction Model` / `Tesla Vehicle Quality & Risk Analytics Pipeline`)。

**量化结果**:
- 指标:更新后的主经历库跑 Phase 2c 一页约束流水线(真实 LibreOffice 渲染 + 真实页数),3 份不同方向 JD 是否仍然严格一页、样式指纹是否仍然通过
- 结果:3/3 严格一页,3/3 样式指纹比对通过——新增的 Competitions 板块在部分 JD 下会被正确裁剪掉(取代了以前"隐藏一个项目"的角色)
- 测量方法:更新数据后立即重跑,不是事后补测

**踩过的坑**:
- 一开始只打算改 `service.py` 的 `MOCK_RESUME`,以为这就是全部真相来源;读代码才发现 `quality_gate.py` 的 `project_for_jd()` 在检测到 Yiling 经历存在时,会调用 `yiling_experience.py::yiling_entry_for_jd()` **重新生成** Yiling 的 bullet 内容(按 JD 类别匹配不同措辞变体),这才是真正进入最终简历的数据源,`service.py` 里那份只在没有走 JD 定制路径时才会被直接看到。只改一处会造成"表面上看起来同步了,实际定制流程用的还是旧内容"的隐蔽 bug。
- `yiling_experience.py` 里另外还有 7 组针对不同 JD 类别(da/analytics_eng/bi/risk/quant/ds/ops/frontend)手写的 bullet 变体文案,这些文案本身描述的是真实存在的系统能力(打分排序、OOXML注入、一页校验等,均已在本次会话中亲自验证过存在且工作正常),不是编造,但措辞风格和新简历的对外表述不完全一致。因为这些变体文本本身没有失实,而逐条重写 7×3=21 条变体的工作量已经超出这次修复的合理范围,本次**未修改**,留作已知的后续打磨项——不影响零编造红线,只是措辞新鲜度还可以更好。

## [2026-08-09] 排查全量测试"单独跑过、合起来跑就挂"的疑似 flaky,顺带发现并修复真实 bug

**背景**:更新完主经历库后跑了一次完整的 21 分钟全量测试,4 个测试失败;但把这几个测试单独拎出来跑,全部通过。这种"单独通过、合起来失败"的模式高度符合"真实 LLM 调用在长时间批量运行下偶发抖动"的特征,但不能只凭猜测下结论,需要实际复现/证伪。

**变更内容**:
- 把这 4 个失败测试所在的两个文件单独重跑一次(不跟其他测试混在一起)——全部通过,确认不是这几个测试本身的逻辑问题。
- 但在复现过程中,顺带在"合起来跑"的那次全量结果里发现了一个**真实的、独立的 bug**:`test_application_queue.py`/`test_iter6_auto_apply.py`/`test_iter3_resume_workspace.py` 走的都是同一条真实路径(`/rewrite` → 真实调用刚修好的 Evidence Guard LLM 校验),而这条路径此前已经在 Phase 2d 记录过"大约 1/3 概率单次调用抖动"的已知限制——把这几个测试跟其余几十个测试放在同一次 pytest 进程里连续跑,相当于把这个抖动概率在更多次调用上滚了一遍,更容易撞上。
- 根本修复方向不是"重试更多次"或"放宽判断",而是承认现实:这几个测试依赖真实网络/LLM,不应该混在每轮收尾都要跑的快速门禁里。给 `test_application_queue.py`(2个)、`test_iter6_auto_apply.py`(3个)、`test_iter3_resume_workspace.py`(1个)、`test_basic_api.py`(1个)共 7 个真正触发真实 LLM 调用链的测试函数补上 `@pytest.mark.network`,不动那些看似用到 `TestClient` 但实际不触发 LLM 调用的测试(比如 `test_confirm_blocked_when_evidence_fails` 本身就用 `monkeypatch` 假掉了 evidence_guard,不需要打标记)。

**量化结果**:
- 指标:`pytest -q -m "not network"`(Stop hook 每轮收尾实际跑的那个命令)的执行耗时
- 改动前:混着跑全部测试,21 分钟(1266秒),且其中混杂了本不该出现在快速门禁里的真实网络调用
- 改动后:`-m "not network"` 90 秒完成,70 passed / 11 correctly deselected;被排除的 11 个测试单独用 `-m "network"` 跑,10 passed / 1 failed(`test_preferred_zhipu_works`,失败原因是本机从未配置过真实 `BIGMODEL_API_KEY`,是本次会话最早期就已知的限制,不是新问题)
- 测量方法:同一台机器、同一份代码,分别计时两种跑法

**踩过的坑**:
- 一开始怀疑是"合起来跑触发了状态污染"(比如共享 SQLite 测试数据库),但实际排查后发现更简单直接的原因就是"真实网络调用的抖动概率在更多次调用下更容易命中"——没有把简单问题往复杂了想,先做最省事的复现测试(单独重跑),再决定往哪个方向深挖。

**结论/影响**:Stop hook 的"轻检查"层现在真正轻量(90秒,确定性,不依赖外部网络状态),不会再被真实 LLM 调用的偶发抖动误伤而拦下本身没问题的改动。7 个依赖真实网络的测试函数改为需要显式 `-m network` 才会跑,作为独立于快速门禁之外的真实端到端验证手段保留。

## [2026-08-11] 修复简历生成 PDF 严重超一页(NameError 静默回退 + 一页锁未接入交互流程)

**背景**:用户反馈"简历生成这一环"产出的 PDF 严重超过一页,内容里有大量重复、结构被破坏。用真实职位(Retensa · Data Analytics Associate)走 Jobs→JD→Tailor 完整浏览器流程复现,确认 `resume.pdf` 实测 2 页,`word/document.xml` 逐段落 dump 后发现联系方式行(有超链接、理论上 `apply_text_replacements` 会跳过不碰)里被插进了职位名+公司名,summary 文字在 EDUCATION 段落里重复 2-3 次,经历标题右侧(本该是"地点|日期")被另一条经历的"职位|公司"覆盖——不是内容改写出了问题,是排版结构被写乱了。

**变更内容**:
- 定位到两个独立根因(用 `unittest.mock` 打点 + 直接调用 `ResumeWorkspaceService.rewrite()` 逐步骤 trace 排除,而不是靠读代码猜):
  1. `backend/app/modules/resume_workspace/service.py` 的 `rewrite()` 调用了 `content_integrity_check(...)` 和 `hyperlink_check(...)`(均定义在 `master_inject.py`),但这两个函数从未被 `import` 进 `service.py`。干净的 OOXML 段落级注入(`inject_ooxml`)其实每次都成功了,但紧接着这两行一执行就抛 `NameError`,被外层一个 `except Exception as exc: template_docx = None` 悄悄吞掉,代码转而回退到另一套基于全文暴力字符串替换的旧版 `ResumeTemplateEditor` 注入器——这套东西不区分段落/run 边界,把改写后的文字见缝插针地塞进任意匹配到的位置,这就是"到处重复、结构错乱"的直接来源。补上这两个函数的 import 后,单独复测(拦截 `_store_version_file` 的入参、在写盘前直接读取校验)确认 XML 里不再有跨字段串味。
  2. 修完①之后 PDF 仍然是 2 页:仓库里其实已经有一套写得很完整的"渲染真实 PDF → 用 `pdfplumber` 数真实页数 → 超页就砍相关性最低的一条经历/项目 → 重渲染,最多 5 轮"的强制单页逻辑(`one_page_lock.py::enforce_one_page`),但只接在了购物车批量投递路径(`shopping_cart/service.py`)上,用户实际在用的 Jobs→JD→Tailor 交互式 Tailor 页面走的是 `resume_workspace/service.py::rewrite()`,从未调用过它——`run_quality_gate` 里那层"单页"检查只是字符数估算(`markdown_len > 6500`),既不准也不会真的删内容。把 `enforce_one_page` 接入 `rewrite()`,用它返回的真实 `docx_bytes`/`pdf_bytes`/`final_resume` 替换原来的直接 `inject_content` 调用,`markdown` 的渲染时机也相应挪到裁剪之后,避免导出的 `.md` 里残留已经被裁掉的条目。

**量化结果**:
- 指标:同一职位/同一 demo 用户走完整流程后,`resume.pdf` 的实际渲染页数(`file` 命令读 PDF 头部页数)
- 改动前:2 pages,`word/document.xml` 段落级 dump 显示跨字段内容互相覆盖/重复,原始证据 `devlog/evidence/2026-08-11_resume-pdf-overflow-content-integrity-check_before.log`
- 改动后:1 page,53(或对应职位下)段全部对应回各自本该出现的字段,无重复;另用不同职位(Love's Travel Stops · Merchandising Analytics Intern)重新走一遍完整浏览器流程复测同样 1 page,原始证据 `devlog/evidence/2026-08-11_resume-pdf-overflow-content-integrity-check_after.log`
- 测量方法:`file resume.pdf` 读页数 + `xml.etree` 逐段落文本 dump 人工比对母本结构 + LibreOffice 转 PNG 目视核对

**踩过的坑**:
- 一开始怀疑是并发请求(前端 React StrictMode 在开发环境下确实观察到同一 JD 被重复创建 session、重复调用 `/agent` 两次)污染了共享可变状态,写了好几版 monkeypatch 脚本去复现"两个并发 `rewrite()` 互相脏读脏写"——排查后发现 `get_master_inventory` 每次调用都是从 SQLite `json.loads` 出来的全新 dict,并不共享引用,这个方向是错的。
- 第二个误判:以为是 `insert_missing_experiences`(把母版里没有的经历用"捐献者"段落格式插入)本身在拼接 run 时越界,写了逐步骤打印每个函数返回值的 trace 脚本,结果发现 `inject_ooxml` 四个内部步骤全程都是干净的——问题实际发生在 `inject_content()` 返回之后、`_store_version_file` 写盘之前的那几行,顺着这个范围往回读代码才看到那个被吞掉的 `NameError`。教训是:内容烂了不代表烂在生成内容的那一步,得用最小复现脚本逐段落/逐函数打点,不能只靠读代码推理"应该"是哪里出问题。

**结论/影响**:交互式 Tailor 流程现在和购物车批量投递路径共用同一套"真实渲染页数做依据"的单页强制逻辑,不再各写一套、行为不一致。副作用是 `rewrite()` 里多了一次同步 LibreOffice 渲染(单轮约几秒,超页需要裁剪时按轮数线性增加,最多 5 轮),用一次性拿到准确的 `pdf_bytes` 顺便省掉了 preview 接口原来"首次访问再异步转 PDF"的那次重复渲染。
