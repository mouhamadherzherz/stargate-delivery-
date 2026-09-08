# -*- coding: utf-8 -*-
"""
Gemini Client Helper - Stargate Delivery System
High-speed, auto-caching, multi-fallback Google Gemini AI client
"""
import json
import urllib.request
import urllib.parse

_CACHED_WORKING_MODEL = "gemini-1.5-flash-latest"

PRIORITY_MODELS = [
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-1.5-pro",
    "gemini-pro"
]


def list_available_models_rest(api_key):
    """جلب قائمة النماذج المتاحة لمفتاح الـ API عبر REST API مباشرة وبشكل سريع."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key.strip()}"
        req = urllib.request.Request(url, headers={"User-Agent": "StargateDelivery/3.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            models = []
            for m in data.get('models', []):
                methods = m.get('supportedGenerationMethods', [])
                if 'generateContent' in methods:
                    name = m.get('name', '').replace('models/', '')
                    if name:
                        models.append(name)
            return models
    except Exception:
        return []


def generate_content_rest(api_key, model_name, prompt, max_tokens=700):
    """إرسال طلب توليد فائق السرعة عبر REST API مباشرة."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.25,
            "maxOutputTokens": max_tokens,
            "topP": 0.85
        }
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "StargateDelivery/3.0"}
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        candidates = res.get('candidates', [])
        if candidates:
            parts = candidates[0].get('content', {}).get('parts', [])
            if parts:
                return parts[0].get('text', '')
    return None


def test_gemini_api_key(api_key):
    """اختبار والتحقق من مفتاح Gemini وتحديد النموذج الشغال فائق السرعة."""
    global _CACHED_WORKING_MODEL
    key = (api_key or '').strip()
    if not key:
        return False, "يرجى إدخال مفتاح API أولاً.", None

    # 1. جلب النماذج المتاحة من حساب جوجل
    discovered = list_available_models_rest(key)
    
    test_queue = []
    if _CACHED_WORKING_MODEL and _CACHED_WORKING_MODEL in discovered:
        test_queue.append(_CACHED_WORKING_MODEL)
    for p in PRIORITY_MODELS:
        if p in discovered and p not in test_queue:
            test_queue.append(p)
    for d in discovered:
        if d not in test_queue:
            test_queue.append(d)
    if not test_queue:
        test_queue = PRIORITY_MODELS

    for m_name in test_queue[:4]:
        try:
            reply = generate_content_rest(key, m_name, "أجب بكلمة واحدة فقط: شغال", max_tokens=30)
            if reply and reply.strip():
                _CACHED_WORKING_MODEL = m_name
                clean_reply = reply.strip()[:30]
                return True, f"تم التحقق والاتصال بنجاح! المحرك السحابي السريع جاهز ⚡ (رد: {clean_reply})", m_name
        except Exception:
            continue

    return False, "تعذر تفعيل مفتاح الذكاء الاصطناعي، يرجى التأكد من نسخه بدقة من Google AI Studio.", None


def ask_gemini(api_key, prompt, system_context=""):
    """توليد رد الذكاء الاصطناعي بسرعة فائقة مع التبديل الذكي."""
    global _CACHED_WORKING_MODEL
    key = (api_key or '').strip()
    if not key:
        return None

    full_prompt = f"{system_context}\n\nسؤال المستخدم:\n{prompt}" if system_context else prompt

    # جرب أولاً النموذج المحفوظ فوراً
    target_models = []
    if _CACHED_WORKING_MODEL:
        target_models.append(_CACHED_WORKING_MODEL)
    for p in PRIORITY_MODELS:
        if p not in target_models:
            target_models.append(p)

    for m_name in target_models[:3]:
        try:
            text = generate_content_rest(key, m_name, full_prompt, max_tokens=850)
            if text and text.strip():
                _CACHED_WORKING_MODEL = m_name
                return text.strip()
        except Exception:
            continue

    return None

def ask_gemini_stream(api_key, prompt, system_context=""):
    """توليد رد الذكاء الاصطناعي مع تدفق حي للكلمات (Streaming) ودعم الأوامر."""
    global _CACHED_WORKING_MODEL
    key = (api_key or '').strip()
    if not key:
        yield "يرجى التحقق من مفتاح API."
        return

    full_prompt = f"{system_context}\n\nسؤال المستخدم:\n{prompt}" if system_context else prompt

    target_models = []
    if _CACHED_WORKING_MODEL:
        target_models.append(_CACHED_WORKING_MODEL)
    for p in PRIORITY_MODELS:
        if p not in target_models:
            target_models.append(p)

    for m_name in target_models[:3]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:streamGenerateContent?alt=sse&key={key}"
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "temperature": 0.25,
                "maxOutputTokens": 850,
                "topP": 0.85
            }
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "StargateDelivery/3.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                _CACHED_WORKING_MODEL = m_name
                for line in resp:
                    line = line.decode('utf-8').strip()
                    if line.startswith("data:"):
                        json_str = line[5:].strip()
                        if json_str:
                            try:
                                chunk_data = json.loads(json_str)
                                candidates = chunk_data.get('candidates', [])
                                if candidates:
                                    parts = candidates[0].get('content', {}).get('parts', [])
                                    if parts:
                                        chunk_text = parts[0].get('text', '')
                                        if chunk_text:
                                            yield chunk_text
                            except Exception:
                                pass
                return
        except Exception:
            continue
    yield "عذراً، فشل الاتصال بخوادم الذكاء الاصطناعي."
