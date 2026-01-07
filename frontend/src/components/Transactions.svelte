<script>
  import { onMount } from 'svelte';
  import {
    getTransactions,
    searchTransactions,
    getCategories,
    getTransactionsByCategory,
  } from '../lib/api.js';
  import { formatCurrency, formatDate } from '../lib/stores.js';

  let transactions = [];
  let total = 0;
  let loading = true;
  let error = null;

  let searchQuery = '';
  let searchTimeout;

  let categories = [];
  let selectedCategory = '';

  const PAGE_SIZE = 20;
  let currentPage = 0;

  $: totalPages = Math.ceil(total / PAGE_SIZE);
  $: canGoBack = currentPage > 0;
  $: canGoForward = currentPage < totalPages - 1;

  onMount(async () => {
    await Promise.all([loadTransactions(), loadCategories()]);
  });

  async function loadTransactions() {
    loading = true;
    error = null;
    try {
      const result = await getTransactions(PAGE_SIZE, currentPage * PAGE_SIZE);
      transactions = result.transactions;
      total = result.total;
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  async function loadCategories() {
    try {
      const result = await getCategories();
      categories = result.categories;
    } catch (err) {
      console.error('Failed to load categories:', err);
    }
  }

  async function handleSearch() {
    if (!searchQuery.trim()) {
      selectedCategory = '';
      currentPage = 0;
      await loadTransactions();
      return;
    }

    loading = true;
    error = null;
    try {
      const result = await searchTransactions(searchQuery);
      transactions = result.transactions;
      total = result.count;
      currentPage = 0;
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  function handleSearchInput() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(handleSearch, 300);
  }

  async function handleCategoryChange() {
    searchQuery = '';
    currentPage = 0;

    if (!selectedCategory) {
      await loadTransactions();
      return;
    }

    loading = true;
    error = null;
    try {
      const result = await getTransactionsByCategory(selectedCategory);
      transactions = result.transactions;
      total = result.count;
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  async function goToPage(page) {
    if (page < 0 || page >= totalPages) return;
    currentPage = page;
    if (!searchQuery && !selectedCategory) {
      await loadTransactions();
    }
  }
</script>

<div class="p-6">
  <h1 class="text-2xl font-bold mb-6 text-gray-800 dark:text-gray-100">Transactions</h1>

  <!-- Filters -->
  <div class="flex flex-col sm:flex-row gap-4 mb-6">
    <!-- Search -->
    <div class="flex-1">
      <input
        type="text"
        bind:value={searchQuery}
        on:input={handleSearchInput}
        placeholder="Search transactions..."
        class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    </div>

    <!-- Category filter -->
    <select
      bind:value={selectedCategory}
      on:change={handleCategoryChange}
      class="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      <option value="">All Categories</option>
      {#each categories as category}
        <option value={category}>{category}</option>
      {/each}
    </select>
  </div>

  {#if loading}
    <div class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  {:else if error}
    <div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-700 dark:text-red-400">
      {error}
    </div>
  {:else}
    <!-- Results count -->
    <div class="text-sm text-gray-500 dark:text-gray-400 mb-4">
      Showing {transactions.length} of {total} transactions
    </div>

    <!-- Table -->
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-gray-50 dark:bg-gray-700">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Date
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Description
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Amount
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Category
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            {#each transactions as tx}
              <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
                  {formatDate(tx.date)}
                </td>
                <td class="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">
                  {tx.description}
                </td>
                <td class="px-4 py-3 text-sm text-right whitespace-nowrap font-medium {tx.transaction_type === 'debit' ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}">
                  {tx.transaction_type === 'debit' ? '-' : '+'}{formatCurrency(tx.amount)}
                </td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                  <span class="px-2 py-1 rounded-full text-xs bg-gray-100 dark:bg-gray-700">
                    {tx.category || 'uncategorized'}
                  </span>
                </td>
              </tr>
            {:else}
              <tr>
                <td colspan="4" class="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  No transactions found
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Pagination -->
    {#if totalPages > 1 && !searchQuery && !selectedCategory}
      <div class="flex items-center justify-between mt-4">
        <button
          on:click={() => goToPage(currentPage - 1)}
          disabled={!canGoBack}
          class="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Previous
        </button>
        <span class="text-sm text-gray-600 dark:text-gray-400">
          Page {currentPage + 1} of {totalPages}
        </span>
        <button
          on:click={() => goToPage(currentPage + 1)}
          disabled={!canGoForward}
          class="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    {/if}
  {/if}
</div>
