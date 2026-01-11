<script>
  import { onMount } from 'svelte';
  import {
    getTransactions,
    searchTransactions,
    getCategories,
    getTransactionsByCategory,
    getTransactionsByDateRange,
    getTransactionsByStatement,
    getStatements,
  } from '../lib/api.js';
  import { formatCurrency, formatDate, filterCategory, filterSource, currentPage } from '../lib/stores.js';

  // Generate unique color for each category using HSL
  // Uses golden angle to distribute hues evenly for any number of categories
  let categoryColorMap = new Map();

  function hslToRgb(h, s, l) {
    const c = (1 - Math.abs(2 * l - 1)) * s;
    const x = c * (1 - Math.abs((h / 60) % 2 - 1));
    const m = l - c / 2;
    let r, g, b;
    if (h < 60) { r = c; g = x; b = 0; }
    else if (h < 120) { r = x; g = c; b = 0; }
    else if (h < 180) { r = 0; g = c; b = x; }
    else if (h < 240) { r = 0; g = x; b = c; }
    else if (h < 300) { r = x; g = 0; b = c; }
    else { r = c; g = 0; b = x; }
    return [Math.round((r + m) * 255), Math.round((g + m) * 255), Math.round((b + m) * 255)];
  }

  function generateCategoryColor(index, total) {
    // Use golden angle (137.5°) for optimal color distribution
    const goldenAngle = 137.508;
    const hue = (index * goldenAngle) % 360;
    const saturation = 0.7;
    const lightness = 0.5;

    const [r1, g1, b1] = hslToRgb(hue, saturation, lightness);
    const [r2, g2, b2] = hslToRgb(hue, saturation, lightness - 0.15);

    return {
      gradient: `linear-gradient(135deg, rgb(${r1},${g1},${b1}), rgb(${r2},${g2},${b2}))`,
      shadow: `0 4px 14px rgba(${r1},${g1},${b1}, 0.4)`
    };
  }

  function buildColorMap(categoryList) {
    categoryColorMap = new Map();
    const sorted = [...categoryList].sort();
    sorted.forEach((cat, index) => {
      categoryColorMap.set(cat, generateCategoryColor(index, sorted.length));
    });
  }

  function getCategoryStyle(category) {
    if (!category) {
      return { background: '#4b5563', boxShadow: 'none' };
    }

    // Fallback if category not in map yet
    if (!categoryColorMap.has(category)) {
      categoryColorMap.set(category, generateCategoryColor(categoryColorMap.size, categoryColorMap.size + 1));
    }

    const color = categoryColorMap.get(category);
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

  let statements = [];
  let selectedStatement = '';
  let selectedYear = '';
  let selectedMonth = '';

  // Generate available years and months from statements
  $: availableYears = [...new Set(statements.map(s => {
    const date = s.statement_date || '';
    return date.substring(0, 4);
  }).filter(y => y))].sort().reverse();

  $: availableMonths = selectedYear
    ? [...new Set(statements
        .filter(s => (s.statement_date || '').startsWith(selectedYear))
        .map(s => (s.statement_date || '').substring(5, 7))
      )].sort()
    : [];

  const monthNames = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  const PAGE_SIZE = 20;
  let pageNum = 0;
  let savedPageNum = 0;  // Remember page position before search/filter

  $: totalPages = Math.ceil(total / PAGE_SIZE);
  $: canGoBack = pageNum > 0;
  $: canGoForward = pageNum < totalPages - 1;

  // Generate visible page numbers for pagination
  // Shows: first, ..., pages around current, ..., last
  $: visiblePages = (() => {
    if (totalPages <= 7) {
      // Show all pages if 7 or fewer
      return Array.from({ length: totalPages }, (_, i) => i);
    }

    const pages = [];
    const current = pageNum;

    // Always show first page
    pages.push(0);

    // Calculate range around current page
    let rangeStart = Math.max(1, current - 2);
    let rangeEnd = Math.min(totalPages - 2, current + 2);

    // Adjust range to always show 5 middle pages when possible
    if (rangeEnd - rangeStart < 4) {
      if (rangeStart === 1) {
        rangeEnd = Math.min(totalPages - 2, rangeStart + 4);
      } else if (rangeEnd === totalPages - 2) {
        rangeStart = Math.max(1, rangeEnd - 4);
      }
    }

    // Add ellipsis or page after first
    if (rangeStart > 1) {
      pages.push('...');
    }

    // Add range pages
    for (let i = rangeStart; i <= rangeEnd; i++) {
      pages.push(i);
    }

    // Add ellipsis or page before last
    if (rangeEnd < totalPages - 2) {
      pages.push('...');
    }

    // Always show last page
    if (totalPages > 1) {
      pages.push(totalPages - 1);
    }

    return pages;
  })();

  onMount(async () => {
    await Promise.all([loadCategories(), loadStatements()]);

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

  async function loadStatements() {
    try {
      const result = await getStatements();
      statements = result.statements || [];
    } catch (err) {
      console.error('Failed to load statements:', err);
    }
  }

  async function loadTransactions() {
    loading = true;
    error = null;
    try {
      const result = await getTransactions(PAGE_SIZE, pageNum * PAGE_SIZE);
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
      // Clearing search - restore previous page position
      selectedCategory = '';
      pageNum = savedPageNum;
      await loadTransactions();
      return;
    }

    // Save current page position before searching (only if not already searching)
    if (!hasActiveFilter()) {
      savedPageNum = pageNum;
    }

    loading = true;
    error = null;
    try {
      const result = await searchTransactions(searchQuery);
      transactions = result.transactions;
      total = result.count;
      pageNum = 0;
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
    pageNum = 0;

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
      selectedStatement = '';
      selectedYear = '';
      selectedMonth = '';
      filterSource.set('transactions');
      handleCategoryChange();
    }
  }

  function filterByStatement(statementNumber) {
    if (statementNumber) {
      selectedStatement = statementNumber;
      selectedCategory = '';
      selectedYear = '';
      selectedMonth = '';
      searchQuery = '';
      filterSource.set('transactions');
      handleStatementChange();
    }
  }

  async function handleStatementChange() {
    searchQuery = '';
    selectedCategory = '';
    selectedYear = '';
    selectedMonth = '';
    pageNum = 0;

    if (!selectedStatement) {
      await loadTransactions();
      return;
    }

    loading = true;
    error = null;
    try {
      const result = await getTransactionsByStatement(selectedStatement);
      transactions = result.transactions;
      total = result.count;
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  async function handleYearChange() {
    selectedMonth = '';
    selectedStatement = '';
    selectedCategory = '';
    searchQuery = '';
    pageNum = 0;

    if (!selectedYear) {
      await loadTransactions();
      return;
    }

    // Filter by full year
    loading = true;
    error = null;
    try {
      const start = `${selectedYear}-01-01`;
      const end = `${selectedYear}-12-31`;
      const result = await getTransactionsByDateRange(start, end);
      transactions = result.transactions;
      total = result.count;
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  async function handleMonthChange() {
    selectedStatement = '';
    selectedCategory = '';
    searchQuery = '';
    pageNum = 0;

    if (!selectedMonth || !selectedYear) {
      return;
    }

    loading = true;
    error = null;
    try {
      const lastDay = new Date(parseInt(selectedYear), parseInt(selectedMonth), 0).getDate();
      const start = `${selectedYear}-${selectedMonth}-01`;
      const end = `${selectedYear}-${selectedMonth}-${lastDay.toString().padStart(2, '0')}`;
      const result = await getTransactionsByDateRange(start, end);
      transactions = result.transactions;
      total = result.count;
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  function clearFilter() {
    const source = $filterSource;
    selectedCategory = '';
    selectedStatement = '';
    selectedYear = '';
    selectedMonth = '';
    filterSource.set('');

    if (source && source !== 'transactions') {
      currentPage.set(source);
    } else {
      loadTransactions();
    }
  }

  function hasActiveFilter() {
    return selectedCategory || selectedStatement || selectedYear;
  }

  async function goToPage(page) {
    if (page < 0 || page >= totalPages) return;
    pageNum = page;
    if (!searchQuery && !selectedCategory) {
      await loadTransactions();
    }
  }

  let jumpToPage = '';

  function handleJumpToPage() {
    const page = parseInt(jumpToPage, 10);
    if (!isNaN(page) && page >= 1 && page <= totalPages) {
      goToPage(page - 1);  // Convert to 0-indexed
      jumpToPage = '';
    }
  }

  function handleJumpKeydown(event) {
    if (event.key === 'Enter') {
      handleJumpToPage();
    }
  }
</script>

<div class="p-6 h-full overflow-y-auto">
  <h1 class="text-2xl font-bold mb-6 text-gray-800 dark:text-gray-100">Transactions</h1>

  <!-- Filters -->
  <div class="flex flex-col gap-4 mb-6">
    <!-- Row 1: Search and Category -->
    <div class="flex flex-col sm:flex-row gap-4">
      <!-- Search -->
      <div class="flex-1 relative">
        <input
          type="text"
          bind:value={searchQuery}
          on:input={handleSearchInput}
          placeholder="Search transactions..."
          class="w-full px-4 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {#if searchQuery}
          <button
            on:click={() => { searchQuery = ''; handleSearch(); }}
            class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            title="Clear search and return to previous page"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        {/if}
      </div>

      <!-- Category filter -->
      <select
        bind:value={selectedCategory}
        on:change={handleCategoryChange}
        class="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        <option value="">All Categories</option>
        {#each categories as category}
          <option value={category}>{formatCategoryName(category)}</option>
        {/each}
      </select>
    </div>

    <!-- Row 2: Year, Month, Statement filters -->
    <div class="flex flex-col sm:flex-row gap-4">
      <!-- Year filter -->
      <select
        bind:value={selectedYear}
        on:change={handleYearChange}
        class="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        <option value="">All Years</option>
        {#each availableYears as year}
          <option value={year}>{year}</option>
        {/each}
      </select>

      <!-- Month filter -->
      <select
        bind:value={selectedMonth}
        on:change={handleMonthChange}
        disabled={!selectedYear}
        class="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
      >
        <option value="">All Months</option>
        {#each availableMonths as month}
          <option value={month}>{monthNames[parseInt(month)]}</option>
        {/each}
      </select>

      <!-- Statement filter -->
      <select
        bind:value={selectedStatement}
        on:change={handleStatementChange}
        class="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        <option value="">All Statements</option>
        {#each statements as stmt}
          <option value={stmt.statement_number}>#{stmt.statement_number} ({stmt.statement_date || 'Unknown'})</option>
        {/each}
      </select>
    </div>
  </div>

  <!-- Active filter indicator -->
  {#if hasActiveFilter()}
    <div class="flex items-center gap-2 mb-4 flex-wrap">
      <span class="text-sm text-gray-500 dark:text-gray-400">Filtered by:</span>
      {#if selectedCategory}
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
      {/if}
      {#if selectedStatement}
        <button
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium text-white cursor-pointer transition-all hover:scale-105 bg-indigo-600"
          on:click={clearFilter}
        >
          Statement #{selectedStatement}
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      {/if}
      {#if selectedYear}
        <button
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium text-white cursor-pointer transition-all hover:scale-105 bg-emerald-600"
          on:click={clearFilter}
        >
          {selectedYear}{selectedMonth ? ` ${monthNames[parseInt(selectedMonth)]}` : ''}
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      {/if}
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
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Stmt
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
                <td class="px-4 py-3 text-sm text-center whitespace-nowrap">
                  {#if tx.statement_number}
                    <button
                      class="text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
                      on:click={() => filterByStatement(tx.statement_number)}
                      title="View all transactions from statement #{tx.statement_number}"
                    >
                      #{tx.statement_number}
                    </button>
                  {:else}
                    <span class="text-gray-500 dark:text-gray-500">-</span>
                  {/if}
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
                <td colspan="5" class="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  No transactions found
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Pagination -->
    {#if totalPages > 1 && !searchQuery && !hasActiveFilter()}
      <div class="flex flex-col sm:flex-row items-center justify-between mt-4 gap-3">
        <div class="flex items-center gap-2 order-2 sm:order-1">
          <span class="text-sm text-gray-600 dark:text-gray-400">
            Page {pageNum + 1} of {totalPages}
          </span>
          <!-- Jump to page -->
          <div class="flex items-center gap-1">
            <input
              type="number"
              bind:value={jumpToPage}
              on:keydown={handleJumpKeydown}
              placeholder="#"
              min="1"
              max={totalPages}
              class="w-14 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              on:click={handleJumpToPage}
              class="px-2 py-1 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
              title="Go to page"
            >
              Go
            </button>
          </div>
        </div>

        <div class="flex items-center gap-1 order-1 sm:order-2">
          <!-- First page -->
          <button
            on:click={() => goToPage(0)}
            disabled={!canGoBack}
            class="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            title="First page"
          >
            ««
          </button>

          <!-- Previous page -->
          <button
            on:click={() => goToPage(pageNum - 1)}
            disabled={!canGoBack}
            class="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Previous page"
          >
            «
          </button>

          <!-- Page numbers -->
          {#each visiblePages as page}
            {#if page === '...'}
              <span class="px-2 py-1.5 text-sm text-gray-400 dark:text-gray-500">...</span>
            {:else}
              <button
                on:click={() => goToPage(page)}
                class="px-3 py-1.5 text-sm border rounded-lg transition-colors
                  {page === pageNum
                    ? 'bg-blue-500 text-white border-blue-500'
                    : 'border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'}"
              >
                {page + 1}
              </button>
            {/if}
          {/each}

          <!-- Next page -->
          <button
            on:click={() => goToPage(pageNum + 1)}
            disabled={!canGoForward}
            class="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Next page"
          >
            »
          </button>

          <!-- Last page -->
          <button
            on:click={() => goToPage(totalPages - 1)}
            disabled={!canGoForward}
            class="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Last page"
          >
            »»
          </button>
        </div>
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
