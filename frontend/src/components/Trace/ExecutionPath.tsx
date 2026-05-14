import React from 'react';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Trace.module.css';

const STATUS_ICONS: Record<string, string> = {
  done: '✓',
  running: '◉',
  pending: '○',
  error: '✗',
};

export const ExecutionPath: React.FC = () => {
  const { state } = useApp();

  // If no trace data yet but messages exist, show placeholder
  if (state.trace.length === 0 && state.messages.length === 0) return null;

  return (
    <div className={styles.execPath}>
      <div className={styles.execTitle}>🔍 检索路径</div>
      <div className={styles.execSteps}>
        {state.trace.length === 0 && state.isThinking && (
          <>
            <div className={styles.execStep}>
              <div className={`${styles.execStepIcon} ${styles.execStepRunning}`}>
                {STATUS_ICONS.running}
              </div>
              <div className={styles.execStepText}>
                <strong>Planning</strong>: {state.thinkingStatus}
              </div>
            </div>
          </>
        )}
        {state.trace.map((step, i) => (
          <div key={i} className={styles.execStep}>
            <div className={`${styles.execStepIcon} ${styles[`execStep${step.status.charAt(0).toUpperCase() + step.status.slice(1)}` as keyof typeof styles] || styles.execStepDone}`}>
              {STATUS_ICONS[step.status] ?? '○'}
            </div>
            <div className={styles.execStepText}>
              <strong>{step.step}</strong>
              <div>{step.detail}</div>
            </div>
          </div>
        ))}
        {state.trace.length === 0 && !state.isThinking && state.messages.length > 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>追踪数据未捕获</div>
        )}
      </div>
    </div>
  );
};
