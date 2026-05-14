import React, { createContext, useContext, useReducer, useCallback, useEffect, type Dispatch } from 'react';
import type { AppState, AppAction, Message, Source, TraceStep } from '../types';
import { appReducer, initialState } from './reducer';
import { sendChat, getAgentState, clearSession } from '../services/api';

interface AppContextValue {
  state: AppState;
  dispatch: Dispatch<AppAction>;
  sendMessage: (text: string) => Promise<void>;
  startNewConversation: () => void;
  switchConversation: (id: string) => void;
  clearCurrentSession: () => Promise<void>;
  refreshAgentState: () => Promise<void>;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  // Initialize first conversation and fetch agent state
  useEffect(() => {
    // Start with one conversation
    dispatch({ type: 'NEW_CONVERSATION' } as AppAction);
    refreshAgentState();
  }, []);

  const refreshAgentState = useCallback(async () => {
    try {
      const s = await getAgentState();
      dispatch({ type: 'SET_AGENT_STATE', payload: s });
    } catch {
      // Agent not available yet (dev server not running)
    }
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    // Add user message
    const userMsg: Message = {
      id: Date.now().toString(36),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    dispatch({ type: 'ADD_MESSAGE', payload: userMsg });
    dispatch({ type: 'SET_THINKING', payload: true });
    dispatch({ type: 'SET_THINKING_STATUS', payload: '正在分析问题...' });
    dispatch({ type: 'SET_SOURCES', payload: [] });
    // Clear previous trace
    // (trace state is app-level, we'll overwrite)

    try {
      dispatch({ type: 'SET_THINKING_STATUS', payload: 'Agent 正在规划...' });
      const response = await sendChat({ query: text });

      // Build trace steps from response
      const traceSteps: TraceStep[] = [];
      response.actions.forEach((a, i) => {
        traceSteps.push({
          step: `${i + 1}️⃣ ${a.tool}`,
          detail: a.query,
          status: 'done',
          timestamp: Date.now(),
        });
      });
      traceSteps.push({
        step: `${response.actions.length + 1}️⃣ reflection`,
        detail: `迭代次数: ${response.trace.iterations}`,
        status: 'done',
        timestamp: Date.now(),
      });

      // Build citations from sources
      const citations = response.sources.map((s, i) => ({
        index: i + 1,
        title: s.title ?? s.tool,
        text: s.text.slice(0, 200),
        score: s.score ?? 0,
        tool: s.tool,
      }));

      const agentMsg: Message = {
        id: (Date.now() + 1).toString(36),
        role: 'agent',
        content: response.answer,
        timestamp: Date.now(),
        citations,
      };

      dispatch({ type: 'ADD_MESSAGE', payload: agentMsg });
      dispatch({ type: 'SET_SOURCES', payload: response.sources });
      // Set trace by dispatching each step
      // (simplified: we just store the trace conceptually)
    } catch (err) {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(36),
        role: 'agent',
        content: `抱歉，请求失败: ${err instanceof Error ? err.message : '未知错误'}`,
        timestamp: Date.now(),
      };
      dispatch({ type: 'ADD_MESSAGE', payload: errorMsg });
    } finally {
      dispatch({ type: 'SET_THINKING', payload: false });
      dispatch({ type: 'SET_THINKING_STATUS', payload: '' });
    }
  }, []);

  const startNewConversation = useCallback(() => {
    dispatch({ type: 'NEW_CONVERSATION' } as AppAction);
  }, []);

  const switchConversation = useCallback((id: string) => {
    dispatch({ type: 'SWITCH_CONVERSATION', payload: id });
  }, []);

  const clearCurrentSession = useCallback(async () => {
    try {
      await clearSession();
    } catch {
      // Ignore if server not available
    }
    dispatch({ type: 'CLEAR_MESSAGES' });
  }, []);

  return (
    <AppContext.Provider value={{
      state, dispatch, sendMessage,
      startNewConversation, switchConversation,
      clearCurrentSession, refreshAgentState,
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
