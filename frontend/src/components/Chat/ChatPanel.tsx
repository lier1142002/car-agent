import React from 'react';
import { ChatHeader } from './ChatHeader';
import { MessageList } from './MessageList';
import { ThinkingIndicator } from './ThinkingIndicator';
import { ChatInput } from './ChatInput';
import styles from '../../styles/Chat.module.css';

export const ChatPanel: React.FC = () => {
  return (
    <div className={styles.chatPanel}>
      <ChatHeader />
      <MessageList />
      <ThinkingIndicator />
      <ChatInput />
    </div>
  );
};
