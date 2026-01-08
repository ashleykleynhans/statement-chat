<script>
  import { currentPage } from './lib/stores.js';
  import Chat from './components/Chat.svelte';
  import Dashboard from './components/Dashboard.svelte';
  import Transactions from './components/Transactions.svelte';
  import Analytics from './components/Analytics.svelte';
  import Budget from './components/Budget.svelte';

  const navItems = [
    { id: 'chat', label: 'Chat', icon: 'chat' },
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'analytics', label: 'Analytics', icon: 'chart' },
    { id: 'budget', label: 'Budget', icon: 'budget' },
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
      <h1 class="text-xl font-bold text-gray-800 dark:text-gray-100">BankBot</h1>
      <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">Your local finance assistant</p>
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
              {:else if item.icon === 'chart'}
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
                </svg>
              {:else if item.icon === 'budget'}
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
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
    {:else if $currentPage === 'analytics'}
      <Analytics />
    {:else if $currentPage === 'budget'}
      <Budget />
    {:else if $currentPage === 'transactions'}
      <Transactions />
    {/if}
  </main>
</div>
