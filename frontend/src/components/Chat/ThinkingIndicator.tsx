import React from 'react';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Chat.module.css';

export const ThinkingIndicator: React.FC = () => {
  const { state } = useApp();

  if (!state.isThinking) return null;

  return (
    <div className={styles.thinking}>
      <div className={styles.thinkingDots}>
        <div className={styles.thinkingDot} />
        <div className={styles.thinkingDot} />
        <div className={styles.thinkingDot} />
      </div>
      <span className={styles.thinkingText}>
        {state.thinkingStatus || '思考中...'}
      </span>
    </div>
  );
};
