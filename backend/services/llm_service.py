"""
LLM Service — Configurable AI wrapper for chatbot.
Supports OpenAI, Anthropic, and Google Gemini APIs.
Falls back to rule-based responses when no API key is set.
"""
import json
import requests
from config import Config


SYSTEM_PROMPT = """You are JalBot, an expert water quality analyst for JalDrishti — ISRO's water intelligence platform. You have access to India's CPCB/CWC water quality dataset (370K records, 34 states, 1963–2025). Answer questions about water quality parameters, river pollution, state-wise trends, parameter thresholds, and CPCB standards. Be concise, data-driven, and scientific.

Key CPCB Standards:
- DO (Dissolved Oxygen): ≥ 6 mg/L for Class A water
- BOD (Biochemical Oxygen Demand): ≤ 3 mg/L for Class B
- pH: 6.5–8.5
- Fecal Coliform: ≤ 500 MPN/100mL for bathing
- Turbidity: ≤ 10 NTU for drinking
- Total Coliform: ≤ 5000 MPN/100mL

WQI Categories: Excellent (0–25), Good (26–50), Moderate (51–75), Poor (76–90), Critical (91+)
"""


class LLMService:
    """Wrapper for multiple LLM providers with rule-based fallback."""

    def __init__(self):
        self.provider = Config.LLM_PROVIDER
        self.api_key = Config.LLM_API_KEY

    def chat(self, message, data_context='', history=None):
        """
        Send message to LLM and return response.
        Falls back to rule-based if no API key configured.
        """
        if not self.api_key:
            return self.rule_based_chat(message, data_context)

        try:
            if self.provider == 'openai':
                return self._openai_chat(message, data_context, history)
            elif self.provider == 'anthropic':
                return self._anthropic_chat(message, data_context, history)
            elif self.provider == 'gemini':
                return self._gemini_chat(message, data_context, history)
            else:
                return self.rule_based_chat(message, data_context)
        except Exception as e:
            print(f"[LLM Error] {e}")
            return self.rule_based_chat(message, data_context)

    def _openai_chat(self, message, data_context, history):
        """Call OpenAI API."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\nCurrent Data Context:\n" + data_context}]

        if history:
            for h in history[-6:]:
                messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})

        messages.append({"role": "user", "content": message})

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 500
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _anthropic_chat(self, message, data_context, history):
        """Call Anthropic API."""
        messages = []
        if history:
            for h in history[-6:]:
                messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": message})

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 500,
                "system": SYSTEM_PROMPT + "\n\nCurrent Data Context:\n" + data_context,
                "messages": messages
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]

    def _gemini_chat(self, message, data_context, history):
        """Call Google Gemini API."""
        prompt = f"{SYSTEM_PROMPT}\n\nData Context:\n{data_context}\n\nUser: {message}"

        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={self.api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 500}
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]

    def rule_based_chat(self, message, data_context=''):
        """
        Rule-based fallback when no LLM API key is configured.
        Uses keyword matching and data context to generate responses.
        """
        msg = message.lower().strip()

        # Greetings
        if any(w in msg for w in ['hello', 'hi', 'hey', 'namaste']):
            return ("Namaste! 🙏 I'm JalBot, your water quality assistant. "
                    "I can answer questions about India's water quality data, CPCB standards, "
                    "river pollution, and state-wise trends. What would you like to know?")

        # CPCB Standards
        if any(w in msg for w in ['standard', 'limit', 'threshold', 'safe level', 'cpcb']):
            return ("📋 **CPCB Water Quality Standards:**\n\n"
                    "• **DO (Dissolved Oxygen):** ≥ 6 mg/L (Class A), ≥ 5 mg/L (Class B)\n"
                    "• **BOD:** ≤ 2 mg/L (Class A), ≤ 3 mg/L (Class B)\n"
                    "• **pH:** 6.5 – 8.5\n"
                    "• **Fecal Coliform:** ≤ 500 MPN/100mL (bathing water)\n"
                    "• **Total Coliform:** ≤ 5000 MPN/100mL\n"
                    "• **Turbidity:** ≤ 10 NTU (drinking water)\n"
                    "• **TDS:** ≤ 500 mg/L (desirable), ≤ 2000 mg/L (permissible)")

        # BOD specific
        if 'bod' in msg:
            return ("📊 **BOD (Biochemical Oxygen Demand):**\n\n"
                    "BOD measures the amount of dissolved oxygen consumed by microorganisms "
                    "to decompose organic matter. Higher BOD = more pollution.\n\n"
                    "• CPCB Class A: ≤ 2 mg/L\n"
                    "• CPCB Class B: ≤ 3 mg/L\n"
                    "• > 30 mg/L: Critical contamination\n\n"
                    + (f"From the dataset: {data_context}" if data_context else ""))

        # DO specific
        if 'dissolved oxygen' in msg or ('do' in msg.split() and len(msg.split()) < 8):
            return ("📊 **Dissolved Oxygen (DO):**\n\n"
                    "DO is critical for aquatic life. Values below 4 mg/L cause hypoxia.\n\n"
                    "• Healthy water: > 6 mg/L\n"
                    "• Stressed: 4–6 mg/L\n"
                    "• Hypoxic: 2–4 mg/L\n"
                    "• Anoxic: < 2 mg/L (fish kills likely)\n\n"
                    + (f"From the dataset: {data_context}" if data_context else ""))

        # WQI
        if 'wqi' in msg or 'water quality index' in msg:
            return ("📊 **Water Quality Index (WQI):**\n\n"
                    "WQI is a composite score (0–100) based on weighted parameters:\n"
                    "• DO: 25% weight\n"
                    "• BOD: 25% weight\n"
                    "• pH: 15% weight\n"
                    "• Turbidity: 15% weight\n"
                    "• Fecal Coliform: 20% weight\n\n"
                    "**Categories:** Excellent (0–25) | Good (26–50) | Moderate (51–75) | "
                    "Poor (76–90) | Critical (91+)\n\n"
                    "Lower score = better water quality.")

        # Polluted rivers
        if any(w in msg for w in ['pollut', 'worst', 'dirty', 'contaminat']):
            return ("🔴 **Most Polluted Water Bodies in India:**\n\n"
                    "Based on CPCB/CWC data, the most polluted rivers include:\n"
                    "1. **Yamuna** (Delhi–Agra stretch) — extreme BOD and FColi\n"
                    "2. **Sabarmati** (Ahmedabad downstream) — high turbidity and BOD\n"
                    "3. **Hindon** (UP) — industrial effluents\n"
                    "4. **Ganga** (Kanpur–Varanasi stretch) — sewage pollution\n"
                    "5. **Musi** (Hyderabad) — untreated sewage\n\n"
                    + (f"From the dataset:\n{data_context}" if data_context else ""))

        # Ganga
        if 'ganga' in msg or 'ganges' in msg:
            return ("🏞️ **Ganga Basin Summary:**\n\n"
                    "The Ganga is India's most important river system, spanning "
                    "Uttarakhand, UP, Bihar, Jharkhand, and West Bengal.\n\n"
                    "Key concerns:\n"
                    "• Sewage discharge from major cities\n"
                    "• Industrial effluents (tanneries in Kanpur)\n"
                    "• Agricultural runoff\n"
                    "• Fecal Coliform consistently above CPCB limits\n\n"
                    + (f"Dataset stats:\n{data_context}" if data_context else ""))

        # Comparison
        if 'compare' in msg or 'vs' in msg or 'versus' in msg:
            return ("📊 **State/Basin Comparison:**\n\n"
                    "I can compare water quality between states or basins. "
                    f"Here's what the data shows:\n\n{data_context}\n\n"
                    "For detailed comparisons, try the Explorer section on the dashboard!")

        # Default with data context
        if data_context:
            return (f"Based on the JalDrishti dataset:\n\n{data_context}\n\n"
                    "Would you like to know more about specific parameters, "
                    "CPCB standards, or a particular river/state?")

        # Generic fallback
        return ("I can help with:\n"
                "• 📋 CPCB water quality standards\n"
                "• 📊 Parameter explanations (DO, BOD, pH, etc.)\n"
                "• 🏞️ River/basin pollution data\n"
                "• 🗺️ State-wise water quality trends\n"
                "• 🔍 Station-specific data\n\n"
                "Try asking: 'What is safe BOD level?' or 'Show Ganga basin summary'")


# Singleton
llm_service = LLMService()
