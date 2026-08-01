# AI 文件 Agent

[English README](README.md)

一个通用的文件操作 agent:用自然语言下达任务,它通过五个工具(列目录、
读文件、搜索、写入、移动)操作 `workspace/` 目录。agent 循环——模型返回
工具调用 → 执行 → 回填结果 → 决定继续或终止——是**手写的 Python 代码**。
不使用 LangChain / LangGraph / CrewAI / Agents SDK / `tool_runner`;
`openai` SDK 仅作为 HTTP 客户端,可对接任何 OpenAI 兼容端点。

## 安装与运行

```bash
pip install -r requirements.txt
cp .env.example .env     # 设置 LLM_PROVIDER(openai | openrouter | ollama)
                         # 和 LLM_API_KEY;LLM_BASE_URL / LLM_MODEL 为可选覆盖项
```

CLI 运行任务(workspace 路径可指定;输出 `trace.jsonl`,每步一行
`{"step","tool","args","result_summary"}` JSON):

```bash
python cli.py --workspace ./workspace --task "找出 workspace 里所有提到 Project Falcon 的文件,生成按月份分组的 falcon_index.md"
```

运行 Web demo:

```bash
docker compose up -d --build     # -> http://localhost:8000
# 或裸机运行: uvicorn ui.server:app
```

在 VPS 上用 nginx 部署:见 `deploy/` 目录。

## 功能特性

- 手写工具调用循环:15 步上限;模型不再调用工具即终止;步数或 token
  预算耗尽时给出尽力而为的最终答复
- 五个工具全部沙箱化在 workspace 内;拒绝 `..` 逃逸和疑似密钥的文件名
  (`.env`、`*.key`、`*.pem` 等)
- 提示注入防护:文件内容被包裹在显式的"不可信数据"标记中,只作为数据
  处理,绝不当作指令执行
- 大文件策略:分页 `read_file` + 子串 `search_content`,1.3 MB 的日志
  不会整个进入上下文
- Web 界面:对话式任务线程、实时逐步 mission log(工具、参数、结果
  摘要)、可折叠文件树与文件查看器、新建文件夹 / 上传 / 删除 / 重置、
  可拖拽调节的侧栏、LLM 调用次数与 token 统计
- 仅靠配置即可切换三家 LLM 提供商:OpenAI、OpenRouter、Ollama Cloud
  (ollama.com 托管 API,非本地守护进程)
- 演示 workspace 生成器(`scripts/generate_workspace.py`,32 个文件),
  内置陷阱:注入诱饵、超大日志、前后矛盾的日期、干扰文件

## 安全 / 防滥用(公网 demo)

demo API 设计上不带口令;防滥用依靠每会话 token 预算(`TOKEN_BUDGET`,
默认 200k tokens,超限后优雅中止)和 nginx 对 `/api/` 的限流
(`deploy/nginx-http-snippet.conf`)。所有文件操作都被沙箱限制在
workspace 内。

## 未完成 / 再给两小时会补的部分

- 没有流式输出(SSE/WebSocket)——UI 每秒轮询一次 `/api/trace`。
- 没有跨会话持久记忆;会话保存在内存字典中。
- demo API 没有任何鉴权;限流只能靠 nginx 按 IP 做。

设计说明(循环终止条件、上下文策略、关键取舍):见 `NOTES.md`。
