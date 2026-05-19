"""
AutoSalesAgent FastAPI 服务器。

提供 REST API + WebSocket 端点，包装 AutoSalesAgent 类的核心功能，
供 React 前端调用。

端点一览:
- GET  /api/health     健康检查
- POST /api/chat       完整 Agent 查询（同步，返回一次性结果）
- POST /api/index      索引知识库文档
- POST /api/clear      清空会话状态
- GET  /api/state      获取 Agent 内部状态快照
- WS   /ws/chat        实时流式查询（逐阶段推送进度事件）
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set

# ---------------------------------------------------------------------------
# Python 路径设置 —— 确保从父项目（agent_car/）导入 agent 和 config
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# 第三方依赖
# ---------------------------------------------------------------------------
import tempfile
import shutil
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, Field
import uvicorn

from agent.agent_core import AutoSalesAgent
from config import config

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format=config.log_format,
)
logger = logging.getLogger(__name__)

# =============================================================================
# Pydantic 模型 —— 请求 / 响应 schema
# =============================================================================


class ChatRequest(BaseModel):
    """聊天请求体。"""

    query: str = Field(..., min_length=1, description="用户查询文本")


class ChatResponse(BaseModel):
    """聊天响应体（一次性返回，非流式）。"""

    answer: str = Field(..., description="Agent 最终自然语言回答")
    sources: List[str] = Field(default_factory=list, description="从记忆提取的信息来源")
    trace: List[str] = Field(default_factory=list, description="人类可读的执行追踪")
    actions: List[Dict[str, str]] = Field(default_factory=list, description="规划的 Action 列表")


class IndexRequest(BaseModel):
    """索引请求体。"""

    file_path: str = Field(..., min_length=1, description="待索引的 PDF 文件绝对路径")


class IndexResponse(BaseModel):
    """索引响应体。"""

    status: str = Field(..., description="操作状态: 'success' 或 'error'")
    chunks: int = Field(0, description="成功索引的文本块数量")


class ClearResponse(BaseModel):
    """清空会话响应体。"""

    status: str = Field("ok", description="操作状态")


class StateResponse(BaseModel):
    """Agent 状态快照响应体。"""

    memory: List[Dict[str, Any]] = Field(default_factory=list, description="短期记忆条目列表")
    tools: List[str] = Field(default_factory=list, description="已注册工具名称")
    rag_indexed: bool = Field(False, description="知识库是否已索引")
    iteration_count: int = Field(0, description="反思模块当前迭代计数")


class HealthResponse(BaseModel):
    """健康检查响应体。"""

    status: str = Field("ok", description="服务运行状态")


class ConfigSettings(BaseModel):
    """配置设置（API Key 脱敏显示）。"""
    llm_api_key: str = ""
    embedding_api_key: str = ""
    embedding_provider: str = "deepseek"
    serpapi_key: str = ""
    llamaparse_api_key: str = ""
    embedding_model: str = ""
    llm_model: str = ""
    llm_api_url: str = ""
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048


class UpdateConfigRequest(BaseModel):
    """更新配置请求体（所有字段可选）。"""
    llm_api_key: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_provider: Optional[str] = None
    serpapi_key: Optional[str] = None
    llamaparse_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_url: Optional[str] = None
    llm_temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    llm_max_tokens: Optional[int] = Field(None, ge=1, le=32768)


class PdfUploadResponse(BaseModel):
    """PDF 上传响应体。"""
    status: str
    filename: str = ""
    chunks: int = 0
    message: str = ""


class EvalRunRequest(BaseModel):
    """评测运行请求体。"""
    dataset_name: str = Field(..., min_length=1, description="数据集文件名")
    retrieval_mode: str = Field("hybrid", pattern="^(dense|sparse|hybrid)$", description="检索模式")
    top_k: int = Field(5, ge=1, le=50, description="检索返回数量")
    generate_answers: bool = Field(True, description="是否生成回答")


class DatasetItem(BaseModel):
    """数据集摘要项。"""
    name: str
    total_samples: int
    by_type: dict
    by_difficulty: dict


# =============================================================================
# Agent 单例 —— 惰性初始化，全局复用
# =============================================================================

_agent: Optional[AutoSalesAgent] = None


def get_agent() -> AutoSalesAgent:
    """获取 AutoSalesAgent 全局单例。

    首次调用时创建实例（包含 LLM 客户端初始化），
    后续调用返回同一实例以保持会话记忆的连续性。

    Returns:
        AutoSalesAgent: 全局唯一的 Agent 实例。
    """
    global _agent
    if _agent is None:
        logger.info("AutoSalesAgent 单例首次初始化中 ...")
        _agent = AutoSalesAgent()
        logger.info("AutoSalesAgent 单例初始化完成，已注册工具: %s", _agent.executor.get_tool_names())
    return _agent


# =============================================================================
# FastAPI 应用实例
# =============================================================================

app = FastAPI(
    title="AutoSalesAgent API",
    description="汽车销售培训 AI Agent —— REST + WebSocket 后端服务",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 开发阶段允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# 辅助函数
# =============================================================================


def _mask_api_key(key: str) -> str:
    """脱敏 API Key 用于前端展示。"""
    if not key or "your-" in key:
        return ""
    if len(key) <= 8:
        return "***"
    return key[:3] + "***" + key[-4:]


# =============================================================================
# REST API 端点
# =============================================================================


@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """健康检查。

    Returns:
        HealthResponse: 固定返回 {"status": "ok"}。
    """
    return HealthResponse(status="ok")


@app.get("/api/config", response_model=ConfigSettings)
async def get_config() -> ConfigSettings:
    """获取当前配置（API Key 脱敏显示）。"""
    return ConfigSettings(
        llm_api_key=_mask_api_key(config.llm_api_key),
        embedding_api_key=_mask_api_key(config.embedding_api_key),
        embedding_provider=config.embedding_provider,
        serpapi_key=_mask_api_key(config.serpapi_key),
        llamaparse_api_key=_mask_api_key(config.llamaparse_api_key),
        embedding_model=config.embedding_model,
        llm_model=config.llm_model,
        llm_api_url=config.llm_api_url,
        llm_temperature=config.llm_temperature,
        llm_max_tokens=config.llm_max_tokens,
    )


@app.put("/api/config")
async def update_config(request: UpdateConfigRequest):
    """运行时更新配置。仅更新传入的非空字段。"""
    data = {k: v for k, v in request.model_dump().items() if v is not None}
    if not data:
        return {"status": "ok", "updated": []}

    updated = config.update_from_dict(data)
    agent = get_agent()

    if "embedding_provider" in updated:
        agent.rag_tool.embedding.switch_provider(config.embedding_provider)
    if any(k in updated for k in ("llm_api_key", "llm_api_url", "llm_model")):
        new_client = OpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_api_url,
        )
        agent.llm_client = new_client
        agent.rag_tool.llm_client = new_client
        agent.planning.llm_client = new_client
        agent.reflection.llm_client = new_client
        agent.memory.llm_client = new_client

    logger.info("配置已更新: %s", updated)
    return {"status": "ok", "updated": updated}


@app.post("/api/upload-pdf", response_model=PdfUploadResponse)
async def upload_pdf(file: UploadFile = File(...)):
    """上传 PDF 文件并索引到知识库。"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return PdfUploadResponse(
            status="error",
            filename=file.filename or "",
            message="仅支持 PDF 文件",
        )

    agent = get_agent()

    # 保存到临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        chunk_count = agent.index_knowledge_base(tmp_path)
        logger.info("PDF 上传索引完成: %s -> %d 块", file.filename, chunk_count)
        return PdfUploadResponse(
            status="success",
            filename=file.filename,
            chunks=chunk_count,
            message=f"已切分为 {chunk_count} 块，成功索引入库",
        )
    except Exception as exc:
        logger.error("PDF 上传索引失败: %s", exc, exc_info=True)
        return PdfUploadResponse(
            status="error",
            filename=file.filename,
            message=str(exc),
        )
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """同步 Agent 查询。

    执行完整的 Plan -> Execute -> Answer -> Reflect 工作流，
    返回最终答案及辅助信息（来源、追踪、Action 列表）。

    Args:
        request: 包含 query 字段的 JSON 请求体。

    Returns:
        ChatResponse: answer / sources / trace / actions。
    """
    agent = get_agent()
    query = request.query.strip()
    logger.info("REST /api/chat: query='%s'", _truncate(query, 120))

    # ---- 保存规划时的 Action 列表（在 run_query 前后抓取） ----
    memory_ctx = agent.memory.get_context(max_entries=10)
    actions = agent.planning.generate_action_plan(query, memory_ctx)
    action_list = [{"tool": a.get("tool", ""), "query": a.get("query", "")} for a in actions]

    # ---- 执行主循环 ----
    answer = agent.run_query(query)

    # ---- 提取辅助信息 ----
    sources = _extract_sources_from_agent(agent)
    trace = _build_trace_from_agent(agent)

    return ChatResponse(
        answer=answer,
        sources=sources,
        trace=trace,
        actions=action_list,
    )


