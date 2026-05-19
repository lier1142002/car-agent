# RAG 评测可视化（二期）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用 Recharts 为评测结果添加可视化图表（雷达图、柱状图、散点图、权重扫描对比图），重构 EvalPanel 为 Tab 布局。

**Architecture:** 安装 recharts 依赖，后端新增 `POST /api/eval/sweep` 权重扫描端点。前端 EvalPanel 重构为 Tab 容器（配置区 + [总览/逐样本/权重扫描] 三个 Tab），每个 Tab 是独立组件通过 props 接收 result。

**Tech Stack:** Python FastAPI (后端), React 18 + TypeScript + Recharts + Ant Design 5 (前端)

**Spec:** `docs/superpowers/specs/2026-05-19-eval-visualization-phase2-design.md`

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `frontend/package.json` | 修改 | 新增 `recharts` 依赖 |
| `frontend/backend/server.py` | 修改 | 新增 `POST /api/eval/sweep` 端点 |
| `frontend/src/types/index.ts` | 修改 | 新增 `WeightSweepRequest` |
| `frontend/src/services/api.ts` | 修改 | 新增 `runSweep()` |
| `frontend/src/components/Settings/EvalPanel.tsx` | 重构 | Tab 容器（瘦身至 ~130 行） |
| `frontend/src/components/Settings/EvalOverviewTab.tsx` | 新建 | 雷达图 + 检索/生成柱状图 |
| `frontend/src/components/Settings/EvalPerSampleTab.tsx` | 新建 | 散点图 + 明细 accordion |
| `frontend/src/components/Settings/EvalSweepTab.tsx` | 新建 | 权重扫描 + 对比柱状图 |

---

