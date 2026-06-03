import React, { createContext, useContext, useReducer, useCallback, useEffect, type Dispatch } from 'react';
import type { AppState, AppAction, Message, Source, InputMode } from '../types';
import { appReducer, initialState, getActiveSessionId } from './reducer';
import {
  vehicleQuery, vehicleCompare, recommend, closeSession, createSession,
  getAgentState, healthCheckV2,
} from '../services/api';

interface AppContextValue {
  state: AppState;
  dispatch: Dispatch<AppAction>;
  /** 发送车型查询 */
  sendQuery: (text: string) => Promise<void>;
  /** 发送多车对比 */
  sendCompare: (vehicles: string[], aspects?: string[]) => Promise<void>;
  /** 发送智能推荐 */
  sendRecommend: (scenario?: string, budget?: string, preferences?: string[]) => Promise<void>;
  startNewConversation: () => void;
  switchConversation: (id: string) => void;
  clearCurrentSession: () => Promise<void>;
  refreshAgentState: () => Promise<void>;
  setInputMode: (mode: InputMode) => void;
  /** 当前活跃的 session_id */
  activeSessionId: string;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  useEffect(() => {
    // 创建首个对话并注册后端 session
    const init = async () => {
      dispatch({ type: 'NEW_CONVERSATION' } as AppAction);
      refreshAgentState();
      // 向后端注册 session
      try {
        const resp = await createSession();
        if (resp.data?.session_id) {
          // 更新首个对话的 sessionId 为后端返回的
          // 通过 setTimeout 确保 reducer 已更新
          setTimeout(() => {
            const convs = state.conversations;
            if (convs.length > 0) {
              dispatch({
                type: 'SET_CONVERSATION_SESSION',
                payload: { conversationId: state.activeId || convs[0].id, sessionId: resp.data!.session_id },
              });
            }
          }, 0);
        }
      } catch {
        // 后端不可用时使用本地生成的 sessionId
      }
      healthCheckV2().then(h => {
        console.log('Backend health:', h.status, 'redis:', h.redis, 'rabbitmq:', h.rabbitmq);
      }).catch(() => {});
    };
    init();
  }, []);

  const refreshAgentState = useCallback(async () => {
    try {
      const s = await getAgentState();
      dispatch({ type: 'SET_AGENT_STATE', payload: s });
    } catch {
      // Agent not available yet
    }
  }, []);

  /** 通用请求处理 */
  const handleRequest = useCallback(async (
    mode: InputMode,
    requestFn: () => Promise<{ status: string; data?: any; error?: string; degraded: boolean; latency_ms: number }>,
    userDisplay: string,
  ) => {
    dispatch({ type: 'SET_THINKING', payload: true });
    dispatch({ type: 'SET_THINKING_STATUS', payload: 'Agent 正在处理...' });

    try {
      const response = await requestFn();

      if (response.status === 'error') {
        dispatch({
          type: 'ADD_MESSAGE',
          payload: {
            id: Date.now().toString(36),
            role: 'agent',
            content: `请求失败: ${response.error || '未知错误'}`,
            timestamp: Date.now(),
            msgType: mode,
          },
        });
        return;
      }

      const content = response.data?.answer as string
        || response.data?.llm_summary as string
        || JSON.stringify(response.data, null, 2);

      const structuredData = response.data || {};

      dispatch({
        type: 'ADD_MESSAGE',
        payload: {
          id: (Date.now() + 1).toString(36),
          role: 'agent',
          content: response.degraded ? `⚠️ [降级响应] ${content}` : content,
          timestamp: Date.now(),
          msgType: mode,
          structuredData,
        },
      });

      if (response.degraded) {
        dispatch({ type: 'SET_THINKING_STATUS', payload: `响应完成 (降级, ${response.latency_ms}ms)` });
      } else {
        dispatch({ type: 'SET_THINKING_STATUS', payload: `响应完成 (${response.latency_ms}ms)` });
      }
    } catch (err) {
      dispatch({
        type: 'ADD_MESSAGE',
        payload: {
          id: (Date.now() + 1).toString(36),
          role: 'agent',
          content: `抱歉，请求失败: ${err instanceof Error ? err.message : '未知错误'}`,
          timestamp: Date.now(),
          msgType: mode,
        },
      });
    } finally {
      dispatch({ type: 'SET_THINKING', payload: false });
      setTimeout(() => dispatch({ type: 'SET_THINKING_STATUS', payload: '' }), 3000);
    }
  }, []);

