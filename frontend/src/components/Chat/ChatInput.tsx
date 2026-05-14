import React, { useState } from 'react';
import { Input, Button } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Chat.module.css';

export const ChatInput: React.FC = () => {
  const [text, setText] = useState('');
  const { sendMessage, state } = useApp();
  const disabled = state.isThinking || !text.trim();

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || state.isThinking) return;
    setText('');
    sendMessage(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={styles.inputArea}>
      <Input
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="输入汽车相关问题，Enter 发送..."
        disabled={state.isThinking}
        style={{ flex: 1 }}
      />
      <Button
        type="primary"
        icon={<SendOutlined />}
        onClick={handleSend}
        disabled={disabled}
        className={styles.sendBtn}
      >
        发送
      </Button>
    </div>
  );
};
