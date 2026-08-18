# HEARTBEAT.md - 看板状态巡检与卡顿任务监控

## 巡检任务清单 (Heartbeat Checklist)

当运行心跳巡检（Heartbeat Poll）时，Agent 自动执行以下检查：

1. **滞留任务检查**：
   - 检查是否有任务处于 `进行中` 超过 24 小时未更新过程描述；
   - 检查是否有任务处于 `审查中` 或 `测试中` 超过 12 小时未流转。
2. **并发上限核验**：
   - 检查开发人员处于 `进行中` 状态的任务是否超出并发上限 (≤3)。
3. **状态-处理人一致性核验**：
   - 检查处于 `审查中` 的任务处理人是否已设为 `REVIEWER`；
   - 检查处于 `测试中` 的任务处理人是否已设为 `QA`；
   - 检查处于 `已完成` / `已验收` 的任务处理人是否已设为 `PM`。
4. **结束时间必填强校验**：
   - 检查处于 `已完成` 或 `已验收` 的任务是否遗漏了 `结束时间`。

## 巡检脚本使用 (heartbeat.py)

上述 4 项已代码化为 `scripts/heartbeat.py`,只读扫描不写盘,支持阈值可配置（Windows 下统一使用 `python` 替代 `python3`）：

```bash
# 默认阈值 (24h/12h) 走全量 4 项检查 (Windows: python scripts/heartbeat.py)
python3 scripts/heartbeat.py

# 自定义滞留阈值 (如 12h/6h 适配快速迭代项目)
python3 scripts/heartbeat.py --stale-in-progress-hours 12 --stale-review-or-test-hours 6

# JSON 输出 (供 CI / 监控集成)
python3 scripts/heartbeat.py --json
```

退出码契约:
- `0` = 全部通过
- `1` = 有 critical 告警 (状态-处理人不一致 / 并发超限 / 终态缺 end_time)
- `2` = 致命错误 (适配器加载失败)

阈值覆盖规则:CLI 传入 > `workflow.config.yaml` 的 `heartbeat` 段 > 脚本默认 24h/12h。

## 审计日志配套工具 (audit_query.py / audit_rotate.py)

巡检只是"现状扫描",**历史追溯**还需审计日志:

- `python3 scripts/audit_query.py --task-id T0001` — 查某任务全量流转
- `python3 scripts/audit_query.py --failed` — 查所有失败事件
- `python3 scripts/audit_query.py --delegated-by USER` — 查代行记录
- `python3 scripts/audit_rotate.py --max-size-mb 50` — 日切分 + 单文件超 50MB 二次切,旧文件 gzip 归档至 `user_data/logs/archive/`
