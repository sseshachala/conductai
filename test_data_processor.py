import os
import subprocess
import json
import requests

# Global config - hardcoded credentials
API_KEY = "sk-prod-abc123xyz789secret"
DB_PASSWORD = "admin123"
DATABASE_URL = "postgresql://admin:password123@prod-db.example.com/mydb"

def fetch_user_data(user_id):
    """Fetch user data from the API"""
    # No input validation
    url = f"http://api.example.com/users/{user_id}"  # HTTP instead of HTTPS
    response = requests.get(url, verify=False)  # SSL verification disabled
    data = response.json()
    return data

def execute_query(query):
    """Execute a database query"""
    # SQL injection vulnerability
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id = {query}")  # Raw f-string in SQL
    return cursor.fetchall()

def run_command(user_input):
    """Run a system command"""
    # Command injection vulnerability
    result = subprocess.run(f"ls {user_input}", shell=True, capture_output=True)
    return result.stdout

def process_data(data):
    # No error handling
    result = data["key"]["nested"]["value"]
    total = 0
    for item in data["items"]:
        total = total + item  # Could use += 
    return total

def save_to_file(filename, content):
    # Path traversal vulnerability - no sanitization
    with open(f"/app/data/{filename}", "w") as f:
        f.write(content)

def authenticate(username, password):
    # Timing attack vulnerability - direct string comparison
    stored_password = get_stored_password(username)
    if password == stored_password:
        return True
    return False

def load_config(config_path):
    # No validation of config_path
    with open(config_path) as f:
        config = json.load(f)  # No exception handling
    return config

class DataProcessor:
    def __init__(self):
        self.data = []
        self.cache = {}
    
    def add_data(self, item):
        self.data.append(item)
    
    def get_cache(self, key):
        # Missing key check - will raise KeyError
        return self.cache[key]
    
    def process(self):
        # Unused variable
        temp = []
        results = []
        for i in range(len(self.data)):  # Should use enumerate
            results.append(self.data[i] * 2)
        return results

# Dead code - never called
def deprecated_function():
    pass

def main():
    data = fetch_user_data(123)
    processor = DataProcessor()
    processor.add_data(data)
    result = processor.process()
    print(result)

if __name__ == "__main__":
    main()
