# 千问办公专家套件申报 · 线上表单即填清单 (Form Inputs)

> **官方提报表单入口**：[千问办公专家套件申报表单](https://alidocs.dingtalk.com/notable/share/form/v01YdgOk25LYmzypq4B_IeSGpBy_Pg2DlSS?source=link)  
> **官方对接人**：@陈志伟(横路)、@崔颢甜(颢青)  

---

### 一、 核心基础信息 (Basic Info)

- **名称 (name)**:
  ```text
  multi-agent-flow
  ```
- **展示名（中文） (displayName)**:
  ```text
  多专家协同研发工作流
  ```
- **展示名（英文） (displayNameEn)**:
  ```text
  Multi-Agent Dev Flow
  ```
- **发布方 (author.name)**:
  ```text
  任可
  ```
- **版本号 (version)**:
  ```text
  1.0.0
  ```
- **分类 (category)**:
  ```text
  产品开发 / 研发管理 (Product & Development)
  ```

---

### 二、 市场描述文案 (Descriptions)

- **描述（中文） (description)**:
  ```text
  面向敏捷研发团队与独立开发者的 8 位 AI 专家协同工作流套件。涵盖需求拆解（严经理）、架构设计（钱架构）、前后端开发（李开发/马前端）、代码审查（周审查）、自动化测试（章测试）、运维结项（吕改特）与文档沉淀（李文通）。具备契约驱动的 5 层防错状态机、全角色在制品并发控制、时序真实性防冲卡、人类专属验收确认门与 Git 提交硬拦截防护，让 AI 研发交付规范透明、质量可控。
  ```
- **描述（英文） (descriptionEn)**:
  ```text
  A production-grade multi-agent collaborative software engineering workflow suite powered by 8 specialized AI roles. Features strict state machine transitions, 5-tier anti-error quality gates, concurrency limit controls across all roles, human-only acceptance confirmation, and pre-commit Git security verification.
  ```

---

### 三、 交互与搜索标签 (Prompts & Tags)

- **初始提示词 (Initial Prompt)**:
  ```text
  /yy-flow start 帮我扫描当前代码库架构，并启动 8 位专家协同研发
  ```
- **标签 / 关键词 (keywords)**:
  ```text
  研发协同, 多Agent, 看板工作流, 质量门禁, 代码审查, 敏捷开发
  ```
- **核心优势介绍 (第 10 项)**:
  ```text
  【方法论与架构背书】
  本套件深度融合敏捷研发管理规范、Diátaxis 国际工程文档标准与软件防错机制（Poka-Yoke）。通过 8 位专家子代理（PM/架构/前后端开发/审查/测试/运维/文档）实现角色物理隔离，有效解决单 Agent“既当裁判又当选手”导致的伪完工与缺陷逃逸问题。

  【核心技术壁垒】
  1. 契约驱动 5 层防错门禁：严格执行强类型 JSON 契约传递、全角色在制品并发上限（WIP Limit）与防冲卡时序校验；
  2. 缺陷原卡闭环修复：测试不通过时严格原卡打回并挂载缺陷日志，严禁无序拆新单；
  3. 人类专属验收安全红线：严禁 AI 擅自标记结项，必须由人类用户终审确认，并辅以 Git Pre-commit 物理硬拦截防护。

  【实测表现与落地案例】
  1. 规模化实战验证：目前已累计实际支持执行 1500+ 项研发协同任务流转，保持平稳运行与全链路审计追溯；
  2. 严格工程质量：套件代码内置 229 项端到端自动化测试用例并通过全量回归验证，在全栈研发场景下实测降低 60% 以上的返工排查成本；
  3. 生态无缝兼容：原生支持千问办公（Qoder）标准，零外部服务依赖，支持离线安全运行、即开即用。
  ```

---

### 四、 附件上传与路径指引 (Attachments)

1. **套件压缩包 (Plugin Zip Package)**:
   - 文件路径：[dist/multi-agent-flow-qwen.zip](file:///Users/yuanyi/MyProject/vibeP/skills-design/2_多专家协同研发工作流/multi-agent-flow/dist/multi-agent-flow-qwen.zip)
   - 体积：**2.47 MB**（≤ 50 MB）
   - 条目数：**96 项**（< 1000）
2. **图标文件 (Icon Asset)**:
   - 文件路径：[assets/icon.png](file:///Users/yuanyi/MyProject/vibeP/skills-design/2_多专家协同研发工作流/multi-agent-flow/assets/icon.png)
   - 规格：**严格 200 × 200 像素**，PNG 格式（21.6 KB）
3. **方案书附件 (Proposal Document)**:
   - 文件路径：[docs/qwen/QWEN_PLUGIN_PROPOSAL.md](file:///Users/yuanyi/MyProject/vibeP/skills-design/2_多专家协同研发工作流/multi-agent-flow/docs/qwen/QWEN_PLUGIN_PROPOSAL.md)
