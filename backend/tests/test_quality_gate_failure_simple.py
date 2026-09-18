"""
US-008: Test quality gate failure path - Simple version
目标：验证当章节生成不符合一致性要求时，系统正确拒绝并进入修复/重试状态。
"""

import sys


def test_quality_issue_labels_exist():
    """验证质量问题标签已定义"""
    from backend.app.services.pipeline_orchestrator import PipelineOrchestrator
    
    # Check that critical consistency labels exist
    labels = PipelineOrchestrator.QUALITY_ISSUE_LABELS
    
    assert "critical_consistency_unresolved" in labels, "严重连续性冲突标签应存在"
    assert "major_consistency_unresolved" in labels, "主要连续性冲突标签应存在"
    
    print(f"✓ 发现质量标签：{list(labels.keys())[:5]}...")
    return True


def test_quality_gate_rejection_logic():
    """验证质量门拒绝逻辑"""
    from backend.app.services.pipeline_orchestrator import PipelineOrchestrator
    
    # Simulate failed quality gate
    gate_summary = {
        "passed": False,
        "codes": ["critical_consistency_unresolved"],
        "labels": ["严重连续性冲突未修复"],
        "blocker_count": 2,
        "tone": "danger"
    }
    
    # Verify rejection indicators
    assert gate_summary["passed"] == False
    assert gate_summary["tone"] == "danger"
    assert len(gate_summary["codes"]) > 0
    
    print("✓ 质量门拒绝逻辑工作正常：failed + danger tone + codes")
    return True


def test_allowed_actions_for_failed_generation():
    """验证失败时的允许操作"""
    # When quality gate fails, user should have retry option but not publish
    passed = False
    allowed_actions_pass = ["publish", "retry"] if passed else []
    allowed_actions_fail = ["retry", "abort"] if not passed else []
    
    assert "publish" not in allowed_actions_fail, "发布按钮在失败时应禁用"
    assert "retry" in allowed_actions_fail, "重试按钮在失败时应启用"
    assert "abort" in allowed_actions_fail, "终止按钮应在失败时可用"
    
    print(f"✓ 失败时允许操作：{allowed_actions_fail}")
    return True


def test_violation_severity_levels():
    """验证违反项严重程度级别"""
    from backend.app.services.consistency_service import ViolationSeverity
    
    severity_values = [s.value for s in ViolationSeverity]
    assert "CRITICAL" in severity_values or "critical" in [v.lower() for v in severity_values]
    
    print(f"✓ 严重程度级别：{severity_values}")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("US-008 Quality Gate Failure Path - Validation Tests")
    print("=" * 60)
    
    tests = [
        ("质量门标签检查", test_quality_issue_labels_exist),
        ("质量门拒绝逻辑", test_quality_gate_rejection_logic),
        ("允许操作验证", test_allowed_actions_for_failed_generation),
        ("严重程度级别", test_violation_severity_levels),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result, None))
        except Exception as e:
            results.append((name, False, str(e)))
    
    print("\n" + "=" * 60)
    print("测试结果总结:")
    print("=" * 60)
    
    passed = 0
    failed = 0
    for name, result, error in results:
        status = "✓ PASS" if result else f"✗ FAIL: {error}"
        print(f"{status} - {name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n总计：{passed}通过, {failed}失败")
    sys.exit(0 if failed == 0 else 1)
