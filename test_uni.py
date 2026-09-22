import license_manager

print("Testing universal code...")
# Admin generates code for UNIVERSAL
code = license_manager.generate_short_license("UNIVERSAL", 30)
print('Code:', code)

is_valid, msg, exp = license_manager.verify_license_code(code)
print('Universal result:', is_valid, msg)