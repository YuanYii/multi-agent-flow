#!/usr/bin/env python3
"""
专家技术能力拓展引擎 (Tech Capability Expander)
根据项目识别出的语言、后端框架、前端框架、数据库存储、单测与安全机制，
为 6 个技术角色（DEV, FRONTEND, REVIEWER, QA, ARCHITECT, DEVOPS）
动态推导并生成 3~5 项高度契合项目技术架构的专业技术能力。
"""

from typing import Any, Dict, List


def _resolve_primary_backend(langs_lower: List[str], backend_lower: List[str], primary_lang: str, build_tools_lower: List[str]) -> str:
    """根据框架、构建清单与语言优先级确定后端主技术体系。"""
    # 1. 框架特征强特征判定
    if any("spring" in f or "mybatis" in f or "quarkus" in f or "micronaut" in f for f in backend_lower):
        return "java"
    if any("gin" in f or "fiber" in f or "echo" in f or "chi" in f for f in backend_lower):
        return "go"
    if any("fastapi" in f or "django" in f or "flask" in f or "agno" in f or "langchain" in f for f in backend_lower):
        return "python"
    if any("express" in f or "nest" in f or "koa" in f for f in backend_lower):
        return "node"
    if any("axum" in f or "actix" in f or "tokio" in f for f in backend_lower):
        return "rust"

    # 2. 构建工具特征判定
    if any("maven" in b or "gradle" in b for b in build_tools_lower):
        return "java"
    if any("cargo" in b for b in build_tools_lower):
        return "rust"

    # 3. 主语言字段判定（排除通用语言）
    pl_lower = primary_lang.lower()
    if "java" in pl_lower:
        return "java"
    if "go" in pl_lower:
        return "go"
    if "rust" in pl_lower:
        return "rust"
    if "python" in pl_lower:
        return "python"
    if any(k in pl_lower for k in ["typescript", "javascript", "node"]):
        return "node"

    # 4. 语言列表遍历兜底（非抢占式）
    if any("java" in l for l in langs_lower):
        return "java"
    if any("go" in l for l in langs_lower):
        return "go"
    if any("rust" in l for l in langs_lower):
        return "rust"
    if any("python" in l for l in langs_lower):
        return "python"
    if any("node" in l or "typescript" in l or "javascript" in l for l in langs_lower):
        return "node"

    return "generic"


def _normalize_caps_entry(raw_val: Any) -> List[str]:
    """将 expert_capabilities 中的单项规整为标准字符串列表 (至多 5 项)，防御字符串被按字符迭代拆散。"""
    if isinstance(raw_val, list):
        return [str(x) for x in raw_val if str(x).strip()][:5]
    if isinstance(raw_val, str) and raw_val.strip():
        return [raw_val.strip()]
    return []


