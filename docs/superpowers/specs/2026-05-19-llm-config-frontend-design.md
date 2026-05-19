# AutoSalesAgent LLM 配置前端化 设计文档

## 概述

当前 LLM 配置（模型选择、API URL、temperature、max_tokens）仅能通过编辑 `config.py` 或环境变量修改，缺乏前端可视化配置入口。本次改动在设置抽屉中新增 LLM 配置区域，与已有的 Embedding 选择器和 API Key 表单并列。

---

## 后端设计

### ConfigSettings 响应模型扩展

`frontend/backend/server.py` 的 `ConfigSettings` 新增 3 个字段：

```python
class ConfigSettings(BaseModel):
    llm_api_key: str = ""
    embedding_api_key: str = ""
    embedding_provider: str = "deepseek"
    serpapi_key: str = ""
    llamaparse_api_key: str = ""
    embedding_model: str = ""
    # ---- 新增 ----
    llm_model: str = ""
    llm_api_url: str = ""
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048
```

### UpdateConfigRequest 扩展

```python
class UpdateConfigRequest(BaseModel):
    llm_api_key: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_provider: Optional[str] = None
    serpapi_key: Optional[str] = None
    llamaparse_api_key: Optional[str] = None
    # ---- 新增 ----
    llm_model: Optional[str] = None
    llm_api_url: Optional[str] = None
    llm_temperature: Optional[float] = None
    llm_max_tokens: Optional[int] = None
```

### GET /api/config 端点

返回新增的 3 个字段，从 `config` 单例读取当前值。

### PUT /api/config 端点

扩展 LLM 客户端重建触发条件。当前只在 `llm_api_key` 变更时重建，改为以下字段任一变更都触发：

- `llm_api_key`
- `llm_api_url`
- `llm_model`

Temperature 变更不重建客户端，仅更新 config 内存值（后续 Agent 调用 `OpenAI` 时自然使用最新 temperature）。

### config.update_from_dict 扩展

`allowed_keys` 新增 `"llm_api_url"`、`"llm_model"`、`"llm_temperature"`、`"llm_max_tokens"`。

---

## 前端设计

### TypeScript 类型扩展 (`types/index.ts`)

```ts
export interface ConfigSettings {
  llm_api_key: string;
  embedding_api_key: string;
  embedding_provider: 'qwen' | 'deepseek';
  serpapi_key: string;
  llamaparse_api_key: string;
  embedding_model: string;
  // ---- 新增 ----
  llm_model: string;
  llm_api_url: string;
  llm_temperature: number;
  llm_max_tokens: number;
}

export interface UpdateConfigPayload {
  llm_api_key?: string;
  embedding_api_key?: string;
  embedding_provider?: 'qwen' | 'deepseek';
  serpapi_key?: string;
  llamaparse_api_key?: string;
  // ---- 新增 ----
  llm_model?: string;
  llm_api_url?: string;
  llm_temperature?: number;
  llm_max_tokens?: number;
}
```

### 新组件 `LlmConfigForm.tsx`

独立的 LLM 配置表单，包含：

| 字段 | 控件 | 说明 |
|------|------|------|
| 模型 | `Select` (mode="tags" 或 combobox) | 预设 `deepseek-chat`、`deepseek-reasoner`，支持输入自定义模型名 |
| API URL | `Input` | 文本输入，失焦时自动 trim |
| Temperature | `Slider` | 范围 0-2，步长 0.1，实时显示当前值 |
| Max Tokens | `InputNumber` | 范围 1-8192 |

**交互逻辑：**
- 从 `config` prop 初始化表单值（config 来自父组件 `/api/config` 的返回值）
- 任一字段修改后标记 `dirty`，启用 "保存 LLM 配置" 按钮
- 保存时调用 `updateConfig` API，仅发送变更字段
- 成功后通过父组件回调刷新配置

**预设模型列表：**
```
deepseek-chat
deepseek-reasoner
gpt-4o
gpt-4o-mini
qwen-plus
qwen-max
```

预设在下拉列表中显示，同时允许用户直接输入任意模型名称。

### SettingsDrawer 集成

在 Embedding 选择器区域和 API Key 表单区域之间插入 LLM 配置 section：

```
┌─ 设置 ──────────────────────────┐
│  Embedding 模型   [卡片选择器]   │
│  ─────────────────────────────  │
│  LLM 配置          [新组件]      │  ← 新增
│  ─────────────────────────────  │
│  API 密钥配置      [密钥表单]    │
│  ─────────────────────────────  │
│  知识库文档        [PDF上传]     │
└────────────────────────────────┘
```

Props 传递：`SettingsDrawer` 已有 `config` state 和 `getConfig` / `updateConfig` 方法，直接传给 `LlmConfigForm`。

### 样式

复用 `Settings.module.css` 现有类：`section`、`sectionTitle`、`divider`、`formItem`、`label`。如需额外样式（Slider 宽度、InputNumber 布局），在 CSS 文件中新增最小限度的规则。

---

## 错误处理

- API 调用失败：`message.error('保存 LLM 配置失败')`
- 模型名为空：保存时校验，提示 "模型名不能为空"
- 后端 URL 不可达：不校验（用户可能使用内网代理地址），运行时由 Agent 自然报错

---

## 改动文件清单

| 文件 | 改动量 | 说明 |
|------|--------|------|
| `frontend/backend/server.py` | ~20 行 | ConfigSettings/UpdateConfigRequest 扩展 + 重建逻辑 |
| `config.py` | ~3 行 | `allowed_keys` 扩展 |
| `frontend/src/types/index.ts` | ~6 行 | 接口新增字段 |
| `frontend/src/components/Settings/LlmConfigForm.tsx` | ~120 行 | 新组件 |
| `frontend/src/components/Settings/SettingsDrawer.tsx` | ~10 行 | 集成 LlmConfigForm |
| `frontend/src/styles/Settings.module.css` | ~15 行 | 新控件样式 |
