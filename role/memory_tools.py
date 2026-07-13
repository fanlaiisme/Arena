"""记忆工具 —— 供 MemorySubagent 使用的 LangChain @tool 函数。

提供 list_memory_files、read_memory、edit_memory 三个工具：
  - list_memory_files: 列出所有记忆文件的 frontmatter 摘要
  - read_memory: 读取单个文件的完整内容（同时标记为"已读"）
  - edit_memory: 编辑文件内容（必须先 read_memory 才能 edit）

线程安全：使用 threading.local() 隔离不同玩家的 memory_dir 和 read_files。
"""

import re
import threading
from pathlib import Path
from langchain_core.tools import tool


# 线程局部存储：每个线程独立维护 memory_dir 和已读文件集合
_local = threading.local()


def set_memory_base_dir(base_dir: str):
    """设置当前线程的记忆目录根路径（线程安全）。"""
    _local.memory_base_dir = Path(base_dir)


def get_memory_base_dir() -> Path:
    """获取当前线程的记忆目录根路径。"""
    base = getattr(_local, 'memory_base_dir', None)
    if base is None:
        raise RuntimeError("记忆目录未初始化，请先调用 set_memory_base_dir()")
    return base


def clear_read_tracking():
    """清除当前线程的已读文件记录（每次 _process 调用前重置）。"""
    _local.read_files = set()


def _mark_read(filepath: str):
    """标记文件已被当前线程读取。"""
    if not hasattr(_local, 'read_files'):
        _local.read_files = set()
    _local.read_files.add(str(filepath))


def _was_read(filepath: str) -> bool:
    """检查文件是否已被当前线程读取。"""
    read_files = getattr(_local, 'read_files', set())
    return str(filepath) in read_files


def _parse_frontmatter(text: str) -> dict:
    """从 markdown 文本中解析 YAML frontmatter。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    end = 1
    while end < len(lines) and lines[end].strip() != "---":
        end += 1
    fm = {}
    for line in lines[1:end]:
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm


def _resolve_path(filepath: str) -> Path:
    """解析文件路径，限制在记忆目录内。"""
    base = get_memory_base_dir()
    p = Path(filepath)
    if p.is_absolute():
        # 绝对路径：必须在 base 之下
        resolved = p.resolve()
        if not str(resolved).startswith(str(base.resolve())):
            raise ValueError(f"路径越界: {filepath} 不在记忆目录 {base} 内")
    else:
        # 相对路径：相对于 base
        resolved = (base / p).resolve()
        if not str(resolved).startswith(str(base.resolve())):
            raise ValueError(f"路径越界: {filepath}")
    return resolved


@tool
def list_memory_files() -> str:
    """列出记忆目录下所有 markdown 文件的 frontmatter 摘要。

    无需参数。返回每个文件的 frontmatter 元信息（name, description, type, day 等），
    供你判断当前玩家输出与哪些文件相关，从而决定要读取哪个文件。

    返回格式（每文件一段）：
      文件名: opponent_model.md
        name: opponent-model
        description: 对夜神月的出价模式、部署偏好...
        type: opponent-model
        last_updated_day: 2
    """
    base = get_memory_base_dir()
    if not base.exists():
        return "⚠️ 记忆目录尚不存在，请先用 edit_memory 创建第一个文件。"

    md_files = sorted(base.rglob("*.md"))
    if not md_files:
        return "⚠️ 记忆目录下暂无 md 文件。"

    lines = []
    for f in md_files:
        rel = str(f.relative_to(base))
        content = f.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        lines.append(f"📄 {rel}")
        if fm:
            for key in ["name", "description", "type", "player", "day", "last_updated_day"]:
                if key in fm:
                    lines.append(f"     {key}: {fm[key]}")
        else:
            lines.append(f"     （无 frontmatter）")
        lines.append("")
    return "\n".join(lines)


@tool
def read_memory(filepath: str) -> str:
    """读取记忆目录下的 markdown 文件。

    参数 filepath 为文件路径，如 "opponent_model.md" 或 "斑目貘/day1.md"。
    返回文件的完整内容（含 frontmatter 和正文）。
    如果文件不存在，返回提示信息。
    """
    try:
        resolved = _resolve_path(filepath)
    except ValueError as e:
        return f"❌ 路径错误: {e}"

    if not resolved.exists():
        return f"⚠️ 文件不存在: {filepath}（可能尚未创建，可使用 edit_memory 创建新文件——此时 old_str 传空字符串 ''）"

    _mark_read(filepath)
    content = resolved.read_text(encoding="utf-8")
    if len(content) > 8000:
        content = content[:8000] + "\n\n...（内容过长，已截断至前 8000 字符）"
    return content


@tool
def edit_memory(filepath: str, old_str: str, new_str: str) -> str:
    """编辑记忆文件中的内容。
    将文件中第一次出现的 old_str 替换为 new_str。
    如果 old_str 为空字符串 ''，则将 new_str 追加到文件末尾（用于初始化新文件）。

    返回格式：
    - "✅ 创建了新文件：[文件名]" — 文件原本不存在
    - "✅ 填充了空模板：[章节名]" — old_str 匹配到空占位符
    - "✏️ 修改了已有内容：[章节名]" — old_str 匹配到已有内容
    - "❌ 未找到匹配内容" — old_str 在文件中不存在
    - "🔄 内容无变化" — old_str 与 new_str 相同

    参数：
    - filepath: 文件路径（如 "opponent_model.md" 或 "斑目貘/day1.md"）
    - old_str: 要被替换的原文本（必须精确匹配，传 '' 表示创建或追加）
    - new_str: 替换后的新文本
    """
    if old_str == new_str:
        return "🔄 内容无变化（old_str 与 new_str 相同）"

    try:
        resolved = _resolve_path(filepath)
    except ValueError as e:
        return f"❌ 路径错误: {e}"

    # ── 新建文件（old_str 为空且文件不存在） ──
    if old_str == "" and not resolved.exists():
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(new_str, encoding="utf-8")
        return f"✅ 创建了新文件：{resolved.name}"

    # read-before-edit 强制：非新建文件必须先 read
    if not _was_read(filepath):
        return (
            f"⛔ 禁止操作：在编辑 {filepath} 之前，必须先调用 read_memory('{filepath}') 读取文件内容。\n"
            f"这是为了防止盲目编辑。请先读取文件，确认 old_str 精确匹配后再编辑。"
        )

    content = resolved.read_text(encoding="utf-8")

    # old_str 为空且文件已存在 → 追加到末尾
    if old_str == "":
        resolved.write_text(content + "\n" + new_str, encoding="utf-8")
        return f"✅ 追加内容到文件末尾：{resolved.name}"

    # 查找并替换
    if old_str not in content:
        return f"❌ 未找到匹配内容（文件: {resolved.name}）"

    # 判断是填充空模板还是修改已有内容
    old_stripped = old_str.strip()
    # 检测章节名（从 old_str 中提取）
    section_name = _extract_section_name(old_str)

    if _is_empty_template(old_stripped):
        action = f"✅ 填充了空模板：{section_name}"
    else:
        action = f"✏️ 修改了已有内容：{section_name}"

    new_content = content.replace(old_str, new_str, 1)
    resolved.write_text(new_content, encoding="utf-8")
    return action


def _extract_section_name(text: str) -> str:
    """从文本中提取章节名，用于日志。"""
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("## "):
            return line[3:].strip()
        if line.startswith("### "):
            return line[4:].strip()
    # 回退：取前 40 个字符
    preview = text.strip()[:40].replace("\n", " ")
    return preview if preview else "（空）"


def _is_empty_template(text: str) -> bool:
    """检查文本是否为空模板占位符。"""
    if not text or not text.strip():
        return True
    stripped = text.strip()
    # 空表格行、空列表项、占位符
    empty_markers = [
        "| — | — | — |",
        "| ... | ... | ... |",
        "- —",
        "（待填写）",
        "暂无",
    ]
    for marker in empty_markers:
        if marker in stripped:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# 记忆重置
# ═══════════════════════════════════════════════════════════════════════════

def _player_opponent_name(player_name: str) -> str:
    """返回对手名。"""
    return "夜神月" if player_name == "斑目貘" else "斑目貘"

# 模板内容（每次实验开始时重置为此状态）
_TEMPLATE_OPPONENT_MODEL = """---
name: opponent-model
description: 对{opponent_name}的出价模式、部署偏好和行为特征的持续观察
metadata:
  type: opponent-model
  player: {player_name}
  last_updated_day: 0
