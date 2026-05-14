import React from 'react';
import { useApp } from '../../store/AppContext';
import { truncate } from '../../utils/format';
import styles from '../../styles/Sidebar.module.css';

export const ConversationList: React.FC = () => {
  const { state, switchConversation } = useApp();

  return (
    <div className={styles.convList}>
      {state.conversations.map(conv => (
        <div
          key={conv.id}
          className={`${styles.convItem} ${conv.id === state.activeId ? styles.convItemActive : ''}`}
          onClick={() => switchConversation(conv.id)}
          title={conv.title}
        >
          💬 {truncate(conv.title, 20)}
        </div>
      ))}
    </div>
  );
};
