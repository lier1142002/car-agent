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
