# RAG 评测前端化（一期） Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增评测 API 端点 + 独立 EvalPanel 抽屉面板，支持选择数据集、配置参数、运行评测、查看指标结果。

**Architecture:** 后端在 server.py 新增 `GET /api/eval/datasets` 和 `POST /api/eval/run` 两个端点，复用现有 `EvalRunner` 和 `GoldenDataset`。前端新建 `EvalPanel` 组件作为独立抽屉，通过 Sidebar 新增入口按钮打开，与 SettingsDrawer 平级。

**Tech Stack:** Python FastAPI + Pydantic (后端), React 18 + TypeScript + Ant Design 5 (前端)

**Spec:** `docs/superpowers/specs/2026-05-19-eval-frontend-phase1-design.md`

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `frontend/backend/server.py` | 修改 | 新增 2 个端点 + Pydantic 模型 |
| `frontend/src/types/index.ts` | 修改 | 新增 Eval 类型定义 |
| `frontend/src/services/api.ts` | 修改 | 新增 2 个 API 函数 |
| `frontend/src/components/Settings/EvalPanel.tsx` | 新建 | 评测面板组件 |
| `frontend/src/components/Sidebar/Sidebar.tsx` | 修改 | 新增 eval 入口按钮 |
| `frontend/src/components/Layout/AppLayout.tsx` | 修改 | 新增 EvalPanel Drawer + state |

---

### Task 1: 新增 server.py eval 端点

**Files:**
- Modify: `frontend/backend/server.py`

- [ ] **Step 1: 添加 Pydantic 模型和导入**

在 server.py 顶部的导入区域（`from config import config` 之后），新增 eval 相关导入：

```python
from eval.dataset import GoldenDataset
from eval.runner import EvalRunner
```

在 `PdfUploadResponse` 类之后（约 line 133），新增两个 Pydantic 模型：

```python
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
```

- [ ] **Step 2: 新增 GET /api/eval/datasets 端点**

在 `get_state` 端点之后（约 line 380），新增：

```python
@app.get("/api/eval/datasets", response_model=List[DatasetItem])
async def get_eval_datasets() -> List[DatasetItem]:
    """列出 eval/datasets/ 目录下所有可用评测数据集。

    返回每个数据集的名称、样本数、类型分布和难度分布。

    Returns:
        List[DatasetItem]: 数据集摘要列表。
    """
    import json as _json
    from pathlib import Path as _Path

    datasets_dir = _Path(__file__).resolve().parent.parent.parent / "eval" / "datasets"
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
```

- [ ] **Step 3: 新增 POST /api/eval/run 端点**

续在 `/api/eval/datasets` 之后：

```python
@app.post("/api/eval/run")
async def run_eval(request: EvalRunRequest):
    """运行 RAG 评测。

    对指定数据集执行检索→生成→评估全流程，返回聚合指标和逐样本明细。

    Args:
        request: 评测配置（数据集名、检索模式、top_k、是否生成回答）。

    Returns:
        dict: EvalReport.to_dict() 的序列化结果。
    """
    from pathlib import Path as _Path

    agent = get_agent()

    # 检查知识库是否已索引
    state = agent.get_state()
    if not state.get("rag_indexed", False):
        raise HTTPException(
            status_code=400,
            detail="请先索引知识库（上传 PDF 或调用 /api/index）",
        )

    # 加载数据集
    datasets_dir = _Path(__file__).resolve().parent.parent.parent / "eval" / "datasets"
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
```

- [ ] **Step 4: 确保 HTTPException 已导入**

检查 server.py 顶部是否有 `from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect`。若无 `HTTPException`，需添加。

实际检查方式：grep 文件中是否已有 `HTTPException`。如果没有，在 FastAPI 导入行追加 `HTTPException`。

- [ ] **Step 5: 验证后端可启动**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from frontend.backend.server import app; print('OK')"
```
Expected: `OK` (无导入错误)

- [ ] **Step 6: Commit**

```bash
git add frontend/backend/server.py
git commit -m "feat: add eval API endpoints (datasets list + run)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: 新增前端 Eval TypeScript 类型

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: 在文件末尾追加 Eval 类型定义**

