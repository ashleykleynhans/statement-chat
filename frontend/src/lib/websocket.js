/**
 * WebSocket store for real-time chat.
 */
import { writable, derived } from 'svelte/store';

// Connection states
export const ConnectionState = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  ERROR: 'error',
};

// Stores
export const connectionState = writable(ConnectionState.DISCONNECTED);
export const sessionId = writable(null);
export const messages = writable([]);
export const isThinking = writable(false);
export const error = writable(null);
export const stats = writable(null);

// Derived store for connection status
export const isConnected = derived(
  connectionState,
  ($state) => $state === ConnectionState.CONNECTED
);

// WebSocket instance
let ws = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY = 2000;

/**
 * Connect to the WebSocket server.
 */
export function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return;
  }

  connectionState.set(ConnectionState.CONNECTING);
  error.set(null);

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/chat`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    reconnectAttempts = 0;
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleMessage(data);
    } catch (err) {
      console.error('Failed to parse WebSocket message:', err);
    }
  };

  ws.onerror = (event) => {
    console.error('WebSocket error:', event);
    error.set('Connection error');
    connectionState.set(ConnectionState.ERROR);
  };

  ws.onclose = () => {
    connectionState.set(ConnectionState.DISCONNECTED);
    sessionId.set(null);

    // Attempt reconnection
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      reconnectAttempts++;
      setTimeout(connect, RECONNECT_DELAY * reconnectAttempts);
    }
  };
}

/**
 * Disconnect from the WebSocket server.
 */
export function disconnect() {
  if (ws) {
    ws.close();
    ws = null;
  }
  connectionState.set(ConnectionState.DISCONNECTED);
  sessionId.set(null);
}

/**
 * Handle incoming WebSocket messages.
 */
function handleMessage(data) {
  switch (data.type) {
    case 'connected':
      connectionState.set(ConnectionState.CONNECTED);
      sessionId.set(data.payload.session_id);
      stats.set(data.payload.stats);
      break;

    case 'chat_response':
      isThinking.set(false);
      messages.update((msgs) => [
        ...msgs,
        {
          role: 'assistant',
          content: data.payload.message,
          transactions: data.payload.transactions || [],
          timestamp: data.payload.timestamp,
          llmStats: data.payload.llm_stats || null,
        },
      ]);
      break;

    case 'error':
      isThinking.set(false);
      error.set(data.payload.message);
      messages.update((msgs) => [
        ...msgs,
        {
          role: 'error',
          content: data.payload.message,
          code: data.payload.code,
          timestamp: new Date().toISOString(),
        },
      ]);
      break;

    case 'cancelled':
      isThinking.set(false);
      break;

    case 'pong':
      // Heartbeat response, ignore
      break;

    case 'cleared':
      // Server confirmed context cleared
      break;

    default:
      console.warn('Unknown message type:', data.type);
  }
}

/**
 * Send a chat message.
 */
export function sendMessage(text) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    error.set('Not connected');
    return;
  }

  if (!text.trim()) {
    return;
  }

  // Add user message to store
  messages.update((msgs) => [
    ...msgs,
    {
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    },
  ]);

  // Show thinking indicator
  isThinking.set(true);
  error.set(null);

  // Send to server
  ws.send(
    JSON.stringify({
      type: 'chat',
      payload: { message: text },
    })
  );
}

/**
 * Clear chat history and server context.
 */
export function clearMessages() {
  messages.set([]);
  // Also clear server-side context (conversation history, cached transactions)
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'clear' }));
  }
}

/**
 * Cancel an in-progress chat request.
 */
export function cancelMessage() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'cancel' }));
    isThinking.set(false);
  }
}

/**
 * Send ping to keep connection alive.
 */
export function ping() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping' }));
  }
}
