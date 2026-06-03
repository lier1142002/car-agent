import React from 'react';
import { SettingOutlined, ExperimentOutlined } from '@ant-design/icons';
import { KnowledgeStatus } from './KnowledgeStatus';
import { ToolStatus } from './ToolStatus';
import { ConversationList } from './ConversationList';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Sidebar.module.css';

interface SidebarProps {
  onSettingsClick: () => void;
  onEvalClick: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ onSettingsClick, onEvalClick }) => {
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
      <div className={styles.settingsBtn} onClick={onEvalClick}>
        <ExperimentOutlined /> RAG 评测
      </div>
      <div className={styles.settingsBtn} onClick={onSettingsClick}>
        <SettingOutlined /> 设置
      </div>
    </div>
  );
};
