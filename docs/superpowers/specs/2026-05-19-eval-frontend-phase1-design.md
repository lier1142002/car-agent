# AutoSalesAgent RAG 评测前端化（一期） 设计文档

## 概述

当前 eval 模块仅支持 CLI/Python 调用，缺少前端可视化入口。一期目标：新增评测 API 端点 + 独立评测面板，支持选择数据集、配置参数、运行评测、查看结果。

**范围外（二三期）：** 数据集管理界面、图表可视化、权重扫描 UI、历史报告对比。

---

## 后端设计

### 新增端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/eval/datasets` | 列出 `eval/datasets/` 下所有 JSON 数据集及摘要 |
| `POST` | `/api/eval/run` | 运行评测，返回 EvalReport |

### GET /api/eval/datasets

扫描 `eval/datasets/` 目录下所有 `.json` 文件，调用 `GoldenDataset.load()` 读取每个数据集，返回摘要列表。

**响应：**

```json
[
  {
    "name": "auto_sales_eval_v1.0",
    "total_samples": 10,
    "by_type": {"factual": 5, "comparative": 3, "sales_scenario": 2},
    "by_difficulty": {"easy": 3, "medium": 5, "hard": 2}
  }
]
```

实现：遍历 `eval/datasets/*.json`，对每个文件调用 `GoldenDataset.load()` + `ds.summary()`。

### POST /api/eval/run

**请求体：**

```json
{
  "dataset_name": "auto_sales_eval_v1.0.json",
  "retrieval_mode": "hybrid",
  "top_k": 5,
  "generate_answers": true
}
```

**处理流程：**

1. 检查 `agent.get_state().rag_indexed` — 未索引返回 400
2. 加载数据集 `GoldenDataset.load(eval/datasets/{dataset_name})`
3. 创建 `EvalRunner(rag_tool=agent.rag_tool, top_k=top_k)`
4. 调用 `runner.run(dataset, retrieval_mode=retrieval_mode, generate_answers=generate_answers)`
5. 返回 `report.to_dict()`

**响应：** 直接使用 `EvalReport.to_dict()` 的 JSON 结构，包含：

```json
{
  "dataset_name": "...",
  "total_samples": 10,
  "retrieval_mode": "hybrid",
  "config": {"dense_weight": 1.0, "sparse_weight": 0.7, "top_k": 5, "generate_answers": true},
  "retrieval_quality": {
    "context_relevance": 0.85,
    "context_recall": 0.72,
    "mrr": 0.68,
    "ndcg": 0.74
  },
  "generation_quality": {
    "faithfulness": 0.91,
    "hallucination_rate": 0.09,
    "answer_relevance": 0.83
  },
  "performance": {
    "avg_retrieval_latency_ms": 12.3,
    "avg_generation_latency_ms": 345.1,
    "p95_retrieval_latency_ms": 25.1,
    "p95_generation_latency_ms": 512.3
  },
  "per_sample": [...],
  "failed_samples": []
}
```

### Pydantic 模型

```python
class EvalRunRequest(BaseModel):
    dataset_name: str = Field(..., min_length=1)
    retrieval_mode: str = Field("hybrid", pattern="^(dense|sparse|hybrid)$")
    top_k: int = Field(5, ge=1, le=50)
    generate_answers: bool = Field(True)

class DatasetItem(BaseModel):
    name: str
    total_samples: int
    by_type: dict
    by_difficulty: dict
```

---

## 前端设计

### TypeScript 类型扩展 (`types/index.ts`)

