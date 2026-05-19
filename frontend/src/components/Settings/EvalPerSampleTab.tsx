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

  // 构建散点图数据（按难度分组，从 result.per_sample 推测难度）
  const scatterData = result.per_sample
    .filter(s => s.context_relevance > 0 || s.faithfulness > 0)
    .map(s => ({
      x: s.context_relevance,
      y: s.faithfulness,
      query: s.query.length > 60 ? s.query.slice(0, 60) + '...' : s.query,
      difficulty: 'medium',  // 默认 medium，EvalSampleResult 无 difficulty 字段
    }));

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