def expand_expert_capabilities(arch_data: Dict[str, Any]) -> Dict[str, List[str]]:
    """根据架构数据提取并拓展 6 大技术角色的专属能力列表（每个角色 3~5 项）"""
    if not isinstance(arch_data, dict):
        return {}

    tech = arch_data.get("tech_stack", {}) or {}

    all_6_roles = ["dev", "frontend", "reviewer", "qa", "architect", "devops"]
    # 0. 优先模式：若配置中已包含全量 6 角色定版 expert_capabilities，快速直通返回
    custom_caps = tech.get("expert_capabilities")
    if isinstance(custom_caps, dict):
        normalized_custom = {r: _normalize_caps_entry(custom_caps.get(r)) for r in all_6_roles}
        if all(normalized_custom.get(r) for r in all_6_roles):
            return normalized_custom

    # 1. 规范化提取各技术维度
    langs = [l.get("name", "") if isinstance(l, dict) else str(l) for l in tech.get("languages", [])]
    langs_lower = [l.lower() for l in langs]
    primary_lang = langs[0] if langs else "通用语言"

    # 后端框架与技术提取
    backend_fws = []
    if "backend_frameworks" in tech and isinstance(tech["backend_frameworks"], list):
        backend_fws = [str(fw) for fw in tech["backend_frameworks"]]
    else:
        for fw in tech.get("frameworks", []):
            fw_name = fw.get("name", "") if isinstance(fw, dict) else str(fw)
            if not any(k in fw_name.lower() for k in ["react", "vue", "next", "nuxt", "svelte", "html", "css"]):
                backend_fws.append(fw_name)
    backend_lower = [f.lower() for f in backend_fws]

    # 前端框架与技术提取
    frontend_fws = []
    if "frontend_frameworks" in tech and isinstance(tech["frontend_frameworks"], list):
        frontend_fws = [str(fw) for fw in tech["frontend_frameworks"]]
    else:
        for fw in tech.get("frameworks", []):
            fw_name = fw.get("name", "") if isinstance(fw, dict) else str(fw)
            if any(k in fw_name.lower() for k in ["react", "vue", "next", "nuxt", "svelte", "html", "css", "ts", "js", "wiki"]):
                frontend_fws.append(fw_name)
    if not frontend_fws:
        app_type = (arch_data.get("project", {}) or {}).get("app_type", "")
        if app_type in ["fullstack", "frontend", "cli_and_fullstack"] or any("js" in l or "ts" in l for l in langs_lower):
            frontend_fws = ["Vanilla JavaScript / HTML5 / CSS3"]
    frontend_lower = [f.lower() for f in frontend_fws]

    # 测试框架提取
    testing = tech.get("testing", {}) or {}
    test_fw = testing.get("framework", "")
    test_lower = test_fw.lower()

    # 存储与数据库提取
    storage_list = [s.get("name", "") if isinstance(s, dict) else str(s) for s in tech.get("databases_and_storage", [])]
    storage_lower = [s.lower() for s in storage_list]

    # 安全与沙箱提取
    security_list = [s.get("name", "") if isinstance(s, dict) else str(s) for s in tech.get("security_and_sandbox", [])]
    security_lower = [s.lower() for s in security_list]

    # 部署与CI
    deploy = arch_data.get("deployment_and_ci", {}) or {}
    is_docker = bool(deploy.get("containerized", False))
    ci_provider = deploy.get("ci_cd_provider", "GitHub Actions")
    build_tools = [b.get("name", "") if isinstance(b, dict) else str(b) for b in tech.get("build_tools", [])]
    build_tools_lower = [b.lower() for b in build_tools]

    # 确定后端主技术体系
    primary_backend = _resolve_primary_backend(langs_lower, backend_lower, primary_lang, build_tools_lower)

    # 语言/栈专属单测框架推导与归一化
    java_test_fw = test_fw if any(k in test_lower for k in ["junit", "testng", "mockito", "spock"]) else "JUnit 5"
    go_test_fw = test_fw if any(k in test_lower for k in ["go test", "ginkgo", "gomega", "testify"]) else "go test"
    rust_test_fw = test_fw if any(k in test_lower for k in ["cargo", "tokio", "rstest"]) else "cargo test"
    node_test_fw = test_fw if any(k in test_lower for k in ["jest", "vitest", "mocha", "jasmine"]) else "Jest / Vitest"
    py_test_fw = test_fw if any(k in test_lower for k in ["pytest", "unittest", "nose"]) else "pytest"

    # =========================================================================
    # 2. 动态生成各专家专属能力 (3~5 项)
    # =========================================================================
    capabilities: Dict[str, List[str]] = {}

    # --- 1. 李开发 (flow-dev) ---
    dev_caps = []
    if primary_backend == "java":
        fw_name = backend_fws[0] if backend_fws else "Spring Boot"
        dev_caps.append(f"Java 与 {fw_name} 核心 RESTful 服务与业务逻辑开发")
        if any("mybatis" in f for f in backend_lower):
            dev_caps.append("MyBatis-Plus 数据持久层映射、分页插件与声明式事务一致性管理")
        elif any("jpa" in f or "hibernate" in f for f in backend_lower):
            dev_caps.append("Spring Data JPA 实体关系映射与事务一致性管理")
        if any("sqlite" in s for s in storage_lower):
            dev_caps.append("嵌入式 SQLite WAL 模式事务管理与并发连接池优化")
        elif any("mysql" in s or "postgresql" in s or "redis" in s for s in storage_lower):
            dev_caps.append("HikariCP 高性能连接池调优与多数据源事务治理")
        dev_caps.append("健壮的防御性编程、全局统一异常拦截 (ControllerAdvice) 与降级重试机制")
        dev_caps.append(f"针对性单元测试撰写与 Mockito 依赖打桩覆盖 ({java_test_fw})")
    elif primary_backend == "python":
        if any("fastapi" in f or "sse" in f or "async" in f for f in backend_lower):
            dev_caps.append("异步 I/O 并发与 SSE 流式长连接通讯编程 (asyncio / sse-starlette)")
        if any("sqlite" in s for s in storage_lower):
            dev_caps.append("嵌入式 SQLite WAL 模式事务管理与并发连接池优化")
        if any("agno" in f or "pydantic" in f for f in backend_lower):
            dev_caps.append("智能体工具链开发与 Pydantic 严格数据契约建模")
        if any("milvus" in s or "bm25" in s or "vector" in s for s in storage_lower):
            dev_caps.append("高维向量嵌入检索与 Rank-BM25 混合召回算法实现")
        dev_caps.append("健壮的防御性编程与异常降级重试退避机制")
        dev_caps.append(f"单元测试撰写与覆盖率达标 ({py_test_fw})")
    elif primary_backend == "go":
        dev_caps.append("Goroutine 高并发协程调度与 Channel 管道安全通信")
        dev_caps.append("高性能微服务接口与底层二进制通信协议解析")
        dev_caps.append("内存逃逸分析、并发锁竞态防御与零内存拷贝优化")
        dev_caps.append(f"单元测试撰写与基准测试覆盖 ({go_test_fw})")
        dev_caps.append("结构化错误处理与 Context 上下文链路超时控制")
    elif primary_backend == "node":
        dev_caps.append("TypeScript 严格类型系统与泛型接口契约设计")
        dev_caps.append("Node.js 异步非阻塞事件循环与高吞吐流式数据处理")
        dev_caps.append(f"单元测试撰写与覆盖率达标 ({node_test_fw})")
        dev_caps.append("RESTful / GraphQL 接口与 ORM 事务一致性管理")
        dev_caps.append("微服务解耦与分布式缓存数据一致性控制")
    elif primary_backend == "rust":
        fw_name = backend_fws[0] if backend_fws else "Axum"
        dev_caps.append(f"Rust 与 {fw_name} 核心异步业务逻辑实现")
        dev_caps.append(f"单元测试撰写与覆盖率达标 ({rust_test_fw})")
        dev_caps.append("所有权生命周期管理、零成本抽象与并发安全保证")
        dev_caps.append("Cargo 依赖治理与本地运行环境维护")
    else:
        fw_name = backend_fws[0] if backend_fws else "业务框架"
        dev_caps.append(f"{primary_lang} 与 {fw_name} 核心业务逻辑实现")
        dev_caps.append(f"单元测试撰写与覆盖率达标 ({py_test_fw})")
        dev_caps.append("依赖治理与异常重试容灾降级")

    capabilities["dev"] = dev_caps[:5]

    # --- 2. 马前端 (flow-frontend) ---
    fe_caps = []
    if any("nuxt" in f for f in frontend_lower):
        fe_caps.append("Nuxt 3 服务端渲染/全静态预渲染 (SSG) 架构与 Vue 3 组件状态治理")
        fe_caps.append("Pinia 状态树管理与复杂交互动画微渲染")
        if any("tailwind" in f for f in frontend_lower):
            fe_caps.append("TailwindCSS 响应式流体布局与深色/浅色主题自由切换")
        else:
            fe_caps.append("现代 CSS 变量驱动的暗黑/明亮双主题与流体微交互")
        fe_caps.append("Vite 构建优化与前端代码分包懒加载")
        fe_caps.append("多端适配与前端性能调优 (Core Web Vitals)")
    elif any("next" in f or "react" in f for f in frontend_lower):
        fe_caps.append("React / Next.js 现代组件化架构与 SSR/SSG 混合渲染优化")
        fe_caps.append("状态管理与高性能虚拟滚动列表交互设计")
        fe_caps.append("前端性能调优 (Core Web Vitals) 与首屏加载秒开优化")
        fe_caps.append("响应式流体布局与深色/浅色主题自由切换")
    elif any("vue" in f for f in frontend_lower):
        fe_caps.append("Vue 3 Composition API 组件封装与响应式状态治理")
        fe_caps.append("Pinia 状态树管理与复杂交互动画微渲染")
        fe_caps.append("Vite 构建优化与前端代码分包懒加载")
        fe_caps.append("多端适配与 CSS 变量主题定制体系")
    else:
        fe_caps.append("原生 DOM 高性能局部更新与零依赖 Web Components 组件封装")
        fe_caps.append("i18n 多语言国际化字典治理与双语动态切换架构")
        fe_caps.append("现代 CSS 变量驱动的暗黑/明亮双主题与流体微交互")
        fe_caps.append("实时 SSE 数据流消费、状态轮询与断线自动重连渲染")
        fe_caps.append("跨端响应式排版弹性适配与无障碍 (a11y) 语义化标准")

    capabilities["frontend"] = fe_caps[:5]

    # --- 3. 周审查 (flow-reviewer) ---
    rev_caps = []
    if any("detect-secrets" in s for s in security_lower) or any("secret" in s for s in security_lower):
        rev_caps.append("代码隐私脱敏与敏感凭据硬扫描 (detect-secrets 规则链)")
    else:
        rev_caps.append("硬编码凭据与 API 密钥泄漏深度安全审计")

    if primary_backend == "java":
        rev_caps.append("Java 线程安全、锁竞争、内存泄漏与数据库连接池耗尽专项审计")
        rev_caps.append("SQL 注入防范、MyBatis 动态 SQL 安全与接口越权漏洞审查")
    elif primary_backend == "python":
        rev_caps.append("异步协程死锁、事件循环阻塞与上下文泄漏专项审计")
        rev_caps.append("接口越权风险、输入边界注入与防御性编程校验")
    elif primary_backend == "go":
        rev_caps.append("Goroutine 协程泄漏与并发 Data Race 竞态死锁审查")
        rev_caps.append("接口越权风险、输入边界注入与防御性编程校验")
    elif primary_backend == "rust":
        rev_caps.append("Unsafe 代码块安全边界、内存泄漏与并发竞态死锁审查")
        rev_caps.append("接口越权风险、输入边界注入与防御性编程校验")
    else:
        rev_caps.append("并发安全、内存泄漏与异步时序死锁专项审计")
        rev_caps.append("接口越权风险、输入边界注入与防御性编程校验")

    if any("dulwich" in s for s in security_lower):
        rev_caps.append("纯 Python Git 沙箱隔离合规性与无外部二进制依赖审查")
    else:
        rev_caps.append("第三方依赖供应链安全与不可变构建沙箱审查")

    rev_caps.append("Clean Code 架构分层契约审查与圈复杂度控制")
    capabilities["reviewer"] = rev_caps[:5]

    # --- 4. 章测试 (flow-qa) ---
    qa_caps = []
    if primary_backend == "java":
        qa_fw_title = f"{java_test_fw} 与 Spring Boot Test" if any("spring" in f for f in backend_lower) else java_test_fw
        qa_caps.append(f"基于 {qa_fw_title} 的全链路端到端功能验收")
        qa_caps.append("基于 Mockito 与 MockMvc 的控制器接口自动化集成测试")
        qa_caps.append("核心业务状态机转移与边界极限条件测试覆盖")
        qa_caps.append("纯净测试沙箱隔离验证与环境零污染断言")
        qa_caps.append("异常注入、容灾恢复与超时退避边界测试")
    else:
        if "bdd" in test_lower or any("bdd" in s for s in testing.get("testing_frameworks", [])):
            qa_caps.append("Gherkin 语法与 BDD 行为驱动测试用例编写 (pytest-bdd)")
        else:
            qa_caps.append("全链路端到端功能验收与场景用例自动化编排")

        if "mutmut" in test_lower or any("mutmut" in s for s in testing.get("testing_frameworks", [])):
            qa_caps.append("变异测试 (Mutation Testing) 与核心状态机覆盖率穿透")
        else:
            qa_caps.append("核心业务状态机转移与边界极限条件测试覆盖")

        if primary_backend == "python":
            qa_caps.append("异步接口集成测试与 Mock 仿真服务端搭建 (pytest-asyncio)")
        elif primary_backend == "go":
            qa_caps.append("Go 原生 Table-Driven 基准测试与并发 Race 探测")
        elif primary_backend == "rust":
            qa_caps.append("Rust 异步集成测试与边界极限条件覆盖")
        else:
            qa_caps.append("接口自动化集成测试与 Mock 依赖仿真环境搭建")

        qa_caps.append("纯净测试沙箱隔离验证与环境零污染断言")
        qa_caps.append("异常注入、容灾恢复与超时退避边界测试")

    capabilities["qa"] = qa_caps[:5]

    # --- 5. 钱架构 (flow-architect) ---
    arch_caps = [
        "模块化单体 (Modular Monolith) 边界划分与松耦合接口解耦",
    ]
    if any("milvus" in s or "vector" in s or "agno" in b for s in storage_lower for b in backend_lower):
        arch_caps.append("智能体知识库与向量/关键词混合检索架构设计 (RAG 融合召回)")
    else:
        arch_caps.append("高可用领域模型设计与服务间接口契约制定")

    arch_caps.append("结构化 ADR (架构决策记录) 规范化沉淀与版本演进")
    if any("sqlite" in s for s in storage_lower):
        arch_caps.append("嵌入式本地存储并发吞吐量与连接池调优建模")
    else:
        arch_caps.append("系统存储拓扑选型与高并发数据读写分离设计")
    arch_caps.append("系统吞吐量建模、Token 预算控制与端到端链路可观测性设计")
    capabilities["architect"] = arch_caps[:5]

    # --- 6. 吕改特 (flow-devops) ---
    devops_caps = []
    if primary_backend == "java":
        devops_caps.append("Maven / Gradle 多模块依赖构建优化与生产 Jar 包分层打包")
        devops_caps.append("Spring Boot Actuator 健康检查与生产可观测性端点运维")
    elif primary_backend == "python":
        devops_caps.append("现代化 Python 包打包与自动化发布流水线 (setuptools-scm / Wheel)")
        devops_caps.append("本地环境健康体检、零污染构建与发布门禁审计")
    elif primary_backend == "node":
        devops_caps.append("npm / monorepo 自动化版本发布与工作区依赖管理")
        devops_caps.append("本地环境健康体检、零污染构建与发布门禁审计")
    elif primary_backend == "rust":
        devops_caps.append("Cargo 多目标架构跨平台静态编译与依赖精简打包")
        devops_caps.append("本地环境健康体检、零污染构建与发布门禁审计")
    else:
        devops_caps.append("多平台跨环境二进制编译构建与发布流水线治理")
        devops_caps.append("本地环境健康体检、零污染构建与发布门禁审计")

    devops_caps.append(f"CI/CD 自动化流水线维护与多平台测试矩阵编排 ({ci_provider})")
    if is_docker:
        devops_caps.append("隔离式 E2E 容器化测试沙箱编排 (Docker Sandbox)")
    else:
        devops_caps.append("本地无容器轻量运行环境配置与系统依赖隔离治理")

    devops_caps.append("SemVer 规范化 Git Tag 打标与 Release Notes 自动化提取")
    capabilities["devops"] = devops_caps[:5]

    # 若存在部分定制的角色专精能力，执行增量合并覆盖（保留定制，自动补全其余）
    if isinstance(custom_caps, dict):
        for r in all_6_roles:
            caps_list = _normalize_caps_entry(custom_caps.get(r))
            if caps_list:
                capabilities[r] = caps_list

    return capabilities
