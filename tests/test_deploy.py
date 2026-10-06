"""Tests for scripts/deploy.py: real git repositories, with Docker, GitHub and the health checks faked."""

from __future__ import annotations

import json
import subprocess
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, ClassVar

import deploy
import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

GREEN = [{"name": deploy.CHECK_NAME, "app": {"slug": "github-actions"}, "status": "completed", "conclusion": "success"}]


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)
    return done.stdout.strip()


class Server:
    """An Argus checkout following a throwaway origin, with Docker and GitHub faked."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.origin = tmp_path / "origin.git"
        self.work = tmp_path / "work"
        self.root = tmp_path / "server"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp_path, "clone", "-q", str(self.origin), str(self.work))
        git(self.work, "config", "user.email", "test@example.com")
        git(self.work, "config", "user.name", "Test")
        git(self.work, "checkout", "-q", "-B", "main")
        self.commit({"README.md": "argus\n"})
        git(tmp_path, "clone", "-q", str(self.origin), str(self.root))
        git(self.root, "config", "user.email", "test@example.com")
        git(self.root, "config", "user.name", "Test")

        self.docker: list[tuple[str, ...]] = []
        self.failing: set[str] = set()  # compose subcommands that fail
        self.checks: list[dict[str, Any]] = GREEN
        self.health: list[bool] = []  # answers of successive healthy() calls; True when empty
        self.messages: list[str] = []
        real_run = deploy.run

        def run(*cmd: str) -> str:
            if cmd[0] == "git":
                return real_run(*cmd)
            self.docker.append(cmd)
            if cmd[2] in self.failing:
                msg = f"docker compose {cmd[2]} failed"
                raise deploy.DeployError(msg)
            if cmd[2:4] == ("ps", "--services"):
                return "grafana\nprometheus\nblackbox"
            return ""

        monkeypatch.setattr(deploy, "ROOT", self.root)
        monkeypatch.setattr(deploy, "BAD_COMMITS", self.root / ".git" / "argus-deploy-bad-commits")
        monkeypatch.setattr(deploy, "run", run)
        monkeypatch.setattr(deploy, "repo_slug", lambda _url: "acme/argus")
        monkeypatch.setattr(deploy, "check_runs", lambda _slug, _sha: self.checks)
        monkeypatch.setattr(deploy, "healthy", lambda: self.health.pop(0) if self.health else True)
        monkeypatch.setattr(deploy, "notify", lambda _webhook, message: self.messages.append(message))

    def commit(self, files: dict[str, str], subject: str = "Change") -> str:
        """Commit files in the working clone and push them to origin's main."""
        for name, text in files.items():
            path = self.work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", subject)
        git(self.work, "push", "-q", "origin", "main")
        return git(self.work, "rev-parse", "HEAD")

    @property
    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD")

    def restarted(self) -> list[tuple[str, ...]]:
        return [cmd[3:] for cmd in self.docker if cmd[2] == "restart"]


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Server:
    return Server(tmp_path, monkeypatch)


def test_nothing_new(server: Server) -> None:
    assert deploy.main([]) == 0
    assert server.docker == []


def test_deploys_and_restarts_what_changed(server: Server) -> None:
    (server.root / ".env").write_text("DISCORD_WEBHOOK_URL=https://discord.invalid/hook\n")
    new = server.commit({"prometheus/prometheus.yml": "x", "dashboards/a.json": "{}"}, "Add a scrape job")
    assert deploy.main([]) == 0
    assert server.head == new
    assert ("docker", "compose", "up", "-d", "--build") in server.docker
    assert server.restarted() == [("prometheus",)]
    assert server.messages == [f"Argus deployed `{new[:7]}`: Add a scrape job"]


def test_dashboard_only_change_restarts_nothing(server: Server, capsys: pytest.CaptureFixture[str]) -> None:
    server.commit({"dashboards/a.json": "{}"})
    assert deploy.main([]) == 0
    assert server.restarted() == []
    assert "restarted: nothing" in capsys.readouterr().out


def test_waits_for_ci(server: Server, capsys: pytest.CaptureFixture[str]) -> None:
    old = server.head
    server.checks = []
    server.commit({"a": "1"})
    assert deploy.main([]) == 0
    assert server.head == old
    assert "is pending; waiting" in capsys.readouterr().out


