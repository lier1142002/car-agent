import React, { useState, useEffect } from 'react';
import { Input, Button } from 'antd';
import { EyeInvisibleOutlined, EyeTwoTone } from '@ant-design/icons';
import type { ConfigSettings, UpdateConfigPayload } from '../../types';
import styles from '../../styles/Settings.module.css';

interface Props {
  config: ConfigSettings | null;
  loading: boolean;
  onSave: (data: UpdateConfigPayload) => void;
}

const KEYS: { field: keyof UpdateConfigPayload; label: string; configKey: keyof ConfigSettings }[] = [
  { field: 'llm_api_key', label: 'LLM API Key', configKey: 'llm_api_key' },
  { field: 'embedding_api_key', label: 'Embedding API Key', configKey: 'embedding_api_key' },
  { field: 'serpapi_key', label: 'SerpAPI Key', configKey: 'serpapi_key' },
  { field: 'llamaparse_api_key', label: 'LlamaParse API Key', configKey: 'llamaparse_api_key' },
];

export const ApiKeyForm: React.FC<Props> = ({ config, loading, onSave }) => {
  const [values, setValues] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (config) {
      const init: Record<string, string> = {};
      for (const k of KEYS) {
        init[k.field] = '';
      }
      setValues(init);
      setDirty(false);
    }
  }, [config?.llm_api_key, config?.embedding_api_key, config?.serpapi_key, config?.llamaparse_api_key]);

  const handleChange = (field: string, value: string) => {
    setValues(prev => ({ ...prev, [field]: value }));
    setDirty(true);
  };

  const handleSave = () => {
    const payload: UpdateConfigPayload = {};
    for (const k of KEYS) {
      const v = values[k.field];
      if (v && v.trim()) {
        (payload as Record<string, string>)[k.field] = v.trim();
      }
    }
    if (Object.keys(payload).length === 0) {
      return;
    }
    onSave(payload);
    setDirty(false);
  };

  return (
    <div className={styles.apiKeyForm}>
      {KEYS.map(k => (
        <div key={k.field} className={styles.formItem}>
          <label className={styles.label}>{k.label}</label>
          <Input.Password
            value={values[k.field]}
            onChange={e => handleChange(k.field, e.target.value)}
            placeholder={config?.[k.configKey] ? `当前: ${config[k.configKey]}` : '未配置'}
            iconRender={visible => visible ? <EyeTwoTone /> : <EyeInvisibleOutlined />}
            size="small"
          />
        </div>
      ))}
      <Button
        type="primary"
        size="small"
        onClick={handleSave}
        loading={loading}
        disabled={!dirty}
        block
      >
        保存密钥
      </Button>
    </div>
  );
};
