import React from 'react';
import { Button, Space, Tag, Tooltip } from 'antd';
import { ClearOutlined, PlusOutlined, ApiOutlined } from '@ant-design/icons';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Chat.module.css';

const MODE_LABELS: Record<string, string> = {
  chat: '💬 车型查询',
  compare: '📊 多车对比',
  recommend: '🎯 智能推荐',
};

export const ChatHeader: React.FC = () => {
  const { state, startNewConversation, clearCurrentSession, activeSessionId } = useApp();

  return (
    <div className={styles.chatHeader}>
      <Space>
        <ApiOutlined />
        <span style={{ fontWeight: 600 }}>AutoSales Agent</span>
        <Tag color="blue">{MODE_LABELS[state.inputMode] || state.inputMode}</Tag>
        {activeSessionId && (
          <Tooltip title={`Session: ${activeSessionId}`}>
            <Tag color="green" style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {activeSessionId.slice(0, 12)}...
            </Tag>
          </Tooltip>
        )}
      </Space>
      <Space>
        <Button icon={<PlusOutlined />} size="small" onClick={startNewConversation}>
          新对话
        </Button>
        <Button icon={<ClearOutlined />} size="small" onClick={clearCurrentSession}>
          清空会话
        </Button>
      </Space>
    </div>
  );
};
