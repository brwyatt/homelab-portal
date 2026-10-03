/**
 * Homelab Portal client-side filtering, collapsible categories, and drag-and-drop reordering.
 */
document.addEventListener('DOMContentLoaded', () => {
  const searchInput = document.getElementById('service-search');
  const clearBtn = document.getElementById('search-clear');
  const serviceCards = document.querySelectorAll('.service-card');
  const categorySections = document.querySelectorAll('.category-section');
  const noResultsEl = document.getElementById('no-results');
  const catalog = document.getElementById('service-catalog');
  const portalMain = document.querySelector('.portal-main');

  const username = portalMain?.getAttribute('data-username') || '';
  const isAuthenticated = portalMain?.getAttribute('data-authenticated') === 'true';

  // Storage helper: persistent localStorage for authenticated users, sessionStorage for guest/unauthenticated
  const storage = isAuthenticated && username ? localStorage : sessionStorage;
  const userPrefix = isAuthenticated && username ? `${username}_` : 'guest_';
  const COLLAPSED_KEY = `portal_collapsed_${userPrefix}sections`;
  const ORDER_KEY = `portal_order_${userPrefix}sections`;

  // Helper to read/write JSON in web storage
  function getStorageItem(key, defaultVal) {
    try {
      const data = storage.getItem(key);
      return data ? JSON.parse(data) : defaultVal;
    } catch {
      return defaultVal;
    }
  }

  function setStorageItem(key, val) {
    try {
      storage.setItem(key, JSON.stringify(val));
    } catch {
      // Storage unavailable or quota exceeded
    }
  }

  // --- 1. Restore Section Ordering ---
  function restoreSectionOrder() {
    if (!catalog) return;
    const savedOrder = getStorageItem(ORDER_KEY, []);
    if (!Array.isArray(savedOrder) || savedOrder.length === 0) return;

    const sectionMap = new Map();
    categorySections.forEach(section => {
      const catId = section.getAttribute('data-category-id');
      if (catId) sectionMap.set(catId, section);
    });

    // Re-append in stored order
    savedOrder.forEach(catId => {
      const sec = sectionMap.get(catId);
      if (sec) {
        catalog.appendChild(sec);
        sectionMap.delete(catId);
      }
    });

    // Append any sections not in saved order at the bottom
    sectionMap.forEach(sec => {
      catalog.appendChild(sec);
    });
  }

  function saveSectionOrder() {
    if (!catalog) return;
    const currentSections = catalog.querySelectorAll('.category-section');
    const order = [];
    currentSections.forEach(sec => {
      const catId = sec.getAttribute('data-category-id');
      if (catId) order.push(catId);
    });
    setStorageItem(ORDER_KEY, order);
  }

  restoreSectionOrder();

  // --- 2. Collapsible Sections ---
  const collapsedSet = new Set(getStorageItem(COLLAPSED_KEY, []));

  function setCollapsed(section, isCollapsed, persist = true) {
    const catId = section.getAttribute('data-category-id');
    const toggleBtn = section.querySelector('.category-toggle-btn');
    const grid = section.querySelector('.services-grid');

    if (isCollapsed) {
      section.classList.add('is-collapsed');
      if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'false');
      if (grid) grid.style.display = 'none';
      if (catId) collapsedSet.add(catId);
    } else {
      section.classList.remove('is-collapsed');
      if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'true');
      if (grid) grid.style.display = '';
      if (catId) collapsedSet.delete(catId);
    }

    if (persist) {
      setStorageItem(COLLAPSED_KEY, Array.from(collapsedSet));
    }
  }

  // Initialize initial collapse states
  categorySections.forEach(section => {
    const catId = section.getAttribute('data-category-id');
    if (catId && collapsedSet.has(catId)) {
      setCollapsed(section, true, false);
    }

    const toggleBtn = section.querySelector('.category-toggle-btn');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const currentlyCollapsed = section.classList.contains('is-collapsed');
        setCollapsed(section, !currentlyCollapsed, true);
      });
    }
  });

  // --- 3. Drag and Drop Reordering ---
  let draggedSection = null;

  categorySections.forEach(section => {
    const header = section.querySelector('.category-header');
    if (!header) return;

    header.addEventListener('dragstart', (e) => {
      draggedSection = section;
      section.classList.add('is-dragging');
      if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', section.getAttribute('data-category-id') || '');
      }
    });

    header.addEventListener('dragend', () => {
      if (draggedSection) {
        draggedSection.classList.remove('is-dragging');
        draggedSection = null;
      }
      document.querySelectorAll('.category-section').forEach(s => s.classList.remove('drag-over-above', 'drag-over-below'));
      saveSectionOrder();
    });

    section.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (!draggedSection || draggedSection === section) return;
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'move';
      }

      const rect = section.getBoundingClientRect();
      const midpoint = rect.top + rect.height / 2;
      if (e.clientY < midpoint) {
        section.classList.add('drag-over-above');
        section.classList.remove('drag-over-below');
      } else {
        section.classList.add('drag-over-below');
        section.classList.remove('drag-over-above');
      }
    });

    section.addEventListener('dragleave', (e) => {
      if (!section.contains(e.relatedTarget)) {
        section.classList.remove('drag-over-above', 'drag-over-below');
      }
    });

    section.addEventListener('drop', (e) => {
      e.preventDefault();
      if (!draggedSection || draggedSection === section) return;

      const rect = section.getBoundingClientRect();
      const midpoint = rect.top + rect.height / 2;

      if (e.clientY < midpoint) {
        catalog.insertBefore(draggedSection, section);
      } else {
        catalog.insertBefore(draggedSection, section.nextSibling);
      }

      section.classList.remove('drag-over-above', 'drag-over-below');
      saveSectionOrder();
    });
  });

  // --- 4. Filtering and Search ---
  if (!searchInput) return;

  function filterServices() {
    const query = searchInput.value.trim().toLowerCase();

    if (query.length > 0) {
      if (clearBtn) clearBtn.style.display = 'block';
    } else {
      if (clearBtn) clearBtn.style.display = 'none';
    }

    let totalVisible = 0;

    categorySections.forEach(section => {
      let sectionVisibleCount = 0;
      const cards = section.querySelectorAll('.service-card');
      const catId = section.getAttribute('data-category-id');

      cards.forEach(card => {
        const name = card.getAttribute('data-name') || '';
        const description = card.getAttribute('data-description') || '';
        const category = card.getAttribute('data-category') || '';

        const matches = !query ||
          name.includes(query) ||
          description.includes(query) ||
          category.includes(query);

        if (matches) {
          card.style.display = '';
          sectionVisibleCount++;
          totalVisible++;
        } else {
          card.style.display = 'none';
        }
      });

      if (sectionVisibleCount > 0) {
        section.style.display = '';
        if (query.length > 0) {
          // Temporarily uncollapse if it matches search
          const grid = section.querySelector('.services-grid');
          if (grid) grid.style.display = '';
          const toggleBtn = section.querySelector('.category-toggle-btn');
          if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'true');
        } else {
          // Restore user's collapse state when search query is cleared
          const wasCollapsed = catId && collapsedSet.has(catId);
          setCollapsed(section, wasCollapsed, false);
        }
      } else {
        section.style.display = 'none';
      }
    });

    if (noResultsEl) {
      if (totalVisible === 0 && query.length > 0) {
        noResultsEl.style.display = 'block';
      } else {
        noResultsEl.style.display = 'none';
      }
    }
  }

  searchInput.addEventListener('input', filterServices);

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      searchInput.value = '';
      filterServices();
      searchInput.focus();
    });
  }

  // Keyboard navigation:
  // - Press "/" to focus search input
  // - Press "Esc" to clear search
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== searchInput) {
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
    } else if (e.key === 'Escape' && document.activeElement === searchInput) {
      searchInput.value = '';
      filterServices();
      searchInput.blur();
    }
  });

  // Render Feather icons if library is loaded
  if (typeof feather !== 'undefined' && feather.replace) {
    feather.replace();
  }

  // --- 4. Service Health Check Status Polling ---
  async function updateHealthStatuses() {
    try {
      const response = await fetch('/api/status');
      if (!response.ok) return;
      const data = await response.json();
      const statuses = data.statuses || {};

      serviceCards.forEach(card => {
        const serviceId = card.getAttribute('data-service-id');
        if (!serviceId) return;

        const footer = card.querySelector('.card-footer');
        const pill = card.querySelector('.status-pill');
        if (!footer || !pill) return;

        const info = statuses[serviceId];
        if (!info || info.status === 'unknown') {
          // No healthcheck configured or status unknown
          pill.className = 'status-pill status-unknown';
          const textEl = pill.querySelector('.status-text');
          if (textEl) textEl.textContent = 'Unknown';
          pill.title = info?.message || 'No health check configured';
        } else if (info.status === 'up') {
          pill.className = 'status-pill status-up';
          const textEl = pill.querySelector('.status-text');
          if (textEl) textEl.textContent = 'Online';
          pill.title = info.message ? `${info.message} (${info.status_code || 200})` : 'Online';
        } else if (info.status === 'down') {
          pill.className = 'status-pill status-down';
          const textEl = pill.querySelector('.status-text');
          if (textEl) textEl.textContent = 'Offline';
          pill.title = info.message || 'Offline';
        }
      });
    } catch {
      // Ignore background poll errors
    }
  }

  // Initial status check and periodic refresh every 15s
  updateHealthStatuses();
  setInterval(updateHealthStatuses, 15000);
});
