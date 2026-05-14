import React from 'react';
import type { Message } from '../../types';
import styles from '../../styles/Chat.module.css';

interface Props {
  message: Message;
}

export const UserMessage: React.FC<Props> = ({ message }) => {
  return (
    <div className={styles.userBubble}>
      <div className={styles.userBubbleInner}>
        {message.content}
      </div>
    </div>
  );
};
