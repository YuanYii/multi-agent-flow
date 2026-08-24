#!/usr/bin/env python3
"""
阿里千问办公 (QwenWork) 专家套件自动化打包与合规校验脚本
(QwenWork Plugin Packager & Pre-Flight Validator)

功能与白皮书硬红线校验：
1. 校验 .qoder-plugin/plugin.json 清单与 name 规范；
2. 校验 assets/icon.png 严格等于 200×200 像素、文件 ≤ 2MB；
3. 组装标准专家套件包目录结构并打包为 zip (≤ 50MB，条目 < 1000)；
4. 校验压缩包内精确存在 skills/yy-flow/SKILL.md。
"""

import os
import sys
import json
import zipfile
import shutil
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
STAGE_DIR = os.path.join(DIST_DIR, "stage_qwen")
OUTPUT_ZIP = os.path.join(DIST_DIR, "multi-agent-flow-qwen.zip")

EXCLUDE_PATTERNS = {
    ".git", ".github", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".coverage", "dist", "node_modules", ".DS_Store"
}


def validate_icon(icon_path: str) -> bool:
    """校验图标：必须存在、严格 200x200 像素、≤ 2MB"""
    if not os.path.exists(icon_path):
        print(f"[ERROR] 图标文件不存在: {icon_path}")
        return False

    size_bytes = os.path.getsize(icon_path)
    if size_bytes > 2 * 1024 * 1024:
        print(f"[ERROR] 图标体积超出 2MB 限制: {size_bytes / 1024:.1f} KB")
        return False

    try:
        with Image.open(icon_path) as img:
            w, h = img.size
            if w != 200 or h != 200:
                print(f"[ERROR] 图标尺寸不合规: 实际为 {w}x{h}，白皮书等式校验要求必须严格为 200x200！")
                return False
    except Exception as e:
        print(f"[ERROR] 无法解析图标文件: {e}")
        return False

    print(f"[PASS] ✅ 图标合规: {icon_path} (200x200 px, {size_bytes / 1024:.1f} KB)")
    return True


def validate_manifest(manifest_path: str) -> dict:
    """校验 .qoder-plugin/plugin.json 清单"""
    if not os.path.exists(manifest_path):
        print(f"[ERROR] 未找到清单文件: {manifest_path}")
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except Exception as e:
        print(f"[ERROR] plugin.json 不是合法 JSON: {e}")
        return None

    name = data.get("name")
    if not name or not isinstance(name, str):
        print("[ERROR] plugin.json 缺少合法的 name 字段！")
        return None

    print(f"[PASS] ✅ 清单合规: name='{name}', displayName='{data.get('displayName')}'")
    return data


def build_and_package() -> bool:
    print("=" * 75)
    print("🚀 [QwenWork Packager] 开始构建千问办公专家套件包...")
    print("=" * 75)

    os.makedirs(DIST_DIR, exist_ok=True)
    if os.path.exists(STAGE_DIR):
        shutil.rmtree(STAGE_DIR)
    os.makedirs(STAGE_DIR, exist_ok=True)

    manifest_path = os.path.join(PROJECT_ROOT, ".qoder-plugin", "plugin.json")
    manifest = validate_manifest(manifest_path)
    if not manifest:
        return False

    icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.png")
    if not validate_icon(icon_path):
        return False

    # 1. 组装目标结构 (单层包裹目录: multi-agent-flow/)
    bundle_name = manifest.get("name", "multi-agent-flow")
    bundle_root = os.path.join(STAGE_DIR, bundle_name)
    os.makedirs(bundle_root, exist_ok=True)

    # 复制 .qoder-plugin/
    os.makedirs(os.path.join(bundle_root, ".qoder-plugin"), exist_ok=True)
    shutil.copyfile(manifest_path, os.path.join(bundle_root, ".qoder-plugin", "plugin.json"))

    # 复制 assets/
    shutil.copytree(os.path.join(PROJECT_ROOT, "assets"), os.path.join(bundle_root, "assets"))

    # 复制 README
    if os.path.exists(os.path.join(PROJECT_ROOT, "README.md")):
        shutil.copyfile(os.path.join(PROJECT_ROOT, "README.md"), os.path.join(bundle_root, "README.md"))

    # 复制技能目录至 skills/yy-flow/
    skill_dst_dir = os.path.join(bundle_root, "skills", "yy-flow")
    os.makedirs(skill_dst_dir, exist_ok=True)

    # 复制 SKILL.md
    skill_src = os.path.join(PROJECT_ROOT, "SKILL.md")
    if os.path.exists(skill_src):
        shutil.copyfile(skill_src, os.path.join(skill_dst_dir, "SKILL.md"))
    else:
        print("[ERROR] 根目录未找到主技能 SKILL.md！")
        return False

    # 复制 scripts, references, templates, rules, agents
    for sub in ["scripts", "references", "templates", "rules", "agents", "kanban"]:
        src_dir = os.path.join(PROJECT_ROOT, sub)
        if os.path.exists(src_dir):
            shutil.copytree(
                src_dir,
                os.path.join(skill_dst_dir, sub),
                ignore=shutil.ignore_patterns("*.pyc", "__pycache__", ".DS_Store", "stage_qwen*")
            )

    # 2. 打包生成 ZIP
    if os.path.exists(OUTPUT_ZIP):
        os.remove(OUTPUT_ZIP)

    entry_count = 0
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zip_fp:
        for root, dirs, files in os.walk(bundle_root):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, STAGE_DIR)
                zip_fp.write(abs_path, rel_path)
                entry_count += 1

    # 3. 校验最终 ZIP
    zip_size = os.path.getsize(OUTPUT_ZIP)
    zip_size_mb = zip_size / (1024 * 1024)

    print("-" * 75)
    print(f"📦 产出压缩包: {OUTPUT_ZIP}")
    print(f"📊 压缩包体积: {zip_size_mb:.2f} MB (上限 50 MB)")
    print(f"📄 包内条目数: {entry_count} (上限 1000)")

    if zip_size_mb > 50.0:
        print("[FAIL] 🛑 压缩包超出 50MB 上限！")
        return False

    if entry_count >= 1000:
        print(f"[FAIL] 🛑 压缩包内条目数 ({entry_count}) 达到或超过 1000 限制！")
        return False

    # 验证精确路径
    with zipfile.ZipFile(OUTPUT_ZIP, "r") as check_fp:
        namelist = check_fp.namelist()
        expected_skill_path = f"{bundle_name}/skills/yy-flow/SKILL.md"
        expected_manifest_path = f"{bundle_name}/.qoder-plugin/plugin.json"
        
        if expected_skill_path not in namelist:
            print(f"[FAIL] 🛑 压缩包内缺失精确路径: {expected_skill_path}")
            return False
        if expected_manifest_path not in namelist:
            print(f"[FAIL] 🛑 压缩包内缺失清单路径: {expected_manifest_path}")
            return False

    print("=" * 75)
    print(f"[SUCCESS]  🎉 千问办公专家套件包打包成功且 100% 通过白皮书红线断言！")
    print(f"👉 产出路径: {OUTPUT_ZIP}")
    print("=" * 75)
    return True


if __name__ == "__main__":
    ok = build_and_package()
    sys.exit(0 if ok else 1)
