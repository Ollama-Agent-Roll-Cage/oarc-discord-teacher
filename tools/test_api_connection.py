#!/usr/bin/env python3
"""
Test script for OARC Discord Teacher UI API connections
This script tests all API endpoints and provides detailed diagnostics
"""

import os
import sys
import logging
import json
import requests
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("APIConnectionTest")

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def test_api_endpoints(port=8080):
    """Test all API endpoints and print detailed results"""
    base_url = f"http://localhost:{port}/api"
    
    endpoints = [
        {"method": "GET", "endpoint": "/dashboard/stats", "name": "Dashboard Stats"},
        {"method": "GET", "endpoint": "/models/base", "name": "Base Models"},
        {"method": "GET", "endpoint": "/models/vision", "name": "Vision Models"},
        {"method": "GET", "endpoint": "/settings", "name": "Settings"},
        {"method": "GET", "endpoint": "/users", "name": "Users"},
        {"method": "GET", "endpoint": "/conversations", "name": "Conversations"},
        {"method": "GET", "endpoint": "/papers", "name": "Papers"},
        {"method": "GET", "endpoint": "/logs", "name": "Logs"},
        {"method": "GET", "endpoint": "/system/info", "name": "System Info"},
        {"method": "POST", "endpoint": "/bot/start", "name": "Start Bot", "data": {}},
        {"method": "POST", "endpoint": "/bot/stop", "name": "Stop Bot", "data": {}}
    ]
    
    print(f"\n=== Testing API endpoints on {base_url} ===\n")
    
    results = []
    total_success = 0
    
    for endpoint_info in endpoints:
        method = endpoint_info["method"]
        endpoint = endpoint_info["endpoint"]
        name = endpoint_info["name"]
        data = endpoint_info.get("data", None)
        
        url = f"{base_url}{endpoint}"
        
        try:
            if method == "GET":
                logger.info(f"Testing GET {url}")
                response = requests.get(url, timeout=10)
            elif method == "POST":
                logger.info(f"Testing POST {url}")
                response = requests.post(url, json=data, timeout=10)
            else:
                logger.error(f"Invalid method {method}")
                continue
            
            success = 200 <= response.status_code < 300
            
            if success:
                total_success += 1
                try:
                    response_data = response.json()
                    data_preview = json.dumps(response_data)[:100] + "..." if len(json.dumps(response_data)) > 100 else json.dumps(response_data)
                except json.JSONDecodeError:
                    data_preview = "Invalid JSON response"
            else:
                try:
                    error_data = response.json()
                    data_preview = json.dumps(error_data)
                except:
                    data_preview = response.text[:100] + "..." if len(response.text) > 100 else response.text
            
            results.append({
                "name": name,
                "url": url,
                "method": method,
                "status_code": response.status_code,
                "success": success,
                "data_preview": data_preview
            })
            
            if success:
                logger.info(f"✅ {name} - {response.status_code} - Success")
            else:
                logger.error(f"❌ {name} - {response.status_code} - Failed: {data_preview}")
            
        except requests.exceptions.Timeout:
            logger.error(f"❌ {name} - Timeout")
            results.append({
                "name": name,
                "url": url,
                "method": method,
                "status_code": "Timeout",
                "success": False,
                "data_preview": "Request timed out"
            })
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ {name} - Connection Error")
            results.append({
                "name": name,
                "url": url,
                "method": method,
                "status_code": "Connection Error",
                "success": False,
                "data_preview": "Could not connect to server"
            })
        except Exception as e:
            logger.error(f"❌ {name} - Exception: {str(e)}")
            results.append({
                "name": name,
                "url": url,
                "method": method,
                "status_code": "Exception",
                "success": False,
                "data_preview": str(e)
            })
    
    # Print summary
    print("\n=== API Test Results ===\n")
    print(f"Total Success: {total_success}/{len(endpoints)}")
    
    # Print detailed results
    print("\n=== Detailed Results ===\n")
    for result in results:
        status = "✅ Success" if result["success"] else "❌ Failed"
        print(f"{status} - {result['name']} ({result['method']} {result['url']})")
        print(f"Status Code: {result['status_code']}")
        print(f"Response: {result['data_preview']}")
        print("")
    
    # Print recommendations for failed endpoints
    failed = [r for r in results if not r["success"]]
    if failed:
        print("\n=== Recommendations for Failed Endpoints ===\n")
        
        for failure in failed:
            print(f"Endpoint: {failure['name']} ({failure['method']} {failure['url']})")
            
            if failure['status_code'] == 500:
                print("- Check server logs for detailed error information")
                print("- Look for exceptions in the API handler for this endpoint")
                print("- Verify the data format being returned from the handler")
            
            if failure['name'] == "Settings":
                print("- Check if the .env file exists and is readable")
                print("- Verify that the settings handler has proper error handling")
                print("- Try creating a minimal .env file if it doesn't exist")
            
            if "bot" in failure['url'].lower():
                print("- Verify that the BotManager class is properly instantiated")
                print("- Check for proper error handling in the bot control methods")
            
            print("")
    
    # Offer to test again if any failed
    if failed and input("\nWould you like to try to fix common issues? (y/n): ").lower() == 'y':
        fix_common_issues(failed)
    
    return total_success == len(endpoints)

