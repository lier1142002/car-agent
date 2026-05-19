import React from 'react';
import { Card, Typography } from 'antd';
import { CloudOutlined, ThunderboltOutlined, HomeOutlined } from '@ant-design/icons';
import styles from '../../styles/Settings.module.css';

const { Text } = Typography;

interface Props {
  value: 'local' | 'qwen' | 'deepseek';
  onChange: (provider: 'local' | 'qwen' | 'deepseek') => void;
}

const PROVIDERS = [
  {
    key: 'local' as const,
    name: '本地 BGE-M3',
    desc: 'BAAI/bge-m3，1024 维，CPU/GPU',
    icon: <HomeOutlined />,
  },
  {
    key: 'deepseek' as const,
    name: 'DeepSeek Embedding',
    desc: 'DeepSeek Embedding API，1536 维',
    icon: <ThunderboltOutlined />,
  },
  {
    key: 'qwen' as const,
    name: '千问 Embedding',
    desc: '阿里云 text-embedding-v3，1024 维',
    icon: <CloudOutlined />,
  },
];

export const EmbeddingSelector: React.FC<Props> = ({ value, onChange }) => {
  return (
    <div className={styles.embeddingCards}>
      {PROVIDERS.map(p => (
        <Card
          key={p.key}
          size="small"
          hoverable
          className={`${styles.providerCard} ${value === p.key ? styles.providerCardActive : ''}`}
          onClick={() => onChange(p.key)}
        >
          <div className={styles.providerCardInner}>
            <span className={styles.providerIcon}>{p.icon}</span>
            <div>
              <Text strong style={{ fontSize: 13 }}>{p.name}</Text>
              <br />
              <Text type="secondary" style={{ fontSize: 11 }}>{p.desc}</Text>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
};
