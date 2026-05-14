import React from 'react';
import type { Source } from '../../types';
import { formatScore, truncate } from '../../utils/format';
import styles from '../../styles/Trace.module.css';

interface Props {
  source: Source;
  index: number;
}

export const SourceCard: React.FC<Props> = ({ source, index }) => {
  return (
    <div className={styles.sourceCard} data-tool={source.tool}>
      <div className={styles.sourceTitle}>
        [{index}] {source.title ?? source.tool}
      </div>
      <div className={styles.sourceText}>
        {truncate(source.text, 180)}
      </div>
      <div className={styles.sourceMeta}>
        <span>{source.tool}</span>
        {source.score !== undefined && (
          <span className={styles.sourceScore}>
            score: {formatScore(source.score)}
          </span>
        )}
      </div>
    </div>
  );
};