  const sessionId = getActiveSessionId(state);

  /** 车型查询 */
  const sendQuery = useCallback(async (text: string) => {
    const sid = getActiveSessionId(state);
    const userMsg: Message = {
      id: Date.now().toString(36),
      role: 'user',
      content: text,
      timestamp: Date.now(),
      msgType: 'chat',
    };
    dispatch({ type: 'ADD_MESSAGE', payload: userMsg });

    await handleRequest('chat', () =>
      vehicleQuery({
        session_id: sid,
        user_id: state.userId,
        query: text,
      })
    , text);
  }, [state, handleRequest]);

  /** 多车对比 */
  const sendCompare = useCallback(async (vehicles: string[], aspects?: string[]) => {
    const sid = getActiveSessionId(state);
    const vehicleList = vehicles.join(', ');
    const userMsg: Message = {
      id: Date.now().toString(36),
      role: 'user',
      content: `对比车型: ${vehicleList}${aspects ? ` (维度: ${aspects.join(', ')})` : ''}`,
      timestamp: Date.now(),
      msgType: 'compare',
    };
    dispatch({ type: 'ADD_MESSAGE', payload: userMsg });

    await handleRequest('compare', () =>
      vehicleCompare({
        session_id: sid,
        user_id: state.userId,
        vehicles,
        aspects,
      })
    , vehicleList);
  }, [state, handleRequest]);

  /** 智能推荐 */
  const sendRecommend = useCallback(async (scenario?: string, budget?: string, preferences?: string[]) => {
    const sid = getActiveSessionId(state);
    const desc = [scenario, budget, ...(preferences || [])].filter(Boolean).join(' | ');
    const userMsg: Message = {
      id: Date.now().toString(36),
      role: 'user',
      content: `智能推荐: ${desc || '综合推荐'}`,
      timestamp: Date.now(),
      msgType: 'recommend',
    };
    dispatch({ type: 'ADD_MESSAGE', payload: userMsg });

    await handleRequest('recommend', () =>
      recommend({
        session_id: sid,
        user_id: state.userId,
        scenario,
        budget,
        preferences,
      })
    , desc);
  }, [state, handleRequest]);

  const startNewConversation = useCallback(() => {
    dispatch({ type: 'NEW_CONVERSATION' } as AppAction);
    // 异步向后端注册新 session (不阻塞 UI)
    const convId = state.activeId;
    createSession().then(resp => {
      if (resp.data?.session_id && convId) {
        dispatch({
          type: 'SET_CONVERSATION_SESSION',
          payload: { conversationId: convId, sessionId: resp.data.session_id },
        });
      }
    }).catch(() => {});
  }, [state.activeId]);

  const switchConversation = useCallback((id: string) => {
    dispatch({ type: 'SWITCH_CONVERSATION', payload: id });
  }, []);

  const clearCurrentSession = useCallback(async () => {
    const sid = getActiveSessionId(state);
    try {
      await closeSession(sid, state.userId);
    } catch {
      // Ignore
    }
    dispatch({ type: 'CLEAR_MESSAGES' });
  }, [state, state.userId]);

  const setInputMode = useCallback((mode: InputMode) => {
    dispatch({ type: 'SET_INPUT_MODE', payload: mode });
  }, []);

  return (
    <AppContext.Provider value={{
      state, dispatch, sendQuery, sendCompare, sendRecommend,
      startNewConversation, switchConversation,
      clearCurrentSession, refreshAgentState, setInputMode,
      activeSessionId: getActiveSessionId(state),
    }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
