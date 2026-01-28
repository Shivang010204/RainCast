/**
 * RainCast AI - Client Side Logic (Dashboard Edition)
 */

// 1. Handle Sidebar Mode Selection
function updateMode(mode, btnElement) {
    // Update the hidden input in the form
    const modeInput = document.getElementById('user_mode');
    if (modeInput) {
        modeInput.value = mode;
    }

    // Update UI: Remove 'active' class from all buttons and add to the clicked one
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    btnElement.classList.add('active');

    // Optional: Visual confirmation for the user
    console.log(`System switched to ${mode} mode.`);
}

// 2. Handle the "Report Actual Weather" feedback (AJAX)
async function reportWeather(status, city) {
    const reportSection = document.querySelector(".report-btns");
    const originalContent = reportSection.innerHTML;
    
    // Provide immediate visual feedback
    reportSection.innerHTML = `<p style="color: #00f2fe; font-size: 0.85rem; width: 100%; text-align: center;">Saving your feedback...</p>`;

    try {
        const response = await fetch('/report', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `status=${encodeURIComponent(status)}&city=${encodeURIComponent(city)}`
        });

        if (response.ok) {
            reportSection.innerHTML = `
                <p style="color: #4cd137; font-size: 0.85rem; width: 100%; text-align: center;">
                    ✔ Thank you! This helps improve our ML model accuracy.
                </p>`;
        } else {
            throw new Error('Server error');
        }
    } catch (error) {
        reportSection.innerHTML = originalContent; // Restore buttons so they can try again
        alert("⚠ Connection failed. Please try again.");
    }
}

// 3. Form Submission Loader
document.getElementById('predictionForm')?.addEventListener('submit', function() {
    const btn = this.querySelector('button');
    btn.innerHTML = "Analyzing...";
    btn.style.opacity = "0.7";
    btn.disabled = true;
});

// 4. Smooth Fade-in for Cards
document.addEventListener("DOMContentLoaded", () => {
    const cards = document.querySelectorAll(".glass-card");
    cards.forEach((card, index) => {
        card.style.opacity = "0";
        card.style.transform = "translateY(20px)";
        card.style.transition = "all 0.5s ease-out";
        
        setTimeout(() => {
            card.style.opacity = "1";
            card.style.transform = "translateY(0)";
        }, 100 * index);
    });
});