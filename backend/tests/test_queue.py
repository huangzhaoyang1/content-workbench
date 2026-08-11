"""队列 service 单测：topic_id 关联 + _flip_topic 状态联动（绝不拖垮流水线）。

数据落在 conftest 隔离的临时目录。
"""
from backend.services.content import dissect
from backend.services.system import queue


def test_add_with_topic_id():
    r = dissect.save_topic("关联选题", "内容")
    tid = r["item"]["id"]
    item = queue.add(topic="某主题", topic_id=tid)
    assert item["topic_id"] == tid
    snap = queue.snapshot()
    assert any(i["topic_id"] == tid for i in snap["items"])


def test_flip_topic_updates_status():
    r = dissect.save_topic("翻转选题", "内容", status="待生产")
    tid = r["item"]["id"]
    queue._flip_topic(tid, "生产中")
    assert dissect.get_topic(tid)["status"] == "生产中"
    queue._flip_topic(tid, "已完成")
    assert dissect.get_topic(tid)["status"] == "已完成"


def test_flip_topic_missing_no_raise():
    # 不存在的选题翻转不应抛异常（流水线容错设计）
    queue._flip_topic("ghost-id", "生产中")


def test_skip_no_running_is_noop():
    # 没有执行中的任务时，skip_current 应返回 ok=False
    r = queue.skip_current()
    assert r["ok"] is False and "没有" in r["reason"]


def test_skip_marks_running_item_skipped():
    # 模拟「执行线程已死」的运行态任务：skip_current 直接标记为 skipped
    item = queue.add("待跳过任务", source="manual")
    item["status"] = "running"
    item["topic_id"] = ""
    queue._save()
    r = queue.skip_current()
    assert r["ok"] is True and r["id"] == item["id"]
    snap = queue.snapshot()
    cur = next(i for i in snap["items"] if i["id"] == item["id"])
    assert cur["status"] == "skipped"
    assert cur["error"] == "用户已跳过"
    assert cur["finished_at"] is not None


def test_load_recovers_interrupted_schedule_as_waiting():
    # 重启恢复：running 的定时任务回退 waiting 以便重新调度；其余来源视为 failed
    import json

    queue._ITEMS.clear()
    queue._LOADED = False

    payload = [
        {
            "id": "s1", "topic": "定时任务A", "angle": "", "extra": "",
            "platform": "wechat", "source": "schedule", "topic_id": "",
            "status": "running", "issue": None, "task_id": "t1",
            "error": None, "created_at": "2026-01-01 00:00:00",
            "started_at": "2026-01-01 00:00:01", "finished_at": None,
        },
        {
            "id": "m1", "topic": "手动任务B", "angle": "", "extra": "",
            "platform": "wechat", "source": "manual", "topic_id": "",
            "status": "running", "issue": None, "task_id": "t2",
            "error": None, "created_at": "2026-01-01 00:00:00",
            "started_at": "2026-01-01 00:00:01", "finished_at": None,
        },
        {
            "id": "w1", "topic": "等待中C", "angle": "", "extra": "",
            "platform": "wechat", "source": "manual", "topic_id": "",
            "status": "waiting", "issue": None, "task_id": None,
            "error": None, "created_at": "2026-01-01 00:00:00",
            "started_at": None, "finished_at": None,
        },
    ]
    queue._STORE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    queue._load()

    items = {i["id"]: i for i in queue.snapshot()["items"]}
    assert items["s1"]["status"] == "waiting"   # 定时任务回退 waiting
    assert items["m1"]["status"] == "failed"     # 手动任务仍按失败处理
    assert items["w1"]["status"] == "waiting"    # 原本 waiting 不变
    # 任务上下文保留
    assert items["s1"]["topic"] == "定时任务A"
    assert items["s1"]["source"] == "schedule"
    # 状态恢复已落盘
    saved = json.loads(queue._STORE.read_text(encoding="utf-8"))
    saved_by_id = {i["id"]: i for i in saved}
    assert saved_by_id["s1"]["status"] == "waiting"
    assert saved_by_id["m1"]["status"] == "failed"
