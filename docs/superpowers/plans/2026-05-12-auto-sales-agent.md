# AutoSalesAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete enterprise car sales training Agent with componentized architecture and workflow-driven execution.

**Architecture:** Layered design — infrastructure (vector DB, embedding API, doc parsing) → tools (RAG, web search, calculator) → agent core (planning, memory, executor, reflection). All LLM/Embedding calls use Alibaba Qianwen API via OpenAI-compatible interface. No heavy frameworks.

**Tech Stack:** Python 3.10+, Milvus, ChromaDB, OpenAI SDK (for Qianwen), LlamaParse, requests, BeautifulSoup, Pydantic

---

## File Structure

| File | Responsibility |
|------|---------------|
| `config.py` | All API keys, URLs, model params, paths |
| `infrastructure/__init__.py` | Package exports |
| `infrastructure/embedding.py` | Qianwen embedding API client (dense + sparse) |
| `infrastructure/vector_db.py` | Milvus connection, schema, indexing, hybrid search |
| `infrastructure/doc_parser.py` | LlamaParse PDF parser + smart chunker |
| `tools/__init__.py` | Tool registry |
| `tools/base_tool.py` | Abstract base tool class |
| `tools/rag_tool.py` | RAG: index → search → answer with citations |
| `tools/web_search_tool.py` | SerpAPI + multi-threaded crawl + ChromaDB |
| `tools/calculator_tool.py` | Safe expression evaluator |
| `agent/__init__.py` | Agent package exports |
| `agent/planning.py` | LLM-based action plan generation |
| `agent/memory.py` | Short-term memory with compression |
| `agent/executor.py` | Task queue execution via tool registry |
| `agent/reflection.py` | Quality evaluation and iteration control |
| `agent/agent_core.py` | Main agent loop orchestrating all modules |
| `prompts/plan_prompt.txt` | Few-shot planning prompt |
| `prompts/reflection_prompt.txt` | Reflection evaluation prompt |
| `prompts/rag_prompt.txt` | RAG answer generation template |
| `main.py` | Interactive CLI with multi-turn conversation |

---

### Task 1: Configuration Module

**Files:** Create `config.py`

Configuration dataclass with all settings: LLM API (Qianwen), Embedding API, Milvus path, SerpAPI key, LlamaParse key, retrieval params.

---

### Task 2: Infrastructure Layer

**Files:** Create `infrastructure/__init__.py`, `infrastructure/embedding.py`, `infrastructure/vector_db.py`, `infrastructure/doc_parser.py`

- `embedding.py`: `EmbeddingClient` class calling Qianwen embedding API, returning `(dense_vector, sparse_dict)`
- `vector_db.py`: `VectorDB` class — Milvus connection, collection creation with dual index (SPARSE_INVERTED_INDEX + AUTOINDEX), insert, dense/sparse/hybrid search with WeightedRanker
- `doc_parser.py`: `DocParser` class — LlamaParse API integration, `chunk_text()` with heading/table/paragraph awareness

---

### Task 3: Tool Layer

**Files:** Create `tools/__init__.py`, `tools/base_tool.py`, `tools/rag_tool.py`, `tools/web_search_tool.py`, `tools/calculator_tool.py`

- `base_tool.py`: Abstract `BaseTool` with `run(query, **kwargs) -> Dict`
- `rag_tool.py`: `RAGTool` — index_documents, hybrid search, LLM answer generation with citation numbers
- `web_search_tool.py`: `WebSearchTool` — SerpAPI query, multi-threaded BeautifulSoup crawl, ChromaDB temp storage, semantic retrieval
- `calculator_tool.py`: `CalculatorTool` — safe eval for math expressions

---

### Task 4: Prompt Files

**Files:** Create `prompts/plan_prompt.txt`, `prompts/reflection_prompt.txt`, `prompts/rag_prompt.txt`

Few-shot prompts for planning, reflection evaluation, and RAG answer generation.

---

### Task 5: Agent Core Layer

**Files:** Create `agent/__init__.py`, `agent/planning.py`, `agent/memory.py`, `agent/executor.py`, `agent/reflection.py`, `agent/agent_core.py`

- `planning.py`: `PlanningModule` — calls LLM with plan prompt, parses JSON ActionList
- `memory.py`: `Memory` — list-based short-term memory with compress() via LLM summarization
- `executor.py`: `Executor` — deque-based task queue, tool registry lookup, sequential execution
- `reflection.py`: `ReflectionModule` — LLM evaluation, iterate-or-stop decision, max 3 iterations
- `agent_core.py`: `AutoSalesAgent` — main loop: plan → execute → answer → reflect → (repeat or output)

---

### Task 6: CLI Entry Point

**Files:** Create `main.py`

Interactive command-line interface with welcome message, multi-turn conversation loop, `/exit` command, session history display.

---

### Task 7: Dependencies Update

**Files:** Modify `requirements.txt`

Add missing deps, remove unnecessary local-model deps.