```ts
export interface EvalRunRequest {
  dataset_name: string;
  retrieval_mode: 'dense' | 'sparse' | 'hybrid';
  top_k: number;
  generate_answers: boolean;
}

export interface EvalRunResponse {
  dataset_name: string;
  total_samples: number;
  retrieval_mode: string;
  config: Record<string, unknown>;
  retrieval_quality: {
    context_relevance: number;
    context_recall: number;
    mrr: number;
    ndcg: number;
  };
  generation_quality: {
    faithfulness: number;
    hallucination_rate: number;
    answer_relevance: number;
  };
  performance: {
    avg_retrieval_latency_ms: number;
    avg_generation_latency_ms: number;
    p95_retrieval_latency_ms: number;
    p95_generation_latency_ms: number;
  };
  per_sample: EvalSampleResult[];
  failed_samples: string[];
}

export interface EvalSampleResult {
  query: string;
  ground_truth: string;
  context_relevance: number;
  context_recall: number;
  mrr: number;
  ndcg: number;
  faithfulness: number;
  hallucination_rate: number;
  answer_relevance: number;
  generated_answer: string;
  retrieval_latency_ms: number;
  generation_latency_ms: number;
}

export interface DatasetSummary {
  name: string;
  total_samples: number;
  by_type: Record<string, number>;
  by_difficulty: Record<string, number>;
}
```

### API 服务 (`services/api.ts`)

```ts
export async function getDatasets(): Promise<DatasetSummary[]> {
  return request<DatasetSummary[]>('/eval/datasets');
}

export async function runEval(data: EvalRunRequest): Promise<EvalRunResponse> {
  return request<EvalRunResponse>('/eval/run', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
```

### 新组件 `EvalPanel.tsx`

独立的评测抽屉面板，包含三部分：

**1. 数据集选择区**

- `Select` 下拉：页面打开时 fetch datasets，显示 `{name} ({total_samples}条)`
- 选中后显示摘要标签：factual N条 / comparative N条 / sales_scenario N条

**2. 参数配置区**

- 检索模式：`Radio.Group` — Dense / Sparse / Hybrid，默认 Hybrid
- Top-K：`InputNumber` min=1 max=50，默认 5
- 生成回答：`Switch` 开关，默认开

**3. 运行 & 结果区**

- "运行评测" 按钮：`loading` 状态，运行时禁用所有控件
- 运行完成后显示结果：
  - **检索质量卡片**：4 个指标，每行 `标签 + 进度条 + 百分比`
  - **生成质量卡片**：3 个指标
  - **性能卡片**：avg + P95 延迟
  - **逐样本明细**：`Collapse` 组件，每条样本展开显示各项指标 + 生成的回答

### Sidebar 入口

在 Sidebar 底部 "设置" 按钮旁边新增 "RAG 评测" 按钮，`onClick` 打开 EvalPanel Drawer。

### 入口集成 (`Sidebar.tsx`)

需要读取 Sidebar.tsx 当前结构确认具体修改点。大致改动：

```tsx
// 新增 state
const [evalOpen, setEvalOpen] = useState(false);

// 新增按钮（设置按钮旁）
<Button onClick={() => setEvalOpen(true)}>RAG 评测</Button>

// 新增 Drawer
<EvalPanel open={evalOpen} onClose={() => setEvalOpen(false)} />
```

---

## 错误处理

| 场景 | 后端 | 前端 |
|------|------|------|
| eval/datasets/ 无 JSON 文件 | 返回空数组 `[]` | 显示 "暂无可用数据集" |
| 数据集文件无效 JSON | 返回 400 + 错误消息 | `message.error` |
| RAG 未索引 | 返回 400 `"请先索引知识库"` | `message.warning` 提示先上传 PDF |
| 单样本评测异常 | try/catch，加入 failed_samples | 结果中展示失败样本列表 |
| 评测运行时再次点击 | 前端按钮 loading 禁用 | — |

---

## 改动文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/backend/server.py` | 修改 | 新增 2 个端点 + Pydantic 模型 (~80 行) |
| `frontend/src/types/index.ts` | 修改 | 新增 4 个 Eval 类型 (~50 行) |
| `frontend/src/services/api.ts` | 修改 | 新增 2 个 API 函数 (~10 行) |
| `frontend/src/components/Settings/EvalPanel.tsx` | 新建 | 评测面板 (~150 行) |
| `frontend/src/components/Sidebar/Sidebar.tsx` | 修改 | 新增入口按钮 (~15 行) |
