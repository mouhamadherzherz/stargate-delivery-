from app import app
import json

client = app.test_client()

with client:
    # Set session directly
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['user_role'] = 'admin'
        sess['username'] = 'stargate'
        sess['display_name'] = 'mouhamad herz'
        sess['user_id'] = 1

    # Test sync credentials API
    res_sync = client.post('/api/system/sync-credentials')
    print("Sync credentials API response:", res_sync.status_code, res_sync.get_json())

    # Test apply update API
    res_update = client.post('/api/system/apply-update')
    print("Apply update API response:", res_update.status_code, res_update.get_json())

print("ALL IN-APP UPDATE API TESTS COMPLETED!")
