/* JalDrishti Chatbot Module — JalBot AI Assistant */

class ChatbotModule {
  constructor() {
    this.isOpen = false;
    this.history = [];
    this.init();
  }

  init() {
    this.setupUI();
    this.setupListeners();
    // Show welcome message
    setTimeout(() => {
      this.addMessage('bot', '👋 Hi! I\'m JalBot. Ask me about India\'s water quality — river pollution, CPCB standards, state comparisons, or specific parameters like BOD, DO, or pH.');
    }, 500);
  }

  setupUI() {
    const btn = document.getElementById('chatbotBtn');
    const closeBtn = document.querySelector('.chatbot-close');
    const sendBtn = document.querySelector('.chat-send');
    if (btn) btn.addEventListener('click', () => this.toggle());
    if (closeBtn) closeBtn.addEventListener('click', () => this.close());
    if (sendBtn) sendBtn.addEventListener('click', () => this.sendMessage());

    // Quick prompts
    document.querySelectorAll('.chat-quick-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const input = document.querySelector('.chat-textbox');
        if (input) { input.value = btn.textContent; this.sendMessage(); }
      });
    });
  }

  setupListeners() {
    const input = document.querySelector('.chat-textbox');
    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendMessage(); }
      });
    }
  }

  toggle() { this.isOpen ? this.close() : this.open(); }

  open() {
    const panel = document.getElementById('chatbotPanel');
    if (panel) { panel.classList.add('active'); this.isOpen = true; }
    setTimeout(() => document.querySelector('.chat-textbox')?.focus(), 100);
  }

  close() {
    const panel = document.getElementById('chatbotPanel');
    if (panel) { panel.classList.remove('active'); this.isOpen = false; }
  }

  async sendMessage() {
    const input = document.querySelector('.chat-textbox');
    if (!input || !input.value.trim()) return;
    const message = input.value.trim();
    input.value = '';
    this.addMessage('user', message);
    this.showTyping();

    try {
      // FIX: was '/chat', now '/api/chat'
      const response = await app.fetch('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message, history: this.history.slice(-6) })
      });
      this.removeTyping();
      if (response.success) {
        this.addMessage('bot', response.reply);
        this.history = response.history || this.history;
      } else {
        this.addMessage('bot', '⚠ Sorry, I encountered an error. Please try again.');
      }
    } catch (error) {
      this.removeTyping();
      this.addMessage('bot', '⚠ Connection failed. Make sure the backend is running on port 5000.');
    }
  }

  addMessage(sender, text) {
    const messages = document.querySelector('.chatbot-messages');
    if (!messages) return;
    const msg = document.createElement('div');
    msg.className = `message ${sender}`;
    // Simple markdown: bold **text**, newlines → <br>
    const formatted = this.escapeHtml(text)
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
    msg.innerHTML = `<div class="message-bubble">${formatted}</div>`;
    messages.appendChild(msg);
    messages.scrollTop = messages.scrollHeight;
  }

  showTyping() {
    const messages = document.querySelector('.chatbot-messages');
    if (!messages) return;
    const typing = document.createElement('div');
    typing.id = 'typingIndicator';
    typing.className = 'message bot';
    typing.innerHTML = '<div class="message-bubble" style="padding:.6rem .9rem"><div class="typing-indicator"><span></span><span></span><span></span></div></div>';
    messages.appendChild(typing);
    messages.scrollTop = messages.scrollHeight;
  }

  removeTyping() { document.getElementById('typingIndicator')?.remove(); }

  escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
  }
}