@app.post("/api/index", response_model=IndexResponse)
async def index_knowledge_base(request: IndexRequest) -> IndexResponse:
    """索引知识库文档。

    调用 agent.index_knowledge_base() 索引指定的 PDF 文件。

    Args:
        request: 包含 file_path 的 JSON 请求体。

    Returns:
        IndexResponse: 索引结果及块数。
    """
    agent = get_agent()
    file_path = request.file_path.strip()
    logger.info("POST /api/index: file_path='%s'", file_path)

    try:
        chunk_count = agent.index_knowledge_base(file_path)
        logger.info("索引完成: %d 个文本块", chunk_count)
        return IndexResponse(status="success", chunks=chunk_count)
    except Exception as exc:
        logger.error("索引失败: %s", exc, exc_info=True)
        return IndexResponse(status="error", chunks=0)


@app.post("/api/clear", response_model=ClearResponse)
async def clear_session() -> ClearResponse:
    """清空当前会话。

    清除短期记忆并重置反思迭代计数器。

    Returns:
        ClearResponse: 固定 {"status": "ok"}。
    """
    agent = get_agent()
    logger.info("POST /api/clear: 清空会话")
    agent.clear_session()
    return ClearResponse(status="ok")


@app.get("/api/state", response_model=StateResponse)
async def get_state() -> StateResponse:
    """获取 Agent 内部状态。

    返回当前记忆、已注册工具、知识库索引状态、迭代计数。

    Returns:
        StateResponse: Agent 状态快照。
    """
    agent = get_agent()
    raw = agent.get_state()
    return StateResponse(
        memory=raw.get("memory", []),
        tools=raw.get("tools", []),
        rag_indexed=bool(raw.get("rag_indexed", False)),
        iteration_count=int(raw.get("iteration_count", 0)),
    )


