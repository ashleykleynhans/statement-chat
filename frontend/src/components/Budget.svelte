<script>
  import { onMount } from 'svelte';
  import { getBudgets, getBudgetSummary, createBudget, updateBudget, deleteBudget, getCategories, exportBudgets, importBudgets, deleteAllBudgets } from '../lib/api.js';
  import { formatCurrency } from '../lib/stores.js';

  let budgets = [];
  let budgetSummary = null;
  let categories = [];
  let loading = true;
  let error = null;
  let saving = false;

  // Form state
  let selectedCategory = '';
  let budgetAmount = '';

  // Edit state
  let editingCategory = null;
  let editAmount = '';

  // Import/export state
  let importing = false;
  let exporting = false;
  let clearing = false;
  let fileInput;

  onMount(async () => {
    await loadData();
  });

  async function loadData() {
    loading = true;
    error = null;
    try {
      const [budgetsData, summaryData, categoriesData] = await Promise.all([
        getBudgets(),
        getBudgetSummary(),
        getCategories()
      ]);
      budgets = budgetsData.budgets || [];
      budgetSummary = summaryData;
      categories = categoriesData.categories || [];
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  async function handleSubmit() {
    if (!selectedCategory || !budgetAmount) return;

    saving = true;
    error = null;

    try {
      await createBudget(selectedCategory, parseFloat(budgetAmount));
      selectedCategory = '';
      budgetAmount = '';
      await loadData();
    } catch (err) {
      error = err.message;
    } finally {
      saving = false;
    }
  }

  async function handleDelete(category) {
    if (!confirm(`Delete budget for ${formatCategoryName(category)}?`)) return;

    try {
      await deleteBudget(category);
      await loadData();
    } catch (err) {
      error = err.message;
    }
  }

  function startEdit(category, currentAmount) {
    editingCategory = category;
    editAmount = currentAmount.toString();
  }

  function cancelEdit() {
    editingCategory = null;
    editAmount = '';
  }

  async function handleEdit() {
    if (!editingCategory || !editAmount) return;

    saving = true;
    error = null;

    try {
      await updateBudget(editingCategory, parseFloat(editAmount));
      editingCategory = null;
      editAmount = '';
      await loadData();
    } catch (err) {
      error = err.message;
    } finally {
      saving = false;
    }
  }

  function formatCategoryName(category) {
    if (!category) return 'Uncategorized';
    return category
      .replace(/_/g, ' ')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }

  function getProgressColor(percentage) {
    if (percentage >= 100) return 'bg-red-500';
    if (percentage >= 80) return 'bg-yellow-500';
    return 'bg-green-500';
  }

  function getProgressTextColor(percentage) {
    if (percentage >= 100) return 'text-red-600 dark:text-red-400';
    if (percentage >= 80) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-green-600 dark:text-green-400';
  }

  async function handleExport() {
    exporting = true;
    error = null;

    try {
      const data = await exportBudgets();
      const json = JSON.stringify(data.budgets, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'budgets.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      error = err.message;
    } finally {
      exporting = false;
    }
  }

  function triggerImport() {
    fileInput.click();
  }

  async function handleImport(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    importing = true;
    error = null;

    try {
      const text = await file.text();
      let budgetsToImport;

      try {
        const parsed = JSON.parse(text);
        // Handle both array format and {budgets: [...]} format
        budgetsToImport = Array.isArray(parsed) ? parsed : parsed.budgets;
      } catch {
        throw new Error('Invalid JSON file');
      }

      if (!Array.isArray(budgetsToImport)) {
        throw new Error('Invalid budget format: expected array of budgets');
      }

      // Validate structure
      for (const budget of budgetsToImport) {
        if (!budget.category || typeof budget.amount !== 'number') {
          throw new Error('Invalid budget entry: each budget must have "category" and "amount"');
        }
      }

      if (!confirm(`Import ${budgetsToImport.length} budget(s)? This will replace all existing budgets.`)) {
        return;
      }

      const result = await importBudgets(budgetsToImport);
      await loadData();
      alert(`Imported ${result.imported} budget(s). ${result.deleted > 0 ? `Replaced ${result.deleted} existing budget(s).` : ''}`);
    } catch (err) {
      error = err.message;
    } finally {
      importing = false;
      // Reset file input so the same file can be selected again
      event.target.value = '';
    }
  }

  async function handleClearAll() {
    if (!confirm(`Delete all ${budgets.length} budget(s)? This cannot be undone.`)) return;

    clearing = true;
    error = null;

    try {
      const result = await deleteAllBudgets();
      await loadData();
    } catch (err) {
      error = err.message;
    } finally {
      clearing = false;
    }
  }

  // Categories that don't have budgets yet
  $: availableCategories = categories.filter(
    cat => !budgets.find(b => b.category === cat)
  );

  // Pre-populate amount when selecting an existing budget to update
  $: {
    const existingBudget = budgets.find(b => b.category === selectedCategory);
    if (existingBudget) {
      budgetAmount = existingBudget.amount.toString();
    }
  }
</script>

<div class="p-6 h-full overflow-y-auto">
  <div class="flex justify-between items-center mb-6">
    <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Budget</h1>
    <div class="flex gap-2">
      <!-- Hidden file input for import -->
      <input
        type="file"
        accept=".json"
        bind:this={fileInput}
        on:change={handleImport}
        class="hidden"
      />
      <button
        on:click={triggerImport}
        disabled={importing}
        class="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors disabled:opacity-50"
        title="Import budgets from JSON file"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
        </svg>
        {importing ? 'Importing...' : 'Import'}
      </button>
      <button
        on:click={handleExport}
        disabled={exporting || budgets.length === 0}
        class="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors disabled:opacity-50"
        title="Export budgets to JSON file"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
        {exporting ? 'Exporting...' : 'Export'}
      </button>
      <button
        on:click={handleClearAll}
        disabled={clearing || budgets.length === 0}
        class="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-red-100 dark:bg-red-900/30 hover:bg-red-200 dark:hover:bg-red-900/50 text-red-700 dark:text-red-400 rounded-lg transition-colors disabled:opacity-50"
        title="Delete all budgets"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
        {clearing ? 'Clearing...' : 'Clear All'}
      </button>
    </div>
  </div>

  {#if error}
    <div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-700 dark:text-red-400 mb-6">
      {error}
    </div>
  {/if}

  <!-- Add Budget Form -->
  <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mb-6">
    <h2 class="text-lg font-semibold mb-4 text-gray-800 dark:text-gray-100">Add Budget</h2>
    <form on:submit|preventDefault={handleSubmit} class="flex flex-col sm:flex-row gap-4">
      <select
        bind:value={selectedCategory}
        class="flex-1 px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        disabled={saving}
      >
        <option value="">Select category...</option>
        {#each availableCategories as category}
          <option value={category}>{formatCategoryName(category)}</option>
        {/each}
        {#if budgets.length > 0}
          <optgroup label="Update existing">
            {#each budgets as budget}
              <option value={budget.category}>{formatCategoryName(budget.category)} (update)</option>
            {/each}
          </optgroup>
        {/if}
      </select>

      <div class="relative flex-1">
        <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 dark:text-gray-400">R</span>
        <input
          type="number"
          bind:value={budgetAmount}
          placeholder="Amount"
          min="0"
          step="100"
          class="w-full pl-8 pr-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          disabled={saving}
        />
      </div>

      <button
        type="submit"
        class="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        disabled={saving || !selectedCategory || !budgetAmount}
      >
        {saving ? 'Saving...' : budgets.find(b => b.category === selectedCategory) ? 'Update' : 'Add'}
      </button>
      {#if selectedCategory}
        <button
          type="button"
          on:click={() => { selectedCategory = ''; budgetAmount = ''; }}
          class="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 font-medium transition-colors"
        >
          Cancel
        </button>
      {/if}
    </form>
  </div>

  {#if loading}
    <div class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  {:else if budgetSummary && budgetSummary.items.length > 0}
    <!-- Budget Summary -->
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mb-6">
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100">Budget Overview</h2>
        <div class="text-sm text-gray-500 dark:text-gray-400">
          Latest statement
        </div>
      </div>

      <!-- Totals -->
      <div class="grid grid-cols-3 gap-4 mb-6 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
        <div>
          <div class="text-sm text-gray-500 dark:text-gray-400">Total Budgeted</div>
          <div class="text-xl font-bold text-gray-900 dark:text-gray-100">
            {formatCurrency(budgetSummary.total_budgeted)}
          </div>
        </div>
        <div>
          <div class="text-sm text-gray-500 dark:text-gray-400">Total Spent</div>
          <div class="text-xl font-bold {getProgressTextColor((budgetSummary.total_spent / budgetSummary.total_budgeted) * 100)}">
            {formatCurrency(budgetSummary.total_spent)}
          </div>
        </div>
        <div>
          <div class="text-sm text-gray-500 dark:text-gray-400">Total Available</div>
          <div class="text-xl font-bold {budgetSummary.total_budgeted - budgetSummary.total_spent >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">
            {formatCurrency(budgetSummary.total_budgeted - budgetSummary.total_spent)}
          </div>
        </div>
      </div>

      <!-- Budget Items -->
      <div class="space-y-4">
        {#each budgetSummary.items as item}
          <div class="group">
            <div class="flex justify-between items-center mb-1">
              <span class="text-sm font-medium text-gray-700 dark:text-gray-300">
                {formatCategoryName(item.category)}
              </span>
              <div class="flex items-center gap-3">
                {#if editingCategory === item.category}
                  <form on:submit|preventDefault={handleEdit} class="flex items-center gap-2">
                    <div class="relative">
                      <span class="absolute left-2 top-1/2 -translate-y-1/2 text-gray-500 dark:text-gray-400 text-xs">R</span>
                      <input
                        type="number"
                        bind:value={editAmount}
                        min="0"
                        step="100"
                        class="w-24 pl-5 pr-2 py-1 text-sm bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
                        disabled={saving}
                      />
                    </div>
                    <button
                      type="submit"
                      class="text-green-600 hover:text-green-700 dark:text-green-400 dark:hover:text-green-300"
                      title="Save"
                      disabled={saving}
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      on:click={cancelEdit}
                      class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                      title="Cancel"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </form>
                {:else}
                  <span class="text-sm {getProgressTextColor(item.percentage)}">
                    {formatCurrency(item.actual)} / {formatCurrency(item.budget)}
                  </span>
                  <button
                    on:click={() => startEdit(item.category, item.budget)}
                    class="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-blue-500 transition-all"
                    title="Edit budget"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </button>
                  <button
                    on:click={() => handleDelete(item.category)}
                    class="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-all"
                    title="Delete budget"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                {/if}
              </div>
            </div>
            <div class="relative h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                class="{getProgressColor(item.percentage)} h-full rounded-full transition-all duration-500"
                style="width: {Math.min(item.percentage, 100)}%"
              ></div>
              {#if item.percentage > 100}
                <div
                  class="absolute top-0 right-0 h-full bg-red-300 dark:bg-red-700 opacity-50"
                  style="width: {Math.min(item.percentage - 100, 100)}%"
                ></div>
              {/if}
            </div>
            <div class="flex justify-between mt-1">
              <span class="text-xs text-gray-500 dark:text-gray-400">
                {item.percentage.toFixed(0)}% used
              </span>
              <span class="text-xs {item.remaining >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">
                {item.remaining >= 0 ? `${formatCurrency(item.remaining)} remaining` : `${formatCurrency(Math.abs(item.remaining))} over budget`}
              </span>
            </div>
          </div>
        {/each}
      </div>
    </div>
  {:else}
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 text-center text-gray-500 dark:text-gray-400">
      <p class="mb-2">No budgets set yet.</p>
      <p class="text-sm">Add a budget above to start tracking your spending.</p>
    </div>
  {/if}
</div>
