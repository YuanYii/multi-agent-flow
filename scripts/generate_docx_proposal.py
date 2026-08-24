import os
import docx
from docx.shared import Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

template_path = "/Users/yuanyi/Downloads/32e9bad9-cf02-4c40-b19c-c0043f3f5179.docx"
out_path = "docs/qwen/千问办公专家套件方案书-多专家协同研发工作流.docx"
download_copy = "/Users/yuanyi/Downloads/千问办公专家套件方案书-多专家协同研发工作流.docx"

doc = docx.Document(template_path)

def set_cell(cell, text, bold=False, font_size=10):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text)
    run.font.name = "Microsoft YaHei"
    run.font.size = Pt(font_size)
    run.bold = bold
    run.font.color.rgb = RGBColor(30, 41, 59)

# 1. Fill basic info paragraphs
for p in doc.paragraphs:
    if "专家名称：" in p.text:
        p.text = "专家名称：多专家协同研发工作流 (multi-agent-flow)"
        p.runs[0].font.name = "Microsoft YaHei"
        p.runs[0].font.size = Pt(12)
        p.runs[0].bold = True
    elif "申报主体：" in p.text:
        p.text = "申报主体：任可"
        p.runs[0].font.name = "Microsoft YaHei"
        p.runs[0].font.size = Pt(12)
    elif "一句话定位：" in p.text:
        p.text = "一句话定位：面向敏捷研发团队与独立开发者的 8 位 AI 专家协同工作流套件，提供契约驱动的 5 层防错状态机、在制品并发控制与人类专属验收质量门禁。"
        p.runs[0].font.name = "Microsoft YaHei"
        p.runs[0].font.size = Pt(10.5)
    elif "差异化壁垒：" in p.text:
        p.text = (
            "差异化壁垒：\n"
            "1. 8 角色细粒度分工闭环：拆解为 PM 严经理、架构师钱架构、开发李开发、前端马前端、审查周审查、测试章测试、运维吕改特、文档李文通，避免单 Agent 自写自测自夸；\n"
            "2. 5 层防错状态机硬门禁：强类型 JSON 契约、在制品并发上限（WIP Limit）、防冲卡时序校验、缺陷原卡打回不拆单、Git Pre-commit 物理硬拦截；\n"
            "3. 人类专属【已验收】安全红线：严禁 AI Agent 自行标记已验收结项，必须由人类用户终审确认；\n"
            "4. 多客户端开箱即用：原生适配千问办公（Qoder）、Antigravity、Claude Code 等主流环境。"
        )
        p.runs[0].font.name = "Microsoft YaHei"
        p.runs[0].font.size = Pt(10.5)
    elif "2.1 目标用户一句话描述" in p.text:
        p.text = (
            "2.1 目标用户一句话描述\n"
            "使用千问办公/AI IDE 进行日常软件需求拆解、架构设计、编码测试与敏捷交付的技术主管、敏捷项目经理、全栈工程师及独立开发者。"
        )
        p.runs[0].font.name = "Microsoft YaHei"
        p.runs[0].font.size = Pt(10.5)
    elif "2.3 核心痛点" in p.text:
        p.text = (
            "2.3 核心痛点\n"
            "1. 单 Agent 角色混淆与盲目自夸：单个 AI 既当裁判又当选手，容易产生伪完工与缺陷逃逸；\n"
            "2. 多任务并发导致上下文爆炸与脏写冲突：缺乏在制品（WIP）并发上限控制，多任务同时修改引发代码污染；\n"
            "3. 过程失控与交付黑盒：缺少阶段门禁校验，AI 擅自跳过审查或测试直接提交，甚至擅自关闭任务。"
        )
        p.runs[0].font.name = "Microsoft YaHei"
        p.runs[0].font.size = Pt(10.5)

# 2. Fill Table 0: Persona 要素
t0 = doc.tables[0]
persona_data = [
    ("岗位", "技术主管 (Tech Lead) / 研发项目经理 (PM) / 全栈工程师 (Full-Stack Dev) / 独立开发者 (Indie Hacker)"),
    ("组织规模", "1~50 人的敏捷研发团队、数字化转型敏捷小组或独立开发工作室"),
    ("日常主要工作", "需求 WBS 拆解、架构设计与 ADR 决策、前后端业务编码、代码审查、自动化测试、缺陷修复、发布运维与工程文档沉淀"),
    ("常用工具", "千问办公、Qoder、VS Code、Git/GitHub、Docker、Postman、pytest/vitest"),
    ("核心 KPI", "研发迭代交付周期 (Lead Time)、缺陷逃逸率 (Defect Rate)、代码审查覆盖率 (CR Rate)、工程文档完备率"),
    ("成功指标", "AI 交付代码 0 悬挂、缺陷返工率降低 60% 以上、研发全流程各阶段状态与产物透明可溯")
]
for row_idx, (k, v) in enumerate(persona_data, start=1):
    set_cell(t0.rows[row_idx].cells[0], k, bold=True)
    set_cell(t0.rows[row_idx].cells[1], v)

# 3. Fill Table 1: 场景清单
t1 = doc.tables[1]
while len(t1.rows) > 1:
    tr = t1.rows[-1]._tr
    t1._tbl.remove(tr)