```ts
/** 数据集摘要 */
export interface DatasetSummary {
  name: string;
  total_samples: number;
  by_type: Record<string, number>;
  by_difficulty: Record<string, number>;
}

/** 评测运行请求 */
export interface EvalRunRequest {
  dataset_name: string;
  retrieval_mode: 'dense' | 'sparse' | 'hybrid';
  top_k: number;
  generate_answers: boolean;
}

/** 单条样本评测结果 */
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

/** 评测运行响应 */
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
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add eval TypeScript types (DatasetSummary, EvalRunRequest, EvalRunResponse, EvalSampleResult)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: 新增 API 服务函数

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: 在 api.ts 末尾新增 2 个函数**

先在文件顶部导入中新增类型引用。当前 import 行：

```ts
import type { ChatRequest, ChatResponse, AgentState, ConfigSettings, UpdateConfigPayload, PdfUploadResponse } from '../types';
```

改为：

```ts
import type { ChatRequest, ChatResponse, AgentState, ConfigSettings, UpdateConfigPayload, PdfUploadResponse, DatasetSummary, EvalRunRequest, EvalRunResponse } from '../types';
```

在文件末尾新增：

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

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add getDatasets and runEval API functions

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 创建 EvalPanel 组件

**Files:**
- Create: `frontend/src/components/Settings/EvalPanel.tsx`

- [ ] **Step 1: 创建 EvalPanel.tsx**

```tsx
import React, { useEffect, useState } from 'react';
import { Drawer, Select, Radio, InputNumber, Switch, Button, message, Collapse, Typography, Descriptions, Tag, Spin } from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';
import { getDatasets, runEval } from '../../services/api';
import type { DatasetSummary, EvalRunResponse } from '../../types';
import styles from '../../styles/Settings.module.css';

const { Text, Title } = Typography;
const { Panel } = Collapse;

