import React, { useState } from 'react';
import { Input, Button, Select, Space, Tag } from 'antd';
import { SendOutlined, SwapOutlined } from '@ant-design/icons';
import { useApp } from '../../store/AppContext';
import type { InputMode } from '../../types';
import styles from '../../styles/Chat.module.css';

const MODE_OPTIONS: { value: InputMode; label: string }[] = [
  { value: 'chat', label: '💬 车型查询' },
  { value: 'compare', label: '📊 多车对比' },
  { value: 'recommend', label: '🎯 智能推荐' },
];

export const ChatInput: React.FC = () => {
  const { state, sendQuery, sendCompare, sendRecommend, setInputMode } = useApp();
  const [text, setText] = useState('');
  const [compareVehicles, setCompareVehicles] = useState('');
  const [compareAspects, setCompareAspects] = useState('');
  const [recScenario, setRecScenario] = useState('');
  const [recBudget, setRecBudget] = useState('');
  const [recPrefs, setRecPrefs] = useState('');

  const disabled = state.isThinking;

  const handleSend = () => {
    if (disabled) return;

    switch (state.inputMode) {
      case 'chat': {
        const trimmed = text.trim();
        if (!trimmed) return;
        setText('');
        sendQuery(trimmed);
        break;
      }
      case 'compare': {
        const vehicles = compareVehicles.split(/[,，\s]+/).filter(Boolean);
        if (vehicles.length < 2) return;
        const aspects = compareAspects.trim()
          ? compareAspects.split(/[,，\s]+/).filter(Boolean)
          : undefined;
        setCompareVehicles('');
        setCompareAspects('');
        sendCompare(vehicles, aspects);
        break;
      }
      case 'recommend': {
        const prefs = recPrefs.trim()
          ? recPrefs.split(/[,，\s]+/).filter(Boolean)
          : undefined;
        sendRecommend(
          recScenario.trim() || undefined,
          recBudget.trim() || undefined,
          prefs,
        );
        setRecScenario('');
        setRecBudget('');
        setRecPrefs('');
        break;
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={styles.inputArea}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1 }}>
        {/* Mode Selector */}
        <Space>
          <span style={{ fontSize: 12, color: '#888' }}>模式:</span>
          {MODE_OPTIONS.map(opt => (
            <Tag
              key={opt.value}
              color={state.inputMode === opt.value ? 'blue' : 'default'}
              style={{ cursor: 'pointer' }}
              onClick={() => setInputMode(opt.value)}
            >
              {opt.label}
            </Tag>
          ))}
        </Space>

        {/* Chat Mode */}
        {state.inputMode === 'chat' && (
          <div style={{ display: 'flex', gap: 8 }}>
            <Input
              value={text}
              onChange={e => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入汽车相关问题，Enter 发送..."
              disabled={disabled}
              style={{ flex: 1 }}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              disabled={disabled || !text.trim()}
            >
              发送
            </Button>
          </div>
        )}

        {/* Compare Mode */}
        {state.inputMode === 'compare' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Input
              value={compareVehicles}
              onChange={e => setCompareVehicles(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入车型名称 (逗号分隔), 如: 问界M5, 理想L7, 特斯拉Model Y"
              disabled={disabled}
            />
            <div style={{ display: 'flex', gap: 8 }}>
              <Input
                value={compareAspects}
                onChange={e => setCompareAspects(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="对比维度 (可选, 逗号分隔), 如: 价格, 续航, 智驾"
                disabled={disabled}
                style={{ flex: 1 }}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                disabled={disabled || compareVehicles.split(/[,，\s]+/).filter(Boolean).length < 2}
              >
                对比
              </Button>
            </div>
          </div>
        )}

        {/* Recommend Mode */}
        {state.inputMode === 'recommend' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <Input
                value={recScenario}
                onChange={e => setRecScenario(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="使用场景 (如: 家用, 通勤, 越野)"
                disabled={disabled}
                style={{ flex: 1 }}
              />
              <Input
                value={recBudget}
                onChange={e => setRecBudget(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="预算 (如: 25-35万)"
                disabled={disabled}
                style={{ flex: 1 }}
              />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Input
                value={recPrefs}
                onChange={e => setRecPrefs(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="偏好标签 (可选, 逗号分隔), 如: 安全, 省油, 空间大"
                disabled={disabled}
                style={{ flex: 1 }}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                disabled={disabled || (!recScenario.trim() && !recBudget.trim())}
              >
                推荐
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
