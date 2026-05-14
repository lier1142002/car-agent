import React from 'react';
import { useApp } from '../../store/AppContext';
import { SourceCard } from './SourceCard';
import { ExecutionPath } from './ExecutionPath';
import styles from '../../styles/Trace.module.css';

export const TracePanel: React.FC = () => {
  const { state } = useApp();
  const hasSources = state.sources.length > 0;

  if (!hasSources && state.messages.length === 0) {
    return (
      <div className={styles.tracePanel}>
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>📖</div>
          <div>知识追溯</div>
          <div style={{ marginTop: 4 }}>发送问题后，此处将展示<br/>回答的引用来源和检索路径</div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.tracePanel}>
      <div className={styles.panelTitle}>📖 知识追溯</div>
      <div className={styles.panelSubtitle}>本次回答引用的信息来源</div>

      {hasSources ? (
        state.sources.map((source, i) => (
          <SourceCard key={i} source={source} index={i + 1} />
        ))
      ) : (
        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>暂无引用来源</div>
      )}

      <ExecutionPath />
    </div>
  );
};
