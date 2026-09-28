"""Regression: OMIT decision must not keep 建议保留 why copy."""

from app.mission_provider import OpenAIMissionProvider


def test_align_experience_why_omit_vs_keep_copy():
    omit = OpenAIMissionProvider._align_experience_why(
        "OMIT",
        "与百度（Baidu）·AI产品经理（校招）相关，建议保留并突出「班级学习委员」中可验证的成果与职责。",
        "班级学习委员",
    )
    assert "暂不放入" in omit
    assert "建议保留" not in omit

    keep = OpenAIMissionProvider._align_experience_why(
        "KEEP",
        "与目标岗位相关，建议保留并突出「运营助理」。",
        "运营助理",
    )
    assert "建议保留" in keep or "相关" in keep
    assert "暂不放入" not in keep
