import React, { useEffect, useState } from 'react';
import { Drawer, Select, Radio, InputNumber, Switch, Button, message, Collapse, Typography, Descriptions, Tag } from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';
import { getDatasets, runEval } from '../../services/api';
import type { DatasetSummary, EvalRunResponse } from '../../types';
import styles from '../../styles/Settings.module.css';

const { Text } = Typography;
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
        </>
      )}
    </Drawer>
  );
};