@app.get("/api/eval/datasets", response_model=List[DatasetItem])
async def get_eval_datasets() -> List[DatasetItem]:
    """列出 eval/datasets/ 目录下所有可用评测数据集。

    Returns:
        List[DatasetItem]: 数据集摘要列表。
    """
    from eval.dataset import GoldenDataset

    datasets_dir = Path(__file__).resolve().parent.parent.parent / "eval" / "datasets"
    items: List[DatasetItem] = []

    if not datasets_dir.exists():
        return items

    for f in sorted(datasets_dir.glob("*.json")):
        try:
            ds = GoldenDataset.load(f)
            summary = ds.summary()
            items.append(DatasetItem(
                name=f.name,
                total_samples=summary["total_samples"],
                by_type=summary.get("by_type", {}),
                by_difficulty=summary.get("by_difficulty", {}),
            ))
        except Exception as exc:
            logger.warning("加载数据集失败: %s - %s", f.name, exc)

    return items


@app.post("/api/eval/run")
async def run_eval(request: EvalRunRequest):
    """运行 RAG 评测。

    Args:
        request: 评测配置（数据集名、检索模式、top_k、是否生成回答）。

    Returns:
        dict: EvalReport.to_dict() 的序列化结果。
    """
    from eval.dataset import GoldenDataset
    from eval.runner import EvalRunner

    agent = get_agent()

    # 检查知识库是否已索引
    state = agent.get_state()
    if not state.get("rag_indexed", False):
        raise HTTPException(
            status_code=400,
            detail="请先索引知识库（上传 PDF 或调用 /api/index）",
        )

    # 加载数据集
    datasets_dir = Path(__file__).resolve().parent.parent.parent / "eval" / "datasets"
    dataset_path = datasets_dir / request.dataset_name
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"数据集不存在: {request.dataset_name}")

    try:
        dataset = GoldenDataset.load(dataset_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"数据集加载失败: {exc}")

    # 运行评测
    try:
        runner = EvalRunner(rag_tool=agent.rag_tool, top_k=request.top_k)
        report = runner.run(
            dataset,
            retrieval_mode=request.retrieval_mode,
            generate_answers=request.generate_answers,
        )
        return report.to_dict()
    except Exception as exc:
        logger.error("评测运行失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"评测运行失败: {exc}")


@app.post("/api/eval/sweep")
async def run_eval_sweep(request: EvalRunRequest):
    """运行混合检索权重扫描评测。

    对 6 组预设 (dense, sparse) 权重组合分别评测，
    用于找到最优权重配比。固定使用 hybrid 模式。

    Args:
        request: 评测配置（dataset_name, top_k, generate_answers）。

    Returns:
        List[dict]: 每组权重的 EvalReport.to_dict() 结果。
    """
    from eval.dataset import GoldenDataset
    from eval.runner import EvalRunner

    agent = get_agent()

    # 检查知识库是否已索引
    state = agent.get_state()
    if not state.get("rag_indexed", False):
        raise HTTPException(
            status_code=400,
            detail="请先索引知识库（上传 PDF 或调用 /api/index）",
        )

    # 加载数据集
    datasets_dir = Path(__file__).resolve().parent.parent.parent / "eval" / "datasets"
    dataset_path = datasets_dir / request.dataset_name
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"数据集不存在: {request.dataset_name}")

    try:
        dataset = GoldenDataset.load(dataset_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"数据集加载失败: {exc}")

    # 运行权重扫描
    try:
        runner = EvalRunner(rag_tool=agent.rag_tool, top_k=request.top_k)
        reports = runner.sweep_weights(
            dataset,
            generate_answers=request.generate_answers,
        )
        return [r.to_dict() for r in reports]
    except Exception as exc:
        logger.error("权重扫描失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"权重扫描失败: {exc}")


# =============================================================================
# WebSocket 端点 —— 实时流式查询
# =============================================================================


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    """WebSocket 实时流式查询端点。

    连接建立后，每条客户端消息（{"query": "..."}）触发一次完整的
    Agent 执行流程，并将各个阶段的进度事件实时推送给客户端。

    推送事件类型:
    - plan_start:  规划开始，携带原始查询
    - plan_result: 规划完成，携带 Action 列表
    - tool_start:  开始执行某个工具
    - tool_result: 工具执行完成，携带结果摘要
    - answer:      初步 / 迭代后的回答文本
    - reflection:  反思评估结果
    - done:        最终完成，携带最终答案、来源、追踪
    - error:       执行出错，携带错误消息
    """
    await websocket.accept()
    logger.info("WebSocket /ws/chat: 客户端已连接")

    try:
        while True:
            # 阻塞等待下一条客户端消息
            raw = await websocket.receive_text()

            # 解析 JSON
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": "无效的 JSON 格式"},
                })
                continue

            query = (data.get("query", "") or "").strip()
            if not query:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": "查询不能为空"},
                })
                continue

            logger.info("WS /ws/chat: query='%s'", _truncate(query, 120))

            # 同步生成流式事件并逐条推送
            for event in _execute_and_stream(query):
                await websocket.send_json(event)

    except WebSocketDisconnect:
        logger.info("WebSocket /ws/chat: 客户端断开")
    except Exception as exc:
        logger.error("WebSocket 未预期异常: %s", exc, exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "payload": {"message": f"服务器内部错误: {exc}"},
            })
        except Exception:
            pass  # 发送错误消息失败，连接可能已断开


