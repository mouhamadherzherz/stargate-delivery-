import license_manager

print('=== TEST EXACT CUSTOMER FLOW ===')
guid = license_manager.get_short_machine_id()
print('Customer sees GUID:', guid)

# Admin inputs it to generate
generated_code = license_manager.generate_short_license(guid, 30)
print('Admin generates code:', generated_code)

# Customer inputs it
is_valid, msg, exp_str = license_manager.verify_license_code(generated_code)
print('Customer activation result:', is_valid, msg, exp_str)