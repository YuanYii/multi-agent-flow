#!/usr/bin/env python3
"""
Multi-Agent Flow · 零依赖简易 HTTP 看板 Web 服务 (增强 RESTful API 引擎)
默认端口 32886，被其他项目实例占用时自动向上探测 (32886-32905)；同项目重复启动直接复用既有实例
提供技能包内置离线看板 (kanban/offline_board.html) 与全量看板操作 REST 接口支持
"""

import sys
import os
import re
import json
import time
import atexit
import hashlib
import tempfile
import argparse
import socket
import urllib.request
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote
from http.server import HTTPServer, SimpleHTTPRequestHandler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
KANBAN_DIR = os.path.join(SKILL_ROOT, "kanban")

DEFAULT_PORT = 32886
PROBE_RANGE = 20
SERVICE_NAME = "multi-agent-flow-kanban"
HEALTH_API_VERSION = 1


def get_local_ip() -> str:
    """获取本机局域网 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _data_root() -> str:
    """数据根目录：与全脚本同链（env > legacy > CWD），共享安装下指向宿主项目"""
    sys.path.insert(0, SCRIPT_DIR)
    import paths as _paths
    return _paths.resolve_data_root()


_DATA_ROOT = _data_root()
USER_DATA_BOARD = os.path.join(_DATA_ROOT, "user_data", "board.json")
USER_DATA_PREFERENCES = os.path.join(_DATA_ROOT, "user_data", "preferences.json")
AUDIT_LOG_FILE = os.path.join(_DATA_ROOT, "user_data", "logs", "audit_trail.log")
LOCK_FILE = USER_DATA_BOARD + ".seq.lock"
KANBAN_RUNTIME_FILE = os.path.join(_DATA_ROOT, "user_data", "kanban_server.json")


def compute_board_version() -> str:
    """计算 board.json 的版本哈希 sha256[:12]；文件缺失或读取失败返回空串。

    供 GET /api/version 探测与第二层 HTTP 乐观锁（If-Match / v）比对使用。
    """
    try:
        with open(USER_DATA_BOARD, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except Exception:
        return ""


def compute_project_fingerprint(data_root: str) -> str:
    """项目实例指纹：data_root 绝对路径哈希。

    必须哈希 data_root 而非 skill_root —— 多项目共享同一份 Skill 拷贝时
    skill_root 相同，若以其为指纹会误"复用"彼此的服务，重新引入串数据问题。
    """
    return hashlib.sha1(os.path.abspath(data_root).encode("utf-8")).hexdigest()[:16]


# 启动成功后由 start_server 填充；/api/health 的数据源
SERVER_STATE = {
    "service": SERVICE_NAME,
    "version": HEALTH_API_VERSION,
    "fingerprint": "",
    "port": None,
    "pid": os.getpid(),
    "data_root": "",
}


from _lib.core import file_lock


_BOARD_MEMORY_CACHE = {
    "mtime": 0.0,
    "size": -1,
    "cards": []
}


def read_board_data() -> list:
    """安全读取 board.json，具备基于文件 mtime 与 size 的高速内存缓存"""
    os.makedirs(os.path.dirname(USER_DATA_BOARD), exist_ok=True)
    if not os.path.exists(USER_DATA_BOARD):
        with open(USER_DATA_BOARD, "w", encoding="utf-8") as f:
            f.write("[]")
        _BOARD_MEMORY_CACHE["mtime"] = 0.0
        _BOARD_MEMORY_CACHE["size"] = 2
        _BOARD_MEMORY_CACHE["cards"] = []
        return []

    try:
        stat = os.stat(USER_DATA_BOARD)
        if (stat.st_mtime == _BOARD_MEMORY_CACHE["mtime"] and
            stat.st_size == _BOARD_MEMORY_CACHE["size"]):
            return [dict(c) for c in _BOARD_MEMORY_CACHE["cards"]]

        with open(USER_DATA_BOARD, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                _BOARD_MEMORY_CACHE["mtime"] = stat.st_mtime
                _BOARD_MEMORY_CACHE["size"] = stat.st_size
                _BOARD_MEMORY_CACHE["cards"] = data
                return [dict(c) for c in data]
            return []
    except Exception:
        return []


def atomic_write_board_data(cards: list) -> bool:
    """持有排他锁 + Temp 文件原子替换写入 board.json"""
    os.makedirs(os.path.dirname(USER_DATA_BOARD), exist_ok=True)
    target_dir = os.path.dirname(USER_DATA_BOARD)

    # 规范化 seq 序号
    for idx, card in enumerate(cards, start=1):
        card["seq"] = idx

    handle = None
    try:
        handle = file_lock.acquire_lock(LOCK_FILE, blocking=True, timeout=5.0)
        with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
            json.dump(cards, tf, indent=2, ensure_ascii=False)
            tmp_name = tf.name
        os.replace(tmp_name, USER_DATA_BOARD)
        return True
    except Exception as e:
        sys.stderr.write(f"[ERROR] atomic_write_board_data failed: {e}\n")
        return False
    finally:
        if handle:
            file_lock.release_lock(handle)


def atomic_mutate_board_data(mutate_fn, expected_version: str = "") -> tuple:
    """持文件排他锁执行 board.json 变更，支持 HTTP 409 乐观并发控制。

    mutate_fn(cards: list) -> (success: bool, status_code: int, message: str, result_data: dict)
    返回: (status_code, message, result_data)
    - 若指定 expected_version 且持锁比对当前哈希不一致 -> 返回 (409, "conflict", {"v": current_v})
    - 否则执行 mutate_fn，原子替换落盘，返回 (status_code, message, {**result_data, "v": new_v})
    """
    os.makedirs(os.path.dirname(USER_DATA_BOARD), exist_ok=True)
    target_dir = os.path.dirname(USER_DATA_BOARD)
    handle = None
    try:
        handle = file_lock.acquire_lock(LOCK_FILE, blocking=True, timeout=5.0)
        current_v = compute_board_version()
        if expected_version and expected_version != current_v:
            return 409, "数据已被其他操作修改，发生版本冲突 (conflict)", {"v": current_v}

        cards = read_board_data()
        success, code, msg, res_data = mutate_fn(cards)
        if not success:
            return code, msg, res_data

        # 规范化 seq 序号
        for idx, card in enumerate(cards, start=1):
            card["seq"] = idx

        with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
            json.dump(cards, tf, indent=2, ensure_ascii=False)
            tmp_name = tf.name
        os.replace(tmp_name, USER_DATA_BOARD)

        new_v = compute_board_version()
        if isinstance(res_data, dict):
            res_data["v"] = new_v
        elif res_data is None:
            res_data = {"v": new_v}
        return code, msg, res_data
    except Exception as e:
        sys.stderr.write(f"[ERROR] atomic_mutate_board_data failed: {e}\n")
        return 500, f"数据写入磁盘失败: {e}", None
    finally:
        if handle:
            file_lock.release_lock(handle)


BOARD_TITLE_SUFFIX = "Multi Agent任务看板"


def read_project_name() -> str:
    """从运行态 workflow 配置读取项目名（project.name），失败返回空串。"""
    try:
        import yaml
        sys.path.insert(0, SCRIPT_DIR)
        import paths as _paths
        config_file = _paths.resolve_runtime_config()
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        name = str(((cfg.get("project") or {}).get("name")) or "").strip()
        # 模板占位值不展示
        return "" if name in ("", "Sample-Project", "project_name") else name
    except Exception:
        return ""


def default_board_title() -> str:
    """默认看板标题：{项目名} Multi Agent任务看板（无项目名时退化为通用标题）"""
    proj = read_project_name()
    return f"{proj} {BOARD_TITLE_SUFFIX}" if proj else "多专家Agent协作任务看板"


def read_preferences_data() -> dict:
    """读取看板布局与偏好配置（title 未定制时注入项目名动态默认值）"""
    dynamic_default = default_board_title()
    if not os.path.exists(USER_DATA_PREFERENCES):
        return {
            "title": dynamic_default,
            "theme": "light",
            "row_height": 55,
            "card_visible_fields": ["id", "name", "assignee", "act_hours", "status"],
            "column_widths": {}
        }
    try:
        with open(USER_DATA_PREFERENCES, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                # 未定制过标题（缺省/旧默认值）→ 跟随项目名动态默认
                title = str(data.get("title") or "").strip()
                if title in ("", "多专家Agent协作任务看板"):
                    data["title"] = dynamic_default
                return data
    except Exception:
        pass
    return {"title": dynamic_default}


def atomic_write_preferences_data(pref: dict) -> bool:
    """原子写入 preferences.json"""
    os.makedirs(os.path.dirname(USER_DATA_PREFERENCES), exist_ok=True)
    target_dir = os.path.dirname(USER_DATA_PREFERENCES)
    try:
        with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
            json.dump(pref, tf, indent=2, ensure_ascii=False)
            tmp_name = tf.name
        os.replace(tmp_name, USER_DATA_PREFERENCES)
        return True
    except Exception as e:
        sys.stderr.write(f"[ERROR] atomic_write_preferences_data failed: {e}\n")
        return False


def allocate_next_task_id(cards: list) -> str:
    r"""分配连续未占用的 T\d+ 编号 (如 T0001 -> T0002)"""
    max_id = 0
    for c in cards:
        cid = str(c.get("id", ""))
        m = re.match(r"^T(\d+)$", cid)
        if m:
            max_id = max(max_id, int(m.group(1)))
    return f"T{max_id + 1:04d}"


# 角色编码/子代理标识 → 角色名（与 transition_task.ROLE_NAME_MAP 同源；
# 看板 assignee 恒存中文名，编码仅作入参别名）
ROLE_NAME_MAP = {
    "PM": "严经理", "ARCHITECT": "钱架构", "DEV": "李开发",
    "FRONTEND": "马前端", "REVIEWER": "周审查", "QA": "章测试",
    "DOCS": "李文通", "DEVOPS": "吕改特",
    "pm": "严经理", "architect": "钱架构", "dev": "李开发",
    "frontend": "马前端", "reviewer": "周审查", "qa": "章测试",
    "docs": "李文通", "devops": "吕改特",
    "flow-pm": "严经理", "flow-architect": "钱架构", "flow-dev": "李开发",
    "flow-frontend": "马前端", "flow-reviewer": "周审查", "flow-qa": "章测试",
    "flow-docs": "李文通", "flow-devops": "吕改特",
    "pm_user": "严经理", "architect_user": "钱架构",
    "dev_user": "李开发", "dev_user_1": "李开发", "dev_user_2": "李开发",
    "frontend_user": "马前端", "reviewer_user": "周审查", "reviewer_user_1": "周审查",
    "qa_user": "章测试", "docs_user": "李文通", "devops_user": "吕改特",
}


def normalize_role_name(val) -> str:
    """角色编码/子代理 ID/占位符 归一化为中文角色名；未命中原样返回"""
    if not val:
        return ""
    key = str(val).strip()
    return ROLE_NAME_MAP.get(key, ROLE_NAME_MAP.get(key.lower(), ROLE_NAME_MAP.get(key.upper(), key)))


# 流程节点 ID（如 T0001-N03）：任务ID + 任务内单调递增节点序号
_NODE_ID_RE = re.compile(r"\b(T\d+)-N?(\d+)\b")


def allocate_node_seq(card: dict) -> int:
    """锁外计算卡片 process 内下一节点序号（调用方须持 seq.lock 写锁）。

    与 offline_board_adapter._next_node_seq 同构：max(N)+1，只追加、回滚烧号不复用。
    """
    max_n = 0
    text = str(card.get("process") or "")
    tid = str(card.get("id", ""))
    for m in _NODE_ID_RE.finditer(text):
        if m.group(1) == tid:
            max_n = max(max_n, int(m.group(2)))
    return max_n + 1


def append_audit_log(task_id: str, role: str, from_status: str, to_status: str, operator: str, comment: str = ""):
    """记录结构化审计事件"""
    os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
    event = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
        "role": role,
        "from_status": from_status,
        "to_status": to_status,
        "operator": operator,
        "comment": comment
    }
    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------
# GET /api/tasks 筛选 / 排序 / 分页 参数处理
# ---------------------------------------------------------------
PAGE_SIZES_WHITELIST = (10, 20, 50, 100)
SORT_FIELDS_WHITELIST = ("seq", "id", "est_hours", "act_hours", "start_date", "end_date")
ORDER_WHITELIST = ("asc", "desc")


def _sort_key(card: dict, field: str):
    """排序键提取：数值字段按数值比较（est_hours/act_hours/seq/id），日期与字符串字段按字典序"""
    if field in ("est_hours", "act_hours"):
        try:
            return float(card.get(field) or 0)
        except (TypeError, ValueError):
            return 0.0
    if field == "seq":
        try:
            return int(card.get("seq") or 0)
        except (TypeError, ValueError):
            return 0
    if field == "id":
        m = re.match(r"^T(\d+)$", str(card.get("id", "")))
        return int(m.group(1)) if m else 0
    return str(card.get(field) or "")


class KanbanHTTPRequestHandler(SimpleHTTPRequestHandler):
    """看板 HTTP 请求分发引擎：支持静态资源与看板 RESTful API"""

    # 补齐静态资源 MIME 表（字体/矢量图/现代图片/文档类）
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
        ".avif": "image/avif",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".eot": "application/vnd.ms-fontobject",
        ".json": "application/json; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=KANBAN_DIR, **kwargs)

    def end_headers(self):
        # 统一追加跨域与防强缓存响应头
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, If-Match")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def _send_json_resp(self, code: int = 200, message: str = "success", data=None, http_status: int = 200):
        """格式化发送统一响应结构体"""
        payload = {
            "code": code,
            "message": message,
            "data": data if data is not None else {},
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(http_status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _parse_request_json(self):
        """解析 HTTP 请求体 JSON 载荷"""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return None
        raw_body = self.rfile.read(content_length).decode("utf-8")
        return json.loads(raw_body)

    def _extract_expected_version(self, body_data=None) -> str:
        """从 If-Match / X-Board-Version 请求头或请求体 (_v/v/expected_v) 提取期望版本哈希"""
        if_match = (self.headers.get("If-Match") or "").strip().strip('"').strip("'")
        if if_match and if_match != "*":
            return if_match[:12]
        x_ver = (self.headers.get("X-Board-Version") or "").strip()
        if x_ver:
            return x_ver[:12]
        if isinstance(body_data, dict):
            for k in ("_v", "v", "expected_v"):
                v_val = str(body_data.get(k) or "").strip()
                if v_val:
                    return v_val[:12]
        return ""

    # -------------------------------------------------------------
    # GET 路由分发
    # -------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 1. 根路径重定向
        if path in ("/", "/index.html", "/offline_board"):
            self.path = "/offline_board.html"
            return super().do_GET()

        # 2. 原生/向后兼容路由：/board.json
        if path in ("/board.json", "/user_data/board.json"):
            cards = read_board_data()
            content = json.dumps(cards, indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
            return

        # 3. REST API: GET /api/tasks (任务列表：组合筛选 + 排序 + 分页)
        if path == "/api/tasks" or path == "/api/cards":
            cards = read_board_data()
            status_filter = query.get("status", [None])[0]
            assignee_filter = query.get("assignee", [None])[0]
            stage_filter = query.get("stage", [None])[0]
            wp_filter = query.get("wp", [None])[0]
            keyword = query.get("keyword", [None])[0] or query.get("q", [None])[0]

            filtered = cards
            if status_filter:
                filtered = [c for c in filtered if c.get("status") == status_filter]
            if assignee_filter:
                filtered = [c for c in filtered if c.get("assignee") == assignee_filter]
            if stage_filter:
                filtered = [c for c in filtered if c.get("stage") == stage_filter or c.get("wp") == stage_filter]
            if wp_filter:
                filtered = [c for c in filtered if c.get("wp") == wp_filter]
            if keyword:
                kw = keyword.lower()
                filtered = [
                    c for c in filtered
                    if kw in str(c.get("id", "")).lower()
                    or kw in str(c.get("name", "")).lower()
                    or kw in str(c.get("assignee", "")).lower()
                    or kw in str(c.get("stage", "")).lower()
                    or kw in str(c.get("wp", "")).lower()
                    or kw in str(c.get("remarks", "")).lower()
                    or kw in str(c.get("wbs", "")).lower()
                ]

            # ---- 排序参数解析（白名单 + 强校验） ----
            sort = (query.get("sort", [None])[0] or "seq").strip().lower()
            order = (query.get("order", [None])[0] or "asc").strip().lower()
            if sort not in SORT_FIELDS_WHITELIST:
                self._send_json_resp(400, f"非法排序字段 sort=[{sort}]，支持: {','.join(SORT_FIELDS_WHITELIST)}", None, http_status=400)
                return
            if order not in ORDER_WHITELIST:
                self._send_json_resp(400, f"非法排序方向 order=[{order}]，支持: asc,desc", None, http_status=400)
                return
            filtered = sorted(filtered, key=lambda c: _sort_key(c, sort), reverse=(order == "desc"))

            # ---- 分页参数解析 ----
            # 契约：省略 page/size 或 size=all → 全量命中集（看板视图）；
            #       携带 page 或 size 数值 → 分页模式（page 默认 1，size 默认 20）
            page_param = query.get("page", [None])[0]
            size_param = query.get("size", [None])[0]
            page = 1
            size = 20
            full_mode = (page_param is None and size_param is None)
            if size_param is not None:
                s_raw = size_param.strip().lower()
                if s_raw == "all":
                    full_mode = True
                else:
                    try:
                        size = int(s_raw)
                    except ValueError:
                        self._send_json_resp(400, f"非法每页条数 size=[{size_param}]，支持: 10,20,50,100,all", None, http_status=400)
                        return
                    if size not in PAGE_SIZES_WHITELIST:
                        self._send_json_resp(400, f"非法每页条数 size=[{size_param}]，支持: 10,20,50,100,all", None, http_status=400)
                        return
            if not full_mode and page_param is not None:
                try:
                    page = int(page_param)
                except ValueError:
                    self._send_json_resp(400, f"非法页码 page=[{page_param}]，必须为 ≥1 的整数", None, http_status=400)
                    return
                if page < 1:
                    self._send_json_resp(400, f"非法页码 page=[{page_param}]，必须为 ≥1 的整数", None, http_status=400)
                    return

            total = len(filtered)
            if full_mode:
                items = filtered
            else:
                start = (page - 1) * size
                items = filtered[start:start + size]

            self._send_json_resp(200, "success", {
                "total": total,
                "items": items,
                "v": compute_board_version()
            })
            return

        # 4. REST API: GET /api/tasks/{task_id} (单任务详情)
        m_task = re.match(r"^/api/tasks/([A-Za-z0-9_\-]+)$", path)
        if m_task:
            task_id = m_task.group(1)
            cards = read_board_data()
            found = next((c for c in cards if c.get("id") == task_id), None)
            if found:
                self._send_json_resp(200, "success", found)
            else:
                self._send_json_resp(404, f"未找到任务 [{task_id}]", None, http_status=404)
            return

        # 5. REST API: GET /api/board/meta 或 /api/preferences (偏好与标题配置)
        if path in ("/api/board/meta", "/api/preferences"):
            pref = read_preferences_data()
            self._send_json_resp(200, "success", pref)
            return

        # 6. REST API: GET /api/version (board.json 版本哈希，供前端轮询与乐观锁)
        if path == "/api/version":
            self._send_json_resp(200, "success", {"v": compute_board_version()})
            return

        # 7. REST API: GET /api/health (实例健康与项目指纹，供端口复用判定)
        if path == "/api/health":
            self._send_json_resp(200, "success", dict(SERVER_STATE))
            return

        # 8. 静态资源 Range 请求支持（音视频拖动/断点续传）
        if self.headers.get("Range"):
            if self._serve_range_request(path):
                return

        # 静态资源请求
        return super().do_GET()

    def _serve_range_request(self, path: str) -> bool:
        """处理静态文件 Range: bytes=start-end 请求（单段）；无法处理时返回 False 交由父类全量响应。"""
        fs_path = self.translate_path(self.path)
        if not os.path.isfile(fs_path):
            return False

        m = re.match(r"^bytes=(\d*)-(\d*)$", self.headers.get("Range", "").strip())
        if not m:
            return False
        start_s, end_s = m.group(1), m.group(2)
        if start_s == "" and end_s == "":
            return False

        total = os.path.getsize(fs_path)
        if start_s == "":
            suffix_len = int(end_s)
            if suffix_len <= 0:
                return self._send_range_error(total)
            start = max(total - suffix_len, 0)
            end = total - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else total - 1
            if start >= total or start > end:
                return self._send_range_error(total)
            end = min(end, total - 1)

        length = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(fs_path))
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        try:
            with open(fs_path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except Exception:
            pass
        return True

    def _send_range_error(self, total: int) -> bool:
        """Range 越界：416 + Content-Range: bytes */total"""
        self.send_response(416)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Range", f"bytes */{total}")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    # -------------------------------------------------------------
    # POST 路由分发
    # -------------------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            body_data = self._parse_request_json()
        except Exception as e:
            self._send_json_resp(400, f"JSON 载荷解析失败: {e}", None, http_status=400)
            return

        expected_v = self._extract_expected_version(body_data)

        # 1. 向后兼容：POST /board.json (全量数组落盘)
        if path in ("/board.json", "/user_data/board.json", "/api/save_board"):
            if not isinstance(body_data, list):
                self._send_json_resp(400, "载荷必须为任务卡片数组", None, http_status=400)
                return

            def _mutate_bulk(cards):
                cards.clear()
                cards.extend(body_data)
                return True, 200, "保存成功", {"count": len(cards)}

            code, msg, data = atomic_mutate_board_data(_mutate_bulk, expected_version=expected_v)
            self._send_json_resp(code, msg, data, http_status=code)
            return

        # 2. REST API: POST /api/tasks 或 /api/cards (创建新任务，支持排他锁自增 ID)
        if path in ("/api/tasks", "/api/cards"):
            if not isinstance(body_data, dict):
                self._send_json_resp(400, "请求体必须为 JSON 对象", None, http_status=400)
                return

            name = str(body_data.get("name", "")).strip()
            if not name:
                self._send_json_resp(400, "任务名称 (name) 不能为空", None, http_status=400)
                return

            def _mutate_create(cards):
                req_id = str(body_data.get("id", "")).strip()
                if req_id:
                    if any(c.get("id") == req_id for c in cards):
                        return False, 409, f"任务编号 [{req_id}] 已存在", None
                    new_id = req_id
                else:
                    new_id = allocate_next_task_id(cards)

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                status = body_data.get("status") or "待开始"
                assignee = normalize_role_name(body_data.get("assignee")) or "李开发"
                remarks = body_data.get("remarks", "")

                new_card = {
                    "id": new_id,
                    "seq": len(cards) + 1,
                    "name": name,
                    "stage": body_data.get("stage", "S6 工作流集成测试"),
                    "wp": body_data.get("wp", "WP-自定义"),
                    "wbs": body_data.get("wbs", ""),
                    "assignee": assignee,
                    "status": status,
                    "handler": body_data.get("handler", assignee),
                    "est_hours": float(body_data.get("est_hours", 0) or 0),
                    "act_hours": float(body_data.get("act_hours", 0) or 0),
                    "start_date": body_data.get("start_date", now_str),
                    "end_date": body_data.get("end_date", ""),
                    "remarks": remarks,
                    "process": ""
                }

                node_id = f"{new_id}-N01"
                init_process = body_data.get("process") or \
                    f"[{node_id}]  [{now_str}]  建单并进入【{status}】，操作人: {assignee}" + \
                    (f"\n操作说明: {remarks}" if remarks else "")
                new_card["process"] = init_process

                cards.append(new_card)
                append_audit_log(new_id, "PM", "无", status, assignee, f"创建任务: {name}")
                return True, 200, f"成功创建任务 {new_id}", new_card

            code, msg, data = atomic_mutate_board_data(_mutate_create, expected_version=expected_v)
            self._send_json_resp(code, msg, data, http_status=code)
            return

        # 3. REST API: POST /api/tasks/batch-delete 或 /api/cards/batch-delete (批量删除)
        if path in ("/api/tasks/batch-delete", "/api/cards/batch-delete"):
            if not isinstance(body_data, dict) or ("task_ids" not in body_data and "ids" not in body_data):
                self._send_json_resp(400, "缺少 task_ids 或 ids 列表", None, http_status=400)
                return

            raw_ids = body_data.get("task_ids") or body_data.get("ids") or []
            task_ids_to_del = set(raw_ids)

            def _mutate_batch_del(cards):
                initial_count = len(cards)
                remaining = [c for c in cards if c.get("id") not in task_ids_to_del]
                cards.clear()
                cards.extend(remaining)
                deleted_count = initial_count - len(cards)
                for tid in task_ids_to_del:
                    append_audit_log(tid, "PM", "-", "已删除", "用户", f"批量删除任务: {tid}")
                return True, 200, f"成功删除 {deleted_count} 条任务", {
                    "deleted_count": deleted_count,
                    "deleted": deleted_count,
                    "remaining_total": len(cards)
                }

            code, msg, data = atomic_mutate_board_data(_mutate_batch_del, expected_version=expected_v)
            self._send_json_resp(code, msg, data, http_status=code)
            return

        # 4. REST API: POST /api/tasks/{task_id}/transition 或 /api/cards/{task_id}/transition
        m_trans = re.match(r"^/api/(?:tasks|cards)/([A-Za-z0-9_\-]+)/transition$", path)
        if m_trans:
            task_id = m_trans.group(1)
            if not isinstance(body_data, dict):
                self._send_json_resp(400, "请求体格式不正确", None, http_status=400)
                return

            target_status = body_data.get("target_status")
            if not target_status:
                self._send_json_resp(400, "缺少 target_status 目标状态", None, http_status=400)
                return

            operator_name = normalize_role_name(body_data.get("operator_name")) or "李开发"
            comment = body_data.get("comment", "").strip()

            def _mutate_trans(cards):
                card = next((c for c in cards if c.get("id") == task_id), None)
                if not card:
                    return False, 404, f"未找到任务 [{task_id}]", None

                from_status = card.get("status", "待开始")
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                card["status"] = target_status
                new_assignee = normalize_role_name(body_data.get("assignee"))
                if new_assignee:
                    card["assignee"] = new_assignee
                if target_status in ("已完成", "已验收"):
                    card["end_date"] = now_str

                node_id = f"{task_id}-N{allocate_node_seq(card):02d}"
                log_text = f"[{node_id}]  [{now_str}]  状态由【{from_status}】更新至【{target_status}】，操作人: {operator_name}"
                if comment:
                    log_text += f"\n操作说明: {comment}"

                current_process = card.get("process", "")
                card["process"] = f"{current_process}\n{log_text}".strip()

                audit_role = body_data.get("operator_role") or "USER"
                append_audit_log(task_id, audit_role, from_status, target_status, operator_name, comment)
                return True, 200, "状态流转成功", {
                    "id": task_id,
                    "node_id": node_id,
                    "from_status": from_status,
                    "to_status": target_status,
                    "history_entry": log_text
                }

            code, msg, data = atomic_mutate_board_data(_mutate_trans, expected_version=expected_v)
            self._send_json_resp(code, msg, data, http_status=code)
            return

        self._send_json_resp(404, "Not Found", None, http_status=404)

    # -------------------------------------------------------------
    # PUT 路由分发
    # -------------------------------------------------------------
    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            body_data = self._parse_request_json()
        except Exception as e:
            self._send_json_resp(400, f"JSON 载荷解析失败: {e}", None, http_status=400)
            return

        expected_v = self._extract_expected_version(body_data)

        # 1. REST API: PUT /api/tasks/reorder 或 /api/cards/reorder (拖拽卡片重排序)
        if path in ("/api/tasks/reorder", "/api/cards/reorder"):
            if not isinstance(body_data, dict) or ("ordered_task_ids" not in body_data and "ordered_ids" not in body_data):
                self._send_json_resp(400, "缺少 ordered_task_ids 或 ordered_ids", None, http_status=400)
                return

            ordered_ids = body_data.get("ordered_task_ids") or body_data.get("ordered_ids") or []

            def _mutate_reorder(cards):
                cards_map = {c.get("id"): c for c in cards}
                new_ordered_cards = []
                for tid in ordered_ids:
                    if tid in cards_map:
                        new_ordered_cards.append(cards_map.pop(tid))
                new_ordered_cards.extend(cards_map.values())
                cards.clear()
                cards.extend(new_ordered_cards)
                return True, 200, "排序保存成功", {"count": len(cards), "reordered": len(ordered_ids)}

            code, msg, data = atomic_mutate_board_data(_mutate_reorder, expected_version=expected_v)
            self._send_json_resp(code, msg, data, http_status=code)
            return

        # 2. REST API: PUT /api/board/meta 或 /api/preferences (更新偏好配置与标题)
        if path in ("/api/board/meta", "/api/preferences"):
            if not isinstance(body_data, dict):
                self._send_json_resp(400, "请求体必须为 JSON 对象", None, http_status=400)
                return

            current_pref = read_preferences_data()
            current_pref.update(body_data)
            if atomic_write_preferences_data(current_pref):
                self._send_json_resp(200, "看板偏好与标题保存成功", current_pref)
            else:
                self._send_json_resp(500, "偏好设置落盘失败", None, http_status=500)
            return

        # 3. REST API: PUT /api/tasks/{task_id} 或 /api/cards/{task_id} (编辑更新单条任务)
        m_task = re.match(r"^/api/(?:tasks|cards)/([A-Za-z0-9_\-]+)$", path)
        if m_task:
            task_id = m_task.group(1)
            if not isinstance(body_data, dict):
                self._send_json_resp(400, "请求体必须为 JSON 对象", None, http_status=400)
                return

            def _mutate_put(cards):
                card = next((c for c in cards if c.get("id") == task_id), None)
                if not card:
                    return False, 404, f"未找到任务 [{task_id}]", None

                updatable_fields = [
                    "name", "stage", "wp", "wbs", "assignee", "handler",
                    "status", "est_hours", "act_hours", "start_date",
                    "end_date", "remarks", "process"
                ]
                updated_keys = []
                for k in updatable_fields:
                    if k in body_data:
                        card[k] = body_data[k]
                        updated_keys.append(k)

                append_audit_log(task_id, "USER", card.get("status", "-"), card.get("status", "-"),
                                 card.get("assignee", "用户"), f"更新任务字段: {','.join(updated_keys)}")
                return True, 200, f"任务 {task_id} 更新成功", {
                    "id": task_id,
                    "updated_fields": updated_keys,
                    "card": card
                }

            code, msg, data = atomic_mutate_board_data(_mutate_put, expected_version=expected_v)
            self._send_json_resp(code, msg, data, http_status=code)
            return

        self._send_json_resp(404, "Not Found", None, http_status=404)

    # -------------------------------------------------------------
    # DELETE 路由分发
    # -------------------------------------------------------------
    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        body_data = None
        try:
            body_data = self._parse_request_json()
        except Exception:
            pass

        expected_v = self._extract_expected_version(body_data)

        # 1. REST API: DELETE /api/tasks/{task_id} 或 /api/cards/{task_id}
        m_task = re.match(r"^/api/(?:tasks|cards)/([A-Za-z0-9_\-]+)$", path)
        if m_task:
            task_id = m_task.group(1)

            def _mutate_del_one(cards):
                initial_len = len(cards)
                remaining = [c for c in cards if c.get("id") != task_id]
                if len(remaining) == initial_len:
                    return False, 404, f"未找到待删除任务 [{task_id}]", None
                cards.clear()
                cards.extend(remaining)
                append_audit_log(task_id, "PM", "-", "已删除", "用户", f"删除任务: {task_id}")
                return True, 200, f"成功删除任务 {task_id}", {"deleted_id": task_id, "deleted": 1}

            code, msg, data = atomic_mutate_board_data(_mutate_del_one, expected_version=expected_v)
            self._send_json_resp(code, msg, data, http_status=code)
            return

        # 2. REST API: DELETE /api/tasks 或 /api/cards (批量删除 ?ids=id1,id2 或 body)
        if path in ("/api/tasks", "/api/cards"):
            ids_param = query.get("ids", [None])[0] or query.get("task_ids", [None])[0]
            ids_list = []
            if ids_param:
                ids_list = [x.strip() for x in ids_param.split(",") if x.strip()]
            elif isinstance(body_data, dict):
                ids_list = body_data.get("ids") or body_data.get("task_ids") or []
            elif isinstance(body_data, list):
                ids_list = body_data

            if not ids_list:
                self._send_json_resp(400, "缺少待删除任务 ID 列表 (ids)", None, http_status=400)
                return

            task_ids_to_del = set(ids_list)

            def _mutate_del_multi(cards):
                initial_len = len(cards)
                remaining = [c for c in cards if c.get("id") not in task_ids_to_del]
                cards.clear()
                cards.extend(remaining)
                deleted_count = initial_len - len(cards)
                for tid in task_ids_to_del:
                    append_audit_log(tid, "PM", "-", "已删除", "用户", f"批量删除任务: {tid}")
                return True, 200, f"成功删除 {deleted_count} 条任务", {
                    "deleted": deleted_count,
                    "deleted_count": deleted_count,
                    "remaining_total": len(cards)
                }

            code, msg, data = atomic_mutate_board_data(_mutate_del_multi, expected_version=expected_v)
            self._send_json_resp(code, msg, data, http_status=code)
            return

        self._send_json_resp(404, "Not Found", None, http_status=404)

    def log_message(self, format, *args):
        # 保持控制台日志简洁（端口跟随实际绑定值）
        try:
            port = self.server.server_address[1]
        except Exception:
            port = "?"
        sys.stderr.write(f" [Kanban HTTP {port}] {self.address_string()} - {format % args}\n")


class ReusableHTTPServer(HTTPServer):
    # Windows 上 SO_REUSEADDR 允许两个活跃进程同时绑定同一端口（等效于 SO_REUSEPORT 的危害），
    # 必须禁用；Unix 上仅允许复用 TIME_WAIT 端口，保留
    allow_reuse_address = (sys.platform != "win32")

    def server_bind(self):
        if self.allow_reuse_address:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # 注意：绝不设置 SO_REUSEPORT —— 它允许多实例同时绑定同一端口，
        # 请求随机分发到不同项目实例，造成看板数据静默串写
        super().server_bind()


def _port_listening(port: int, timeout: float = 0.2) -> bool:
    """探测 127.0.0.1:{port} 是否有进程监听（固定探测回环地址，避免 macOS 防火墙弹窗）"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except Exception:
        return False


