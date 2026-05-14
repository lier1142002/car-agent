import React, { useRef, useEffect } from 'react';
import { useApp } from '../../store/AppContext';
import { UserMessage } from './UserMessage';
import { AgentMessage } from './AgentMessage';
import styles from '../../styles/Chat.module.css';

export const MessageList: React.FC = () => {
  const { state } = useApp();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.messages]);

  return (
    <div className={styles.messageList}>
      {state.messages.length === 0 && (
        <div style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
          fontSize: 15,
        }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🚗</div>
            <div>欢迎使用 AutoSalesAgent</div>
            <div style={{ fontSize: 12, marginTop: 8, color: 'var(--text-muted)' }}>
              我可以帮您查询汽车参数、对比车型、计算购车费用
            </div>
          </div>
        </div>
      )}
      {state.messages.map(msg => (
        msg.role === 'user'
          ? <UserMessage key={msg.id} message={msg} />
          : <AgentMessage key={msg.id} message={msg} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
};
