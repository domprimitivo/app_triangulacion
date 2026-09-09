import requests
import sys
import json
from datetime import datetime

class MileforumAPITester:
    def __init__(self, base_url="https://bimestral-activation.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        if headers is None:
            headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)

            success = response.status_code == expected_status
            
            result = {
                'test': name,
                'endpoint': endpoint,
                'method': method,
                'expected_status': expected_status,
                'actual_status': response.status_code,
                'success': success,
                'response_data': None,
                'error': None
            }

            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    result['response_data'] = response.json()
                except:
                    result['response_data'] = response.text
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    result['error'] = error_data
                    print(f"   Error: {error_data}")
                except:
                    result['error'] = response.text
                    print(f"   Error: {response.text}")

            self.test_results.append(result)
            return success, result['response_data']

        except Exception as e:
            print(f"❌ Failed - Exception: {str(e)}")
            result = {
                'test': name,
                'endpoint': endpoint,
                'method': method,
                'expected_status': expected_status,
                'actual_status': None,
                'success': False,
                'response_data': None,
                'error': str(e)
            }
            self.test_results.append(result)
            return False, {}

    def test_api_root(self):
        """Test API root endpoint"""
        return self.run_test("API Root", "GET", "api/", 200)

    def test_get_domains(self):
        """Test domains endpoint"""
        success, response = self.run_test("Get Domains", "GET", "api/domains", 200)
        if success and response:
            domains = response.get('domains', [])
            print(f"   Found {len(domains)} domains")
            if len(domains) == 12:
                print("   ✅ Correct number of domains (12)")
            else:
                print(f"   ⚠️  Expected 12 domains, got {len(domains)}")
        return success

    def test_register_user_valid(self):
        """Test user registration with valid data"""
        test_data = {
            "name": f"Test User {datetime.now().strftime('%H%M%S')}",
            "email": f"test_{datetime.now().strftime('%H%M%S')}@example.com",
            "domain": "abogado"
        }
        
        success, response = self.run_test(
            "Register User (Valid)", 
            "POST", 
            "api/register", 
            200, 
            data=test_data
        )
        
        if success and response:
            print(f"   ✅ User registered with ID: {response.get('id')}")
        
        return success

    def test_register_user_invalid_domain(self):
        """Test user registration with invalid domain"""
        test_data = {
            "name": "Test User Invalid",
            "email": f"invalid_{datetime.now().strftime('%H%M%S')}@example.com",
            "domain": "invalid_domain"
        }
        
        return self.run_test(
            "Register User (Invalid Domain)", 
            "POST", 
            "api/register", 
            400, 
            data=test_data
        )

    def test_register_user_duplicate_email(self):
        """Test user registration with duplicate email"""
        # First registration
        test_data = {
            "name": "Test User Duplicate",
            "email": "duplicate@example.com",
            "domain": "contador"
        }
        
        # Try first registration
        self.run_test(
            "Register User (First)", 
            "POST", 
            "api/register", 
            200, 
            data=test_data
        )
        
        # Try duplicate registration
        return self.run_test(
            "Register User (Duplicate Email)", 
            "POST", 
            "api/register", 
            400, 
            data=test_data
        )

    def test_analytics_track(self):
        """Test analytics tracking"""
        test_data = {
            "event_type": "test_event",
            "event_data": {
                "test": True,
                "timestamp": datetime.now().isoformat()
            }
        }
        
        success, response = self.run_test(
            "Track Analytics Event", 
            "POST", 
            "api/analytics/track", 
            200, 
            data=test_data
        )
        
        if success and response:
            print(f"   ✅ Event tracked with ID: {response.get('event_id')}")
        
        return success

    def test_analytics_get_events(self):
        """Test getting analytics events"""
        return self.run_test("Get Analytics Events", "GET", "api/analytics/events", 200)

    def test_analytics_summary(self):
        """Test analytics summary"""
        return self.run_test("Get Analytics Summary", "GET", "api/analytics/summary", 200)

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting Mileforum API Tests")
        print("=" * 50)
        
        # Basic API tests
        self.test_api_root()
        self.test_get_domains()
        
        # Registration tests
        self.test_register_user_valid()
        self.test_register_user_invalid_domain()
        self.test_register_user_duplicate_email()
        
        # Analytics tests
        self.test_analytics_track()
        self.test_analytics_get_events()
        self.test_analytics_summary()
        
        # Print summary
        print("\n" + "=" * 50)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print("❌ Some tests failed")
            print("\nFailed tests:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  - {result['test']}: {result.get('error', 'Status code mismatch')}")
            return 1

def main():
    tester = MileforumAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())