scenes = [
    ("1. 项目全自动扫描与架构初始化", "项目创建 / 首次接入", "新项目代码结构复杂，AI 无法快速摸清架构上下文与规范", "项目根目录源码 / git 仓库", "生成 project_architecture.yaml 架构档案与 8 专家上下文", "是 (生成架构配置文件)"),
    ("2. 需求 WBS 细化与任务拆解", "高频 (每次迭代 / 故事开工)", "大需求模糊、边界不清，AI 容易漏做或过度实现", "自然语言需求 / 用户故事", "生成拆解后的原子任务卡与责任专家分配 (PM 严经理调度)", "是 (写入看板任务卡)"),
    ("3. 架构设计与 ADR 决策记录", "中频 (技术选型 / 结构重构)", "架构决策缺失沉淀，后期成为团队维护黑盒", "技术选型或重构方案", "标准化 ADR 架构决策记录与技术栈依赖更新", "是 (写入 docs 架构文档)"),
    ("4. 原子任务开发与编码交付", "极高频 (日常任务实施)", "编码与契约脱节，前后端协作接口不一致", "待办任务卡 + 架构上下文", "业务功能代码实现、关联单测用例与变更清单", "是 (编写项目源代码)"),
    ("5. 代码审查与门禁审计", "高频 (任务提测前)", "代码风格不统一、潜在漏洞未检出、AI 盲目自夸", "开发提交的代码 diff 与交付说明", "严格 Review 意见 (P0-P3 缺陷清单、重构建议、门禁判定)", "否 (只读审计与评估)"),
    ("6. 自动化测试与缺陷原卡打回", "高频 (提测验证阶段)", "缺少自动化验证，测试不通过却拆新单导致追溯困难", "待测代码与测试用例", "测试执行日志、覆盖率报告；缺陷时原卡打回挂载缺陷", "是 (执行测试与状态打回)"),
    ("7. 人类专属验收与结项上锁", "高频 (任务终态验收)", "AI 擅自结项跳过人工把关，导致不可控交付", "测试通过的任务卡与验收清单", "人类核验通过后，状态变更为【已验收】，任务卡结项上锁", "是 (写入终态已验收状态)"),
    ("8. 可视化多角色实时看板查询", "随时 (日常进度追踪)", "多人/多 Agent 协同进度不透明，无法直观掌握卡点", "无 / yy-flow kanban 指令", "浏览器实时渲染 3 列看板与 8 角色在制品状态", "否 (只读可视化查询)"),
    ("9. Git 提交前置硬门禁拦截", "高频 (每次 git commit)", "存在进行中或未验收任务卡时误提交代码污染主干", "本地 git commit 动作", "Pre-commit 钩子校验；存在非终态卡时物理中断拦截", "否 (执行安全门禁判定)"),
    ("10. 敏捷迭代复盘与文档沉淀", "中频 (迭代结项 / 发版)", "迭代完成无沉淀，技术负债与质量数据丢失", "本期已完成任务集与审计记录", "生成敏捷复盘总结报告与全量工程文档归档", "是 (写入复盘与沉淀文档)")
]

for sc in scenes:
    row = t1.add_row()
    for col_idx, val in enumerate(sc):
        set_cell(row.cells[col_idx], val, bold=(col_idx==0))

# 4. Fill Table 2: 核心 Skills 清单
t2 = doc.tables[2]
while len(t2.rows) > 1:
    tr = t2.rows[-1]._tr
    t2._tbl.remove(tr)

skills_data = [
    ("yy-flow", "全生命周期多专家协同工作流编排与状态推进", "自然语言指令 / /yy-flow", "8 位专家按序流转，推进任务自需求至验收"),
    ("yy-flow-start", "项目开工与自动化技术栈扫描初始化", "/yy-flow start [项目路径]", "完成架构扫描、生成多专家上下文与看板初始配置"),
    ("yy-flow-status", "多专家当前任务状态与在制品进度查询", "/yy-flow status", "输出终端结构化看板与各角色在制品卡片详情"),
    ("yy-flow-kanban", "启动本地可视化 Web 看板服务", "/yy-flow kanban [端口]", "启动 HTTP 实时看板服务并输出可视化浏览器看板"),
    ("yy-flow-metrics", "研发质量度量与合规数据分析", "/yy-flow metrics", "输出流转周期、打回率、WIP 并发与质量得分报表")
]
for sk in skills_data:
    row = t2.add_row()
    for col_idx, val in enumerate(sk):
        set_cell(row.cells[col_idx], val, bold=(col_idx==0))

# 5. Fill Table 3: 连接器 MCP 清单
t3 = doc.tables[3]
while len(t3.rows) > 1:
    tr = t3.rows[-1]._tr
    t3._tbl.remove(tr)

mcp_row = t3.add_row()
set_cell(mcp_row.cells[0], "多专家协同原生引擎 (无外部独立 MCP)", bold=True)
set_cell(mcp_row.cells[1], "本套件采用本地轻量 CLI 脚本引擎与 Git 钩子驱动，无需依赖外部独立 MCP 服务，零额外网络开销，支持完全离线与私有化运行。")
set_cell(mcp_row.cells[2], "内置 35 项流转、门禁、度量与看板核心脚本工具（如 transition_task, verify_git_gate, check_stage_gate 等）")

# Save document
os.makedirs("docs/qwen", exist_ok=True)
doc.save(out_path)
doc.save(download_copy)
print(f"Successfully generated {out_path} and {download_copy}")
