import React, { useEffect, useState } from 'react';
import { Drawer, message } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { ApiKeyForm } from './ApiKeyForm';
import { EmbeddingSelector } from './EmbeddingSelector';
import { PdfUploader } from './PdfUploader';
import { getConfig, updateConfig, uploadPdf } from '../../services/api';
import { useApp } from '../../store/AppContext';
import type { ConfigSettings, UpdateConfigPayload } from '../../types';
import styles from '../../styles/Settings.module.css';

interface Props {
  open: boolean;
  onClose: () => void;
}

export const SettingsDrawer: React.FC<Props> = ({ open, onClose }) => {
  const { refreshAgentState } = useApp();
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      getConfig()
        .then(setConfig)
        .catch(() => message.error('获取配置失败，请检查后端服务'));
    }
  }, [open]);

  const handleSaveKeys = async (data: UpdateConfigPayload) => {
    setLoading(true);
    try {
      await updateConfig(data);
      message.success('配置已更新');
      const newConfig = await getConfig();
      setConfig(newConfig);
    } catch {
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleEmbeddingChange = async (provider: 'qwen' | 'deepseek') => {
    try {
      await updateConfig({ embedding_provider: provider });
      message.success(`Embedding 已切换为 ${provider === 'qwen' ? '千问' : 'DeepSeek'}`);
      const newConfig = await getConfig();
      setConfig(newConfig);
      refreshAgentState();
    } catch {
      message.error('切换失败');
    }
  };

  const handlePdfUpload = async (file: File) => {
    try {
      const result = await uploadPdf(file);
      if (result.status === 'success') {
        message.success(`已切分为 ${result.chunks} 块，成功入库`);
        refreshAgentState();
      } else {
        message.error(result.message || '上传失败');
      }
    } catch {
      message.error('上传失败');
    }
  };

  return (
    <Drawer
      title={<><SettingOutlined /> 设置</>}
      placement="right"
      width={420}
      open={open}
      onClose={onClose}
      className={styles.drawer}
    >
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>Embedding 模型</h4>
        <EmbeddingSelector
          value={config?.embedding_provider ?? 'qwen'}
          onChange={handleEmbeddingChange}
        />
      </div>

      <div className={styles.divider} />

      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>API 密钥配置</h4>
        <ApiKeyForm
          config={config}
          loading={loading}
          onSave={handleSaveKeys}
        />
      </div>

      <div className={styles.divider} />

      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>知识库文档</h4>
        <PdfUploader onUpload={handlePdfUpload} />
      </div>
    </Drawer>
  );
};
