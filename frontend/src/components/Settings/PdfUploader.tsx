import React, { useState } from 'react';
import { Upload, Progress, Alert } from 'antd';
import { InboxOutlined, FilePdfOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import styles from '../../styles/Settings.module.css';

const { Dragger } = Upload;

interface Props {
  onUpload: (file: File) => Promise<void>;
}

export const PdfUploader: React.FC<Props> = ({ onUpload }) => {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const handleUpload: UploadProps['customRequest'] = async ({ file, onSuccess, onError }) => {
    const pdfFile = file as File;
    setUploading(true);
    setProgress(0);
    setResult(null);

    // Simulate progress while uploading
    const timer = setInterval(() => {
      setProgress(prev => Math.min(prev + 20, 80));
    }, 300);

    try {
      await onUpload(pdfFile);
      clearInterval(timer);
      setProgress(100);
      setResult({ type: 'success', message: 'PDF 已成功解析入库' });
      onSuccess?.('ok');
    } catch {
      clearInterval(timer);
      setProgress(0);
      setResult({ type: 'error', message: '上传或解析失败' });
      onError?.(new Error('upload failed'));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className={styles.pdfUploader}>
      <Dragger
        accept=".pdf"
        showUploadList={false}
        customRequest={handleUpload}
        disabled={uploading}
        className={styles.dragger}
      >
        <p className={styles.draggerIcon}>
          <InboxOutlined />
        </p>
        <p className={styles.draggerText}>点击或拖拽 PDF 文件到此区域</p>
        <p className={styles.draggerHint}>仅支持 .pdf 格式</p>
      </Dragger>

      {uploading && (
        <div className={styles.progressWrap}>
          <Progress percent={progress} status="active" size="small" />
          <span className={styles.progressText}>正在解析入库...</span>
        </div>
      )}

      {result && (
        <Alert
          type={result.type}
          message={result.message}
          showIcon
          icon={result.type === 'success' ? <FilePdfOutlined /> : undefined}
          style={{ marginTop: 12 }}
        />
      )}
    </div>
  );
};
