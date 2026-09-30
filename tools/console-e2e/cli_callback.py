"""Exercise the actual CLI loopback callback without persisting credentials."""
import contextlib
import io
import json
import sys
import urllib.request
import webbrowser

from conduct_cli.main import _web_login_flow


def main():
    webbrowser.open = lambda url: print("LOGIN_URL " + url, file=sys.__stdout__, flush=True)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = _web_login_flow("https://localhost:3444", "https://localhost:3443")
        assert result["workspace_id"] == "bbbbbbbb-0000-4000-8000-000000000001"
        request = urllib.request.Request("https://localhost:3444/projects", headers={
            "Authorization": "Bearer " + result["agent_token"]})
        with urllib.request.urlopen(request, timeout=15) as response:
            assert response.status == 200 and isinstance(json.load(response), list)
    print("CLI_PASS", flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        print("CLI_FAIL; credentials omitted", flush=True)
        raise SystemExit(1)
