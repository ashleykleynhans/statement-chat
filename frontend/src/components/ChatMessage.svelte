<script>
  import { formatCurrency, formatDate } from '../lib/stores.js';

  export let message;

  let showTransactions = false;

  $: hasTransactions = message.transactions?.length > 0;

  // Format message content with colors for budget info
  function formatContent(content) {
    if (!content) return '';

    // Escape HTML first
    let formatted = content
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Color "OVER BUDGET" in red
    formatted = formatted.replace(
      /OVER BUDGET/g,
      '<span class="text-red-500 font-semibold">OVER BUDGET</span>'
    );

    // Color percentages based on value
    formatted = formatted.replace(
      /(\d+)% used/g,
      (match, pct) => {
        const percent = parseInt(pct);
        let colorClass = 'text-green-500';
        if (percent >= 100) colorClass = 'text-red-500';
        else if (percent >= 80) colorClass = 'text-yellow-500';
        return `<span class="${colorClass}">${pct}% used</span>`;
      }
    );

    // Color "remaining" amounts in green
    formatted = formatted.replace(
      /(R[\d,\.]+)\s+remaining/g,
      '<span class="text-green-500">$1 remaining</span>'
    );

    // Color "over budget by" amounts in red
    formatted = formatted.replace(
      /by (R[\d,\.]+)/g,
      'by <span class="text-red-500 font-semibold">$1</span>'
    );

    return formatted;
  }

  $: formattedContent = formatContent(message.content);
</script>

<div class="flex {message.role === 'user' ? 'justify-end' : 'justify-start'} mb-4">
  <div
    class="max-w-[80%] rounded-lg px-4 py-3 {message.role === 'user'
      ? 'bg-blue-600 text-white'
      : message.role === 'error'
        ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800'
        : 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow'}"
  >
    <!-- Message content -->
    <div class="whitespace-pre-wrap">{@html formattedContent}</div>

    <!-- Transactions (for assistant messages) -->
    {#if hasTransactions}
      <button
        class="mt-2 text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
        on:click={() => (showTransactions = !showTransactions)}
      >
        <svg
          class="w-4 h-4 transition-transform {showTransactions ? 'rotate-90' : ''}"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
        {showTransactions ? 'Hide' : 'Show'} {message.transactions.length} transaction{message.transactions.length !== 1 ? 's' : ''}
      </button>

      {#if showTransactions}
        <div class="mt-2 border-t border-gray-200 dark:border-gray-700 pt-2">
          <div class="space-y-2 text-sm">
            {#each message.transactions as tx}
              <div class="flex justify-between items-center py-1 border-b border-gray-100 dark:border-gray-700 last:border-0">
                <div>
                  <div class="font-medium">{tx.description}</div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">
                    {formatDate(tx.date)} &middot; {tx.category || 'uncategorized'}
                  </div>
                </div>
                <div
                  class="font-medium {tx.transaction_type === 'debit'
                    ? 'text-red-600 dark:text-red-400'
                    : 'text-green-600 dark:text-green-400'}"
                >
                  {tx.transaction_type === 'debit' ? '-' : '+'}{formatCurrency(tx.amount)}
                </div>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    {/if}

    <!-- Timestamp -->
    <div
      class="text-xs mt-1 {message.role === 'user'
        ? 'text-blue-200'
        : 'text-gray-400 dark:text-gray-500'}"
    >
      {new Date(message.timestamp).toLocaleTimeString()}
    </div>
  </div>
</div>
