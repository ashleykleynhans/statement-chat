<script>
  import { formatCurrency, formatDate } from '../lib/stores.js';

  export let message;

  let showTransactions = false;

  $: hasTransactions = message.transactions?.length > 0;

  // Extract budget info for progress bar
  function extractBudgetInfo(content) {
    if (!content) return null;

    // Match patterns like "R8,000.00" for budget and "R8,615.00" for spent, "106%" for percentage
    // Flexible pattern: "budget is R..." or "overall budget is R..."
    const budgetMatch = content.match(/budget is (R[\d,\.]+)/i);
    const spentMatch = content.match(/spent (R[\d,\.]+)/i);
    const percentMatch = content.match(/\((\d+)% used\)/);

    if (budgetMatch && spentMatch && percentMatch) {
      const parseAmount = (str) => parseFloat(str.replace(/[R,]/g, ''));
      return {
        budget: parseAmount(budgetMatch[1]),
        spent: parseAmount(spentMatch[1]),
        percent: parseInt(percentMatch[1]),
        budgetStr: budgetMatch[1],
        spentStr: spentMatch[1]
      };
    }

    // Also try to match "You've spent R... of R... budget" pattern
    const altMatch = content.match(/spent (R[\d,\.]+).*?of (R[\d,\.]+) budget/i);
    const altPercentMatch = content.match(/(\d+)%/);
    if (altMatch && altPercentMatch) {
      const parseAmount = (str) => parseFloat(str.replace(/[R,]/g, ''));
      return {
        budget: parseAmount(altMatch[2]),
        spent: parseAmount(altMatch[1]),
        percent: parseInt(altPercentMatch[1]),
        budgetStr: altMatch[2],
        spentStr: altMatch[1]
      };
    }

    return null;
  }

  $: budgetInfo = extractBudgetInfo(message.content);

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

    // Format PAYMENTS TOTALING/DEPOSITS TOTALING lines nicely (remove >>> <<< markers)
    formatted = formatted.replace(
      /&gt;&gt;&gt; (\d+) PAYMENTS TOTALING: (R[\d,\.]+) \| (\d+) DEPOSITS TOTALING: (R[\d,\.]+) &lt;&lt;&lt;/g,
      '<div class="mt-2 pt-2 border-t border-gray-200 dark:border-gray-600 font-medium">' +
        '<span class="text-red-500">$1 payments: $2</span> · ' +
        '<span class="text-green-500">$3 deposits: $4</span></div>'
    );

    // Format OVERALL BUDGET TOTAL (remove >>> <<< markers)
    formatted = formatted.replace(
      /&gt;&gt;&gt; OVERALL BUDGET TOTAL: (R[\d,\.]+) budgeted, (R[\d,\.]+) spent, (R-?[\d,\.]+) remaining &lt;&lt;&lt;/g,
      '<div class="mt-2 pt-2 border-t border-gray-200 dark:border-gray-600 font-medium">' +
        'Budget: $1 · <span class="text-red-500">Spent: $2</span> · ' +
        '<span class="text-green-500">Remaining: $3</span></div>'
    );

    // Strip any remaining >>> <<< markers the LLM might have copied
    formatted = formatted.replace(/&gt;&gt;&gt;/g, '');
    formatted = formatted.replace(/&lt;&lt;&lt;/g, '');

    // Format transaction lists into tables
    // Match lists that follow a header line ending with ":"
    const listPattern = /^(.*?:)\n((?:[-•] .+\n?|[A-Z].+\| R[\d,\.]+\n?)+)/gm;
    formatted = formatted.replace(listPattern, (match, header, list) => {
      const lines = list.trim().split('\n').filter(l => l.trim());
      if (lines.length === 0) return match;

      const rows = lines.map(line => {
        // Pattern: "- 2025-11-03: Description - R1,000.00"
        const dateDescAmtMatch = line.match(/^[-•] (\d{4}-\d{2}-\d{2}): (.+?) - (R[\d,\.]+)$/);
        if (dateDescAmtMatch) {
          return `<tr class="border-b border-gray-100 dark:border-gray-700"><td class="py-2 pr-3 text-gray-500 text-xs">${dateDescAmtMatch[1]}</td><td class="py-2 pr-3">${dateDescAmtMatch[2]}</td><td class="py-2 text-right text-red-500 dark:text-red-400 font-medium">-${dateDescAmtMatch[3]}</td></tr>`;
        }
        // Pattern: "Description | R1,000.00" (no dash prefix)
        const pipeMatch = line.match(/^(.+?) \| (R[\d,\.]+)$/);
        if (pipeMatch) {
          return `<tr class="border-b border-gray-100 dark:border-gray-700"><td class="py-2 pr-3">${pipeMatch[1]}</td><td class="py-2 text-right text-red-500 dark:text-red-400 font-medium">-${pipeMatch[2]}</td></tr>`;
        }
        // Pattern: "- R1,000.00 (2025-11-03)"
        const amtDateMatch = line.match(/^[-•] (R[\d,\.]+) \((\d{4}-\d{2}-\d{2})\)$/);
        if (amtDateMatch) {
          return `<tr class="border-b border-gray-100 dark:border-gray-700"><td class="py-2 pr-3 text-gray-500 text-xs">${amtDateMatch[2]}</td><td class="py-2 text-right text-red-500 dark:text-red-400 font-medium">-${amtDateMatch[1]}</td></tr>`;
        }
        // Fallback: just show the line
        return `<tr class="border-b border-gray-100 dark:border-gray-700"><td class="py-2" colspan="3">${line.replace(/^[-•] /, '')}</td></tr>`;
      }).join('');

      return `${header}<table class="mt-3 text-sm w-full"><tbody>${rows}</tbody></table>`;
    });

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

    <!-- Budget progress bar -->
    {#if budgetInfo}
      <div class="mt-3 pt-2 border-t border-gray-200 dark:border-gray-700">
        <div class="flex justify-between text-xs mb-1">
          <span>Spent: {budgetInfo.spentStr}</span>
          <span>Budget: {budgetInfo.budgetStr}</span>
        </div>
        <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4 overflow-hidden">
          <div
            class="h-4 rounded-full transition-all duration-500 {budgetInfo.percent >= 100
              ? 'bg-red-500'
              : budgetInfo.percent >= 80
                ? 'bg-yellow-500'
                : 'bg-green-500'}"
            style="width: {Math.min(budgetInfo.percent, 100)}%"
          ></div>
        </div>
        <div class="text-center text-xs mt-1 font-medium {budgetInfo.percent >= 100
          ? 'text-red-500'
          : budgetInfo.percent >= 80
            ? 'text-yellow-600 dark:text-yellow-400'
            : 'text-green-500'}">
          {budgetInfo.percent}% used
        </div>
      </div>
    {/if}

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
