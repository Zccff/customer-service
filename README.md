# 电商智能客服系统

基于 FastAPI、LangGraph、MySQL 和 Milvus 的智能客服演示项目，包含意图分流、订单与售后工具调用、知识库检索问答、人工审核及评估页面。订单、物流等业务数据使用演示数据。

## 环境准备

需要 Python 3.12 或更高版本、[uv](https://docs.astral.sh/uv/) 和 Docker Compose。先启动 Docker，再在项目根目录安装依赖并创建配置文件。

Windows PowerShell：

```powershell
uv sync
Copy-Item .env.example .env
```

macOS / Linux：

```bash
uv sync
cp .env.example .env
```

编辑 `.env`，填写聊天模型的地址、模型名和密钥（`CHAT_BASE_URL`、`CHAT_MODEL`、`CHAT_API_KEY`），以及嵌入和重排服务的密钥（`EMBED_API_KEY`、`RERANK_API_KEY`）。使用其他服务商时，再按 `.env.example` 调整相应地址和模型配置。不要提交 `.env`。

## 启动服务

Windows：

```powershell
.\start.cmd
```

macOS / Linux：

```bash
make dev
```

启动过程会拉起 MySQL、Milvus 等依赖，以及物流、售后 MCP 服务。MySQL 首次创建数据卷时会自动执行 `sql/` 下的初始化脚本。应用就绪后，打开 <http://localhost:8000>；知识库管理页位于 <http://localhost:8000/kb>。

首次使用知识库时，在管理页依次运行“离线建库”和“向量化”任务。向量化会调用 `.env` 配置的嵌入模型服务。完成后可在聊天页测试知识库问答。

停止应用：Windows 运行 `.\stop.cmd`；macOS / Linux 运行 `make dev-down`。停止应用不会删除 Docker 中的数据。
