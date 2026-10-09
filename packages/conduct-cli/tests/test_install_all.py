from types import SimpleNamespace

from conduct_cli.commands import playbooks as cli


def test_install_all_forwards_authenticated_token_to_every_install(monkeypatch):
    installed = []
    token = "cond_agt_test"

    monkeypatch.setattr(
        cli,
        "_require_auth",
        lambda _args: ("https://api.example.test", "workspace-id", token),
    )
    monkeypatch.setattr(cli, "cmd_install", installed.append)

    cli.cmd_install_all(
        SimpleNamespace(project="Smoke Test", repo="owner/repo", input=[])
    )

    assert [args.slug for args in installed] == cli._ALL_SLUGS
    assert all(args.server == "https://api.example.test" for args in installed)
    assert all(args.workspace == "workspace-id" for args in installed)
    assert all(args.token == token for args in installed)


def test_install_repo_flag_satisfies_required_repo_input(monkeypatch):
    posted = []

    def fake_req(method, url, _hdrs, body=None):
        if method == "GET":
            return {"name": "Autopilot", "icon": "", "requires_repo": True, "inputs": {"repo": {}}}
        posted.append(body)
        return {"id": "wf-1", "name": body["name"]}

    monkeypatch.setattr(cli, "_require_auth", lambda _args: ("https://api.example.test", "ws", "tok"))
    monkeypatch.setattr(cli.api, "req", fake_req)

    cli.cmd_install(SimpleNamespace(slug="autopilot_full", repo="owner/repo", input=[], project=None, name=None))

    assert posted[0]["inputs"]["repo"] == "owner/repo"