def _query_health(port: int, timeout: float = 0.8) -> dict | None:
    """GET /api/health；非本服务（404/超时/非 JSON）返回 None。

    显式禁用代理：系统/环境代理（http_proxy 等）会拦截 127.0.0.1 请求，
    把 health 探测转发给代理进程，导致复用判定永远失败。
    兼容统一响应体（{"code":200,"data":{...}}）与裸 health 载荷。
    """
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]  # 统一响应体解包
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _is_same_instance(health: dict | None, fingerprint: str) -> bool:
    """判定监听者是否为同项目的本服务实例（指纹不区分指纹来源层）"""
    if not health:
        return False
    return health.get("service") == SERVICE_NAME and health.get("fingerprint") == fingerprint


class ProbeResult:
    """端口探测结果：action ∈ {"bind", "reuse"}；bind 时携带已绑定的 server，reuse 时携带既有实例 health"""

    def __init__(self, action: str, port: int, health: dict | None = None, httpd=None):
        self.action = action
        self.port = port
        self.health = health
        self.httpd = httpd


def _is_addr_in_use(e: OSError) -> bool:
    """跨平台判断"地址被占用"错误（macOS/Linux errno 48/98，Windows winerror 10048）"""
    import errno as _errno
    if e.errno == _errno.EADDRINUSE:
        return True
    if getattr(e, "winerror", None) == 10048:
        return True
    return "Address already in use" in str(e) or "only one usage" in str(e).lower()


