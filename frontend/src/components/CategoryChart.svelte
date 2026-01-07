<script>
  import { formatCurrency } from '../lib/stores.js';

  export let categories = [];

  // Calculate max value for scaling
  $: maxDebit = Math.max(...categories.map((c) => c.total_debits || 0), 1);

  // Sort by total debits descending
  $: sortedCategories = [...categories]
    .filter((c) => c.total_debits > 0)
    .sort((a, b) => b.total_debits - a.total_debits);
</script>

<div class="space-y-3">
  {#each sortedCategories as category}
    {@const percentage = ((category.total_debits / maxDebit) * 100).toFixed(0)}
    <div class="flex items-center gap-4">
      <div class="w-32 text-sm text-gray-600 dark:text-gray-400 truncate" title={category.category || 'uncategorized'}>
        {category.category || 'uncategorized'}
      </div>
      <div class="flex-1 h-6 bg-gray-100 dark:bg-gray-700 rounded overflow-hidden">
        <div
          class="h-full bg-blue-500 dark:bg-blue-600 transition-all duration-300"
          style="width: {percentage}%"
        ></div>
      </div>
      <div class="w-28 text-sm text-right text-gray-700 dark:text-gray-300">
        {formatCurrency(category.total_debits)}
      </div>
      <div class="w-16 text-xs text-right text-gray-500 dark:text-gray-400">
        ({category.count})
      </div>
    </div>
  {/each}

  {#if sortedCategories.length === 0}
    <p class="text-gray-500 dark:text-gray-400 text-center py-4">No spending data available</p>
  {/if}
</div>