def test_never_deploys_a_failed_commit(server: Server, capsys: pytest.CaptureFixture[str]) -> None:
    old = server.head
    server.checks = [{**GREEN[0], "conclusion": "failure"}]
    server.commit({"a": "1"})
    assert deploy.main([]) == 0
    assert server.head == old
    assert "is failure; not deploying it" in capsys.readouterr().out


def test_dry_run_changes_nothing(server: Server, capsys: pytest.CaptureFixture[str]) -> None:
    old = server.head
    new = server.commit({"a": "1"}, "Something")
    assert deploy.main(["--dry-run"]) == 0
    assert server.head == old
    assert server.docker == []
    assert f"would deploy {old[:7]} -> {new[:7]}: Something" in capsys.readouterr().out


def test_only_follows_main(server: Server, capsys: pytest.CaptureFixture[str]) -> None:
    git(server.root, "checkout", "-q", "--detach")
    server.commit({"a": "1"})
    assert deploy.main([]) == 0
    assert "only follows main" in capsys.readouterr().out


def test_refuses_local_edits(server: Server, capsys: pytest.CaptureFixture[str]) -> None:
    (server.root / "README.md").write_text("edited on the server\n")
    server.commit({"a": "1"})
    assert deploy.main([]) == 1
    assert "local changes" in capsys.readouterr().out


def test_refuses_local_commits(server: Server, capsys: pytest.CaptureFixture[str]) -> None:
    (server.root / "local").write_text("x")
    git(server.root, "add", "local")
    git(server.root, "commit", "-q", "-m", "local")
    server.commit({"a": "1"})
    assert deploy.main([]) == 1
    assert "not an ancestor" in capsys.readouterr().out


def test_rolls_back_when_unhealthy_and_skips_the_commit_later(server: Server) -> None:
    old = server.head
    new = server.commit({"provisioning/alerting/rules.yaml": "bad"}, "Break Grafana")
    server.health = [False, True]
    assert deploy.main([]) == 1
    assert server.head == old
    assert server.restarted() == [("grafana",), ("grafana",)]
    assert (server.root / ".git" / "argus-deploy-bad-commits").read_text() == new + "\n"
    assert server.messages == [
        (
            f"Argus deploy of `{new[:7]}` (Break Grafana) failed: Grafana or Prometheus did not come back. "
            f"Rolled back to `{old[:7]}`; it is healthy again."
        )
    ]
    server.docker.clear()
    assert deploy.main([]) == 0
    assert server.docker == []


def test_rollback_reports_a_still_unhealthy_server(server: Server) -> None:
    server.commit({"a": "1"})
    server.health = [False, False]
    assert deploy.main([]) == 1
    assert "NOT healthy either" in server.messages[0]


def test_rolls_back_when_a_step_fails(server: Server) -> None:
    old = server.head
    server.commit({"a": "1"})
    server.failing = {"restart"}
    (server.root / "blackbox").mkdir()
    server.commit({"blackbox/blackbox.yml": "x"})
    assert deploy.main([]) == 1
    assert server.head == old
    assert "rolling back failed too (docker compose restart failed)" in server.messages[0]


def test_unexpected_errors_exit_1(server: Server, monkeypatch: pytest.MonkeyPatch) -> None:
    def offline(_slug: str, _sha: str) -> list[dict[str, Any]]:
        reason = "offline"
        raise urllib.error.URLError(reason)

    monkeypatch.setattr(deploy, "check_runs", offline)
    server.commit({"a": "1"})
    assert deploy.main([]) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/acme/argus.git",
        "https://github.com/acme/argus",
        "https://github.com/acme/argus/",
        "git@github.com:acme/argus.git",
        "ssh://git@github.com/acme/argus.git",
    ],
)
def test_repo_slug(url: str) -> None:
    assert deploy.repo_slug(url) == "acme/argus"


def test_repo_slug_rejects_other_hosts() -> None:
    with pytest.raises(deploy.DeployError, match="not a GitHub repository"):
        deploy.repo_slug("https://gitlab.example.com/acme/argus.git")


def check(**fields: str) -> dict[str, Any]:
    return {**GREEN[0], **fields}


