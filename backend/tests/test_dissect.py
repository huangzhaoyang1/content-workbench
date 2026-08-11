"""选题库 service 单测：保存 / 标签 / 过滤 / 软删回收站 / 版本历史。

数据全部落在 conftest 隔离的临时目录，绝不碰真实选题库。
"""
import pytest

from backend.services.content import dissect


def _save(title, content="", **kw):
    return dissect.save_topic(title=title, content=content, **kw)


def test_save_and_get():
    r = _save("标题A", "正文A", tags=["x", "y"])
    tid = r["item"]["id"]
    item = dissect.get_topic(tid)
    assert item is not None
    assert item["title"] == "标题A"
    assert set(item["tags"]) == {"x", "y"}


def test_empty_title_rejected():
    with pytest.raises(dissect.DissectError):
        dissect.save_topic(title="")


def test_list_and_filter_by_tag():
    _save("T1", "c1", tags=["go"])
    _save("T2", "c2", tags=["py"])
    allt = dissect.list_topics()
    assert len(allt["items"]) >= 2
    go = dissect.list_topics(tag="go")
    assert len(go["items"]) == 1
    assert all("go" in i["tags"] for i in go["items"])


def test_tags_list_counts_descending():
    _save("a", "c", tags=["m", "n"])
    _save("b", "c", tags=["m"])
    tags = dissect.list_tags()
    assert "m" in tags["tags"] and "n" in tags["tags"]
    # m 出现 2 次应排在 n（1 次）之前
    assert tags["tags"].index("m") < tags["tags"].index("n")


def test_soft_delete_and_trash():
    r = _save("del", "c")
    tid = r["item"]["id"]
    assert dissect.get_topic(tid) is not None

    dissect.delete_topic(tid)
    # 库里没了
    assert dissect.get_topic(tid) is None
    # 回收站里有
    trash = dissect.list_trash()
    assert any(i["id"] == tid for i in trash["items"])

    # 恢复
    dissect.restore_topic(tid)
    assert dissect.get_topic(tid) is not None

    # 彻底删除
    dissect.delete_topic(tid)
    dissect.purge_topic(tid)
    trash = dissect.list_trash()
    assert not any(i["id"] == tid for i in trash["items"])


def test_batch_delete_and_empty_trash():
    a = _save("a", "c")
    b = _save("b", "c")
    ids = [a["item"]["id"], b["item"]["id"]]
    res = dissect.delete_topics(ids)
    assert res["removed"] == 2
    # 缺失 id 静默跳过，不报错
    res2 = dissect.delete_topics(["nope1", "nope2"])
    assert res2["removed"] == 0
    assert dissect.list_trash()["total"] == 2
    dissect.empty_trash()
    assert dissect.list_trash()["total"] == 0


def test_version_snapshot_on_overwrite():
    r = _save("V", "v1")
    tid = r["item"]["id"]
    # 首次保存没有旧版本
    assert dissect.list_topic_versions(tid)["total"] == 0
    # 覆盖保存 → 给 v1 拍快照
    dissect.save_topic(title="V", content="v2")
    vers = dissect.list_topic_versions(tid)
    assert vers["total"] == 1
    vid = vers["versions"][0]["version_id"]
    snap = dissect.get_topic_version(tid, vid)
    assert snap["content"] == "v1"
    # 回退 → 内容变回 v1，且回退前会把当前(v2)再拍一版，不丢当前
    dissect.restore_topic_version(tid, vid)
    assert dissect.get_topic(tid)["content"] == "v1"
    assert dissect.list_topic_versions(tid)["total"] == 2


def test_status_change_does_not_make_version():
    r = _save("U", "u1")
    tid = r["item"]["id"]
    # 仅改状态，不拍版本
    dissect.update_topic(tid, status="已完成")
    assert dissect.list_topic_versions(tid)["total"] == 0
    # 改正文才拍版本
    dissect.update_topic(tid, content="u2")
    assert dissect.list_topic_versions(tid)["total"] == 1


def test_missing_topic_raises_404():
    with pytest.raises(dissect.DissectError) as e:
        dissect.update_topic("ghost", content="x")
    assert e.value.status_code == 404
