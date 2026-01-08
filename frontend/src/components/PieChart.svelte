<script>
  import { createEventDispatcher } from 'svelte';
  import { formatCurrency } from '../lib/stores.js';

  export let data = []; // Array of { category, value, count }
  export let size = 280;

  const dispatch = createEventDispatcher();

  // SVG center and radius
  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 10;
  const innerRadius = radius * 0.6; // Donut hole

  // Generate unique colors using HSL with golden angle distribution
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

  function generateColor(index) {
    const goldenAngle = 137.508;
    const hue = (index * goldenAngle) % 360;
    const [r, g, b] = hslToRgb(hue, 0.7, 0.5);
    return `rgb(${r},${g},${b})`;
  }

  // Calculate total and slices
  $: total = data.reduce((sum, d) => sum + Math.abs(d.value || 0), 0);

  $: slices = (() => {
    if (total === 0) return [];

    let currentAngle = -90; // Start at top
    return data
      .filter(d => d.value > 0)
      .map((d, i) => {
        const value = Math.abs(d.value);
        const angle = (value / total) * 360;
        const slice = {
          category: d.category,
          value: value,
          count: d.count || 0,
          startAngle: currentAngle,
          endAngle: currentAngle + angle,
          percentage: ((value / total) * 100).toFixed(1),
          color: generateColor(i)
        };
        currentAngle += angle;
        return slice;
      });
  })();

  // Convert polar to cartesian coordinates
  function polarToCartesian(centerX, centerY, r, angleInDegrees) {
    const angleInRadians = (angleInDegrees * Math.PI) / 180;
    return {
      x: centerX + r * Math.cos(angleInRadians),
      y: centerY + r * Math.sin(angleInRadians)
    };
  }

  // Create SVG arc path for a donut slice
  function describeArc(startAngle, endAngle) {
    const start = polarToCartesian(cx, cy, radius, endAngle);
    const end = polarToCartesian(cx, cy, radius, startAngle);
    const innerStart = polarToCartesian(cx, cy, innerRadius, endAngle);
    const innerEnd = polarToCartesian(cx, cy, innerRadius, startAngle);

    const largeArcFlag = endAngle - startAngle <= 180 ? 0 : 1;

    return [
      'M', start.x, start.y,
      'A', radius, radius, 0, largeArcFlag, 0, end.x, end.y,
      'L', innerEnd.x, innerEnd.y,
      'A', innerRadius, innerRadius, 0, largeArcFlag, 1, innerStart.x, innerStart.y,
      'Z'
    ].join(' ');
  }

  function formatCategoryName(category) {
    if (!category) return 'Uncategorized';
    return category
      .replace(/_/g, ' ')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }

  let hoveredSlice = null;

  function handleClick(category) {
    dispatch('select', { category });
  }
</script>

<div class="flex flex-col lg:flex-row items-center gap-6">
  <!-- Pie Chart SVG -->
  <div class="relative">
    <svg width={size} height={size} class="transform -rotate-0">
      {#each slices as slice, i}
        <path
          d={describeArc(slice.startAngle, slice.endAngle)}
          fill={slice.color}
          class="cursor-pointer transition-all duration-200 hover:opacity-80"
          style="transform-origin: {cx}px {cy}px; {hoveredSlice === i ? 'transform: scale(1.03);' : ''}"
          on:mouseenter={() => hoveredSlice = i}
          on:mouseleave={() => hoveredSlice = null}
          on:click={() => handleClick(slice.category)}
          role="button"
          tabindex="0"
          on:keypress={(e) => e.key === 'Enter' && handleClick(slice.category)}
        >
          <title>{formatCategoryName(slice.category)}: {formatCurrency(slice.value)} ({slice.percentage}%)</title>
        </path>
      {/each}

      <!-- Center text -->
      <text x={cx} y={cy - 10} text-anchor="middle" class="fill-gray-700 dark:fill-gray-300 text-sm font-medium">
        Total
      </text>
      <text x={cx} y={cy + 15} text-anchor="middle" class="fill-gray-900 dark:fill-gray-100 text-lg font-bold">
        {formatCurrency(total)}
      </text>
    </svg>

    <!-- Hover tooltip -->
    {#if hoveredSlice !== null && slices[hoveredSlice]}
      <div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 pointer-events-none">
        <div class="bg-white dark:bg-gray-800 shadow-lg rounded-lg px-3 py-2 text-center border border-gray-200 dark:border-gray-700">
          <div class="text-sm font-medium text-gray-900 dark:text-gray-100">
            {formatCategoryName(slices[hoveredSlice].category)}
          </div>
          <div class="text-lg font-bold" style="color: {slices[hoveredSlice].color}">
            {slices[hoveredSlice].percentage}%
          </div>
        </div>
      </div>
    {/if}
  </div>

  <!-- Legend -->
  <div class="flex-1 space-y-2 max-h-64 overflow-y-auto">
    {#each slices as slice, i}
      <button
        class="w-full flex items-center gap-3 p-2 rounded-lg transition-all hover:bg-gray-100 dark:hover:bg-gray-700/50 cursor-pointer group"
        on:click={() => handleClick(slice.category)}
        on:mouseenter={() => hoveredSlice = i}
        on:mouseleave={() => hoveredSlice = null}
      >
        <div
          class="w-4 h-4 rounded-sm flex-shrink-0"
          style="background-color: {slice.color}"
        ></div>
        <div class="flex-1 text-left text-sm text-gray-700 dark:text-gray-300 truncate group-hover:text-gray-900 dark:group-hover:text-gray-100">
          {formatCategoryName(slice.category)}
        </div>
        <div class="text-sm font-medium text-gray-900 dark:text-gray-100">
          {formatCurrency(slice.value)}
        </div>
        <div class="text-xs text-gray-500 dark:text-gray-400 w-12 text-right">
          {slice.percentage}%
        </div>
      </button>
    {/each}

    {#if slices.length === 0}
      <p class="text-gray-500 dark:text-gray-400 text-center py-4">No data available</p>
    {/if}
  </div>
</div>