def fix_common_issues(failed_endpoints):
    """Attempt to fix common issues with failed endpoints"""
    settings_failed = any(f["name"] == "Settings" for f in failed_endpoints)
    
    if settings_failed:
        print("\nAttempting to fix Settings API issues...")
        
        # Check if .env file exists
        env_path = os.path.join(PROJECT_ROOT, ".env")
        if not os.path.exists(env_path):
            print("Creating minimal .env file...")
            with open(env_path, "w") as f:
                f.write("# OARC Discord Teacher Bot Environment\n")
                f.write("DISCORD_TOKEN=\n")
                f.write("OLLAMA_MODEL=phi4:latest\n")
                f.write("OLLAMA_VISION_MODEL=llava:latest\n")
                f.write("DATA_DIR=data\n")
                f.write("TEMPERATURE=0.7\n")
                f.write("TIMEOUT=120.0\n")
                f.write("CHANGE_NICKNAME=True\n")
            print(f"Created minimal .env file at {env_path}")
        else:
            print(f".env file already exists at {env_path}")
        
        # Test API again
        print("\nRe-testing settings API...")
        port = 8080
        url = f"http://localhost:{port}/api/settings"
        
        try:
            response = requests.get(url, timeout=10)
            if 200 <= response.status_code < 300:
                print(f"✅ Settings API now working! Status: {response.status_code}")
                try:
                    data = response.json()
                    print(f"Settings data: {json.dumps(data, indent=2)[:200]}...")
                except:
                    print("Response received but not valid JSON")
            else:
                print(f"❌ Settings API still failing with status {response.status_code}")
                print("You may need to restart the UI application")
        except Exception as e:
            print(f"❌ Error testing settings API: {str(e)}")
    
    # Check for other common issues
    bot_control_failed = any("bot" in f["url"].lower() for f in failed_endpoints)
    if bot_control_failed:
        print("\nBot control API issues detected...")
        print("Recommendations:")
        print("1. Ensure the BotManager class is properly instantiated in your UI code")
        print("2. Verify the bot_manager.py file has proper error handling")
        print("3. Restart the UI application to reinitialize the bot manager")

def main():
    """Main function"""
    # Use command line port or default to 8080
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    
    print(f"Testing API on port {port}...")
    success = test_api_endpoints(port)
    
    if success:
        print("\n✅ All API endpoints are working correctly!")
    else:
        print("\n❌ Some API endpoints are not working correctly.")
        print("Please check the recommendations above and consider restarting the UI application.")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
