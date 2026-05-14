import React from 'react';
import type { Message } from '../../types';
import styles from '../../styles/Chat.module.css';

interface Props {
  message: Message;
}

export const AgentMessage: React.FC<Props> = ({ message }) => {
  return (
    <div className={styles.agentRow}>
      <div className={styles.agentAvatar}>🤖</div>
      <div>
        <div className={styles.agentBubble}>
          <div className="message-content">
            {message.content.split('\n').map((line, i) => (
              <React.Fragment key={i}>
                {line}
                {i < message.content.split('\n').length - 1 && <br />}
              </React.Fragment>
            ))}
          </div>
          {message.citations && message.citations.length > 0 && (
            <div className={styles.citations}>
              🔗 引用:
              {message.citations.map(c => (
                <span key={c.index} className={styles.citationLink} title={c.text}>
                  [{c.index}] {c.title}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
