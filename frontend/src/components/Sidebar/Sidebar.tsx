import React from 'react';
import { SettingOutlined, ExperimentOutlined } from '@ant-design/icons';
import { KnowledgeStatus } from './KnowledgeStatus';
import { ToolStatus } from './ToolStatus';
import { ConversationList } from './ConversationList';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Sidebar.module.css';

interface SidebarProps {
  onOpenSettings: () => void;
  onOpenEval: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ onOpenSettings, onOpenEval }) => {
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
      <div className={styles.settingsBtn} onClick={onOpenEval}>
        <ExperimentOutlined /> RAG 评测
      </div>
      <div className={styles.settingsBtn} onClick={onOpenSettings}>
        <SettingOutlined /> 设置
      </div>
    </div>
  );
};