# =============================================================================
# 流式执行核心 —— 逐步推送事件
# =============================================================================


def _execute_and_stream(query: str) -> Generator[Dict[str, Any], None, None]:
    """同步执行 Agent 完整工作流并以生成器逐步产出事件。

    此函数完全模拟 agent.run_query() 的逻辑，但在每个阶段通过
    yield 返回事件字典，供 WebSocket 逐条推送。

    工作流阶段:
    1. 规划 (plan_start -> plan_result)
    2. 工具执行 (tool_start -> tool_result 每工具一对)
    3. 初步答案生成 (answer)
    4. 反思迭代 (reflection -> tool_start/tool_result -> answer)
    5. 完成 (done)

    Args:
        query: 用户自然语言查询。

    Yields:
        Dict[str, Any]: 事件字典，格式 {"type": str, "payload": dict}。
    """
    agent = get_agent()

    # ------------------------------------------------------------------
    # 阶段 1: 规划
    # ------------------------------------------------------------------
    agent.memory.add(query, content_type="user_query")

    yield {"type": "plan_start", "payload": {"query": query}}

    memory_ctx = agent.memory.get_context(max_entries=10)
    actions = agent.planning.generate_action_plan(query, memory_ctx)

    action_list = [
        {"tool": a.get("tool", ""), "query": a.get("query", "")}
        for a in actions
    ]
    yield {
        "type": "plan_result",
        "payload": {"actions": action_list, "count": len(actions)},
    }

    # ------------------------------------------------------------------
    # 阶段 2: 闲聊路径（空 Action List）
    # ------------------------------------------------------------------
    if not actions:
        answer = agent._chat_reply(query)  # pylint: disable=protected-access
        agent.memory.add(answer, content_type="final_answer")
        yield {"type": "answer", "payload": {"answer": answer}}
        yield _build_done_event(agent, answer)
        return

    # ------------------------------------------------------------------
    # 阶段 3: 逐个执行工具
    # ------------------------------------------------------------------
    exec_results: List[Dict[str, Any]] = []

    for action in actions:
        tool_name = action.get("tool", "")
        tool_query = action.get("query", "")

        yield {
            "type": "tool_start",
            "payload": {"tool": tool_name, "query": tool_query},
        }

        result_entry = _execute_single_action(agent, tool_name, tool_query)
        exec_results.append(result_entry)

        yield {
            "type": "tool_result",
            "payload": {
                "tool": tool_name,
                "result": _truncate(result_entry.get("result", ""), 1000),
                "sources": _format_sources_from_metadata(result_entry.get("metadata", {})),
            },
        }

    # 存储工具结果到记忆
    for result in exec_results:
        agent.memory.add(
            f"[{result['tool']}] {result['result'][:500]}",
            content_type="tool_result",
        )

    # ------------------------------------------------------------------
    # 阶段 4: 生成初步答案
    # ------------------------------------------------------------------
    current_answer = agent._generate_answer(query, exec_results)  # pylint: disable=protected-access
    yield {"type": "answer", "payload": {"answer": current_answer}}

    # ------------------------------------------------------------------
    # 阶段 5: 反思迭代
    # ------------------------------------------------------------------
    agent.reflection.reset()
    for iteration in range(config.reflection_max_iterations):
        should_continue, new_actions = agent.reflection.evaluate_and_refine(
            query=query,
            current_answer=current_answer,
            memory_context=agent.memory.get_context(),
        )

        # 发射反思事件
        yield {
            "type": "reflection",
            "payload": {
                "score": (
                    config.reflection_quality_threshold
                    if not should_continue
                    else 0.0
                ),
                "needs_iteration": should_continue,
                "iteration": iteration + 1,
            },
        }

        if not should_continue or not new_actions:
            break

        # 执行补充 Actions
        logger.info("--- WS 迭代补充 (第 %d 轮) ---", iteration + 1)
        for action in new_actions:
            tool_name = action.get("tool", "")
            tool_query = action.get("query", "")

            yield {
                "type": "tool_start",
                "payload": {"tool": tool_name, "query": tool_query},
            }

            supplement_result = _execute_single_action(agent, tool_name, tool_query)
            exec_results.append(supplement_result)

            agent.memory.add(
                f"[补充-{tool_name}] {supplement_result['result'][:500]}",
                content_type="tool_result",
            )

            yield {
                "type": "tool_result",
                "payload": {
                    "tool": tool_name,
                    "result": _truncate(supplement_result.get("result", ""), 1000),
                    "sources": _format_sources_from_metadata(
                        supplement_result.get("metadata", {})
                    ),
                },
            }

        # 重新生成答案
        current_answer = agent._generate_answer(query, exec_results)  # pylint: disable=protected-access
        yield {"type": "answer", "payload": {"answer": current_answer}}

    # ------------------------------------------------------------------
    # 阶段 6: 完成
    # ------------------------------------------------------------------
    agent.memory.add(current_answer, content_type="final_answer")
    yield _build_done_event(agent, current_answer)


