# 06-工程治理与审计度量规约 (Governance & Audit Spec)

## 一、 Git 分支模型与隔离规约

- 遵循单任务原子分支或独立 Worktree 隔离原则；
- 严禁未经审查直接在 `master` / `main` 上强制推送；
- 任务提审前必须运行 `check_stage_gate.py` 与 `check_secrets.py` 确保凭据合规。

---

## 二、 审计追踪与交付度量 (Telemetry)

- 所有状态跃迁强制写入 `user_data/logs/audit_trail.log`；
- 运行 `python3 scripts/metrics_analyzer.py` 分析任务交付周期（Lead Time）、等待时长与吞吐量；
- 运行 `python3 scripts/heartbeat.py` 巡检大盘健康度、超时滞留与并发超限预警。
