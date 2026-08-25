"""
阿里千问办公 (QwenWork) 专家套件自动化打包与合规校验核心模块
"""
import os
import sys
import json
import zipfile
import shutil
from typing import Optional, Dict, Any

try:
    from PIL import Image
except ImportError:
    Image = None

import paths as _paths

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

    if Image is not None:
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


def validate_manifest(manifest_path: str) -> Optional[Dict[str, Any]]:
    """校验 .qoder-plugin/plugin.json 清单"""
    if not os.path.exists(manifest_path):
        print(f"[ERROR] 未找到清单文件: {manifest_path}")
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] 清单 JSON 格式解析失败: {e}")
        return None

    name = data.get("name", "")
    if not name or not name.isascii() or not (name.replace("-", "").replace("_", "").isalnum()):
        print(f"[ERROR] 插件名称不合规: '{name}'，必须由英文、数字、下划线或连字符组成！")
        return None

    if not data.get("version") or not data.get("description"):
        print("[ERROR] 清单缺失 version 或 description 字段！")
        return None

    print(f"[PASS] ✅ 清单文件合规: name='{name}', version='{data.get('version')}'")
    return data


def package_plugin(project_root: Optional[str] = None) -> bool:
    """组装并打包插件"""
    if project_root is None:
        project_root = _paths.skill_root()
    dist_dir = os.path.join(project_root, "dist")
    stage_dir = os.path.join(dist_dir, "stage_qwen")
    output_zip = os.path.join(dist_dir, "multi-agent-flow-qwen.zip")

    os.makedirs(dist_dir, exist_ok=True)
    if os.path.exists(stage_dir):
        shutil.rmtree(stage_dir)
    os.makedirs(stage_dir, exist_ok=True)

    manifest_src = os.path.join(project_root, ".qoder-plugin", "plugin.json")
    icon_src = os.path.join(project_root, "assets", "icon.png")

    if not validate_manifest(manifest_src) or not validate_icon(icon_src):
        return False

    qoder_stage = os.path.join(stage_dir, ".qoder-plugin")
    assets_stage = os.path.join(stage_dir, "assets")
    skill_stage = os.path.join(stage_dir, "skills", "yy-flow")

    os.makedirs(qoder_stage, exist_ok=True)
    os.makedirs(assets_stage, exist_ok=True)
    os.makedirs(skill_stage, exist_ok=True)

    shutil.copy2(manifest_src, os.path.join(qoder_stage, "plugin.json"))
    shutil.copy2(icon_src, os.path.join(assets_stage, "icon.png"))

    for item in ["SKILL.md", "scripts", "references", "rules", "templates", "agents", "config"]:
        s = os.path.join(project_root, item)
        d = os.path.join(skill_stage, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, ignore=shutil.ignore_patterns(*EXCLUDE_PATTERNS))
        elif os.path.isfile(s):
            shutil.copy2(s, d)

    if os.path.exists(output_zip):
        os.remove(output_zip)

    file_count = 0
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(stage_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, stage_dir)
                zf.write(file_path, arcname)
                file_count += 1

    shutil.rmtree(stage_dir)

    zip_size = os.path.getsize(output_zip)
    if zip_size > 50 * 1024 * 1024:
        print(f"[ERROR] 压缩包体积超出 50MB 限制: {zip_size / (1024*1024):.2f} MB")
        return False

    if file_count >= 1000:
        print(f"[ERROR] 压缩包内文件数量超出 1000 限制: {file_count}")
        return False

    with zipfile.ZipFile(output_zip, "r") as zf:
        namelist = zf.namelist()
        if "skills/yy-flow/SKILL.md" not in namelist:
            print("[ERROR] 校验失败：未在根路径下检测到 skills/yy-flow/SKILL.md！")
            return False

    print(f"[SUCCESS] 🎉 阿里千问专家套件打包完成: {output_zip} (包含 {file_count} 个文件, 体积 {zip_size / 1024:.1f} KB)")
    return True
