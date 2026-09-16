# -*- coding: utf-8 -*-
"""
Gemini Client Helper - Stargate Delivery System
High-speed, auto-caching, multi-fallback Google Gemini AI client
"""
import json
import requests
import re
import urllib.request
import urllib.error


_CACHED_WORKING_MODEL = "gemini-1.5-flash-latest"

PRIORITY_MODELS = [
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash-exp",
    "gemini-1.5-pro",
    "gemini-pro"
]


def list_available_models_rest(api_key):
    key = (api_key or '').strip()
    if not key:
        return []
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    try:
        resp = requests.get(url, headers={"User-Agent": "StargateDelivery/3.0"}, timeout=10)
        data = resp.json()
        models = []
        for m in data.get('models', []):
            methods = m.get('supportedGenerationMethods', [])
            if 'generateContent' in methods:
                name = m.get('name', '').replace('models/', '')
                if name:
                    models.append(name)
        if models:
            return models
    except Exception:
        pass

    # Fallback to standard urllib if requests fails or returns no models
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "StargateDelivery/3.0"})
        with urllib.request.urlopen(req, timeout=7) as resp:
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


def generate_content_rest(api_key, model_name, prompt, max_tokens=800):
    key = (api_key or '').strip()
    if not key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.25, "maxOutputTokens": max_tokens, "topP": 0.85}
    }
    try:
        resp = requests.post(url, json=payload, headers={"User-Agent": "StargateDelivery/3.0"}, timeout=20)
        res = resp.json()
        candidates = res.get('candidates', [])
        if candidates:
            parts = candidates[0].get('content', {}).get('parts', [])
            if parts:
                return parts[0].get('text', '')
    except Exception:
        pass

    # Fallback to standard urllib if requests fails
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "StargateDelivery/3.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            candidates = res.get('candidates', [])
            if candidates:
                parts = candidates[0].get('content', {}).get('parts', [])
                if parts:
                    return parts[0].get('text', '')
    except Exception:
        pass
    return None


def test_gemini_api_key(api_key):
    """اختبار والتحقق من مفتاح Gemini وتحديد النموذج الشغال فائق السرعة."""
    global _CACHED_WORKING_MODEL
    key = (api_key or '').strip()
    if not key:
        return False, "يرجى إدخال مفتاح API أولاً في خانة المفتاح.", None

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

    last_err = ""
    for m_name in test_queue[:4]:
        try:
            reply = generate_content_rest(key, m_name, "أجب بكلمة واحدة فقط: متصل", max_tokens=30)
            if reply and reply.strip():
                _CACHED_WORKING_MODEL = m_name
                clean_reply = reply.strip()[:30]
                return True, f"تم التحقق والاتصال بنجاح! المحرك السحابي الذكي جاهز ⚡ (الرد: {clean_reply})", m_name
        except urllib.error.HTTPError as he:
            try:
                err_body = he.read().decode('utf-8', errors='ignore')
                err_json = json.loads(err_body)
                last_err = err_json.get('error', {}).get('message', str(he))
            except Exception:
                last_err = str(he)
        except Exception as ex:
            last_err = str(ex)

    msg = f"تعذر تفعيل المفتاح. تأكد من نسخه بدقة من Google AI Studio."
    if "API_KEY_INVALID" in last_err or "not valid" in last_err.lower():
        msg = "المفتاح المدخل غير صحيح (Invalid API Key). يرجى نسخه مجدداً من Google AI Studio."
    elif "RESOURCE_EXHAUSTED" in last_err or "quota" in last_err.lower():
        msg = "تم استهلاك الحصة المجانية للمفتاح حالياً، يرجى المحاولة لاحقاً أو تجربة مفتاح آخر."
    return False, msg, None


def ask_gemini(api_key, prompt, system_context=""):
    """توليد رد الذكاء الاصطناعي بسرعة فائقة مع التبديل الذكي."""
    global _CACHED_WORKING_MODEL
    key = (api_key or '').strip()
    if not key:
        return None

    full_prompt = f"{system_context}\n\nسؤال المستخدم:\n{prompt}" if system_context else prompt

    target_models = []
    if _CACHED_WORKING_MODEL:
        target_models.append(_CACHED_WORKING_MODEL)
    for p in PRIORITY_MODELS:
        if p not in target_models:
            target_models.append(p)

    for m_name in target_models[:4]:
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
        yield "يرجى التحقق من تفعيل مفتاح Google Gemini في صفحة الإعدادات."
        return

    full_prompt = f"{system_context}\n\nسؤال المستخدم:\n{prompt}" if system_context else prompt

    target_models = []
    if _CACHED_WORKING_MODEL:
        target_models.append(_CACHED_WORKING_MODEL)
    for p in PRIORITY_MODELS:
        if p not in target_models:
            target_models.append(p)

    for m_name in target_models[:4]:
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
            with urllib.request.urlopen(req, timeout=12) as resp:
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
    yield "عذراً، فشل الاتصال بخوادم Google AI. يرجى التحقق من اتصال الإنترنت أو صحة المفتاح."


