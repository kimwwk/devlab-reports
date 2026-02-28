// Filter functionality
const filterButtons = document.querySelectorAll('.filter-btn');
const messageCards = document.querySelectorAll('.message-card');

filterButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        const filterType = btn.getAttribute('data-type');

        // Toggle active state
        if (filterType === 'all') {
            filterButtons.forEach(b => b.classList.add('active'));
            messageCards.forEach(card => card.style.display = 'block');
        } else {
            btn.classList.toggle('active');

            // Check if any filters are active
            const activeFilters = Array.from(filterButtons)
                .filter(b => b.classList.contains('active') && b.getAttribute('data-type') !== 'all')
                .map(b => b.getAttribute('data-type'));

            if (activeFilters.length === 0) {
                // No filters active, show all
                messageCards.forEach(card => card.style.display = 'block');
                document.querySelector('[data-type="all"]').classList.add('active');
            } else {
                // Show only matching cards
                messageCards.forEach(card => {
                    const cardType = card.getAttribute('data-type');
                    card.style.display = activeFilters.includes(cardType) ? 'block' : 'none';
                });
                document.querySelector('[data-type="all"]').classList.remove('active');
            }
        }
    });
});

// Collapsible functionality - arrow rotates and content expands
function toggleCollapsible(index) {
    const content = document.getElementById(`collapsible-${index}`);
    const icon = document.getElementById(`toggle-icon-${index}`);

    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        icon.textContent = '▼';
    } else {
        content.classList.add('hidden');
        icon.textContent = '▶';
    }
}

// Result content expansion - toggle between truncated and full view
function toggleResultExpansion(index) {
    const content = document.getElementById(`result-content-${index}`);
    const text = document.getElementById(`expand-text-${index}`);

    if (content.classList.contains('tool-result-content-truncated')) {
        content.classList.remove('tool-result-content-truncated');
        content.classList.add('tool-result-content-full');
        text.textContent = '▲ COLLAPSE';
    } else {
        content.classList.remove('tool-result-content-full');
        content.classList.add('tool-result-content-truncated');
        text.textContent = '▼ EXPAND';
    }
}

// Initialize
console.log('Agent Report loaded:', messages.length, 'messages');
