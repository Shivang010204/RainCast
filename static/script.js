/**
 * RainCast AI - Obsidian Pro Logic
 */

// 1. Smooth Form Submission & UI Feedback
document.querySelector('.search-box-ui')?.addEventListener('submit', function(e) {
    const btn = this.querySelector('button');
    // Change button to a loading state
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Executing...';
    btn.style.opacity = "0.8";
    btn.style.pointerEvents = "none";
});

// 2. Handle Report Status with Professional Feedback
async function reportWeather(status, city) {
    const reportControls = document.querySelector(".report-controls-ui");
    if (!reportControls) return;

    // Preserve height to prevent layout shift
    const originalHeight = reportControls.offsetHeight;
    reportControls.style.minHeight = `${originalHeight}px`;
    
    // Smooth fade out of buttons
    reportControls.style.opacity = "0.5";
    reportControls.style.pointerEvents = "none";

    try {
        const response = await fetch('/report', {
            method: 'POST',
            // Note: Since the HTML now uses a real form for file uploads, 
            // this AJAX is for quick-clicks. 
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `status=${encodeURIComponent(status)}&city=${encodeURIComponent(city)}`
        });

        if (response.ok) {
            reportControls.innerHTML = `
                <div style="grid-column: span 2; text-align: center; animation: fadeIn 0.5s ease;">
                    <p style="color: var(--success); font-weight: 600; margin: 0;">
                        <i class="fa-solid fa-circle-check"></i> Analysis Verified Successfully
                    </p>
                </div>`;
        }
    } catch (error) {
        reportControls.style.opacity = "1";
        reportControls.style.pointerEvents = "all";
        console.error("Verification failed", error);
    }
}

// 3. Dynamic "Glass-Card" Animation Sequence
document.addEventListener("DOMContentLoaded", () => {
    const cards = document.querySelectorAll(".glass-card");
    
    cards.forEach((card, index) => {
        // Initial state
        card.style.opacity = "0";
        card.style.transform = "translateY(30px) scale(0.98)";
        card.style.transition = "all 0.6s cubic-bezier(0.23, 1, 0.32, 1)"; 
        
        // Staggered reveal
        setTimeout(() => {
            card.style.opacity = "1";
            card.style.transform = "translateY(0) scale(1)";
        }, 150 * index);
    });
});

// 4. Input Field "Focus" Glow Effect
const searchInput = document.querySelector('.search-box-ui input');
if (searchInput) {
    searchInput.addEventListener('focus', () => {
        document.querySelector('.search-box-ui').style.borderColor = 'var(--primary)';
        document.querySelector('.search-box-ui').style.boxShadow = '0 0 20px rgba(99, 102, 241, 0.15)';
    });
    
    searchInput.addEventListener('blur', () => {
        document.querySelector('.search-box-ui').style.borderColor = 'var(--border)';
        document.querySelector('.search-box-ui').style.boxShadow = 'none';
    });
}