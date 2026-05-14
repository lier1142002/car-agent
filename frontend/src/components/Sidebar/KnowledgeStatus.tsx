import React from 'react';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Sidebar.module.css';

export const KnowledgeStatus: React.FC = () => {
  const { state } = useApp();
  const isIndexed = state.agentState?.rag_indexed ?? false;

  return (
    <div className={styles.statusCard}>
      <div className={styles.statusCardTitle}>📚 知识库</div>
      <div className={isIndexed ? styles.statusOk : styles.statusOff}>
        {isIndexed ? '✅ 已索引' : '⏳ 未索引'}
      </div>
    </div>
  );
};
