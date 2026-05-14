import type { WSMessage } from '../types';

type MessageHandler = (msg: WSMessage) => void;
type StatusHandler = (connected: boolean) => void;

export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: MessageHandler[] = [];
  private statusHandlers: StatusHandler[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = true;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  constructor(url: string = '/ws/chat') {
    // Use relative path so Vite proxy handles it
    // Build absolute WS URL from current location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.url = url.startsWith('ws') ? url : `${protocol}//${window.location.host}${url}`;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) return;
    this.shouldReconnect = true;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.notifyStatus(true);
      };

      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const msg: WSMessage = JSON.parse(event.data);
          this.handlers.forEach(h => h(msg));
        } catch {
          // Ignore malformed messages
        }
      };

      this.ws.onclose = () => {
        this.notifyStatus(false);
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        // onclose will fire after this
      };
    } catch {
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (!this.shouldReconnect) return;
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.notifyStatus(false);
  }

  send(query: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ query }));
    }
  }

  onMessage(handler: MessageHandler): () => void {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter(h => h !== handler);
    };
  }

  onStatusChange(handler: StatusHandler): () => void {
    this.statusHandlers.push(handler);
    return () => {
      this.statusHandlers = this.statusHandlers.filter(h => h !== handler);
    };
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private notifyStatus(connected: boolean): void {
    this.statusHandlers.forEach(h => h(connected));
  }
}