# =============================================================================
# 内部辅助函数
# =============================================================================


def _execute_single_action(
    agent: AutoSalesAgent,
    tool_name: str,
    tool_query: str,
) -> Dict[str, Any]:
    """执行单个 Action 并返回标准化结果字典。

    Args:
        agent: Agent 实例。
        tool_name: 要调用的工具名称。
        tool_query: 传递给工具 run() 方法的查询字符串。

    Returns:
        Dict: 包含 tool, query, status, result, metadata 的结果字典。
    """
    try:
        tool = agent.executor.get_tool(tool_name)
        tool_output = tool.run(tool_query)
        return {
            "tool": tool_name,
            "query": tool_query,
            "status": tool_output.get("status", "unknown"),
            "result": tool_output.get("result", ""),
            "metadata": tool_output.get("metadata", {}),
        }
    except KeyError:
        logger.warning("工具未注册: %s", tool_name)
        return {
            "tool": tool_name,
            "query": tool_query,
            "status": "error",
            "result": f"工具未注册: {tool_name}",
            "metadata": {},
        }
    except Exception as exc:
        logger.error("工具 '%s' 执行异常: %s", tool_name, exc)
        return {
            "tool": tool_name,
            "query": tool_query,
            "status": "error",
            "result": f"执行异常: {exc}",
            "metadata": {},
        }


