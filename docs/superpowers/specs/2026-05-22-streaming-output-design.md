# Streaming Output Design

## Overview

为 AutoSalesAgent 添加完整的流式输出能力，包含两个层面：

1. **阶段级流式**：前端通过 WebSocket 实时展示 Agent 工作流各阶段进度（规划→工具调用→答案→反思）
2. **Token 级流式**：在答案生成阶段，LLM 文本逐 token 推送到前端，实现类似 ChatGPT 的逐字渲染效果

## Architecture

```
用户输入 → WebSocket → 后端逐阶段推送事件 → 前端实时渲染
                              │
    ┌─────────────────────────┼─────────────────────────┐
    ▼                         ▼                         ▼
plan_start              tool_start/result              token
plan_result             (每个工具一对)            (逐token流式)
                                                         │
                                                    ┌────┴────┐
                                                    ▼         ▼
                                               reflection   done
```

## Backend Changes

### 1. `agent/agent_core.py`

新增两个流式生成方法：

- `_generate_answer_stream(query, exec_results) -> Generator[str, None, None]`
  - 构建与 `_generate_answer` 相同的 system_prompt + user content
  - 调用 `llm_client.chat.completions.create(..., stream=True)`
  - 逐 chunk yield `chunk.choices[0].delta.content or ""`

- `_chat_reply_stream(user_input) -> Generator[str, None, None]`
  - 闲聊路径的流式版本，同理使用 `stream=True`

流式调用异常时降级：catch 后 fallback 为非流式调用。

### 2. `frontend/backend/server.py`

修改 `_execute_and_stream()` 中的答案生成阶段：

**原逻辑**：
```python
current_answer = agent._generate_answer(query, exec_results)
yield {"type": "answer", "payload": {"answer": current_answer}}
```

**新逻辑**（初步答案和迭代答案均如此）：
```python
yield {"type": "answer_start", "payload": {}}
full_answer = ""
for token in agent._generate_answer_stream(query, exec_results):
    full_answer += token
    yield {"type": "token", "payload": {"text": token}}
yield {"type": "answer_end", "payload": {"answer": full_answer}}
```

**新增事件类型**：
- `answer_start` — 开始生成答案，前端可创建空的 agent Message
- `token` — 单个文本 token，前端逐字追加
- `answer_end` — 答案生成完毕，携带完整答案用于 citations 等

保留原 `answer` 事件做降级兼容（非流式路径仍可用）。

## Frontend Changes

### 1. `types/index.ts`

WSMessage type 扩展新增 `answer_start`、`token`、`answer_end` 类型。

### 2. `services/api.ts`

新增 `createChatWebSocket()` 工厂函数，返回 WebSocket 实例。

### 3. `store/AppContext.tsx`

重写 `sendMessage()` 方法：

1. 添加 user Message
2. 建立 WebSocket 连接到 `ws://localhost:8000/ws/chat`
3. 发送 `{"query": "..."}`
4. `onmessage` 分流处理：
   - `plan_start` → `SET_THINKING_STATUS("正在规划...")`
   - `plan_result` → 展示 Action 列表，更新 thinkingStatus
   - `tool_start` → `ADD_TRACE_STEP(running)`，更新 thinkingStatus
   - `tool_result` → `UPDATE_TRACE_STEP(done)`
   - `answer_start` → 创建空 agent Message，`ADD_MESSAGE`，隐藏 ThinkingIndicator
   - `token` → `UPDATE_LAST_AGENT_MESSAGE` 逐字追加
   - `answer_end` → 附加 citations 到 agent Message
   - `reflection` → 更新 thinkingStatus（如需迭代回到 tool_start）
   - `done` → 最终状态确认
   - `error` → 显示错误消息
5. `onclose` / `onerror` → 处理断线，显示错误

### 4. `ThinkingIndicator.tsx`

展示更详细的阶段文案，根据 `thinkingStatus` 动态显示。

## Data Flow

```
sendMessage(text)
  → ADD_MESSAGE(user)
  → SET_THINKING(true)
  → new WebSocket("/ws/chat")
  → ws.send({query})

  ws.onmessage(event):
    plan_start    → SET_THINKING_STATUS + ADD_TRACE_STEP(pending)
    plan_result   → UPDATE_TRACE_STEP(done)
    tool_start    → SET_THINKING_STATUS + ADD_TRACE_STEP(running)
    tool_result   → UPDATE_TRACE_STEP(done)
    answer_start  → ADD_MESSAGE(agent, content="")
    token         → UPDATE_LAST_AGENT_MESSAGE(content += token)
    answer_end    → attach citations
    reflection    → SET_THINKING_STATUS
    done          → SET_THINKING(false), ws.close()
```

## Error Handling

- WebSocket 连接失败：降级到 REST `/api/chat` 作为 fallback
- LLM 流式调用异常：catch 后降级为非流式 `_generate_answer`，仍通过 `answer_end` 返回完整结果
- 中途断线：显示 "连接已断开" 错误消息，保留已接收的部分内容

## Files Changed

| File | Change |
|------|--------|
| `agent/agent_core.py` | +`_generate_answer_stream()`, +`_chat_reply_stream()` |
| `frontend/backend/server.py` | 修改 `_execute_and_stream()` 答案阶段，新增 token 事件 |
| `frontend/src/types/index.ts` | WSMessage 类型扩展 |
| `frontend/src/services/api.ts` | +`createChatWebSocket()` |
| `frontend/src/store/AppContext.tsx` | 重写 `sendMessage()` 使用 WebSocket |
| `frontend/src/components/Chat/ThinkingIndicator.tsx` | 增强阶段文案 |
