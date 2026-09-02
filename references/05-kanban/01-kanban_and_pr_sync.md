# 05-看板运维与 PR 自动解阻规约 (Kanban & PR Sync Spec)

## 一、 Web 看板服务与端口自增探测

- 默认端口为 `32886`；
- 若端口被其他项目实例占用，自动在 `32886 - 32905` 区间向上探测可用端口并自动绑定；
- 同项目重复启动直接复用既有实例，并在终端输出可访问链接；
- 严格遵循 RFC 1918 局域网私网 IP 白名单与 Active Master Token 鉴权保护。

---

## 二、 GitHub PR 状态监听与自动解阻

- 运行 `python3 scripts/sync_pr_status.py` 或 `heartbeat.py --sync-pr`；
- 自动扫描【已阻塞】任务卡中关联的 PR 状态；
- 检测到 PR Merged 后，自动将任务推进至【已完成】，并唤起 PM 严经理执行终态验收。
