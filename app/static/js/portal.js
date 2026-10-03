/**
 * Homelab Portal client-side filtering and keyboard navigation.
 */
document.addEventListener('DOMContentLoaded', () => {
  const searchInput = document.getElementById('service-search');
  const clearBtn = document.getElementById('search-clear');
  const serviceCards = document.querySelectorAll('.service-card');
  const categorySections = document.querySelectorAll('.category-section');
  const noResultsEl = document.getElementById('no-results');

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

      // Show/hide category section based on whether any cards match
      if (sectionVisibleCount > 0) {
        section.style.display = '';
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
});
