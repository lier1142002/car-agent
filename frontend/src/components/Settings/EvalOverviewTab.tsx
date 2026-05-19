import React from 'react';
import { Typography, Descriptions, Empty } from 'antd';
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import type { EvalRunResponse } from '../../types';
import styles from '../../styles/Settings.module.css';

const { Text } = Typography;

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
            <Radar dataKey="value" stroke="#58a6ff" fill="#58a6ff" fillOpacity={0.2} />
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
              formatter={(val: any) => ((val * 100).toFixed(1) + '%')}
            />
            <Bar dataKey="value" fill="#3fb950" radius={[4, 4, 0, 0]} />
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
                  formatter={(val: any) => ((val * 100).toFixed(1) + '%')}
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
              <Text key={i} type="danger" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                {q}
              </Text>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
