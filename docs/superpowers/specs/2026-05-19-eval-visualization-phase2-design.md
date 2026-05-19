# AutoSalesAgent RAG 评测可视化（二期） 设计文档

## 概述

在一期评测运行器基础上，使用 Recharts 图表库为评测结果添加可视化展示。新增后端权重扫描端点，前端重构 EvalPanel 为 Tab 布局，拆分为三个独立图表组件。

**依赖**：一期 eval 前端 (`docs/superpowers/specs/2026-05-19-eval-frontend-phase1-design.md`)

---

## 后端设计

### 新增端点

**`POST /api/eval/sweep`** — 权重扫描评测

请求体（复用 EvalRunRequest 的部分字段）：

```json
{
  "dataset_name": "auto_sales_eval_v1.0.json",
  "top_k": 5,
  "generate_answers": false
}
```

缺省 `retrieval_mode`（sweep 固定 hybrid）。后端逻辑：

1. 检查 RAG 索引状态
2. 加载数据集
3. 创建 `EvalRunner(rag_tool=agent.rag_tool, top_k=top_k)`
4. 调用 `runner.sweep_weights(dataset, generate_answers=generate_answers)`
5. 返回 `[report.to_dict() for report in reports]`

**注意**：共享 `EvalRunRequest` 模型（仅不传 retrieval_mode），不新建模型。top_k 从请求读取，不传则默认 5。

### Pydantic 模型调整

`EvalRunRequest.retrieval_mode` 已有默认值 `"hybrid"`，sweep 端点忽略此字段即可。无需新增模型。

---

## 前端设计

### 新增依赖

```bash
npm install recharts
```

### 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `EvalPanel.tsx` | 重构 | Tab 容器：配置区 + 运行按钮 + Tabs 结果区 |
| `EvalOverviewTab.tsx` | 新建 | 雷达图 + 检索柱状图 + 生成柱状图 + 性能数据 |
| `EvalPerSampleTab.tsx` | 新建 | 散点图 + 逐样本明细列表 |
| `EvalSweepTab.tsx` | 新建 | 权重扫描运行 + 分组柱状对比图 |
| `types/index.ts` | 修改 | 新增 `WeightSweepRequest` |
| `api.ts` | 修改 | 新增 `runSweep()` |
| `package.json` | 修改 | 新增 `recharts` 依赖 |

### EvalPanel.tsx 重构

```
┌─ RAG 评测 ─────────────────────────────────────┐
│  数据集 ▼  模式 ○○●  Top-K [5]  ☑生成        │
│  [▶ 运行评测]                                    │
│  ───────────────────────────────────────────    │
│  [总览]  [逐样本]  [权重扫描]                     │
│  ┌──── 当前 Tab 内容 ─────────────────────┐     │
│  │  ...                                     │     │
│  └──────────────────────────────────────────┘     │
└─────────────────────────────────────────────────┘
```

- 配置区和运行按钮保持在 Tabs 上方
- `result` state 继续持有 `EvalRunResponse`
- `activeTab` state 控制当前 Tab

### EvalOverviewTab.tsx

Props: `{ result: EvalRunResponse; generateAnswers: boolean }`

**雷达图** (`RadarChart`)：
- 6 个极点：Context Relevance, Context Recall, MRR, NDCG, Faithfulness, Answer Relevance
- 数据源：`retrieval_quality` + `generation_quality` 对象合并
- 半透明蓝色填充 + 描边
- 如果 `generateAnswers=false`，仅显示 4 个检索维度

**检索质量柱状图** (`BarChart`)：
- X 轴：4 个检索指标名
- Y 轴：0-1
- 单色柱状，每根柱顶部显示数值标签

**生成质量柱状图** (`BarChart`)：
- X 轴：3 个生成指标名
- 仅在 `generateAnswers=true` 时渲染
- 与检索柱状图样式一致

**布局**：`Row` + `Col`，雷达图 12 格，柱状图区 12 格（两个柱状图上下各半）。

### EvalPerSampleTab.tsx

Props: `{ result: EvalRunResponse }`

**散点图** (`ScatterChart`)：
- X 轴：Context Relevance (0-1)
- Y 轴：Faithfulness (0-1)
- 每点一条样本，颜色按难度：
  - easy: `#3fb950`
  - medium: `#d29922`
  - hard: `#f85149`
- Tooltip：hover 显示 query 文本（截断 60 字）

**难度图例**：散点图下方显示 3 个颜色图例项

**明细列表**：散点图下方保留一期 Collapse accordion

### EvalSweepTab.tsx

Props: `{ datasetName: string | null; topK: number }`

**运行区**：
- 默认权重组合显示为可勾选列表（6 组预设，全部默认选中）
- "运行权重扫描" 按钮，loading 状态

**结果对比图** (`BarChart`)：
- X 轴：3 个核心指标（Context Recall, MRR, Faithfulness）
- 每指标下一组柱状 = 各权重组合，颜色区分
- 图例显示 `dense=X, sparse=Y` 格式

**后端调用**：`POST /api/eval/sweep`，传入 dataset_name + top_k + generate_answers=false

### TypeScript 类型扩展

```ts
export interface WeightSweepRequest {
  dataset_name: string;
  top_k: number;
  generate_answers: boolean;
}
```

Sweep 响应直接复用 `EvalRunResponse[]`。

### API 函数

```ts
export async function runSweep(data: WeightSweepRequest): Promise<EvalRunResponse[]> {
  return request<EvalRunResponse[]>('/eval/sweep', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
```

---

## 错误处理

- Sweep 无数据集：后端 400，前端 `message.error`
- 图表数据为空：显示空状态 `Empty` 组件
- Recharts 渲染异常：每个 Tab 独立 try/catch 不影响其他 Tab

---

## 改动文件清单

| 文件 | 改动量 | 说明 |
|------|--------|------|
| `frontend/backend/server.py` | ~30 行 | 新增 `POST /api/eval/sweep` |
| `frontend/src/types/index.ts` | ~5 行 | 新增 `WeightSweepRequest` |
| `frontend/src/services/api.ts` | ~6 行 | 新增 `runSweep()` |
| `frontend/src/components/Settings/EvalPanel.tsx` | 重构 ~120 行 | Tab 容器 |
| `frontend/src/components/Settings/EvalOverviewTab.tsx` | 新建 ~100 行 | 雷达图 + 柱状图 |
| `frontend/src/components/Settings/EvalPerSampleTab.tsx` | 新建 ~80 行 | 散点图 + 明细 |
| `frontend/src/components/Settings/EvalSweepTab.tsx` | 新建 ~100 行 | 权重扫描 |
| `frontend/package.json` | +1 行 | recharts 依赖 |
