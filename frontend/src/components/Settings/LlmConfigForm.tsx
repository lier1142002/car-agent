import React, { useState, useEffect, useMemo } from 'react';
import { Select, Input, Slider, InputNumber, Button, message } from 'antd';
import type { ConfigSettings, UpdateConfigPayload } from '../../types';
import { updateConfig } from '../../services/api';
import styles from '../../styles/Settings.module.css';

interface Props {
  config: ConfigSettings | null;
  onSaved: () => void;
}

const PRESET_MODELS = [
  { value: 'deepseek-chat', label: 'deepseek-chat (推荐)' },
  { value: 'deepseek-reasoner', label: 'deepseek-reasoner' },
  { value: 'gpt-4o', label: 'gpt-4o' },
  { value: 'gpt-4o-mini', label: 'gpt-4o-mini' },
  { value: 'qwen-plus', label: 'qwen-plus' },
  { value: 'qwen-max', label: 'qwen-max' },
];

export const LlmConfigForm: React.FC<Props> = ({ config, onSaved }) => {
  const [model, setModel] = useState('');
  const [apiUrl, setApiUrl] = useState('');
  const [temperature, setTemperature] = useState(0.1);
  const [maxTokens, setMaxTokens] = useState(2048);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (config) {
      setModel(config.llm_model || '');
      setApiUrl(config.llm_api_url || '');
      setTemperature(config.llm_temperature ?? 0.1);
      setMaxTokens(config.llm_max_tokens ?? 2048);
      setDirty(false);
    }
  }, [config?.llm_model, config?.llm_api_url, config?.llm_temperature, config?.llm_max_tokens]);

  // 动态生成 Select options：预设 + 当前自定义值（如果不在预设中）
  const modelOptions = useMemo(() => {
    if (model && !PRESET_MODELS.find(o => o.value === model)) {
      return [...PRESET_MODELS, { value: model, label: model }];
    }
    return PRESET_MODELS;
  }, [model]);

  const handleSave = async () => {
    if (!model.trim()) {
      message.error('模型名不能为空');
      return;
    }
    setSaving(true);
    try {
      const payload: UpdateConfigPayload = {
        llm_model: model.trim(),
        llm_api_url: apiUrl.trim(),
        llm_temperature: temperature,
        llm_max_tokens: maxTokens,
      };
      await updateConfig(payload);
      message.success('LLM 配置已更新');
      setDirty(false);
      onSaved();
    } catch {
      message.error('保存 LLM 配置失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.apiKeyForm}>
      <div className={styles.formItem}>
        <label className={styles.label}>模型</label>
        <Select
          value={model || undefined}
          onChange={(val) => { setModel(val); setDirty(true); }}
          onSearch={(val) => { setModel(val); setDirty(true); }}
          placeholder="选择或输入模型名"
          showSearch
          filterOption={(input, option) =>
            (option?.label as string ?? '').toLowerCase().includes(input.toLowerCase())
          }
          options={modelOptions}
          size="small"
        />
      </div>

      <div className={styles.formItem}>
        <label className={styles.label}>API URL</label>
        <Input
          value={apiUrl}
          onChange={(e) => { setApiUrl(e.target.value); setDirty(true); }}
          placeholder="https://api.deepseek.com/v1"
          size="small"
        />
      </div>

      <div className={styles.formItem}>
        <label className={styles.label}>Temperature ({temperature})</label>
        <Slider
          min={0}
          max={2}
          step={0.1}
          value={temperature}
          onChange={(val) => { setTemperature(val); setDirty(true); }}
        />
      </div>

      <div className={styles.formItem}>
        <label className={styles.label}>Max Tokens</label>
        <InputNumber
          min={1}
          max={8192}
          value={maxTokens}
          onChange={(val) => { if (val !== null) { setMaxTokens(val); setDirty(true); } }}
          size="small"
          style={{ width: '100%' }}
        />
      </div>

      <Button
        type="primary"
        size="small"
        onClick={handleSave}
        loading={saving}
        disabled={!dirty}
        block
      >
        保存 LLM 配置
      </Button>
    </div>
  );
};
