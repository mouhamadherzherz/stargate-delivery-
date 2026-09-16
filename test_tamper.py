import license_manager

print("Testing signature validation...")
# Simulated customer short ID
guid = '81B2-5D8A'
print('GUID:', guid)

# Admin generates code
code = license_manager.generate_short_license(guid, 30)
print('Code:', code)

# Let's tamper with 1 character (change last character to something else valid, e.g. A instead of P)
tampered_code = code[:-1] + ('A' if code[-1] != 'A' else 'B')
print('Tampered code:', tampered_code)

is_valid, msg, exp = license_manager.verify_license_code(tampered_code)
print('Verify tampered result:', is_valid, msg)

is_valid, msg, exp = license_manager.verify_license_code(code)
print('Verify valid result:', is_valid, msg)