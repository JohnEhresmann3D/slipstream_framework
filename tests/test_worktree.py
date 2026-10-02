from slipstream.loop.workspaces.git_worktree import GitWorktreePolicy, GitWorktreeWorkspaceManager


def test_git_worktree_manager_isolates_workspace(git_repo):
    manager = GitWorktreeWorkspaceManager(
        GitWorktreePolicy(preserve_on_success=False, preserve_on_needs_human=False, preserve_on_error=False)
    )
    handle = manager.prepare("worktree-test", git_repo)
    assert handle.isolated
    assert handle.path != git_repo
    assert (handle.path / "README.md").exists()
    manager.cleanup(handle, "DONE")
    assert not handle.path.exists()
