import React, { useEffect, useRef } from 'react';
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
        <div className={styles.emptyState}>
          <h3>👋 欢迎使用 AutoSales Agent</h3>
          <p>选择模式开始:</p>
          <ul>
            <li>💬 <strong>车型查询</strong> — 查询任意车型参数、配置、报价</li>
            <li>📊 <strong>多车对比</strong> — 输入多个车型进行横向对比分析</li>
            <li>🎯 <strong>智能推荐</strong> — 根据场景和预算获得购车推荐</li>
          </ul>
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
