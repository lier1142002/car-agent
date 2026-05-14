import React from 'react';
import { KnowledgeStatus } from './KnowledgeStatus';
import { ToolStatus } from './ToolStatus';
import { ConversationList } from './ConversationList';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Sidebar.module.css';

export const Sidebar: React.FC = () => {
  const { startNewConversation } = useApp();

  return (
    <div className={styles.sidebar}>
      <div className={styles.logo}>🚗 AutoSalesAgent</div>
      <KnowledgeStatus />
      <ToolStatus />
      <hr className={styles.divider} />
      <div className={styles.sectionLabel}>对话历史</div>
      <ConversationList />
      <div className={styles.newConvBtn} onClick={startNewConversation}>
        + 新建对话
      </div>
    </div>
  );
};
