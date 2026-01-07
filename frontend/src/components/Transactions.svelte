<script>
  import { onMount } from 'svelte';
  import {
    getTransactions,
    searchTransactions,
    getCategories,
    getTransactionsByCategory,
  } from '../lib/api.js';
  import { formatCurrency, formatDate, filterCategory } from '../lib/stores.js';

  // Expanded vibrant color palette - 24 distinct colors
  const categoryColors = [
    { gradient: 'linear-gradient(135deg, #3b82f6, #1d4ed8)', shadow: '0 4px 14px rgba(59, 130, 246, 0.4)' },      // Blue
    { gradient: 'linear-gradient(135deg, #10b981, #059669)', shadow: '0 4px 14px rgba(16, 185, 129, 0.4)' },      // Emerald
    { gradient: 'linear-gradient(135deg, #f43f5e, #e11d48)', shadow: '0 4px 14px rgba(244, 63, 94, 0.4)' },       // Rose
    { gradient: 'linear-gradient(135deg, #f59e0b, #d97706)', shadow: '0 4px 14px rgba(245, 158, 11, 0.4)' },      // Amber
    { gradient: 'linear-gradient(135deg, #8b5cf6, #6d28d9)', shadow: '0 4px 14px rgba(139, 92, 246, 0.4)' },      // Violet
    { gradient: 'linear-gradient(135deg, #06b6d4, #0891b2)', shadow: '0 4px 14px rgba(6, 182, 212, 0.4)' },       // Cyan
    { gradient: 'linear-gradient(135deg, #ec4899, #db2777)', shadow: '0 4px 14px rgba(236, 72, 153, 0.4)' },      // Pink
    { gradient: 'linear-gradient(135deg, #84cc16, #65a30d)', shadow: '0 4px 14px rgba(132, 204, 22, 0.4)' },      // Lime
    { gradient: 'linear-gradient(135deg, #f97316, #ea580c)', shadow: '0 4px 14px rgba(249, 115, 22, 0.4)' },      // Orange
    { gradient: 'linear-gradient(135deg, #6366f1, #4f46e5)', shadow: '0 4px 14px rgba(99, 102, 241, 0.4)' },      // Indigo
    { gradient: 'linear-gradient(135deg, #14b8a6, #0d9488)', shadow: '0 4px 14px rgba(20, 184, 166, 0.4)' },      // Teal
    { gradient: 'linear-gradient(135deg, #d946ef, #a21caf)', shadow: '0 4px 14px rgba(217, 70, 239, 0.4)' },      // Fuchsia
    { gradient: 'linear-gradient(135deg, #ef4444, #dc2626)', shadow: '0 4px 14px rgba(239, 68, 68, 0.4)' },       // Red
    { gradient: 'linear-gradient(135deg, #22c55e, #16a34a)', shadow: '0 4px 14px rgba(34, 197, 94, 0.4)' },       // Green
    { gradient: 'linear-gradient(135deg, #a855f7, #9333ea)', shadow: '0 4px 14px rgba(168, 85, 247, 0.4)' },      // Purple
    { gradient: 'linear-gradient(135deg, #eab308, #ca8a04)', shadow: '0 4px 14px rgba(234, 179, 8, 0.4)' },       // Yellow
    { gradient: 'linear-gradient(135deg, #0ea5e9, #0284c7)', shadow: '0 4px 14px rgba(14, 165, 233, 0.4)' },      // Sky
    { gradient: 'linear-gradient(135deg, #f472b6, #ec4899)', shadow: '0 4px 14px rgba(244, 114, 182, 0.4)' },     // Pink light
    { gradient: 'linear-gradient(135deg, #2dd4bf, #14b8a6)', shadow: '0 4px 14px rgba(45, 212, 191, 0.4)' },      // Teal light
    { gradient: 'linear-gradient(135deg, #818cf8, #6366f1)', shadow: '0 4px 14px rgba(129, 140, 248, 0.4)' },     // Indigo light
    { gradient: 'linear-gradient(135deg, #fb923c, #f97316)', shadow: '0 4px 14px rgba(251, 146, 60, 0.4)' },      // Orange light
    { gradient: 'linear-gradient(135deg, #4ade80, #22c55e)', shadow: '0 4px 14px rgba(74, 222, 128, 0.4)' },      // Green light
    { gradient: 'linear-gradient(135deg, #c084fc, #a855f7)', shadow: '0 4px 14px rgba(192, 132, 252, 0.4)' },     // Purple light
    { gradient: 'linear-gradient(135deg, #38bdf8, #0ea5e9)', shadow: '0 4px 14px rgba(56, 189, 248, 0.4)' },      // Sky light
  ];

  // Color assignment map - built from sorted categories for consistency
  let categoryColorMap = new Map();

  function buildColorMap(categoryList) {
    categoryColorMap = new Map();
    const sorted = [...categoryList].sort();
    sorted.forEach((cat, index) => {
      categoryColorMap.set(cat, index % categoryColors.length);
    });
  }

  function getCategoryStyle(category) {
    if (!category) {
      return { background: '#4b5563', boxShadow: 'none' };
    }

    // Fallback if category not in map yet
    if (!categoryColorMap.has(category)) {
      categoryColorMap.set(category, categoryColorMap.size % categoryColors.length);
    }

    const color = categoryColors[categoryColorMap.get(category)];
    return { background: color.gradient, boxShadow: color.shadow };
  }

  function formatCategoryName(category) {
    if (!category) return 'Uncategorized';
    return category
      .replace(/_/g, ' ')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }

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
    await loadCategories();

    // Check if there's a filter from Dashboard navigation
    const initialFilter = $filterCategory;
    if (initialFilter) {
      selectedCategory = initialFilter;
      filterCategory.set(''); // Clear the store
      await handleCategoryChange();
    } else {
      await loadTransactions();
    }
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
      buildColorMap(categories);
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

  function filterByCategory(category) {
    if (category) {
      selectedCategory = category;
      handleCategoryChange();
    }
  }

  function clearFilter() {
    selectedCategory = '';
    handleCategoryChange();
  }

  async function goToPage(page) {
    if (page < 0 || page >= totalPages) return;
    currentPage = page;
    if (!searchQuery && !selectedCategory) {
      await loadTransactions();
    }
  }
