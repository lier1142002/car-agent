import React from 'react';
import { Card, Typography, Tag } from 'antd';
import { HomeOutlined, CheckCircleFilled } from '@ant-design/icons';
import styles from '../../styles/Settings.module.css';

const { Text } = Typography;

export const EmbeddingSelector: React.FC = () => {
  return (
    <div className={styles.embeddingCards}>
      <Card
        size="small"
        className={`${styles.providerCard} ${styles.providerCardActive}`}
      >
        <div className={styles.providerCardInner}>
          <span className={styles.providerIcon}><HomeOutlined /></span>
          <div>
            <Text strong style={{ fontSize: 13 }}>本地 BGE-M3</Text>
            <Tag color="green" style={{ marginLeft: 8, fontSize: 10 }}>当前</Tag>
            <br />
            <Text type="secondary" style={{ fontSize: 11 }}>BAAI/bge-m3，1024 维，CPU/GPU</Text>
          </div>
        </div>
      </Card>
    </div>
  );
};
