import React from 'react';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Sidebar.module.css';

const TOOL_LABELS: Record<string, string> = {
  rag_tool: '📖 RAG',
  web_search: '🌐 搜索',
  calculator_tool: '🔢 计算器',
};

export const ToolStatus: React.FC = () => {
  const { state } = useApp();
  const tools = state.agentState?.tools ?? [];

  return (
    <div className={styles.statusCard}>
      <div className={styles.statusCardTitle}>🛠 可用工具</div>
      <div className={styles.toolsList}>
        {tools.length === 0 && <span className={styles.statusOff}>未加载</span>}
        {tools.map(tool => (
          <span key={tool} className={styles.toolTag}>
            {TOOL_LABELS[tool] ?? tool}
          </span>
        ))}
      </div>
    </div>
  );
};
