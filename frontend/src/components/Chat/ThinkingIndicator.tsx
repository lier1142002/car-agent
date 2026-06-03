import React from 'react';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Chat.module.css';

const PHASE_LABELS: Record<string, string> = {
  'rag_tool': '检索知识库',
  'web_search': '联网搜索',
  'calculator_tool': '计算分析',
};

export const ThinkingIndicator: React.FC = () => {
  const { state } = useApp();

  if (!state.isThinking) return null;

  const status = state.thinkingStatus || '思考中...';
  const runningSteps = state.trace.filter(t => t.status === 'running');

  return (
    <div className={styles.thinking}>
      <div className={styles.thinkingDots}>
        <div className={styles.thinkingDot} />
        <div className={styles.thinkingDot} />
        <div className={styles.thinkingDot} />
      </div>
      <div>
        <div className={styles.thinkingText}>{status}</div>
        {runningSteps.length > 0 && (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            {runningSteps.map(s => (
              <span key={s.step} style={{ marginRight: 8 }}>
                {s.step.replace('▶ ', '')}: {s.detail.slice(0, 40)}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
