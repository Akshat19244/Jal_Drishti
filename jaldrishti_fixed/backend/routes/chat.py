"""
Chat API — /api/chat
AI chatbot with LLM integration and data context injection.
Falls back to rule-based responses when no API key is configured.
"""
from flask import Blueprint, request, jsonify
from services.llm_service import llm_service
from services.data_service import DataService
from utils.cache import TTLCache

chat_bp = Blueprint('chat', __name__)
cache = TTLCache()


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    """
    POST /api/chat
    Body: {
        "message": "What is the BOD in Ganga?",
        "history": [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ]
    }
    """
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({'success': False, 'error': 'No JSON payload'}), 400
        
        message = payload.get('message', '').strip()
        history = payload.get('history', [])
        
        if not message:
            return jsonify({'success': False, 'error': 'Empty message'}), 400
        
        # Build data context from dataset
        ds = DataService()
        data_context = _build_context_from_query(message, ds)
        
        # Call LLM or rule-based fallback
        response = llm_service.chat(message, data_context, history)
        
        # Update history
        history.append({'role': 'user', 'content': message})
        history.append({'role': 'assistant', 'content': response})

        return jsonify({
            'success': True,
            'reply': response,
            'history': history,
            'meta': {
                'context_used': bool(data_context),
                'provider': llm_service.provider if llm_service.api_key else 'rule-based'
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/api/chat/context', methods=['GET'])
def get_chat_context():
    """
    GET /api/chat/context?state=Gujarat&parameter=BOD
    Fetch data context for UI to pass to chatbot.
    """
    state = request.args.get('state', 'all')
    parameter = request.args.get('parameter', None)
    
    cache_key = f"chat_context_{state}_{parameter}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})

    try:
        ds = DataService()
        data = ds.get_state_data(state)
        
        if data.empty:
            return jsonify({'success': False, 'error': 'No data found'}), 404
        
        # Build context
        context = {
            'state': state,
            'stations': int(data['Station_Name'].nunique()),
            'wqi_avg': round(float(data['WQI'].mean()), 2),
            'do_avg': round(float(data['DO'].mean()), 2),
            'bod_avg': round(float(data['BOD'].mean()), 2),
            'ph_avg': round(float(data['pH'].mean()), 2),
            'fcol_avg': round(float(data['Fecal_Coliform'].mean()), 2),
        }
        
        if parameter and parameter in data.columns:
            context[f'{parameter}_avg'] = round(float(data[parameter].mean()), 2)
            context[f'{parameter}_min'] = round(float(data[parameter].min()), 2)
            context[f'{parameter}_max'] = round(float(data[parameter].max()), 2)
        
        cache.set(cache_key, context, ttl=300)
        
        return jsonify({
            'success': True,
            'data': context,
            'meta': {'state': state}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _build_context_from_query(message, ds):
    """
    Extract intent from message and build relevant data context.
    """
    msg_lower = message.lower()
    context_parts = []
    
    # Detect state mention
    states = ds.get_unique_states()
    detected_state = 'all'
    for state in states:
        if state.lower() in msg_lower:
            detected_state = state
            break
    
    # Detect basin mention
    basins = ds.get_unique_basins()
    detected_basin = None
    for basin in basins:
        if basin.lower() in msg_lower:
            detected_basin = basin
            break
    
    # Fetch relevant data
    if detected_basin:
        data = ds.df[ds.df['Basin'] == detected_basin]
        context_parts.append(f"🏞️ {detected_basin} Basin:")
    else:
        data = ds.get_state_data(detected_state)
        context_parts.append(f"📍 {detected_state}:")
    
    if not data.empty:
        context_parts.append(f"Avg WQI: {round(float(data['WQI'].mean()), 2)}")
        context_parts.append(f"Avg BOD: {round(float(data['BOD'].mean()), 2)} mg/L")
        context_parts.append(f"Avg DO: {round(float(data['DO'].mean()), 2)} mg/L")
        context_parts.append(f"Avg FColi: {round(float(data['Fecal_Coliform'].mean()), 2)} MPN/100mL")
    
    return " | ".join(context_parts)
