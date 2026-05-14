# AutoSalesAgent 可视化配置 & PDF上传 & Embedding切换 设计文档

## 概述

在现有三栏布局基础上新增右侧设置抽屉（Settings Drawer），提供：
- API Key 可视化配置（LLM / Embedding / SerpAPI / LlamaParse）
- PDF 文件上传 → 解析切分 → 自动入库
- Embedding 提供商运行时切换（千问 / DeepSeek）

---

## 后端设计

### Embedding 抽象层重构

当前 `infrastructure/embedding.py` 仅支持千问 API。改造为工厂模式：

```
infrastructure/embedding.py
├── BaseEmbeddingProvider       — 抽象基类
│   ├── encode_text(text) -> (dense, sparse)
│   └── encode_batch(texts) -> (dense_list, sparse_list)
├── QwenEmbeddingProvider       — 千问 text-embedding-v3（现有逻辑迁移）
├── DeepSeekEmbeddingProvider   — DeepSeek API（OpenAI 兼容接口）
└── EmbeddingClient             — 外观类
    ├── __init__(provider: str) — 根据 "qwen" / "deepseek" 初始化对应 provider
    ├── switch_provider(name)   — 运行时切换
    └── encode_text / encode_batch — 委托给当前 provider
```

**DeepSeek provider 配置：**
- API URL: `https://api.deepseek.com/v1`
- Model: `deepseek-embedding`（或用户自定义）
- 接口格式：OpenAI 兼容 `/embeddings`
- 输出维度：由 API 返回决定，默认配置 1536

### Config 模型扩展

`config.py` 新增字段：

```python
embedding_provider: str = "qwen"  # "qwen" / "deepseek"
deepseek_api_key: str = ""        # DeepSeek API Key
deepseek_api_url: str = "https://api.deepseek.com/v1"
deepseek_embedding_model: str = "deepseek-embedding"
```

新增方法 `update_from_dict(data: dict)` 支持运行时部分更新配置。

### API 端点

#### `GET /api/config` — 获取当前配置

```json
{
  "llm_api_key": "sk-***b3f2",
  "embedding_api_key": "sk-***a1c4",
  "embedding_provider": "qwen",
  "serpapi_key": "***",
  "llamaparse_api_key": "***",
  "embedding_model": "text-embedding-v3"
}
```

API Key 脱敏规则：长度 ≤ 8 显示 `***`，长度 > 8 显示前 3 位 + `***` + 后 4 位。

#### `PUT /api/config` — 运行时更新配置

请求体（所有字段可选，仅更新传入字段）：

```json
{
  "llm_api_key": "sk-new-key",
  "embedding_api_key": "sk-new-key",
  "embedding_provider": "deepseek",
  "serpapi_key": "new-key",
  "llamaparse_api_key": "new-key"
}
```

处理逻辑：
1. 更新 `config` 全局单例对应字段
2. 若 `embedding_provider` 变化 → 调用 `EmbeddingClient.switch_provider()`
3. 若 LLM/Embedding API Key 变化 → 重建对应的 OpenAI 客户端实例
4. 配置仅会话内有效（重启恢复为 config.py 默认值 + 环境变量）

#### `POST /api/upload-pdf` — PDF 上传入库

- Content-Type: `multipart/form-data`
- 字段: `file` (PDF 文件)
- 返回: `{ "status": "success", "filename": "xxx.pdf", "chunks": 42 }`

处理流程：
1. 接收上传文件，保存到临时目录
2. 调用 `DocParser.parse()` 解析为 Markdown
3. 调用 `DocParser.chunk_text()` 智能切块
4. 调用 `RAGTool.index_documents()` 写入 Milvus
5. 清理临时文件
6. 返回结果

---

## 前端设计

### 组件树