---

## 出价模式
- 激进程度: 待观察
- 偏好出价区间: 待观察
- 虚张声势倾向: 待观察
- 弃权率: 待观察

## 部署模式
- 第2局策略: 待观察
- 疲劳管理: 待观察

## 关键观察
- （暂无观察）
"""

_TEMPLATE_GLADIATOR_KNOWLEDGE = """---
name: gladiator-knowledge
description: 对20名角斗士的胜率排名推测和实战表现记录
metadata:
  type: gladiator-knowledge
  player: {player_name}
  last_updated_day: 0
---

## 胜率排名推测
| 排名 | 胜率 | 推测角色 | 置信度 | 依据 |
|------|------|---------|--------|------|
| 1 | 98.4% | — | — | — |
| 2 | 88.2% | — | — | — |
| 3 | 82.1% | — | — | — |
| ... | ... | ... | ... | ... |
| 20 | 1.4% | — | — | — |

## 实战表现记录
| 角斗士 | 出场次数 | 胜场 | 印象 |
|--------|---------|------|------|
| — | — | — | 尚无实战记录 |
"""


def reset_player_memories(player_name: str, memory_dir: str):
    """重置指定玩家所有记忆文件为模板状态。

    删除所有 day{N}.md，将 opponent_model.md 和 gladiator_knowledge.md 恢复为模板。
    调用时机：每次 run_experiment() 开始时。

    Args:
        player_name: 玩家名称
        memory_dir: 该玩家的记忆目录路径（如 role/memory/斑目貘）
    """
    from pathlib import Path as _Path
    _base = _Path(memory_dir)
    _base.mkdir(parents=True, exist_ok=True)
    opponent_name = _player_opponent_name(player_name)

    # 删除所有 day{N}.md 文件（上局残留）
    for day_file in sorted(_base.glob("day*.md")):
        day_file.unlink()
        try:
            # 同时清理可能存在的 .bak 备份
            _Path(str(day_file) + ".bak").unlink(missing_ok=True)
        except Exception:
            pass

    # 写入 opponent_model.md 模板
    (_base / "opponent_model.md").write_text(
        _TEMPLATE_OPPONENT_MODEL.format(
            player_name=player_name, opponent_name=opponent_name),
        encoding="utf-8")

    # 写入 gladiator_knowledge.md 模板
    (_base / "gladiator_knowledge.md").write_text(
        _TEMPLATE_GLADIATOR_KNOWLEDGE.format(player_name=player_name),
        encoding="utf-8")
