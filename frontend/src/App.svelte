<script>
  import { currentPage } from './lib/stores.js';
  import Chat from './components/Chat.svelte';
  import Dashboard from './components/Dashboard.svelte';
  import Transactions from './components/Transactions.svelte';

  const navItems = [
    { id: 'chat', label: 'Chat', icon: 'chat' },
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'transactions', label: 'Transactions', icon: 'list' },
  ];

  function setPage(page) {
    currentPage.set(page);
  }
</script>

<div class="flex h-screen bg-gray-50 dark:bg-gray-900">
  <!-- Sidebar -->
  <aside class="w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col">
    <!-- Logo -->
    <div class="p-4 border-b border-gray-200 dark:border-gray-700">
      <h1 class="text-xl font-bold text-gray-800 dark:text-gray-100">Statement Chat</h1>
      <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">Bank Statement Assistant</p>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 p-4">
      <ul class="space-y-1">
        {#each navItems as item}
          <li>
            <button
              on:click={() => setPage(item.id)}
              class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors
                {$currentPage === item.id
                  ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}"
            >
              <!-- Icons -->
              {#if item.icon === 'chat'}
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              {:else if item.icon === 'dashboard'}
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                </svg>
              {:else if item.icon === 'list'}
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                </svg>
              {/if}
              <span class="font-medium">{item.label}</span>
            </button>
          </li>
        {/each}
      </ul>
    </nav>

    <!-- Footer -->
    <div class="p-4 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-400 dark:text-gray-500">
      Powered by Ollama
    </div>
  </aside>

  <!-- Main Content -->
  <main class="flex-1 overflow-hidden">
    {#if $currentPage === 'chat'}
      <Chat />
    {:else if $currentPage === 'dashboard'}
      <Dashboard />
    {:else if $currentPage === 'transactions'}
      <Transactions />
    {/if}
  </main>
</div>
