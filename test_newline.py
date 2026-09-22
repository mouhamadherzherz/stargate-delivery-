import license_manager

print("Testing newline...")
guid = '81B2-5D8A'
code = license_manager.generate_short_license(guid, 30)

# Add a newline
code_with_newline = code + '\n'

is_valid, msg, exp = license_manager.verify_license_code(code_with_newline)
print('Newline result:', is_valid, msg)