<script>
  import { onMount } from 'svelte';
  import { getStats, getCategorySummary } from '../lib/api.js';
  import { formatCurrency, currentPage, filterCategory } from '../lib/stores.js';
  import CategoryChart from './CategoryChart.svelte';

  let stats = null;
  let categorySummary = null;
  let loading = true;
  let error = null;

  onMount(async () => {
    try {
      [stats, categorySummary] = await Promise.all([
        getStats(),
        getCategorySummary(),
      ]);
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  });

  function handleCategorySelect(event) {
    const { category } = event.detail;
    filterCategory.set(category);
    currentPage.set('transactions');
  }
</script>

<div class="p-6 h-full overflow-y-auto">
  <h1 class="text-2xl font-bold mb-6 text-gray-800 dark:text-gray-100">Dashboard</h1>

  {#if loading}
    <div class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  {:else if error}
    <div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-700 dark:text-red-400">
      {error}
    </div>
  {:else}
    <!-- Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">Total Transactions</div>
        <div class="text-2xl font-bold text-gray-900 dark:text-gray-100">
          {stats?.total_transactions?.toLocaleString() || 0}
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">Statements Imported</div>
        <div class="text-2xl font-bold text-gray-900 dark:text-gray-100">
          {stats?.total_statements?.toLocaleString() || 0}
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">Total Debits</div>
        <div class="text-2xl font-bold text-red-600 dark:text-red-400">
          {formatCurrency(stats?.total_debits || 0)}
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">Total Credits</div>
        <div class="text-2xl font-bold text-green-600 dark:text-green-400">
          {formatCurrency(stats?.total_credits || 0)}
        </div>
      </div>
    </div>

    <!-- Category Chart -->
    {#if categorySummary?.categories?.length > 0}
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 class="text-lg font-semibold mb-4 text-gray-800 dark:text-gray-100">Spending by Category</h2>
        <CategoryChart categories={categorySummary.categories} on:select={handleCategorySelect} />
      </div>
    {/if}
  {/if}
</div>