def probe_port(requested_port: int, fingerprint: str, pinned: bool = False) -> ProbeResult:
    """端口探测与复用判定。

    - pinned=True（显式 --port/KANBAN_PORT）：只试 requested_port；同指纹复用，否则硬失败
    - pinned=False：requested_port 起向上探测 DEFAULT_PORT..DEFAULT_PORT+PROBE_RANGE
    """
    candidates = [requested_port] if pinned else list(
        dict.fromkeys([requested_port] + list(range(DEFAULT_PORT, DEFAULT_PORT + PROBE_RANGE + 1)))
    )

    last_error = ""
    for port in candidates:
        if _port_listening(port):
            health = _query_health(port)
            if _is_same_instance(health, fingerprint):
                return ProbeResult("reuse", port, health)
            # 其他项目实例或无关服务 → 尝试下一端口
            continue
        try:
            httpd = ReusableHTTPServer(("127.0.0.1", port), KanbanHTTPRequestHandler)
            return ProbeResult("bind", port, httpd=httpd)
        except OSError as e:
            if _is_addr_in_use(e):
                # bind-close 竞态：探测时空闲、绑定时被抢 → 落到下一候选
                last_error = str(e)
                continue
            raise

    print(f"[FAILED]  [ERROR] 候选端口全部不可用 (尝试了 {len(candidates)} 个): {last_error or '均被其他服务占用'}")
    sys.exit(1)