</script>

<div class="p-6 h-full overflow-y-auto">
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

  <!-- Active filter indicator -->
  {#if selectedCategory}
    <div class="flex items-center gap-2 mb-4">
      <span class="text-sm text-gray-500 dark:text-gray-400">Filtered by:</span>
      <button
        class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium text-white cursor-pointer transition-all hover:scale-105"
        style="background: {getCategoryStyle(selectedCategory).background}; box-shadow: {getCategoryStyle(selectedCategory).boxShadow};"
        on:click={clearFilter}
      >
        {formatCategoryName(selectedCategory)}
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  {/if}

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
                <td class="px-4 py-3 text-sm">
                  <button
                    class="category-badge"
                    style="background: {getCategoryStyle(tx.category).background}; box-shadow: {getCategoryStyle(tx.category).boxShadow};"
                    on:click={() => filterByCategory(tx.category)}
                    title="View all {formatCategoryName(tx.category)} transactions"
                  >
                    {formatCategoryName(tx.category)}
                  </button>
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

<style>
  .category-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.375rem 0.875rem;
    border-radius: 9999px;
    font-size: 0.7rem;
    font-weight: 700;
    color: white;
    letter-spacing: 0.05em;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.15);
    backdrop-filter: blur(4px);
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    white-space: nowrap;
    cursor: pointer;
  }

  .category-badge:hover {
    transform: translateY(-2px) scale(1.05);
    filter: brightness(1.1);
    border-color: rgba(255, 255, 255, 0.3);
  }

  .category-badge:active {
    transform: translateY(0) scale(0.98);
  }
</style>
