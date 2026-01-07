<script>
  import { onMount, afterUpdate } from 'svelte';
  import {
    connect,
    disconnect,
    sendMessage,
    clearMessages,
    messages,
    isConnected,
    isThinking,
    connectionState,
    ConnectionState,
    error,
  } from '../lib/websocket.js';
  import ChatMessage from './ChatMessage.svelte';

  let inputText = '';
  let messagesContainer;

  onMount(() => {
    connect();
    return () => disconnect();
  });

  // Auto-scroll to bottom on new messages
  afterUpdate(() => {
    if (messagesContainer) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
  });

  function handleSubmit(event) {
    event.preventDefault();
    if (inputText.trim() && $isConnected && !$isThinking) {
      sendMessage(inputText);
      inputText = '';
    }
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      handleSubmit(event);
    }
  }
</script>

<div class="flex flex-col h-full">
  <!-- Header -->
  <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
    <h1 class="text-lg font-semibold text-gray-800 dark:text-gray-100">Chat</h1>
    <div class="flex items-center gap-3">
      <!-- Connection status -->
      <div class="flex items-center gap-2 text-sm">
        <div
          class="w-2 h-2 rounded-full {$connectionState === ConnectionState.CONNECTED
            ? 'bg-green-500'
            : $connectionState === ConnectionState.CONNECTING
              ? 'bg-yellow-500 animate-pulse'
              : 'bg-red-500'}"
        ></div>
        <span class="text-gray-500 dark:text-gray-400">
          {$connectionState === ConnectionState.CONNECTED
            ? 'Connected'
            : $connectionState === ConnectionState.CONNECTING
              ? 'Connecting...'
              : 'Disconnected'}
        </span>
      </div>

      <!-- Clear button -->
      {#if $messages.length > 0}
        <button
          class="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          on:click={clearMessages}
        >
          Clear
        </button>
      {/if}
    </div>
  </div>

  <!-- Messages -->
  <div
    bind:this={messagesContainer}
    class="flex-1 overflow-y-auto p-4 bg-gray-50 dark:bg-gray-900"
  >
    {#if $messages.length === 0}
      <div class="flex flex-col items-center justify-center h-full text-gray-500 dark:text-gray-400">
        <svg class="w-16 h-16 mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="1.5"
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          />
        </svg>
        <p class="text-lg font-medium">Ask me about your transactions</p>
        <p class="text-sm mt-1">Try "How much did I spend on groceries last month?"</p>
      </div>
    {:else}
      {#each $messages as message}
        <ChatMessage {message} />
      {/each}

      <!-- Thinking indicator -->
      {#if $isThinking}
        <div class="flex justify-start mb-4">
          <div class="bg-white dark:bg-gray-800 rounded-lg px-4 py-3 shadow">
            <div class="flex items-center gap-2">
              <div class="flex gap-1">
                <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0ms"></div>
                <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 150ms"></div>
                <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 300ms"></div>
              </div>
              <span class="text-sm text-gray-500 dark:text-gray-400">Thinking...</span>
            </div>
          </div>
        </div>
      {/if}
    {/if}
  </div>

  <!-- Error banner -->
  {#if $error}
    <div class="px-4 py-2 bg-red-50 dark:bg-red-900/20 border-t border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 text-sm">
      {$error}
    </div>
  {/if}

  <!-- Input -->
  <form
    on:submit={handleSubmit}
    class="p-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800"
  >
    <div class="flex gap-3">
      <input
        type="text"
        bind:value={inputText}
        on:keydown={handleKeyDown}
        placeholder={$isConnected ? 'Type your question...' : 'Connecting...'}
        disabled={!$isConnected || $isThinking}
        class="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
      />
      <button
        type="submit"
        disabled={!$isConnected || $isThinking || !inputText.trim()}
        class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        Send
      </button>
    </div>
  </form>
</div>
