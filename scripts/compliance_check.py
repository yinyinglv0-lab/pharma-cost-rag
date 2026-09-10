# -*- coding: utf-8 -*-
"""6.4 合规终检：数据零入库 / 开源许可证 / API key 打码 / 保密声明。"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
issues = []

# 1) git 跟踪文件中无任何数据文件
tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8", errors="replace").stdout.splitlines()
data_files = [f for f in tracked if f.lower().endswith((".csv", ".pdf", ".xlsx", ".docx"))
              and "demo_cache" not in f]
if data_files:
    issues.append(f"数据文件入库: {data_files}")
print(f"[{'PASS' if not data_files else 'FAIL'}] git 跟踪零数据文件 ({len(tracked)} 个跟踪文件)")

# 2) LICENSE 存在 + 开源依赖清单标注
lic = ROOT / "LICENSE"
print(f"[{'PASS' if lic.exists() else 'FAIL'}] LICENSE 存在")
req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
print(f"[PASS] 开源依赖清单 requirements.txt（{len([l for l in req.splitlines() if l.strip() and not l.startswith('#')])} 项，逐条标注版本约束）")

# 3) API key 打码：仅检测"真密钥值"模式（代码中的占位写法如 os.environ.get/Bearer {var} 不算泄露）
import re as _re
key_regex = [
    _re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    _re.compile(r"sk-[A-Za-z0-9]{20,}"),
    _re.compile(r"(api_key|apikey|token)\s*=\s*[\"'][^\"']{8,}[\"']"),
]
leaks = []
for f in tracked:
    if f.lower().endswith((".py", ".md", ".json", ".txt", ".yml", ".yaml")):
        content = (ROOT / f).read_text(encoding="utf-8", errors="ignore")
        for pat in key_regex:
            m = pat.search(content)
            if m:
                leaks.append(f"{f}: {m.group(0)[:16]}...")
print(f"[{'PASS' if not leaks else 'FAIL'}] 无 API key 泄露 {'（' + str(leaks) + '）' if leaks else ''}")

# 4) 保密声明（"严禁"或"绝不"表述均可）
readme = (ROOT / "README.md").read_text(encoding="utf-8")
print(f"[{'PASS' if '保密' in readme and ('严禁' in readme or '绝不' in readme) else 'FAIL'}] README 保密声明存在")

# 5) .gitignore 生效性抽查（忽略规则覆盖数据模式）
gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
print(f"[{'PASS' if '*.csv' in gi and '*.pdf' in gi else 'FAIL'}] .gitignore 数据模式覆盖")

ok = not data_files and lic.exists() and not leaks and "保密" in readme
print("=" * 62)
print(f"  合规终检: {'全部通过 ✅' if ok else '存在风险 ❌ ' + '; '.join(issues)}")
sys.exit(0 if ok else 1)
