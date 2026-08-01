"""Smoke test for the five workspace tools (no LLM involved).

Run from repo root:  .venv/Scripts/python tests/smoke_tools.py
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.tools import WorkspaceTools
from agent.utils import extract_date_from_content, month_key

tools = WorkspaceTools(ROOT / "workspace")
failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# 1. list_directory
listing = tools.list_directory(".")
check("list_directory shows tree", "drafts/" in listing and "server.log" in listing)

# 2. read_file pagination on the big log
page1 = tools.read_file("logs/server.log", offset=0, limit=50)
check("read_file meta reports total lines", "total_lines: 20000" in page1, page1.splitlines()[0])
check("read_file flags more_lines", "more_lines: True" in page1)
page2 = tools.read_file("logs/server.log", offset=8100, limit=50)
check("read_file pagination finds needle region", "Project Falcon" in page2)
big = tools.read_file("logs/server.log", offset=0, limit=20000)
check("read_file caps chars at ~5000", len(big) < 5600 and "char_truncated: True" in big,
      f"len={len(big)}")

# 3. search_content finds the needle in the big log
res = tools.search_content("Project Falcon")
check("search_content finds needle in big log", "logs/server.log:8123" in res, res[:300])
check("search_content finds multiple files", res.count("\n") >= 5)
check("search_content case-insensitive", "falcon_birdwatching" in tools.search_content("FALCON"))

# 4. write_file + move_file
shutil.rmtree(ROOT / "workspace" / "tmp_test", ignore_errors=True)
check("write_file ok", tools.write_file("tmp_test/hello.txt", "hi there").startswith("Wrote"))
check("written content readable", "hi there" in tools.read_file("tmp_test/hello.txt"))
check("move_file ok", "Moved" in tools.move_file("tmp_test/hello.txt", "tmp_test/bye.txt"))
check("move source gone", "file not found" in tools.read_file("tmp_test/hello.txt"))

# 5. sandbox: path escapes rejected (execute() turns them into Error strings)
check("read ../ rejected", "Error" in tools.execute("read_file", {"path": "../evil.txt"}))
check("write ../ rejected", "Error" in tools.execute("write_file", {"path": "../evil.txt", "content": "x"}))
check("move ../ rejected", "Error" in tools.execute("move_file", {"source": "README.txt", "destination": "../evil.txt"}))
check("absolute escape rejected", "Error" in tools.execute("read_file", {"path": str(ROOT / "README.md")}))
check("escape did not write file", not (ROOT / "evil.txt").exists())

# 6. error strings instead of crashes
check("missing file -> Error string", tools.read_file("nope.txt").startswith("Error"))
check("bad json args -> Error string", tools.execute("read_file", "{not json").startswith("Error"))
check("unknown tool -> Error string", tools.execute("rm_rf", {}).startswith("Error"))
check("bad arg types -> Error string", tools.execute("read_file", {"path": 123}).startswith("Error"))

# 7. utils date parsing
d = extract_date_from_content("Date: 2025-04-20\nRenamed to Project Kestrel.")
check("extract_date YYYY-MM-DD", d is not None and month_key(d) == "2025-04")
d2 = extract_date_from_content("announced 2 March 2025 at noon")
check("extract_date '2 March 2025'", d2 is not None and month_key(d2) == "2025-03")
check("extract_date none", extract_date_from_content("no dates here") is None)

# cleanup of test artifacts (keep workspace tidy)
shutil.rmtree(ROOT / "workspace" / "tmp_test", ignore_errors=True)

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("ALL TOOL SMOKE TESTS PASSED")
