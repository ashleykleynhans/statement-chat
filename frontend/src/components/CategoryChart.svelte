<script>
  import { createEventDispatcher } from 'svelte';
  import { formatCurrency } from '../lib/stores.js';

  export let categories = [];

  const dispatch = createEventDispatcher();

  // Calculate max value for scaling
  $: maxDebit = Math.max(...categories.map((c) => c.total_debits || 0), 1);

  // Sort by total debits descending
  $: sortedCategories = [...categories]
    .filter((c) => c.total_debits > 0)
    .sort((a, b) => b.total_debits - a.total_debits);

  // Color palette matching Transactions.svelte
  const categoryColors = [
    { gradient: 'linear-gradient(135deg, #3b82f6, #1d4ed8)', shadow: '0 4px 14px rgba(59, 130, 246, 0.4)' },
    { gradient: 'linear-gradient(135deg, #10b981, #059669)', shadow: '0 4px 14px rgba(16, 185, 129, 0.4)' },
    { gradient: 'linear-gradient(135deg, #f43f5e, #e11d48)', shadow: '0 4px 14px rgba(244, 63, 94, 0.4)' },
    { gradient: 'linear-gradient(135deg, #f59e0b, #d97706)', shadow: '0 4px 14px rgba(245, 158, 11, 0.4)' },
    { gradient: 'linear-gradient(135deg, #8b5cf6, #6d28d9)', shadow: '0 4px 14px rgba(139, 92, 246, 0.4)' },
    { gradient: 'linear-gradient(135deg, #06b6d4, #0891b2)', shadow: '0 4px 14px rgba(6, 182, 212, 0.4)' },
    { gradient: 'linear-gradient(135deg, #ec4899, #db2777)', shadow: '0 4px 14px rgba(236, 72, 153, 0.4)' },
    { gradient: 'linear-gradient(135deg, #84cc16, #65a30d)', shadow: '0 4px 14px rgba(132, 204, 22, 0.4)' },
    { gradient: 'linear-gradient(135deg, #f97316, #ea580c)', shadow: '0 4px 14px rgba(249, 115, 22, 0.4)' },
    { gradient: 'linear-gradient(135deg, #6366f1, #4f46e5)', shadow: '0 4px 14px rgba(99, 102, 241, 0.4)' },
    { gradient: 'linear-gradient(135deg, #14b8a6, #0d9488)', shadow: '0 4px 14px rgba(20, 184, 166, 0.4)' },
    { gradient: 'linear-gradient(135deg, #d946ef, #a21caf)', shadow: '0 4px 14px rgba(217, 70, 239, 0.4)' },
    { gradient: 'linear-gradient(135deg, #ef4444, #dc2626)', shadow: '0 4px 14px rgba(239, 68, 68, 0.4)' },
    { gradient: 'linear-gradient(135deg, #22c55e, #16a34a)', shadow: '0 4px 14px rgba(34, 197, 94, 0.4)' },
    { gradient: 'linear-gradient(135deg, #a855f7, #9333ea)', shadow: '0 4px 14px rgba(168, 85, 247, 0.4)' },
    { gradient: 'linear-gradient(135deg, #eab308, #ca8a04)', shadow: '0 4px 14px rgba(234, 179, 8, 0.4)' },
    { gradient: 'linear-gradient(135deg, #0ea5e9, #0284c7)', shadow: '0 4px 14px rgba(14, 165, 233, 0.4)' },
    { gradient: 'linear-gradient(135deg, #f472b6, #ec4899)', shadow: '0 4px 14px rgba(244, 114, 182, 0.4)' },
    { gradient: 'linear-gradient(135deg, #2dd4bf, #14b8a6)', shadow: '0 4px 14px rgba(45, 212, 191, 0.4)' },
    { gradient: 'linear-gradient(135deg, #818cf8, #6366f1)', shadow: '0 4px 14px rgba(129, 140, 248, 0.4)' },
    { gradient: 'linear-gradient(135deg, #fb923c, #f97316)', shadow: '0 4px 14px rgba(251, 146, 60, 0.4)' },
    { gradient: 'linear-gradient(135deg, #4ade80, #22c55e)', shadow: '0 4px 14px rgba(74, 222, 128, 0.4)' },
    { gradient: 'linear-gradient(135deg, #c084fc, #a855f7)', shadow: '0 4px 14px rgba(192, 132, 252, 0.4)' },
    { gradient: 'linear-gradient(135deg, #38bdf8, #0ea5e9)', shadow: '0 4px 14px rgba(56, 189, 248, 0.4)' },
  ];

  let categoryColorMap = new Map();

  $: {
    categoryColorMap = new Map();
    const allCats = categories.map(c => c.category).filter(Boolean).sort();
    allCats.forEach((cat, index) => {
      categoryColorMap.set(cat, index % categoryColors.length);
    });
  }

  function getBarStyle(category) {
    if (!category) return { background: '#4b5563' };
    const index = categoryColorMap.get(category) ?? 0;
    return { background: categoryColors[index].gradient };
  }

  function formatCategoryName(category) {
    if (!category) return 'Uncategorized';
    return category
      .replace(/_/g, ' ')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }

  function handleClick(category) {
    dispatch('select', { category });
  }
</script>

<div class="space-y-2">
  {#each sortedCategories as category}
    {@const percentage = ((category.total_debits / maxDebit) * 100).toFixed(0)}
    <button
      class="w-full flex items-center gap-4 p-2 -mx-2 rounded-lg transition-all hover:bg-gray-100 dark:hover:bg-gray-700/50 cursor-pointer group"
      on:click={() => handleClick(category.category)}
      title="View {formatCategoryName(category.category)} transactions"
    >
      <div class="w-32 text-sm text-gray-600 dark:text-gray-400 truncate text-left group-hover:text-gray-900 dark:group-hover:text-gray-200 transition-colors">
        {formatCategoryName(category.category)}
      </div>
      <div class="flex-1 h-7 bg-gray-100 dark:bg-gray-700 rounded-lg overflow-hidden shadow-inner">
        <div
          class="h-full rounded-lg transition-all duration-300 group-hover:opacity-90"
          style="width: {percentage}%; background: {getBarStyle(category.category).background};"
        ></div>
      </div>
      <div class="w-28 text-sm text-right text-gray-700 dark:text-gray-300 font-medium">
        {formatCurrency(category.total_debits)}
      </div>
      <div class="w-16 text-xs text-right text-gray-500 dark:text-gray-400">
        ({category.count})
      </div>
      <svg class="w-4 h-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
      </svg>
    </button>
  {/each}

  {#if sortedCategories.length === 0}
    <p class="text-gray-500 dark:text-gray-400 text-center py-4">No spending data available</p>
  {/if}
</div>