@pytest.mark.parametrize(
    ("runs", "result"),
    [
        ([check()], "success"),
        ([check(conclusion="failure"), check()], "success"),  # a passing re-run counts
        ([], "pending"),
        ([check(status="in_progress", conclusion="")], "pending"),
        ([check(conclusion="failure")], "failure"),
        ([check(conclusion="cancelled")], "failure"),
        ([{**check(), "app": {"slug": "someone-else"}}], "pending"),  # only GitHub Actions' check counts
        ([check(name="Other check")], "pending"),
    ],
)
def test_ci_result(runs: list[dict[str, Any]], result: str) -> None:
    assert deploy.ci_result(runs) == result


def test_read_env(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# comment\nA=1\nB = 'two'\nC=\"x=y\"\nnot a setting\n")
    assert deploy.read_env(env) == {"A": "1", "B": "two", "C": "x=y"}
    assert deploy.read_env(tmp_path / "missing") == {}


def test_changed_services_only_restarts_running_ones() -> None:
    changed = ["logs/loki.yaml", "blackbox/blackbox.yml", "provisioning/a", "provisioning/b", "README.md"]
    assert deploy.changed_services(changed, {"grafana", "blackbox", "prometheus"}) == ["blackbox", "grafana"]


def test_health_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    published = {"grafana": "0.0.0.0:3000", "prometheus": "127.0.0.1:9091"}
    monkeypatch.setattr(deploy, "run", lambda *cmd: published[cmd[3]])
    assert deploy.health_urls() == ["http://127.0.0.1:3000/api/health", "http://127.0.0.1:9091/-/ready"]


def test_healthy_waits_until_everything_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([False, True, True])
    monkeypatch.setattr(deploy, "health_urls", lambda: ["http://a", "http://b"])
    monkeypatch.setattr(deploy, "answers", lambda _url: next(answers))
    monkeypatch.setattr(deploy.time, "sleep", lambda _s: None)
    assert deploy.healthy()


def test_healthy_gives_up(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(deploy, "health_urls", lambda: ["http://a"])
    assert not deploy.healthy(timeout=0)
    assert "not answering: http://a" in capsys.readouterr().out


class Handler(BaseHTTPRequestHandler):
    """Answers every request with the class's status and body, and records POST bodies."""

    status = 200
    body = b"{}"
    posted: ClassVar[list[bytes]] = []

    def do_GET(self) -> None:
        self.send_response(self.status)
        self.end_headers()
        self.wfile.write(self.body)

    def do_POST(self) -> None:
        self.posted.append(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        pass


@pytest.fixture
def http() -> Iterator[str]:
    Handler.status, Handler.body = 200, b"{}"
    Handler.posted.clear()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def test_answers(http: str) -> None:
    assert deploy.answers(http + "/api/health")
    Handler.status = 503
    assert not deploy.answers(http + "/api/health")


def test_answers_nothing_listening(http: str) -> None:
    port = http.rsplit(":", 1)[1]
    assert not deploy.answers(f"http://127.0.0.1:{int(port) + 1 if int(port) < 65535 else 1}/")


def test_check_runs(http: str, monkeypatch: pytest.MonkeyPatch) -> None:
    Handler.body = json.dumps({"total_count": 1, "check_runs": GREEN}).encode()
    seen = []
    real = deploy.http_json

    def local(url: str) -> Any:  # noqa: ANN401
        seen.append(url)
        return real(http + "/")

    monkeypatch.setattr(deploy, "http_json", local)
    assert deploy.check_runs("acme/argus", "abc") == GREEN
    assert seen == ["https://api.github.com/repos/acme/argus/commits/abc/check-runs?check_name=Dashboards+%2B+config"]


def test_notify(http: str, capsys: pytest.CaptureFixture[str]) -> None:
    deploy.notify("", "not sent")
    deploy.notify(http + "/hook", "deployed")
    assert [json.loads(body) for body in Handler.posted] == [{"content": "deployed"}]
    deploy.notify("http://127.0.0.1:1/hook", "lost")
    assert "Discord notification failed" in capsys.readouterr().out


def test_run_reports_the_failing_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deploy, "ROOT", tmp_path)
    assert deploy.run("git", "--version").startswith("git version")
    with pytest.raises(deploy.DeployError, match="git rev-parse HEAD failed: fatal"):
        deploy.run("git", "rev-parse", "HEAD")
