# test_vuln.py — security classifier test fixture
# DO NOT deploy. Contains intentional vulnerabilities for Security Loop testing.

import ssl
import requests

AWS_KEY = "AKIA1234567890ABCDEF"          # line 7  — critical: AWS Access Key ID
GITHUB_TOKEN = "ghp_" + "A" * 36          # line 8  — high: GitHub PAT

def authenticate(user):
    password = 'hardcoded_secret_p4ss'    # line 11 — high: hardcoded password
    api_key = 'sk-abcdefghijklmnopqrstu'  # line 12 — high: OpenAI key
    return password, api_key

def run_user_code(code_input):
    result = eval(code_input)             # line 16 — high: eval() injection
    return result

def execute_command(cmd):
    exec(cmd)                              # line 20 — high: exec() injection

def fetch_data(url):
    resp = requests.get(url, verify=False) # line 23 — medium: TLS verification bypassed
    return resp.json()

def insecure_ssl():
    ctx = ssl.create_default_context()
    ctx.verify_mode = ssl.CERT_NONE        # line 28 — high: SSL verification disabled
    return ctx

def read_file(path):
    with open("../../etc/passwd") as f:    # line 32 — medium: path traversal
        return f.read()
