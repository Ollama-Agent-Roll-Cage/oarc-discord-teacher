#!/usr/bin/env python3
"""
Test script for the Ollama Teacher Bot Web API
This helps diagnose issues with the HTTP API endpoints
"""
import requests
import json
import logging
import sys
import os
import time
from urllib.parse import urljoin

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WebAPITester")

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Default API base URL
API_BASE_URL = "http://127.0.0.1:8080"

def test_api_endpoint(endpoint, method="GET", data=None, expected_status=200):
    """Test a specific API endpoint and return the result"""
    url = urljoin(API_BASE_URL, endpoint)
    logger.info(f"Testing {method} {url}")
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, timeout=5)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, timeout=5)
        elif method.upper() == "DELETE":
            response = requests.delete(url, timeout=5)
        else:
            logger.error(f"Unsupported method: {method}")
            return False, None
            
        logger.info(f"Status code: {response.status_code}")
        
        # Check if response is valid JSON
        try:
            if response.text:
                result = response.json()
                logger.info(f"Response is valid JSON: {type(result)}")
                
                # Print a preview of the response content
                if isinstance(result, dict):
                    preview = {k: str(v)[:100] + "..." if isinstance(v, str) and len(str(v)) > 100 else v 
                              for k, v in result.items()}
                    logger.info(f"Response preview: {json.dumps(preview, indent=2)}")
                elif isinstance(result, list):
                    logger.info(f"Response is a list with {len(result)} items")
                    if result and len(result) > 0:
                        logger.info(f"First item preview: {json.dumps(result[0], indent=2)}")
                else:
                    logger.info(f"Response: {result}")
            else:
                logger.warning("Empty response body")
                result = None
        except json.JSONDecodeError as e:
            logger.error(f"Response is not valid JSON: {e}")
            logger.error(f"Response text: {response.text[:200]}")
            return False, response.text
            
        # Check if status code is as expected
        if response.status_code == expected_status:
            logger.info(f"✅ Test passed ({response.status_code} == {expected_status})")
            return True, result
        else:
            logger.error(f"❌ Test failed: Expected status {expected_status}, got {response.status_code}")
            return False, result
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Request failed: {e}")
        return False, None

def test_cors(endpoint):
    """Test CORS headers for an endpoint"""
    url = urljoin(API_BASE_URL, endpoint)
    logger.info(f"Testing CORS for {url}")
    
    try:
        # Send OPTIONS request
        response = requests.options(url, headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET"
        }, timeout=5)
        
        logger.info(f"Status code: {response.status_code}")
        
        # Check for CORS headers
        cors_headers = [
            "Access-Control-Allow-Origin",
            "Access-Control-Allow-Methods",
            "Access-Control-Allow-Headers"
        ]
        
        missing_headers = []
        for header in cors_headers:
            if header not in response.headers:
                missing_headers.append(header)
                logger.error(f"❌ Missing CORS header: {header}")
            else:
                logger.info(f"✅ {header}: {response.headers[header]}")
                
        if not missing_headers:
            logger.info("✅ All CORS headers present")
            return True
        else:
            logger.error(f"❌ Missing CORS headers: {', '.join(missing_headers)}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ CORS test failed: {e}")
        return False

def run_all_tests():
    """Run all API tests"""
    logger.info("=== Starting Web API Tests ===")
    
    # Test base endpoints
    test_results = {
        "dashboard_stats": test_api_endpoint("/api/dashboard/stats"),
        "base_models": test_api_endpoint("/api/models/base"),
        "vision_models": test_api_endpoint("/api/models/vision"),
        "settings": test_api_endpoint("/api/settings"),
        "cors_dashboard": test_cors("/api/dashboard/stats"),
        "cors_models": test_cors("/api/models/base")
    }
    
    # Print summary
    logger.info("\n=== Test Results Summary ===")
    for test_name, (success, _) in test_results.items():
        logger.info(f"{test_name}: {'✅ PASSED' if success else '❌ FAILED'}")
    
    return all(success for success, _ in test_results.values())

def test_browser_fetch():
    """Generate a browser fetch test script"""
    logger.info("Generating browser fetch test script")
    
    script = """
// Copy and paste this into your browser's developer console

// Test GET endpoint
console.log("Testing GET /api/models/base...");
fetch("http://localhost:8080/api/models/base")
    .then(response => {
        console.log("Status:", response.status);
        console.log("Headers:", response.headers);
        return response.json();
    })
    .then(data => {
        console.log("Data:", data);
        console.log("TEST PASSED");
    })
    .catch(error => {
        console.error("ERROR:", error);
        console.log("TEST FAILED");
    });

// Test CORS with OPTIONS
console.log("Testing CORS with OPTIONS...");
fetch("http://localhost:8080/api/models/base", {
    method: "OPTIONS",
    headers: {
        "Origin": "http://example.com",
        "Access-Control-Request-Method": "GET"
    }
})
    .then(response => {
        console.log("Status:", response.status);
        console.log("Headers:", response.headers);
        console.log("TEST PASSED");
    })
    .catch(error => {
        console.error("ERROR:", error);
        console.log("TEST FAILED");
    });
    """
    
    print("\n=== Browser Test Script ===")
    print(script)
    
    # Save to file
    script_path = os.path.join(PROJECT_ROOT, "tools", "browser_test.js")
    with open(script_path, "w") as f:
        f.write(script)
        
    logger.info(f"Browser test script saved to {script_path}")

if __name__ == "__main__":
    # Check if a specific port was provided
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
            API_BASE_URL = f"http://127.0.0.1:{port}"
            logger.info(f"Using custom port: {port}")
        except ValueError:
            logger.warning(f"Invalid port number: {sys.argv[1]}, using default: 8080")
    
    logger.info(f"Testing API at: {API_BASE_URL}")
    success = run_all_tests()
    test_browser_fetch()
    
    if success:
        logger.info("✅ All tests passed!")
        sys.exit(0)
    else:
        logger.error("❌ Some tests failed. Check the logs for details.")
        sys.exit(1)
