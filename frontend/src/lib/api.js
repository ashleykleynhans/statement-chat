/**
 * REST API client for the statement-chat backend.
 */

const BASE_URL = '/api/v1';

/**
 * Fetch wrapper with error handling.
 */
async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    if (error.instructions) {
      throw new Error(`${error.error} ${error.instructions}`);
    }
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Get database statistics.
 */
export async function getStats() {
  return fetchJSON(`${BASE_URL}/stats`);
}

/**
 * Get paginated transactions.
 */
export async function getTransactions(limit = 20, offset = 0) {
  return fetchJSON(`${BASE_URL}/transactions?limit=${limit}&offset=${offset}`);
}

/**
 * Search transactions by query.
 */
export async function searchTransactions(query) {
  return fetchJSON(`${BASE_URL}/transactions/search?q=${encodeURIComponent(query)}`);
}

/**
 * Get all categories.
 */
export async function getCategories() {
  return fetchJSON(`${BASE_URL}/categories`);
}

/**
 * Get category spending summary.
 */
export async function getCategorySummary() {
  return fetchJSON(`${BASE_URL}/categories/summary`);
}

/**
 * Get transactions by category.
 */
export async function getTransactionsByCategory(category) {
  return fetchJSON(`${BASE_URL}/transactions/category/${encodeURIComponent(category)}`);
}

/**
 * Get transactions by type (debit/credit).
 */
export async function getTransactionsByType(type) {
  return fetchJSON(`${BASE_URL}/transactions/type/${type}`);
}

/**
 * Get transactions in date range.
 */
export async function getTransactionsByDateRange(start, end) {
  return fetchJSON(`${BASE_URL}/transactions/date-range?start=${start}&end=${end}`);
}

/**
 * Get transactions by statement number.
 */
export async function getTransactionsByStatement(statementNumber) {
  return fetchJSON(`${BASE_URL}/transactions/statement/${encodeURIComponent(statementNumber)}`);
}

/**
 * Health check.
 */
export async function healthCheck() {
  return fetchJSON('/health');
}

// ============ Analytics API ============

/**
 * Get list of all statements.
 */
export async function getStatements() {
  return fetchJSON(`${BASE_URL}/statements`);
}

/**
 * Get analytics for the latest statement.
 */
export async function getLatestAnalytics() {
  return fetchJSON(`${BASE_URL}/analytics/latest`);
}

/**
 * Get analytics for a specific statement.
 */
export async function getAnalyticsByStatement(statementNumber) {
  return fetchJSON(`${BASE_URL}/analytics/statement/${encodeURIComponent(statementNumber)}`);
}

// ============ Budget API ============

/**
 * Get all budgets.
 */
export async function getBudgets() {
  return fetchJSON(`${BASE_URL}/budgets`);
}

/**
 * Get budget summary with actual spending comparison.
 */
export async function getBudgetSummary() {
  return fetchJSON(`${BASE_URL}/budgets/summary`);
}

/**
 * Create a budget.
 */
export async function createBudget(category, amount) {
  return fetchJSON(`${BASE_URL}/budgets`, {
    method: 'POST',
    body: JSON.stringify({ category, amount }),
  });
}

/**
 * Update an existing budget.
 */
export async function updateBudget(category, amount) {
  return fetchJSON(`${BASE_URL}/budgets/${encodeURIComponent(category)}`, {
    method: 'PUT',
    body: JSON.stringify({ amount }),
  });
}

/**
 * Delete a budget.
 */
export async function deleteBudget(category) {
  return fetchJSON(`${BASE_URL}/budgets/${encodeURIComponent(category)}`, {
    method: 'DELETE',
  });
}

/**
 * Export all budgets as JSON.
 */
export async function exportBudgets() {
  return fetchJSON(`${BASE_URL}/budgets/export`);
}

/**
 * Import budgets from JSON (replaces all existing budgets).
 */
export async function importBudgets(budgets) {
  return fetchJSON(`${BASE_URL}/budgets/import`, {
    method: 'POST',
    body: JSON.stringify({ budgets }),
  });
}

/**
 * Delete all budgets.
 */
export async function deleteAllBudgets() {
  return fetchJSON(`${BASE_URL}/budgets`, {
    method: 'DELETE',
  });
}

// ============ Export API ============

/**
 * Build URL for exporting transactions as CSV.
 * @param {Object} filters - Optional filter parameters
 * @param {string} filters.q - Search query
 * @param {string} filters.category - Category filter
 * @param {string} filters.statement - Statement number
 * @param {string} filters.start_date - Start date (YYYY-MM-DD)
 * @param {string} filters.end_date - End date (YYYY-MM-DD)
 * @returns {string} Export URL
 */
export function getExportUrl(filters = {}) {
  const params = new URLSearchParams();
  if (filters.q) params.append('q', filters.q);
  if (filters.category) params.append('category', filters.category);
  if (filters.statement) params.append('statement', filters.statement);
  if (filters.start_date) params.append('start_date', filters.start_date);
  if (filters.end_date) params.append('end_date', filters.end_date);

  const queryString = params.toString();
  return `${BASE_URL}/transactions/export${queryString ? '?' + queryString : ''}`;
}