interface Props {
  open: boolean;
  onClose: () => void;
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

export const EvalPanel: React.FC<Props> = ({ open, onClose }) => {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string | null>(null);
  const [retrievalMode, setRetrievalMode] = useState<'dense' | 'sparse' | 'hybrid'>('hybrid');
  const [topK, setTopK] = useState(5);
  const [generateAnswers, setGenerateAnswers] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<EvalRunResponse | null>(null);

  useEffect(() => {
    if (open) {
      getDatasets()
        .then(setDatasets)
        .catch(() => message.error('获取数据集列表失败'));
      setResult(null);
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
      message.success('评测完成');
    } catch {
      message.error('评测运行失败');
    } finally {
      setRunning(false);
    }
  };

  const renderMetricBar = (value: number) => {
    const pct = Math.max(0, Math.min(1, value));
    const width = Math.round(pct * 100);
    const color = pct >= 0.8 ? '#3fb950' : pct >= 0.6 ? '#d29922' : '#f85149';
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, width: '100%' }}>
        <span style={{ flex: 1, height: 6, background: '#21262d', borderRadius: 3, overflow: 'hidden' }}>
          <span style={{ display: 'block', width: `${width}%`, height: '100%', background: color, borderRadius: 3 }} />
        </span>
        <span style={{ color, fontWeight: 600, minWidth: 48, textAlign: 'right' }}>{(value * 100).toFixed(1)}%</span>
      </span>
    );
  };

  return (
    <Drawer
      title={<><ExperimentOutlined /> RAG 评测</>}
      placement="right"
      width={480}
      open={open}
      onClose={onClose}
      className={styles.drawer}
    >
      {/* 数据集选择 */}
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>评测数据集</h4>
        <Select
          value={selectedDataset}
          onChange={setSelectedDataset}
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

      {/* 结果展示 */}
      {result && (
        <>
          <div className={styles.divider} />

          <div className={styles.section}>
            <h4 className={styles.sectionTitle}>检索质量</h4>
            {Object.entries(result.retrieval_quality).map(([key, val]) => (
              <div key={key} className={styles.formItem} style={{ marginBottom: 8 }}>
                <label className={styles.label}>{METRIC_LABELS[key] || key}</label>
                {renderMetricBar(val)}
              </div>
            ))}
          </div>

          {generateAnswers && result.generation_quality && (
            <>
              <div className={styles.divider} />
              <div className={styles.section}>
                <h4 className={styles.sectionTitle}>生成质量</h4>
                {Object.entries(result.generation_quality).map(([key, val]) => (
                  <div key={key} className={styles.formItem} style={{ marginBottom: 8 }}>
                    <label className={styles.label}>{METRIC_LABELS[key] || key}</label>
                    {renderMetricBar(val)}
                  </div>
                ))}
              </div>
            </>
          )}

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
              {result.performance.avg_generation_latency_ms > 0 && (
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

          {result.failed_samples.length > 0 && (
            <>
              <div className={styles.divider} />
              <div className={styles.section}>
                <h4 className={styles.sectionTitle}>失败样本 ({result.failed_samples.length})</h4>
                {result.failed_samples.map((q, i) => (
                  <Text key={i} type="danger" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                    {q}
                  </Text>
                ))}
              </div>
            </>
          )}

          <div className={styles.divider} />
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
                    <Descriptions.Item label="Latency">{s.retrieval_latency_ms.toFixed(0)}ms</Descriptions.Item>
                    <Descriptions.Item label="Hallucination">{(s.hallucination_rate * 100).toFixed(1)}%</Descriptions.Item>
                  </Descriptions>
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
        </>
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
git commit -m "feat: add EvalPanel component with dataset selector, param config, and results display

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Sidebar 入口 + AppLayout 集成

**Files:**
- Modify: `frontend/src/components/Sidebar/Sidebar.tsx`
- Modify: `frontend/src/components/Layout/AppLayout.tsx`

- [ ] **Step 1: 修改 Sidebar.tsx**

Sidebar 需要新增 `onOpenEval` prop 和入口按钮。

当前 Sidebar.tsx 内容（完整已知，不再重复）。改动：

```tsx
import React from 'react';
import { SettingOutlined, ExperimentOutlined } from '@ant-design/icons';  // 新增 ExperimentOutlined
import { KnowledgeStatus } from './KnowledgeStatus';
import { ToolStatus } from './ToolStatus';
import { ConversationList } from './ConversationList';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Sidebar.module.css';

interface SidebarProps {
  onOpenSettings: () => void;
  onOpenEval: () => void;  // 新增
}

export const Sidebar: React.FC<SidebarProps> = ({ onOpenSettings, onOpenEval }) => {
  const { startNewConversation } = useApp();

  return (
    <div className={styles.sidebar}>
      <div className={styles.logo}>🚗 AutoSalesAgent</div>
      <KnowledgeStatus />
      <ToolStatus />
      <hr className={styles.divider} />
      <div className={styles.sectionLabel}>对话历史</div>
      <ConversationList />
      <div className={styles.newConvBtn} onClick={startNewConversation}>
        + 新建对话
      </div>
      <div className={styles.settingsBtn} onClick={onOpenEval}>
        <ExperimentOutlined /> RAG 评测
      </div>
      <div className={styles.settingsBtn} onClick={onOpenSettings}>
        <SettingOutlined /> 设置
      </div>
    </div>
  );
};
```

- [ ] **Step 2: 修改 AppLayout.tsx**

```tsx
import React, { useState } from 'react';
import { Layout } from 'antd';
import { Sidebar } from '../Sidebar/Sidebar';
import { ChatPanel } from '../Chat/ChatPanel';
import { TracePanel } from '../Trace/TracePanel';
import { SettingsDrawer } from '../Settings/SettingsDrawer';
import { EvalPanel } from '../Settings/EvalPanel';  // 新增

const { Sider, Content } = Layout;

export const AppLayout: React.FC = () => {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [evalOpen, setEvalOpen] = useState(false);  // 新增

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider width={220} style={{ background: '#0d1117', borderRight: '1px solid #30363d' }}>
        <Sidebar
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenEval={() => setEvalOpen(true)}
        />
      </Sider>
      <Content style={{ display: 'flex', flexDirection: 'column' }}>
        <ChatPanel />
      </Content>
      <Sider width={300} style={{ background: '#0d1117', borderLeft: '1px solid #30363d' }}>
        <TracePanel />
      </Sider>
      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <EvalPanel open={evalOpen} onClose={() => setEvalOpen(false)} />
    </Layout>
  );
};
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Sidebar/Sidebar.tsx frontend/src/components/Layout/AppLayout.tsx
git commit -m "feat: add EvalPanel entry in Sidebar and wire up in AppLayout

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: 构建验证 + 端到端测试

**Files:**
- None (verification only)

- [ ] **Step 1: 运行前端构建**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 2: 后端启动验证**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from frontend.backend.server import app; print('OK')"
```
Expected: OK

- [ ] **Step 3: API 端点 smoke test** (启动后端后手动或自动)

```bash
# 启动后端
cd c:/Users/18049/Desktop/agent_car && python frontend/backend/server.py &
sleep 3

# 测试 datasets 端点
curl -s http://localhost:8000/api/eval/datasets | python -m json.tool
# Expected: JSON 数组，包含 eval/datasets/ 下的数据集列表

# 杀掉后端
kill %1
```

- [ ] **Step 4: 验证 git log**

```bash
git log --oneline -6
```
Expected: 6 commits (spec + plan + 4 implementation tasks).

- [ ] **Step 5: Commit any remaining changes**

```bash
git status
# 如有未提交的变更，提交之
```
