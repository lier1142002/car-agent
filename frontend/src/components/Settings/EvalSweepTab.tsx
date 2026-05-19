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
                  formatter={(val: any) => (Number(val) * 100).toFixed(1) + '%'}
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
                      最佳 Recall: dense={String(bestRecall.config.dense_weight)}, sparse={String(bestRecall.config.sparse_weight)}
                      {' '}({(bestRecall.retrieval_quality.context_recall * 100).toFixed(1)}%)
                    </div>
                    <div style={{ fontSize: 12, color: '#8b949e' }}>
                      最佳 Faithfulness: dense={String(bestFaith.config.dense_weight)}, sparse={String(bestFaith.config.sparse_weight)}
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
