"""投递状态机：可前进、也可退回上一阶段；CLOSED 为终态。

- PATCH 允许沿 APPLICATION_FORWARD 前进，也允许退回更早的活跃阶段（误点修正）。
- CLOSED 可从任意活跃状态进入，进入后不可再变（终态）。
- POST（用于导入历史记录）仍允许直接给任意状态，不受转移表约束。
"""
from app.application_routes import APPLICATION_FORWARD, APPLICATION_STATUSES


def _create(client, profile_id, status="PENDING", company="Acme", role="PM"):
    response = client.post(
        f"/api/v1/profiles/{profile_id}/applications",
        json={"company": company, "role": role, "status": status},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _patch(client, application_id, status):
    return client.patch(f"/api/v1/applications/{application_id}", json={"status": status})


def test_backward_transition_is_allowed(client, persisted_profile):
    """允许退回更早的活跃阶段（用户误点后可修正）。"""
    row = _create(client, persisted_profile.id, "INTERVIEW")

    moved = _patch(client, row["id"], "APPLIED")

    assert moved.status_code == 200
    assert moved.json()["status"] == "APPLIED"


def test_backward_transition_skipping_stages_is_allowed(client, persisted_profile):
    row = _create(client, persisted_profile.id, "OFFER")

    moved = _patch(client, row["id"], "SCREENING")

    assert moved.status_code == 200
    assert moved.json()["status"] == "SCREENING"


def test_forward_transition_is_allowed(client, persisted_profile):
    row = _create(client, persisted_profile.id, "APPLIED")

    moved = _patch(client, row["id"], "INTERVIEW")

    assert moved.status_code == 200
    assert moved.json()["status"] == "INTERVIEW"
    assert moved.json()["stage"] == "INTERVIEW"


def test_closed_is_reachable_from_active_states_but_locked_after(client, persisted_profile):
    row = _create(client, persisted_profile.id, "OFFER")

    closed = _patch(client, row["id"], "CLOSED")
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"

    reopened = _patch(client, row["id"], "OFFER")
    assert reopened.status_code == 422
    assert "已结束" in reopened.json()["detail"]


def test_post_still_seeds_any_status_for_imports(client, persisted_profile):
    row = _create(client, persisted_profile.id, "OFFER")
    assert row["status"] == "OFFER"


def test_unknown_status_is_still_rejected(client, persisted_profile):
    row = _create(client, persisted_profile.id, "PENDING")

    response = _patch(client, row["id"], "NOT_A_STATUS")

    assert response.status_code == 422
    assert "无效的投递状态" in response.json()["detail"]


def test_no_transition_table_edge_goes_backwards():
    """转移表里不能出现任何「倒退」边——这是漏斗口径唯一的保证。"""
    rank = {name: index for index, name in enumerate(APPLICATION_STATUSES)}
    for source, targets in APPLICATION_FORWARD.items():
        assert source in rank
        for target in targets:
            assert target in rank, f"{target} 不在正式状态列表里"
            assert rank[target] > rank[source], f"{source} → {target} 是倒退边"


def test_every_status_has_a_transition_entry():
    assert set(APPLICATION_FORWARD) == set(APPLICATION_STATUSES)
