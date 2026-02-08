const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const fileInput = document.getElementById('image-upload');
const activityFeed = document.getElementById('activity-feed');
const companySelect = document.getElementById('company-select');

let chatHistory = []; 
let currentPolicy = "Standard Policy";

// --- WebSocket Setup ---
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${protocol}//${window.location.host}/ws`;
let socket = new WebSocket(wsUrl);

socket.onopen = () => {
    console.log("Connected to Real-time Dashboard");
};

socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'event') {
        addFeedItem(data);
    } else if (data.type === 'stats') {
        updateStats(data.data);
    }
};

socket.onclose = () => {
    console.log("Disconnected from Dashboard");
};

function updateStats(stats) {
    if (document.getElementById('stat-resolution')) 
        document.getElementById('stat-resolution').innerText = stats.resolution;
    if (document.getElementById('stat-time')) 
        document.getElementById('stat-time').innerText = stats.avg_time;
    if (document.getElementById('stat-satisfaction')) 
        document.getElementById('stat-satisfaction').innerText = stats.satisfaction;
}

// --- Company Loading Logic ---
let companyId = null;
let tagline = window.location.pathname.split('/')[1];

async function loadCompanyContext() {
    if (!tagline || tagline === 'index.html' || tagline === 'static') {
        // Fallback or Landing Page logic
        console.log("No company context");
        return;
    }

    try {
        const res = await fetch(`/api/company/${tagline}`);
        if (!res.ok) throw new Error("Company not found");
        
        const company = await res.json();
        
        // Apply Branding
        document.title = `${company.name} Support`;
        document.querySelector('.business-info strong').innerText = company.name;
        
        if (company.banner_color) {
            document.documentElement.style.setProperty('--accent-brown', company.banner_color);
            // Also update logo icon color if needed, but CSS variable handles most
        }

        // Set Policy
        currentPolicy = company.return_policy;
        companyId = company.id;
        
        // Update Select (Read-only for user in this mode)
        companySelect.innerHTML = `<option>${company.name} Policy (Active)</option>`;
        
    } catch (e) {
        console.error("Failed to load company", e);
        alert("Company not found. Redirecting to home.");
        window.location.href = "/";
    }
}

loadCompanyContext();

// --- Chat Logic ---
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;
    
    // User Message
    addMessage(text, 'user');
    userInput.value = '';
    
    // Loading
    const loadingId = addLoadingIndicator();
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message: text, 
                history: chatHistory,
                company_policy: currentPolicy,
                company_id: companyId 
            })
        });
        
        const data = await response.json();
        removeMessage(loadingId);
        
        // Bot Message
        addMessage(data.reply, 'bot');
        
        // Update history
        chatHistory.push({ role: "user", content: text });
        chatHistory.push({ role: "model", content: data.reply });
        
    } catch (error) {
        removeMessage(loadingId);
        console.error("Chat Error:", error);
        addMessage(`Connection Error ❌ (${error.message || 'Unknown'})`, 'bot');
    }
}

// --- Image Upload Logic ---
fileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    addMessage(`📷 Uploading ${file.name}...`, 'user');
    const loadingId = addLoadingIndicator();
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('message', "I have uploaded an image of the issue.");
    formData.append('company_policy', currentPolicy);
    if (companyId) formData.append('company_id', companyId);
    
    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        removeMessage(loadingId);
        
        // Bot Reply
        addMessage(data.reply, 'bot');
        
        chatHistory.push({ role: "user", content: "I have uploaded an image of the issue." });
        chatHistory.push({ role: "model", content: data.reply });
        
        // Clear input so same file can be selected again
        fileInput.value = '';
        
    } catch (error) {
        removeMessage(loadingId);
        addMessage("Upload Failed ❌", 'bot');
    }
});

// --- UI Helpers ---
function addMessage(text, sender) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', sender);
    
    const bubble = document.createElement('div');
    bubble.classList.add('bubble');
    // Simple markdown-ish bold rendering
    bubble.innerHTML = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
    
    msgDiv.appendChild(bubble);
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addLoadingIndicator() {
    const id = 'loading-' + Date.now();
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', 'bot');
    msgDiv.id = id;
    
    const bubble = document.createElement('div');
    bubble.classList.add('bubble');
    bubble.textContent = "...";
    
    msgDiv.appendChild(bubble);
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return id;
}

function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function addFeedItem(event) {
    const item = document.createElement('div');
    item.classList.add('feed-item');
    item.innerHTML = `
        <div class="icon-small material-icons">${event.icon}</div> 
        <div class="content">
            <strong>${event.title}</strong> <span class="time">${event.time}</span>
            <div class="sub">${event.subtitle}</div>
        </div>
    `;
    
    item.style.opacity = '0';
    item.style.transform = 'translateY(-10px)';
    item.style.transition = 'all 0.3s ease';
    
    activityFeed.prepend(item);
    
    setTimeout(() => {
        item.style.opacity = '1';
        item.style.transform = 'translateY(0)';
    }, 10);
}
