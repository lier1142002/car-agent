# LLM 配置前端化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在设置抽屉中新增 LLM 完整配置区域（模型、API URL、Temperature、Max Tokens），与已有的 Embedding 选择器和 API Key 表单并列。

**Architecture:** 后端扩展 `ConfigSettings`/`UpdateConfigRequest` 增加 4 个字段，LLM 客户端重建触发条件从仅 `llm_api_key` 扩展为 `llm_api_key`/`llm_api_url`/`llm_model` 三者。前端新建 `LlmConfigForm` 组件，在 `SettingsDrawer` 中 Embedding 和 API Key 区域之间插入。

**Tech Stack:** Python FastAPI + Pydantic (后端), React 18 + TypeScript + Ant Design 5 (前端)

**Spec:** `docs/superpowers/specs/2026-05-19-llm-config-frontend-design.md`

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `config.py` | 修改 | `allowed_keys` 新增 `llm_temperature`, `llm_max_tokens` |
| `frontend/backend/server.py` | 修改 | 扩展 Pydantic 模型 + GET/PUT 端点 + 客户端重建逻辑 |
| `frontend/src/types/index.ts` | 修改 | `ConfigSettings`/`UpdateConfigPayload` 新增字段 |
| `frontend/src/components/Settings/LlmConfigForm.tsx` | 新建 | LLM 配置表单组件 (~90 行) |
| `frontend/src/components/Settings/SettingsDrawer.tsx` | 修改 | 集成 LlmConfigForm |
| `frontend/src/styles/Settings.module.css` | 修改 | 新增 LLM 表单样式 |

---

### Task 1: 扩展 config.py 的 allowed_keys

**Files:**
- Modify: `config.py:175-181`

- [ ] **Step 1: 在 allowed_keys 中添加 llm_temperature 和 llm_max_tokens**

`config.py` 第 175-181 行改为：

```python
        allowed_keys = {
            "llm_api_key", "llm_api_url", "llm_model",
            "llm_temperature", "llm_max_tokens",
            "embedding_api_key", "embedding_api_url", "embedding_model",
            "embedding_provider",
            "deepseek_api_key", "deepseek_api_url", "deepseek_embedding_model",
            "serpapi_key", "llamaparse_api_key",
        }
```

- [ ] **Step 2: 验证 config.py 可正常导入**

```bash
python -c "from config import config; print(config.llm_temperature, config.llm_max_tokens)"
```
Expected: `0.1 2048`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat: add llm_temperature and llm_max_tokens to allowed_keys

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: 扩展 server.py 后端模型和端点

**Files:**
- Modify: `frontend/backend/server.py`

- [ ] **Step 1: 扩展 ConfigSettings 模型 (lines 108-115)**

```python
class ConfigSettings(BaseModel):
    """配置设置（API Key 脱敏显示）。"""
    llm_api_key: str = ""
    embedding_api_key: str = ""
    embedding_provider: str = "deepseek"
    serpapi_key: str = ""
    llamaparse_api_key: str = ""
    embedding_model: str = ""
    llm_model: str = ""
    llm_api_url: str = ""
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048
```

- [ ] **Step 2: 扩展 UpdateConfigRequest 模型 (lines 118-124)**

```python
class UpdateConfigRequest(BaseModel):
    """更新配置请求体（所有字段可选）。"""
    llm_api_key: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_provider: Optional[str] = None
    serpapi_key: Optional[str] = None
    llamaparse_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_url: Optional[str] = None
    llm_temperature: Optional[float] = None
    llm_max_tokens: Optional[int] = None
```

- [ ] **Step 3: 扩展 get_config 端点 (lines 209-216)**

```python
    return ConfigSettings(
        llm_api_key=_mask_api_key(config.llm_api_key),
        embedding_api_key=_mask_api_key(config.embedding_api_key),
        embedding_provider=config.embedding_provider,
        serpapi_key=_mask_api_key(config.serpapi_key),
        llamaparse_api_key=_mask_api_key(config.llamaparse_api_key),
        embedding_model=config.embedding_model,
        llm_model=config.llm_model,
        llm_api_url=config.llm_api_url,
        llm_temperature=config.llm_temperature,
        llm_max_tokens=config.llm_max_tokens,
    )
```

- [ ] **Step 4: 扩展 LLM 客户端重建触发条件 (line 231)**

将：
```python
    if any(k in updated for k in ("llm_api_key",)):
```
改为：
```python
    if any(k in updated for k in ("llm_api_key", "llm_api_url", "llm_model")):
```

- [ ] **Step 5: 验证后端端点**

启动后端后测试：

