"""历史任务 service 单测：扫描 / 标签 / 软删回收站。

数据落在 conftest 隔离的临时 streamlit_root 下。
"""
import json

import pytest

from backend.services.data import tasks
from backend.services.system.config import settings


def _make_issue(issue: int, title="测试标题", status="ok"):
    issues_dir = settings.streamlit_root / "data" / "issues"
    d = issues_dir / str(issue)
    d.mkdir(parents=True, exist_ok=True)
    (d / "result.json").write_text(
        json.dumps({"title": title, "topic": title, "status": status}),
        encoding="utf-8",
    )
    return d


def test_scan_issues_empty():
    res, skipped = tasks.scan_issues()
    assert res == []
    assert skipped == []


def test_scan_and_tags():
    _make_issue(1, title="甲")
    _make_issue(2, title="乙")
    res, _ = tasks.scan_issues()
    assert len(res) == 2

    tasks.set_task_tags(1, ["hot", "ai"])
    assert tasks.get_task_tags(1) == ["hot", "ai"]
    # scan 把标签带上
    res, _ = tasks.scan_issues()
    t1 = next(t for t in res if t["issue"] == 1)
    assert set(t1["tags"]) == {"hot", "ai"}
    # 按标签过滤
    out = tasks.filter_tasks(res, "", "", "", "", "hot")
    assert len(out) == 1 and out[0]["issue"] == 1
    # 清空标签
    tasks.set_task_tags(1, [])
    assert tasks.get_task_tags(1) == []


def test_soft_delete_and_trash():
    _make_issue(5)
    res, _ = tasks.scan_issues()
    assert any(t["issue"] == 5 for t in res)

    r = tasks.delete_task(5)
    assert r["issue"] == 5 and "trashed" in r
    # 不在库里
    res, _ = tasks.scan_issues()
    assert not any(t["issue"] == 5 for t in res)
    # 在回收站
    assert tasks.list_trash_tasks()["total"] == 1
    # 恢复
    tasks.restore_task(5)
    res, _ = tasks.scan_issues()
    assert any(t["issue"] == 5 for t in res)
    # 彻底删除
    tasks.delete_task(5)
    tasks.purge_task(5)
    assert tasks.list_trash_tasks()["total"] == 0


def test_delete_missing_404():
    with pytest.raises(tasks.TasksError) as e:
        tasks.delete_task(999999)
    assert e.value.status_code == 404


def test_empty_trash():
    _make_issue(7)
    tasks.delete_task(7)
    tasks.empty_task_trash()
    assert tasks.list_trash_tasks()["total"] == 0