def _write_runtime_file(port: int, fingerprint: str):
    """落盘运行时信息，供人工排障与后续工具查询（不做启动快速路径）"""
    try:
        os.makedirs(os.path.dirname(KANBAN_RUNTIME_FILE), exist_ok=True)
        payload = {
            "port": port,
            "pid": os.getpid(),
            "fingerprint": fingerprint,
            "started_at": datetime.now().isoformat(),
        }
        with open(KANBAN_RUNTIME_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except Exception as e:
        sys.stderr.write(f"[WARN] 运行时文件写入失败 (不影响服务): {e}\n")


def _remove_runtime_file():
    try:
        if os.path.exists(KANBAN_RUNTIME_FILE):
            os.remove(KANBAN_RUNTIME_FILE)
    except Exception:
        pass


def start_server(port: int = DEFAULT_PORT, host: str = "0.0.0.0", pinned: bool = False):
    """启动简易 HTTP 看板服务（含端口探测与同项目复用）"""
    if not os.path.exists(KANBAN_DIR):
        print(f"[FAILED]  [ERROR] 无法找到看板目录: {KANBAN_DIR}")
        sys.exit(1)

    fingerprint = compute_project_fingerprint(_DATA_ROOT)
    result = probe_port(port, fingerprint, pinned=pinned)

    if result.action == "reuse":
        print("\n" + "=" * 70)
        print(f"[REUSE]  本项目看板服务已在运行 (端口: {result.port})，直接复用既有实例")
        print(f" 既有实例 PID: {result.health.get('pid', '未知')} | 启动于: {result.health.get('data_root', '')}")
        print("=" * 70)
        print_kanban_urls(result.port, get_local_ip())
        return

    # probe_port 在 127.0.0.1 上试探性绑定成功；若最终要求监听其他 host，重建监听
    httpd = result.httpd
    if host not in ("", "127.0.0.1", "localhost"):
        httpd.server_close()
        try:
            httpd = ReusableHTTPServer((host, result.port), KanbanHTTPRequestHandler)
        except OSError as e:
            print(f"[FAILED]  [ERROR] 端口 {result.port} 绑定 {host} 失败: {e}")
            sys.exit(1)

    SERVER_STATE.update(
        fingerprint=fingerprint,
        port=result.port,
        pid=os.getpid(),
        data_root=_DATA_ROOT,
    )

    _write_runtime_file(result.port, fingerprint)
    atexit.register(_remove_runtime_file)

    local_ip = get_local_ip()
    print_kanban_urls(result.port, local_ip)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP]  收到终止信号，正在关闭看板 HTTP 服务...")
        httpd.server_close()


def print_kanban_urls(port: int, local_ip: str):
    print("\n" + "=" * 70)
    print(f"[START]  Multi-Agent Flow 看板 Web 服务已就绪 (端口: {port})")
    print("=" * 70)
    print(f" 本地访问地址  : http://localhost:{port}/")
    print(f" 替代本地链接  : http://127.0.0.1:{port}/offline_board.html")
    if local_ip != "127.0.0.1":
        print(f" 局域网访问地址: http://{local_ip}:{port}/")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Flow 看板简易 HTTP 服务")
    parser.add_argument("--port", type=int, default=None,
                        help=f"固定服务端口 (默认: 环境变量 KANBAN_PORT 或 {DEFAULT_PORT}+自动探测)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听 Host (默认: 0.0.0.0)")
    args = parser.parse_args()

    env_port = os.environ.get("KANBAN_PORT", "").strip()
    if args.port is not None:
        port, pinned = args.port, True
    elif env_port:
        port, pinned = int(env_port), True
    else:
        port, pinned = DEFAULT_PORT, False

    start_server(port=port, host=args.host, pinned=pinned)


if __name__ == "__main__":
    main()