```bash
# 测试 GET /api/config — 应包含新字段
curl -s http://localhost:8000/api/config | python -m json.tool

# 测试 PUT /api/config — 更新 temperature
curl -s -X PUT http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{"llm_temperature": 0.5}' | python -m json.tool
# Expected: {"status": "ok", "updated": ["llm_temperature"]}

# 测试 PUT /api/config — 切换模型应触发客户端重建
curl -s -X PUT http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{"llm_model": "deepseek-chat"}'
# Expected: {"status": "ok", "updated": ["llm_model"]}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/backend/server.py
git commit -m "feat: add LLM model/url/temperature/max_tokens to config API

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: 扩展前端 TypeScript 类型

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: 扩展 ConfigSettings (lines 104-112)**

```ts
export interface ConfigSettings {
  llm_api_key: string;
  embedding_api_key: string;
  embedding_provider: 'qwen' | 'deepseek';
  serpapi_key: string;
  llamaparse_api_key: string;
  embedding_model: string;
  llm_model: string;
  llm_api_url: string;
  llm_temperature: number;
  llm_max_tokens: number;
}
```

- [ ] **Step 2: 扩展 UpdateConfigPayload (lines 114-121)**

```ts
export interface UpdateConfigPayload {
  llm_api_key?: string;
  embedding_api_key?: string;
  embedding_provider?: 'qwen' | 'deepseek';
  serpapi_key?: string;
  llamaparse_api_key?: string;
  llm_model?: string;
  llm_api_url?: string;
  llm_temperature?: number;
  llm_max_tokens?: number;
}
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```
Expected: No new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add LLM config fields to TypeScript types

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 创建 LlmConfigForm 组件

**Files:**
- Create: `frontend/src/components/Settings/LlmConfigForm.tsx`

- [ ] **Step 1: 创建 LlmConfigForm.tsx**

```tsx
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
  { value: 'deepseek-chat', label: 'deepseek-chat' },
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
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Settings/LlmConfigForm.tsx
git commit -m "feat: add LlmConfigForm component with model/url/temperature/max_tokens

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: 在 SettingsDrawer 中集成 LlmConfigForm

**Files:**
- Modify: `frontend/src/components/Settings/SettingsDrawer.tsx`

- [ ] **Step 1: 添加 import**

第 4 行后添加：
```tsx
import { LlmConfigForm } from './LlmConfigForm';
```

- [ ] **Step 2: 添加 handleLlmSaved 回调**

在 `handleEmbeddingChange` 之后（第 54 行后）添加：
```tsx
  const handleLlmSaved = async () => {
    const newConfig = await getConfig();
    setConfig(newConfig);
    refreshAgentState();
  };
```

- [ ] **Step 3: 在 Embedding 区域和 API Key 区域之间插入 LLM 配置 section**

在第一个 `</div>` (第 85 行 Embedding section 结束) 和 `<div className={styles.divider} />` (第 87 行) 之间插入：

```tsx
      <div className={styles.divider} />

      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>LLM 配置</h4>
        <LlmConfigForm
          config={config}
          onSaved={handleLlmSaved}
        />
      </div>
```

完整的 return JSX 应为：

```tsx
    <Drawer ...>
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>Embedding 模型</h4>
        <EmbeddingSelector
          value={config?.embedding_provider ?? 'deepseek'}
          onChange={handleEmbeddingChange}
        />
      </div>

      <div className={styles.divider} />

      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>LLM 配置</h4>
        <LlmConfigForm
          config={config}
          onSaved={handleLlmSaved}
        />
      </div>

      <div className={styles.divider} />

      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>API 密钥配置</h4>
        <ApiKeyForm ... />
      </div>
      ...
    </Drawer>
```

- [ ] **Step 4: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Settings/SettingsDrawer.tsx
git commit -m "feat: integrate LlmConfigForm into SettingsDrawer

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: 添加 Logo 和验证完整性

**Files:**
- Modify: `frontend/src/styles/Settings.module.css` (if needed — actually existing `.apiKeyForm`, `.formItem`, `.label` classes are reused by LlmConfigForm)

- [ ] **Step 1: 验证前端构建**

```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 2: 端到端验证**

1. 启动后端: `python frontend/backend/server.py`
2. 启动前端: `cd frontend && npm run dev`
3. 打开浏览器 `http://localhost:3000`
4. 点击左侧 ⚙ 设置按钮
5. 验证 LLM 配置区域出现在 Embedding 选择器下方、API Key 表单上方
6. 选择一个模型 → 点击 "保存 LLM 配置" → 验证成功提示
7. 输入自定义模型名 → 保存 → 验证成功
8. 调节 Temperature 滑块 → 保存 → 验证成功
9. 修改 Max Tokens → 保存 → 验证成功

- [ ] **Step 3: Commit any remaining changes**

```bash
git status
git add -A
git commit -m "feat: complete LLM config frontend integration

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```
