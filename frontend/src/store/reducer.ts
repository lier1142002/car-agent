import type { AppState, AppAction, Message } from '../types';

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function generateSessionId(): string {
  return 'sess_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
}

export const initialState: AppState = {
  conversations: [],
  activeId: '',
  messages: [],
  isThinking: false,
  thinkingStatus: '',
  sources: [],
  trace: [],
  agentState: null,
  sessionId: generateSessionId(),
  userId: 'default_user',
  inputMode: 'chat',
};

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_THINKING':
      return { ...state, isThinking: action.payload };

    case 'SET_THINKING_STATUS':
      return { ...state, thinkingStatus: action.payload };

    case 'ADD_MESSAGE': {
      const msg = action.payload;
      const newMessages = [...state.messages, msg];
      const updatedConversations = state.conversations.map(c =>
        c.id === state.activeId
          ? { ...c, messages: newMessages, title: c.title === '新对话' && msg.role === 'user'
              ? msg.content.slice(0, 30) : c.title }
          : c
      );
      return { ...state, messages: newMessages, conversations: updatedConversations };
    }

    case 'UPDATE_LAST_AGENT_MESSAGE': {
      const msgs = [...state.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'agent') {
          msgs[i] = { ...msgs[i], content: msgs[i].content + action.payload };
          break;
        }
      }
      return { ...state, messages: msgs };
    }

    case 'SET_LAST_AGENT_MESSAGE': {
      const msgs = [...state.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'agent') {
          msgs[i] = { ...msgs[i], content: action.payload };
          break;
        }
      }
      return { ...state, messages: msgs };
    }

    case 'SET_SOURCES':
      return { ...state, sources: action.payload };

    case 'ADD_TRACE_STEP':
      return { ...state, trace: [...state.trace, action.payload] };

    case 'UPDATE_TRACE_STEP': {
      const newTrace = state.trace.map(t =>
        t.step === action.payload.step
          ? { ...t, status: action.payload.status, detail: action.payload.detail ?? t.detail }
          : t
      );
      return { ...state, trace: newTrace };
    }

    case 'SET_AGENT_STATE':
      return { ...state, agentState: action.payload };

    case 'NEW_CONVERSATION': {
      const newConv = {
        id: generateId(),
        title: '新对话',
        messages: [],
        createdAt: Date.now(),
      };
      return {
        ...state,
        conversations: [newConv, ...state.conversations],
        activeId: newConv.id,
        messages: [],
        sources: [],
        trace: [],
      };
    }

    case 'SWITCH_CONVERSATION': {
      const conv = state.conversations.find(c => c.id === action.payload);
      return {
        ...state,
        activeId: action.payload,
        messages: conv?.messages ?? [],
        sources: [],
        trace: [],
      };
    }

    case 'CLEAR_MESSAGES':
      return {
        ...state,
        messages: [],
        sources: [],
        trace: [],
        isThinking: false,
      };

    case 'SET_SESSION_ID':
      return { ...state, sessionId: action.payload };

    case 'SET_INPUT_MODE':
      return { ...state, inputMode: action.payload };

    default:
      return state;
  }
}
