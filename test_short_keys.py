import license_manager

print('=== SHORT KEY SYSTEM TEST ===')
short_id = license_manager.get_short_machine_id()
print('Short ID:', short_id)

code = license_manager.generate_short_license(short_id, 30)
print('Generated Code (30 days):', code)

is_valid, msg, exp = license_manager.verify_license_code(code)
print('Verify Result:', is_valid, msg, exp)

print('\nTesting Universal Code:')
uni_code = license_manager.generate_short_license('UNIVERSAL', 365)
print('Universal Code (365 days):', uni_code)
uni_valid, uni_msg, uni_exp = license_manager.verify_license_code(uni_code)
print('Universal Verify Result:', uni_valid, uni_msg, uni_exp)