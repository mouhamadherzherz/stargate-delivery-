import base64
import struct
import hashlib
import hmac

SECRET_KEY_SEED = b"STARGATE_SECRET_KEY_SEED_2024"

code = 'AP5W-U7G5-U5BV-TWAL'
clean_code = code.replace('-', '')
try:
    payload = base64.b32decode(clean_code)
    print("Decoded successfully!")
    print("Length:", len(payload))
    exp_bytes = payload[:2]
    salt_bytes = payload[2:4]
    signature_in_code = payload[4:]
    
    days = struct.unpack('>H', exp_bytes)[0]
    print(f"Days since 2024-01-01: {days}")
    
    # Let's see if it's universal
    msg_uni = b"UNIVERSAL" + exp_bytes + salt_bytes
    sig_uni = hmac.new(SECRET_KEY_SEED, msg_uni, hashlib.sha256).digest()[:6]
    if sig_uni == signature_in_code:
        print("It IS a UNIVERSAL code!")
    else:
        print("It is NOT a UNIVERSAL code.")
        
    print("Signature in code:", signature_in_code.hex())
    print("Expected Universal Sig:", sig_uni.hex())
except Exception as e:
    print("Failed to decode:", str(e))