```
AppLayout (现有三栏)
├── Sidebar
│   ├── ... (现有内容)
│   └── SettingsTrigger          — 齿轮按钮，点击打开 Drawer
├── ChatPanel (现有)
├── TracePanel (现有)
└── SettingsDrawer (新增)         — Ant Design Drawer，右侧滑出，宽度 420px
    ├── DrawerHeader             — 标题 "设置" + 关闭按钮
    ├── ApiKeyForm
    │   ├── LLM API Key 输入框   — Input.Password + "测试" 按钮
    │   ├── Embedding API Key    — Input.Password
    │   ├── SerpAPI Key          — Input.Password
    │   ├── LlamaParse API Key   — Input.Password
    │   └── 保存按钮             — Button primary
    ├── Divider
    ├── EmbeddingSelector
    │   ├── 千问卡片              — Radio 卡片（图标 + 描述）
    │   └── DeepSeek 卡片         — Radio 卡片
    ├── Divider
    └── PdfUploader
        ├── Upload.Dragger       — 拖拽区域（仅 .pdf）
        ├── 进度条               — Progress bar
        └── 结果提示             — Alert（成功/失败）
```

### 数据流

```
SettingsDrawer 打开 → GET /api/config → 填充表单初始值
用户修改 API Key → 保存 → PUT /api/config → 刷新 agentState
用户切换 Embedding → onChange → PUT /api/config (provider字段)
用户拖入 PDF → POST /api/upload-pdf → 进度 → 成功提示 → 刷新 KnowledgeStatus
```

### 类型扩展

```typescript
// 新增接口
interface ConfigSettings {
  llm_api_key: string;          // 脱敏显示用
  embedding_api_key: string;    // 脱敏显示用
  embedding_provider: 'qwen' | 'deepseek';
  serpapi_key: string;
  llamaparse_api_key: string;
  embedding_model: string;
}

interface UpdateConfigPayload {
  llm_api_key?: string;
  embedding_api_key?: string;
  embedding_provider?: 'qwen' | 'deepseek';
  serpapi_key?: string;
  llamaparse_api_key?: string;
}

interface PdfUploadResponse {
  status: 'success' | 'error';
  filename: string;
  chunks: number;
}
```

### 文件清单

```
frontend/src/
├── components/Settings/
│   ├── SettingsDrawer.tsx        — Drawer 容器 + 保存状态管理
│   ├── ApiKeyForm.tsx            — API Key 表单区域
│   ├── EmbeddingSelector.tsx     — Embedding 模型卡片选择器
│   └── PdfUploader.tsx           — PDF 拖拽上传组件
├── components/Sidebar/
│   └── Sidebar.tsx               — 底部增加设置按钮入口
├── services/api.ts               — 新增 updateConfig, uploadPdf, getConfig
├── types/index.ts                — 新增 ConfigSettings 等接口
├── store/
│   ├── reducer.ts                — 新增 SET_CONFIG 等 action
│   └── AppContext.tsx            — 新增 updateConfig, uploadPdf 方法
└── styles/
    └── Settings.module.css       — 设置面板样式
```

---

## 交互细节

### 设置入口
- Sidebar 底部显示齿轮图标 `SettingOutlined` + "设置"，点击打开 Drawer
- Drawer 打开时先调用 `GET /api/config` 加载当前配置

### API Key 保存
- 密码框默认显示脱敏值，用户点击后清空输入新值
- 未修改的字段不发送更新（PUT body 仅包含变更字段）
- 保存成功后 `message.success("配置已更新")`

### Embedding 切换
- 两个卡片 Radio 组，当前激活的卡片有蓝色边框
- 切换时自动保存，无需额外点保存按钮
- 切换成功后显示 "Embedding 已切换为 千问/DeepSeek"

### PDF 上传
- 仅接受 .pdf 文件，其他类型拦截 + 警告
- 上传中显示 Spin + "正在解析入库..."
- 成功后显示：Alert success "已切分为 42 块，成功索引入库 [刷新状态]"
- 失败显示：Alert error + 错误详情

---

## 自审清单

1. **无占位符**: 所有接口路径、请求/响应格式、组件名称均已明确定义
2. **内部一致**: 后端新增 3 个端点与前端 3 个功能区域一一对应；Embedding 抽象层接口清晰
3. **范围合理**: 单一 spec 覆盖配置可视化 + PDF上传 + Embedding切换三个关联功能
4. **无歧义**: API Key 脱敏规则明确；Embedding provider 切换行为具体；PDF 上传流程完整
