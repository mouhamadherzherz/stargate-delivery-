with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Split around 'if __name__ == \'__main__\':'
marker_main = "if __name__ == '__main__':"
marker_routes = "# ===================== QUICK SCAN DISPATCH (Scan-and-Assign) ====================="

if marker_main in content and marker_routes in content:
    idx_main = content.find(marker_main)
    idx_routes = content.find(marker_routes)
    
    if idx_routes > idx_main:
        routes_block = content[idx_routes:]
        main_block = content[idx_main:idx_routes]
        pre_block = content[:idx_main]
        
        # Modify main block to use 127.0.0.1 for desktop and ensure reliable startup
        main_block_fixed = main_block.replace(
            "target=lambda: app.run(host='0.0.0.0', port=_port, debug=False, use_reloader=False, threaded=True)",
            "target=lambda: app.run(host='127.0.0.1', port=_port, debug=False, use_reloader=False, threaded=True)"
        )
        
        new_content = pre_block + routes_block + "\n\n" + main_block_fixed
        
        with open("app.py", "w", encoding="utf-8") as f:
            f.write(new_content)
        print("Successfully reordered app.py: all routes defined before if __name__ == '__main__'!")
    else:
        print("Routes already before __main__.")
else:
    print("Markers not found.")