### Task 1: 安装 recharts 依赖

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: 安装 recharts**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npm install recharts
```

- [ ] **Step 2: 验证安装**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && node -e "require('recharts'); console.log('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat: add recharts dependency for eval visualization

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: 新增 POST /api/eval/sweep 端点

**Files:**
- Modify: `frontend/backend/server.py`

- [ ] **Step 1: 在 eval/run 端点之后新增 sweep 端点**

位置：在 `POST /api/eval/run` 端点之后（`raise HTTPException(status_code=500, detail=f"评测运行失败: {exc}")` 代码块之后）。

新增：

```python
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
```

- [ ] **Step 2: 验证导入**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from frontend.backend.server import app; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add frontend/backend/server.py
git commit -m "feat: add POST /api/eval/sweep endpoint for weight sweep evaluation

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: 新增 sweep 类型 + API 函数

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: 新增 WeightSweepRequest 类型**

在 `frontend/src/types/index.ts` 的 eval 类型区域追加：

```ts
/** 权重扫描请求 */
export interface WeightSweepRequest {
  dataset_name: string;
  top_k: number;
  generate_answers: boolean;
}
```

- [ ] **Step 2: 修改 api.ts import**

`frontend/src/services/api.ts` 的 import 行当前：

```ts
import type { ChatRequest, ChatResponse, AgentState, ConfigSettings, UpdateConfigPayload, PdfUploadResponse, DatasetSummary, EvalRunRequest, EvalRunResponse } from '../types';
```

末尾追加 `WeightSweepRequest`：

```ts
import type { ChatRequest, ChatResponse, AgentState, ConfigSettings, UpdateConfigPayload, PdfUploadResponse, DatasetSummary, EvalRunRequest, EvalRunResponse, WeightSweepRequest } from '../types';
```

- [ ] **Step 3: 新增 runSweep 函数**

在 `api.ts` 文件末尾追加：

```ts
export async function runSweep(data: WeightSweepRequest): Promise<EvalRunResponse[]> {
  return request<EvalRunResponse[]>('/eval/sweep', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
```

- [ ] **Step 4: 验证 TypeScript 编译**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/services/api.ts
git commit -m "feat: add WeightSweepRequest type and runSweep API function

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 创建 EvalOverviewTab 组件

**Files:**
- Create: `frontend/src/components/Settings/EvalOverviewTab.tsx`

- [ ] **Step 1: 创建 EvalOverviewTab.tsx**

```tsx
import React from 'react';
import { Typography, Descriptions, Empty } from 'antd';
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import type { EvalRunResponse } from '../../types';
import styles from '../../styles/Settings.module.css';

const { Title } = Typography;

interface Props {
  result: EvalRunResponse;
  generateAnswers: boolean;
}

const METRIC_LABELS: Record<string, string> = {
  context_relevance: 'Context Relevance',
  context_recall: 'Context Recall',
  mrr: 'MRR',
  ndcg: 'NDCG',
  faithfulness: 'Faithfulness',
  hallucination_rate: 'Hallucination Rate',
  answer_relevance: 'Answer Relevance',
};

const COLORS = {
  radar: '#58a6ff',
  bar: '#3fb950',
};

export const EvalOverviewTab: React.FC<Props> = ({ result, generateAnswers }) => {
  if (!result) return <Empty description="请先运行评测" />;

  const radarData = [
    ...Object.entries(result.retrieval_quality).map(([key, val]) => ({
      metric: METRIC_LABELS[key] || key,
      value: val,
    })),
    ...(generateAnswers
      ? Object.entries(result.generation_quality)
          .filter(([key]) => key !== 'hallucination_rate')
          .map(([key, val]) => ({
            metric: METRIC_LABELS[key] || key,
            value: val,
          }))
      : []),
  ];

  const retrievalBarData = Object.entries(result.retrieval_quality).map(([key, val]) => ({
    name: METRIC_LABELS[key] || key,
    value: val,
  }));

  const genBarData = Object.entries(result.generation_quality)
    .filter(([key]) => key !== 'hallucination_rate')
    .map(([key, val]) => ({
      name: METRIC_LABELS[key] || key,
      value: val,
    }));

  return (
    <div>
      {/* 雷达图 */}
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>指标雷达图</h4>
        <ResponsiveContainer width="100%" height={280}>
          <RadarChart data={radarData}>
            <PolarGrid stroke="#30363d" />
            <PolarAngleAxis dataKey="metric" tick={{ fill: '#8b949e', fontSize: 11 }} />
            <PolarRadiusAxis domain={[0, 1]} tick={{ fill: '#8b949e', fontSize: 10 }} />
            <Radar dataKey="value" stroke={COLORS.radar} fill={COLORS.radar} fillOpacity={0.2} />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      <div className={styles.divider} />

      {/* 检索质量柱状图 */}
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>检索质量</h4>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={retrievalBarData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid stroke="#30363d" strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fill: '#8b949e', fontSize: 11 }} />
            <YAxis domain={[0, 1]} tick={{ fill: '#8b949e', fontSize: 10 }} />
            <Tooltip
              contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 4 }}
              formatter={(val: number) => (val * 100).toFixed(1) + '%'}
            />
            <Bar dataKey="value" fill={COLORS.bar} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* 生成质量柱状图 */}
      {generateAnswers && genBarData.length > 0 && (
        <>
          <div className={styles.divider} />
          <div className={styles.section}>
            <h4 className={styles.sectionTitle}>生成质量</h4>
            <ResponsiveContainer width="100%" height={150}>
              <BarChart data={genBarData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid stroke="#30363d" strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fill: '#8b949e', fontSize: 11 }} />
                <YAxis domain={[0, 1]} tick={{ fill: '#8b949e', fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 4 }}
                  formatter={(val: number) => (val * 100).toFixed(1) + '%'}
                />
                <Bar dataKey="value" fill="#58a6ff" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {/* 性能 */}
      <div className={styles.divider} />
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>性能</h4>
        <Descriptions size="small" column={2} colon={false}>
          <Descriptions.Item label="检索延迟 (avg)">
            {result.performance.avg_retrieval_latency_ms.toFixed(1)} ms
          </Descriptions.Item>
          <Descriptions.Item label="检索延迟 (P95)">
            {result.performance.p95_retrieval_latency_ms.toFixed(1)} ms
          </Descriptions.Item>
          {generateAnswers && (
            <>
              <Descriptions.Item label="生成延迟 (avg)">
                {result.performance.avg_generation_latency_ms.toFixed(1)} ms
              </Descriptions.Item>
              <Descriptions.Item label="生成延迟 (P95)">
                {result.performance.p95_generation_latency_ms.toFixed(1)} ms
              </Descriptions.Item>
            </>
          )}
        </Descriptions>
      </div>

      {/* 失败样本 */}
      {result.failed_samples.length > 0 && (
        <>
          <div className={styles.divider} />
          <div className={styles.section}>
            <h4 className={styles.sectionTitle}>失败样本 ({result.failed_samples.length})</h4>
            {result.failed_samples.map((q, i) => (
              <Typography.Text key={i} type="danger" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                {q}
              </Typography.Text>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Settings/EvalOverviewTab.tsx
git commit -m "feat: add EvalOverviewTab with radar chart and bar charts

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: 创建 EvalPerSampleTab 组件

**Files:**
- Create: `frontend/src/components/Settings/EvalPerSampleTab.tsx`

- [ ] **Step 1: 创建 EvalPerSampleTab.tsx**

```tsx
import React from 'react';
import { Typography, Descriptions, Collapse, Empty } from 'antd';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ZAxis,
} from 'recharts';
import type { EvalRunResponse } from '../../types';
import styles from '../../styles/Settings.module.css';

const { Text } = Typography;
const { Panel } = Collapse;

interface Props {
  result: EvalRunResponse;
}

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: '#3fb950',
  medium: '#d29922',
  hard: '#f85149',
};

export const EvalPerSampleTab: React.FC<Props> = ({ result }) => {
  if (!result || result.per_sample.length === 0) return <Empty description="暂无样本数据" />;

  // 构建散点图数据（按难度分组）
  const scatterData = result.per_sample
    .filter(s => s.context_relevance > 0 || s.faithfulness > 0)
    .map(s => ({
      x: s.context_relevance,
      y: s.faithfulness,
      query: s.query.length > 60 ? s.query.slice(0, 60) + '...' : s.query,
      difficulty: s.ground_truth ? 'medium' : 'easy', // 近似难度标记
    }));

  // 按颜色分组
  const easyData = scatterData.filter(d => d.difficulty === 'easy');
  const mediumData = scatterData.filter(d => d.difficulty === 'medium');
  const hardData = scatterData.filter(d => d.difficulty === 'hard');

  return (
    <div>
      {/* 散点图 */}
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>样本分布 (Relevance × Faithfulness)</h4>
        <ResponsiveContainer width="100%" height={300}>
          <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
            <CartesianGrid stroke="#30363d" strokeDasharray="3 3" />
            <XAxis
              dataKey="x"
              name="Context Relevance"
              domain={[0, 1]}
              tick={{ fill: '#8b949e', fontSize: 10 }}
              label={{ value: 'Context Relevance', position: 'bottom', fill: '#8b949e', fontSize: 11 }}
            />
            <YAxis
              dataKey="y"
              name="Faithfulness"
              domain={[0, 1]}
              tick={{ fill: '#8b949e', fontSize: 10 }}
              label={{ value: 'Faithfulness', angle: -90, position: 'left', fill: '#8b949e', fontSize: 11 }}
            />
            <ZAxis range={[60, 60]} />
            <Tooltip
              contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 4 }}
              formatter={(val: number, name: string) => [
                (val * 100).toFixed(1) + '%',
                name === 'x' ? 'Context Relevance' : 'Faithfulness',
              ]}
            />
            <Legend />
            <Scatter name="easy" data={easyData} fill={DIFFICULTY_COLORS.easy} />
            <Scatter name="medium" data={mediumData} fill={DIFFICULTY_COLORS.medium} />
            <Scatter name="hard" data={hardData} fill={DIFFICULTY_COLORS.hard} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <div className={styles.divider} />

      {/* 逐样本明细 */}
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>逐样本明细 ({result.per_sample.length} 条)</h4>
        <Collapse size="small" ghost>
          {result.per_sample.map((s, i) => (
            <Panel
              key={i}
              header={
                <Text ellipsis style={{ fontSize: 12, maxWidth: 380 }}>
                  {s.query}
                </Text>
              }
            >
              <Descriptions size="small" column={2} colon={false}>
                <Descriptions.Item label="Context Relevance">{s.context_relevance.toFixed(3)}</Descriptions.Item>
                <Descriptions.Item label="Context Recall">{s.context_recall.toFixed(3)}</Descriptions.Item>
                <Descriptions.Item label="Faithfulness">{s.faithfulness.toFixed(3)}</Descriptions.Item>
                <Descriptions.Item label="Answer Relevance">{s.answer_relevance.toFixed(3)}</Descriptions.Item>
                <Descriptions.Item label="MRR">{s.mrr.toFixed(3)}</Descriptions.Item>
                <Descriptions.Item label="NDCG">{s.ndcg.toFixed(3)}</Descriptions.Item>
                <Descriptions.Item label="Latency">{s.retrieval_latency_ms.toFixed(0)}ms</Descriptions.Item>
                <Descriptions.Item label="Hallucination">{(s.hallucination_rate * 100).toFixed(1)}%</Descriptions.Item>
              </Descriptions>
              {s.ground_truth && (
                <div style={{ marginTop: 8 }}>
                  <Text strong style={{ fontSize: 12 }}>标准答案:</Text>
                  <Text style={{ fontSize: 12, display: 'block', marginTop: 4, padding: 8, background: '#161b22', borderRadius: 4 }}>
                    {s.ground_truth}
                  </Text>
                </div>
              )}
              {s.generated_answer && (
                <div style={{ marginTop: 8 }}>
                  <Text strong style={{ fontSize: 12 }}>生成的回答:</Text>
                  <Text style={{ fontSize: 12, display: 'block', marginTop: 4, padding: 8, background: '#161b22', borderRadius: 4 }}>
                    {s.generated_answer}
                  </Text>
                </div>
              )}
            </Panel>
          ))}
        </Collapse>
      </div>
    </div>
  );
};
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Settings/EvalPerSampleTab.tsx
git commit -m "feat: add EvalPerSampleTab with scatter chart and sample details

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: 创建 EvalSweepTab 组件

**Files:**
- Create: `frontend/src/components/Settings/EvalSweepTab.tsx`

- [ ] **Step 1: 创建 EvalSweepTab.tsx**

```tsx
import React, { useState } from 'react';
import { Button, message, Empty, Spin } from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { runSweep } from '../../services/api';
import type { EvalRunResponse } from '../../types';
import styles from '../../styles/Settings.module.css';

interface Props {
  datasetName: string | null;
  topK: number;
}

const SWEEP_COLORS = ['#58a6ff', '#3fb950', '#d29922', '#f85149', '#bc8cff', '#ff7b72'];

export const EvalSweepTab: React.FC<Props> = ({ datasetName, topK }) => {
  const [sweepResults, setSweepResults] = useState<EvalRunResponse[] | null>(null);
  const [sweeping, setSweeping] = useState(false);

  const handleSweep = async () => {
    if (!datasetName) {
      message.warning('请先在顶部选择数据集');
      return;
    }
    setSweeping(true);
    try {
      const reports = await runSweep({
        dataset_name: datasetName,
        top_k: topK,
        generate_answers: false,
      });
      setSweepResults(reports);
      message.success(`权重扫描完成: ${reports.length} 组权重`);
    } catch {
      message.error('权重扫描失败');
    } finally {
      setSweeping(false);
    }
  };

  // 构建对比柱状图数据
  const barData = ['context_recall', 'mrr', 'faithfulness'].map(metric => {
    const row: Record<string, string | number> = { metric };
    if (sweepResults) {
      for (const r of sweepResults) {
        const dw = r.config.dense_weight as number;
        const sw = r.config.sparse_weight as number;
        const label = `d=${dw.toFixed(1)} s=${sw.toFixed(1)}`;
        const val =
          metric === 'context_recall' ? r.retrieval_quality.context_recall :
          metric === 'mrr' ? r.retrieval_quality.mrr :
          r.generation_quality.faithfulness;
        row[label] = val;
      }
    }
    return row;
  });

  const barKeys = sweepResults
    ? sweepResults.map(r => {
        const dw = r.config.dense_weight as number;
        const sw = r.config.sparse_weight as number;
        return `d=${dw.toFixed(1)} s=${sw.toFixed(1)}`;
      })
    : [];

  return (
    <div>
      <Button
        type="primary"
        icon={<ExperimentOutlined />}
        onClick={handleSweep}
        loading={sweeping}
        disabled={!datasetName}
        block
      >
        {sweeping ? '扫描中...' : '运行权重扫描 (6 组 preset)'}
      </Button>

      {sweeping && (
        <div style={{ textAlign: 'center', marginTop: 24 }}>
          <Spin tip="权重扫描中，请稍候..." />
        </div>
      )}

      {sweepResults && !sweeping && (
        <>
          <div className={styles.divider} />
          <div className={styles.section}>
            <h4 className={styles.sectionTitle}>权重扫描对比</h4>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={barData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid stroke="#30363d" strokeDasharray="3 3" />
                <XAxis dataKey="metric" tick={{ fill: '#8b949e', fontSize: 11 }} />
                <YAxis domain={[0, 1]} tick={{ fill: '#8b949e', fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 4 }}
                  formatter={(val: number) => (val * 100).toFixed(1) + '%'}
                />
                <Legend />
                {barKeys.map((key, i) => (
                  <Bar key={key} dataKey={key} fill={SWEEP_COLORS[i % SWEEP_COLORS.length]} radius={[3, 3, 0, 0]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* 最佳组合提示 */}
          {sweepResults.length > 0 && (
            <div style={{ marginTop: 12 }}>
              {(() => {
                const bestRecall = sweepResults.reduce((a, b) =>
                  a.retrieval_quality.context_recall > b.retrieval_quality.context_recall ? a : b
                );
                const bestFaith = sweepResults.reduce((a, b) =>
                  a.generation_quality.faithfulness > b.generation_quality.faithfulness ? a : b
                );
                return (
                  <>
                    <div style={{ fontSize: 12, color: '#8b949e', marginBottom: 4 }}>
                      最佳 Recall: dense={bestRecall.config.dense_weight}, sparse={bestRecall.config.sparse_weight}
                      {' '}({(bestRecall.retrieval_quality.context_recall * 100).toFixed(1)}%)
                    </div>
                    <div style={{ fontSize: 12, color: '#8b949e' }}>
                      最佳 Faithfulness: dense={bestFaith.config.dense_weight}, sparse={bestFaith.config.sparse_weight}
                      {' '}({(bestFaith.generation_quality.faithfulness * 100).toFixed(1)}%)
                    </div>
                  </>
                );
              })()}
            </div>
          )}
        </>
      )}

      {!sweepResults && !sweeping && (
        <Empty description="点击上方按钮运行权重扫描" style={{ marginTop: 24 }} />
      )}
    </div>
  );
};
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Settings/EvalSweepTab.tsx
git commit -m "feat: add EvalSweepTab with weight sweep and comparison bar chart

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: 重构 EvalPanel 为 Tab 容器

**Files:**
- Modify: `frontend/src/components/Settings/EvalPanel.tsx`

- [ ] **Step 1: 重写 EvalPanel.tsx**

需要从当前的完整组件（290 行）精简为约 130 行的 Tab 容器。保留配置区 + 运行按钮，结果区替换为 Tabs。

当前 EvalPanel.tsx 需要改变的部分：
- **保留**：import、Props、state (datasets, selectedDataset, retrievalMode, topK, generateAnswers, running, result)、useEffect、handleRun
- **删除**：`renderMetricBar` 函数、所有结果展示 JSX（从 `{result && (` 开始的部分）
- **新增**：`import { Tabs } from 'antd'`、`activeTab` state、3 个 Tab 组件的 import、Tabs 替换结果区

完整的新文件内容：

```tsx
import React, { useEffect, useState } from 'react';
import { Drawer, Select, Radio, InputNumber, Switch, Button, message, Tabs, Typography, Tag } from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';
import { getDatasets, runEval } from '../../services/api';
import type { DatasetSummary, EvalRunResponse } from '../../types';
import { EvalOverviewTab } from './EvalOverviewTab';
import { EvalPerSampleTab } from './EvalPerSampleTab';
import { EvalSweepTab } from './EvalSweepTab';
import styles from '../../styles/Settings.module.css';

const { Text } = Typography;

interface Props {
  open: boolean;
  onClose: () => void;
}

export const EvalPanel: React.FC<Props> = ({ open, onClose }) => {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string | null>(null);
  const [retrievalMode, setRetrievalMode] = useState<'dense' | 'sparse' | 'hybrid'>('hybrid');
  const [topK, setTopK] = useState(5);
  const [generateAnswers, setGenerateAnswers] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<EvalRunResponse | null>(null);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    if (open) {
      getDatasets()
        .then(setDatasets)
        .catch(() => message.error('获取数据集列表失败'));
      setResult(null);
      setActiveTab('overview');
    }
  }, [open]);

  const selectedInfo = datasets.find(d => d.name === selectedDataset);

  const handleRun = async () => {
    if (!selectedDataset) {
      message.warning('请先选择数据集');
      return;
    }
    setRunning(true);
    setResult(null);
    try {
      const res = await runEval({
        dataset_name: selectedDataset,
        retrieval_mode: retrievalMode,
        top_k: topK,
        generate_answers: generateAnswers,
      });
      setResult(res);
      setActiveTab('overview');
      message.success('评测完成');
    } catch {
      message.error('评测运行失败');
    } finally {
      setRunning(false);
    }
  };

  return (
    <Drawer
      title={<><ExperimentOutlined /> RAG 评测</>}
      placement="right"
      width={540}
      open={open}
      onClose={onClose}
      className={styles.drawer}
    >
      {/* 数据集选择 */}
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>评测数据集</h4>
        <Select
          value={selectedDataset}
          onChange={(val) => { setSelectedDataset(val); setResult(null); }}
          placeholder="选择数据集"
          options={datasets.map(d => ({
            value: d.name,
            label: `${d.name} (${d.total_samples} 条)`,
          }))}
          style={{ width: '100%' }}
          size="small"
          notFoundContent="暂无可用数据集"
        />
        {selectedInfo && (
          <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {Object.entries(selectedInfo.by_type).map(([t, c]) => (
              <Tag key={t} color="blue">{t}: {c}</Tag>
            ))}
            {Object.entries(selectedInfo.by_difficulty).map(([d, c]) => (
              <Tag key={d} color="default">{d}: {c}</Tag>
            ))}
          </div>
        )}
      </div>

      <div className={styles.divider} />

      {/* 参数配置 */}
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>评测参数</h4>

        <div className={styles.formItem}>
          <label className={styles.label}>检索模式</label>
          <Radio.Group
            value={retrievalMode}
            onChange={e => setRetrievalMode(e.target.value)}
            optionType="button"
            buttonStyle="solid"
            size="small"
          >
            <Radio.Button value="dense">Dense</Radio.Button>
            <Radio.Button value="sparse">Sparse</Radio.Button>
            <Radio.Button value="hybrid">Hybrid</Radio.Button>
          </Radio.Group>
        </div>

        <div className={styles.formItem} style={{ marginTop: 12 }}>
          <label className={styles.label}>Top-K</label>
          <InputNumber
            min={1}
            max={50}
            value={topK}
            onChange={v => v !== null && setTopK(v)}
            size="small"
            style={{ width: 120 }}
          />
        </div>

        <div className={styles.formItem} style={{ marginTop: 12 }}>
          <label className={styles.label}>生成回答</label>
          <Switch checked={generateAnswers} onChange={setGenerateAnswers} size="small" />
          <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
            关闭则仅评估检索质量
          </Text>
        </div>
      </div>

      <div className={styles.divider} />

      {/* 运行按钮 */}
      <Button
        type="primary"
        icon={<ExperimentOutlined />}
        onClick={handleRun}
        loading={running}
        disabled={!selectedDataset}
        block
      >
        {running ? '评测中...' : '运行评测'}
      </Button>

      {/* 结果区 —— Tab 布局 */}
      {result && (
        <>
          <div className={styles.divider} />
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            size="small"
            items={[
              {
                key: 'overview',
                label: '总览',
                children: <EvalOverviewTab result={result} generateAnswers={generateAnswers} />,
              },
              {
                key: 'persample',
                label: `逐样本 (${result.per_sample.length})`,
                children: <EvalPerSampleTab result={result} />,
              },
              {
                key: 'sweep',
                label: '权重扫描',
                children: <EvalSweepTab datasetName={selectedDataset} topK={topK} />,
              },
            ]}
          />
        </>
      )}

      {!result && !running && (
        <div style={{ textAlign: 'center', marginTop: 24, color: '#8b949e', fontSize: 13 }}>
          选择数据集后点击 "运行评测"
        </div>
      )}
    </Drawer>
  );
};
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Settings/EvalPanel.tsx
git commit -m "feat: refactor EvalPanel to Tab container with overview/persample/sweep tabs

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: 构建验证

**Files:**
- None (verification only)

- [ ] **Step 1: 运行前端构建**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 2: 后端导入验证**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from frontend.backend.server import app; print('OK')"
```
Expected: OK

- [ ] **Step 3: 确认所有提交**

```bash
git log --oneline -8
```

- [ ] **Step 4: Commit any remaining changes**

```bash
git status
```