def _extract_sources_from_agent(agent: AutoSalesAgent) -> List[str]:
    """从 Agent 短期记忆中提取去重后的信息来源文本。

    Args:
        agent: Agent 实例。

    Returns:
        List[str]: 去重后的来源文本片段列表（每条最长 1000 字符）。
    """
    raw = agent.get_state()
    memory = raw.get("memory", [])
    sources: List[str] = []
    seen: Set[str] = set()

    for entry in memory:
        if entry.get("type") == "tool_result":
            content = entry.get("content", "")
            dedup_key = content[:200]
            if dedup_key not in seen:
                seen.add(dedup_key)
                sources.append(content[:1000])

    return sources


def _build_trace_from_agent(agent: AutoSalesAgent) -> List[str]:
    """从 Agent 记忆构建人类可读的执行追踪列表。

    Args:
        agent: Agent 实例。

    Returns:
        List[str]: 追踪条目（最多 20 条，每条目截断至 120 字符）。
    """
    raw = agent.get_state()
    memory = raw.get("memory", [])
    trace: List[str] = []
    for entry in memory[-20:]:
        etype = entry.get("type", "step")
        content = entry.get("content", "")[:120]
        trace.append(f"[{etype}] {content}")
    return trace


def _build_done_event(agent: AutoSalesAgent, final_answer: str) -> Dict[str, Any]:
    """构建 WebSocket 'done' 事件。

    Args:
        agent: Agent 实例。
        final_answer: 最终回答文本。

    Returns:
        Dict: 符合约定格式的 done 事件字典。
    """
    return {
        "type": "done",
        "payload": {
            "final_answer": final_answer,
            "sources": _extract_sources_from_agent(agent),
            "trace": _build_trace_from_agent(agent),
        },
    }


def _format_sources_from_metadata(metadata: Any) -> str:
    """将工具 metadata 中的 sources 字段格式化为字符串。

    Args:
        metadata: 工具 run() 返回的 metadata 字段。

    Returns:
        str: 格式化后的来源信息文本。
    """
    if not isinstance(metadata, dict):
        return ""
    raw_sources = metadata.get("sources", "")
    if isinstance(raw_sources, list):
        return "; ".join(str(s) for s in raw_sources)
    return str(raw_sources)


def _truncate(text: str, max_len: int) -> str:
    """截断文本到指定最大长度。

    Args:
        text: 输入文本。
        max_len: 最大字符数。

    Returns:
        str: 截断后的文本（超长时末尾不添加省略号以保持 JSON 清洁）。
    """
    return text if len(text) <= max_len else text[:max_len]


# =============================================================================
# 程序入口
# =============================================================================

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=config.log_level.lower(),
    )
