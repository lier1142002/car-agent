import React from 'react';
import { Button, App } from 'antd';
import { ClearOutlined, ReloadOutlined } from '@ant-design/icons';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Chat.module.css';

export const ChatHeader: React.FC = () => {
  const { state, clearCurrentSession, refreshAgentState } = useApp();
  const { message } = App.useApp();

  const handleClear = async () => {
    await clearCurrentSession();
    message.success('会话已清空');
  };

  const handleRefresh = async () => {
    await refreshAgentState();
    message.success('状态已刷新');
  };

  const activeConv = state.conversations.find(c => c.id === state.activeId);

  return (
    <div className={styles.header}>
      <span className={styles.headerTitle}>
        💬 {activeConv?.title ?? '对话'}
      </span>
      <div style={{ display: 'flex', gap: 8 }}>
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={handleRefresh}
          type="text"
          style={{ color: 'var(--text-secondary)' }}
        />
        <Button
          size="small"
          icon={<ClearOutlined />}
          onClick={handleClear}
          type="text"
          style={{ color: 'var(--text-secondary)' }}
        />
      </div>
    </div>
  );
};
