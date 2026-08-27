"""
敏感凭证与硬编码密钥安全扫描核心模块
"""
import os
import sys
import re
from typing import List, Tuple

SECRET_PATTERNS = [
    (re.compile(r'cli_[a-zA-Z0-9]{16,}', re.IGNORECASE), "飞书 App ID / Token"),
    (re.compile(r'(app_secret|appsecret|secret)\s*:\s*["\']?[a-zA-Z0-9]{20,}', re.IGNORECASE), "硬编码 App Secret"),
    # 等号赋值风格（Python/JS/TS/Env）: SECRET = "..." / const appSecret = "..."
    # 值字符集扩展含 -_. 等常见密钥字符（如 sk- 前缀密钥），并要求引号包裹或首字符非纯数字以免误伤普通数字赋值
    (re.compile(r'(?:const|let|var|)\s*(?:[A-Z_]*|app[A-Za-z]*)?(?:SECRET|secret|Secret)[A-Z_a-z_0-9]*\s*=\s*["\'][^"\']{20,}["\']', re.IGNORECASE), "硬编码密钥(等号赋值)"),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}', re.IGNORECASE), "GitHub Personal Access Token"),
    (re.compile(r'ATATT3[a-zA-Z0-9_\-=]{40,}', re.IGNORECASE), "Jira API Token"),
    (re.compile(r'-----BEGIN ' + r'PRIVATE KEY-----'), "RSA 私钥凭证")
]


def scan_file(file_path: str) -> List[Tuple[int, str, str]]:
    findings = []
    # 跳过对检查器脚本自身的匹配
    fn = os.path.basename(file_path)
    if fn in ("check_secrets.py", "secrets_checker.py"):
        return findings

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                clean_line = line.strip()
                if clean_line.startswith('#'):
                    continue
                for pattern, desc in SECRET_PATTERNS:
                    match = pattern.search(line)
                    if match:
                        matched_str = match.group(0)
                        # 如果匹配内容纯粹且完全是规范的变量占位符如 ${FEISHU_BASE_TOKEN}，则视为符合规范
                        if re.match(r'^\$\{[A-Za-z0-9_:-]+\}$', matched_str.strip()):
                            continue
                        findings.append((line_num, desc, clean_line))
    except Exception as e:
        print(f"[WARN] 无法读取文件 {file_path}: {e}")
    return findings


def run_secrets_scan(workflow_root: str, data_root: str) -> int:
    total_issues = 0
    scan_dirs = [
        os.path.join(workflow_root, d) for d in ["config", "scripts", "agents", "docs", "kanban"]
    ]
    if os.path.abspath(data_root) != os.path.abspath(workflow_root):
        scan_dirs += [
            os.path.join(data_root, "user_data"),
            os.path.join(data_root, "docs"),
        ]

    for d in scan_dirs:
        if not os.path.exists(d):
            continue
        for root, _, files in os.walk(d):
            for file in files:
                if file.endswith(('.yaml', '.yml', '.json', '.py', '.sh', '.md')):
                    file_path = os.path.join(root, file)
                    issues = scan_file(file_path)
                    if issues:
                        rel_path = os.path.relpath(file_path, workflow_root)
                        print(f"\n[ALERT] 在文件 `{rel_path}` 中检测到潜在敏感硬编码风险：")
                        for line_num, desc, clean_line in issues:
                            # 脱敏展示
                            masked_line = clean_line[:40] + "..." if len(clean_line) > 40 else clean_line
                            print(f"  - 第 {line_num} 行 [{desc}]: {masked_line}")
                            total_issues += 1
    return total_issues
