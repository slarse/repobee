"""Helper functions for the integration tests."""
import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile

import _repobee.ext
import gitlab

from const import (
    ORG_NAME,
    LOCAL_BASE_URL,
    TOKEN,
    MASTER_ORG_NAME,
    BASE_DOMAIN,
    LOCAL_DOMAIN,
    TEACHER,
)


def api_instance(org_name=ORG_NAME):
    """Return a valid instance of the GitLabAPI class."""
    return _repobee.ext.gitlab.GitLabAPI(LOCAL_BASE_URL, TOKEN, org_name)


def gitlab_and_groups():
    """Return a valid gitlab instance, along with the master group and the
    target group.
    """
    gl = gitlab.Gitlab(LOCAL_BASE_URL, private_token=TOKEN, ssl_verify=False)
    master_group = gl.groups.list(search=MASTER_ORG_NAME)[0]
    target_group = gl.groups.list(search=ORG_NAME)[0]
    return gl, master_group, target_group


def run_in_docker_with_coverage(command, extra_args=None):
    assert extra_args, "extra volume args are required to run with coverage"
    coverage_command = (
        "coverage run --branch --append --source _repobee -m " + command
    )
    return run_in_docker(coverage_command, extra_args=extra_args)


def run_in_docker(command, extra_args=None):
    extra_args = " ".join(extra_args) if extra_args else ""
    docker_command = (
        "sudo docker run {} --net development --rm --name repobee "
        "repobee:test /bin/sh -c '{}'"
    ).format(extra_args, command)
    proc = subprocess.run(
        docker_command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(
        proc.stdout.decode(sys.getdefaultencoding())
    )  # for test output on failure
    return proc


def update_repo(repo_name, filename, text):
    """Add a file with the given filename and text to the repo."""
    gl = gitlab.Gitlab(LOCAL_BASE_URL, private_token=TOKEN, ssl_verify=False)
    proj, *_ = [
        p for p in gl.projects.list(search=repo_name) if p.name == repo_name
    ]
    env = os.environ.copy()
    env["GIT_SSL_NO_VERIFY"] = "true"
    env["GIT_AUTHOR_EMAIL"] = "slarse@kth.se"
    env["GIT_AUTHOR_NAME"] = "Simon"
    env["GIT_COMMITTER_EMAIL"] = env["GIT_AUTHOR_EMAIL"]
    env["GIT_COMMITTER_NAME"] = env["GIT_AUTHOR_NAME"]
    with tempfile.TemporaryDirectory() as tmpdir:
        url_with_token = (
            proj.web_url.replace(
                "https://", "https://oauth2:{}@".format(TOKEN)
            ).replace(BASE_DOMAIN, LOCAL_DOMAIN)
            + ".git"
        )
        clone_proc = subprocess.run(
            "git clone {}".format(url_with_token).split(), cwd=tmpdir, env=env
        )
        assert clone_proc.returncode == 0

        repo_dir = pathlib.Path(tmpdir) / proj.name
        new_file = repo_dir / filename
        new_file.touch()
        new_file.write_text(text)

        add_proc = subprocess.run(
            "git add {}".format(filename).split(), cwd=str(repo_dir), env=env
        )
        assert add_proc.returncode == 0

        commit_proc = subprocess.run(
            "git commit -am newfile".split(), cwd=str(repo_dir), env=env
        )
        assert commit_proc.returncode == 0

        push_proc = subprocess.run(
            "git push".split(), cwd=str(repo_dir), env=env
        )
        assert push_proc.returncode == 0

    assert proj.files.get(filename, "master").decode().decode("utf8") == text


def hash_directory(path):
    shas = []
    for dirpath, _, filenames in os.walk(str(path)):
        if ".git" in dirpath:
            continue
        files = list(
            pathlib.Path(dirpath) / filename for filename in filenames
        )
        shas += (hashlib.sha1(file.read_bytes()).digest() for file in files)
    return hashlib.sha1(b"".join(sorted(shas))).digest()


def expected_num_members_group_assertion(expected_num_members):
    def group_assertion(expected, actual):
        assert expected.name == actual.name
        # +1 member for the group owner
        assert len(actual.members.list(all=True)) == expected_num_members + 1
        assert len(actual.projects.list(all=True)) == 1
        project_name = actual.projects.list(all=True)[0].name
        assert actual.name.startswith(project_name)
        for member in actual.members.list(all=True):
            if member.username == TEACHER:
                continue
            assert member.username not in project_name
            assert member.access_level == gitlab.REPORTER_ACCESS

    return group_assertion
