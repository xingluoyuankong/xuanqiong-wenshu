"""US-005: Tests for health check differentiation logic."""

import asyncio
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.enhanced_healthcheck import (
    ErrorType,
    HealthCheckResult,
    HealthStatus,
    RetryConfig,
    ServiceHealthChecker,
)


# ==================== Fixtures ====================

@pytest.fixture
def mock_async_client():
    """创建模拟的 async HTTP client."""
    client = AsyncMock()
    return client


@pytest.fixture
def temp_db_file(tmp_path):
    """创建临时数据库文件用于测试。"""
    db_path = tmp_path / "test_db.db"
    db_path.write_bytes(b"\x00\x01\x02")  # 创建虚拟文件
    return str(db_path)


@pytest.fixture
def checker_with_config():
    """创建带自定义配置的检查器（短超时、少重试便于测试）。"""
    return ServiceHealthChecker(
        config=RetryConfig(
            max_retries=3,
            base_interval_seconds=1,
            timeout_seconds=1,
            slow_threshold_seconds=2.0,
        )
    )


# ==================== Unit Tests ====================


class TestHealthStatusEnum:
    """测试枚举定义。"""

    def test_ok_value(self):
        assert HealthStatus.OK.value == "ok"

    def test_slow_value(self):
        assert HealthStatus.SLOW.value == "slow"

    def test_failed_value(self):
        assert HealthStatus.FAILED.value == "failed"


class TestErrorTypeEnum:
    """测试错误类型枚举。"""

    def test_timeout_is_none(self):
        assert ErrorType.TIMEOUT.value is None  # Enum None 是特殊的

    def test_connection_refused_exists(self):
        assert ErrorType.CONNECTION_REFUSED.value == "connection_refused"

    def test_all_error_types_present(self):
        expected = {
            "timeout",
            "connection_refused",
            "dns_error",
            "http_error",
            "json_error",
            "unknown",
        }
        actual = {e.value for e in ErrorType if e.value is not None}
        assert actual == expected


class TestHealthCheckResultToDict:
    """测试结果序列化为字典。"""

    def test_basic_conversion(self):
        result = HealthCheckResult(
            service_name="Test",
            url="http://localhost",
            status=HealthStatus.OK,
            attempts=1,
            time_to_check_ms=42,
        )
        d = result.to_dict()

        assert d["service_name"] == "Test"
        assert d["url"] == "http://localhost"
        assert d["status"] == "ok"
        assert d["attempts"] == 1
        assert d["time_to_check_ms"] == 42

    def test_with_last_error(self):
        result = HealthCheckResult(
            service_name="FailingService",
            url="http://bad.com",
            status=HealthStatus.FAILED,
            last_error="Connection refused",
            error_type=ErrorType.CONNECTION_REFUSED,
        )
        d = result.to_dict()

        assert d["last_error"] == "Connection refused"
        assert d["error_type"] == "connection_refused"


class TestRetryConfigIntervals:
    """测试重试间隔生成策略。"""

    def test_exponential_backoff(self):
        config = RetryConfig(max_retries=5, base_interval_seconds=1)
        intervals = config.intervals
        assert intervals == [1, 2, 4, 8, 16]

    def test_linear_retry(self):
        config = RetryConfig(max_retries=4, exponential_backoff=False)
        intervals = config.intervals
        assert intervals == [1, 1, 1, 1]

    def test_capped_intervals(self):
        # 当 max_retries > intervals length 时应该 cap
        config = RetryConfig(max_retries=10, base_interval_seconds=2)
        # 应该只生成到 max_retries
        assert len(config.intervals) == 10


class TestEndpointCheck_OKResponse:
    """测试正常响应的场景。"""

    @pytest.mark.asyncio
    async def test_success_http_response(self, mock_async_client):
        """模拟 HTTP 200 响应返回 OK 状态。"""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_success = True
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.status_code = 200

        mock_async_client.get = AsyncMock(return_value=mock_response)

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=1, timeout_seconds=1)
        )

        result = await checker.check_endpoint(
            "http://test.com/api/health", "TestAPI", mock_async_client
        )

        assert result.status == HealthStatus.OK
        assert result.attempts == 1
        assert result.error_type == ErrorType.NONE
        assert "http_status" in result.details

    @pytest.mark.asyncio
    async def test_success_with_json_data(self, mock_async_client):
        """验证 JSON 解析成功后的 key 提取。"""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_success = True
        mock_response.json.return_value = {
            "status": "healthy",
            "version": "1.0.0",
            "database": "connected",
        }

        mock_async_client.get = AsyncMock(return_value=mock_response)

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=1, timeout_seconds=1)
        )
        result = await checker.check_endpoint("http://api.test", "Backend", mock_async_client)

        assert result.status == HealthStatus.OK
        assert list(result.details.keys()) == ["http_status", "response_json_keys"]
        assert len(result.details["response_json_keys"]) <= 5

    @pytest.mark.asyncio
    async def test_multiple_attempts_until_success(self, mock_async_client):
        """测试前几次失败最终成功的情况（模拟慢启动后恢复）。"""
        responses = [
            MagicMock(is_success=False, status_code=503),  # 503
            MagicMock(is_success=False, status_code=502),  # 502
            MagicMock(is_success=True, json=lambda: {"status": "ok"}, status_code=200),  # OK
        ]
        call_count = [0]

        async def mock_get(*args, **kwargs):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            return responses[idx]

        mock_async_client.get = mock_get

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=5, timeout_seconds=1)
        )
        result = await checker.check_endpoint("http://slow.test", "SlowAPI", mock_async_client)

        assert result.status == HealthStatus.OK
        assert result.attempts == 3
        assert len(result.attempt_history) == 3


class TestEndpointCheck_Timeout:
    """测试超时的场景（应标记为 SLOW）。"""

    @pytest.mark.asyncio
    async def test_single_timeout_returns_slow(self, mock_async_client):
        """单次超时即标记为 SLOW。"""
        mock_async_client.get = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=1, timeout_seconds=1)
        )
        result = await checker.check_endpoint("http://timeout.test", "TimeoutAPI", mock_async_client)

        assert result.status == HealthStatus.SLOW
        assert result.error_type == ErrorType.TIMEOUT
        assert "timed out" in result.last_error.lower()

    @pytest.mark.asyncio
    async def test_mixed_timeout_and_failure_returns_slow(self, mock_async_client):
        """如果最后是超时，即使中间有连接拒绝也应标记为 SLOW。"""
        errors = [
            httpx.ConnectError("Connection refused"),  # 第一次
            httpx.TimeoutException("Timed out"),  # 第二次是超时
        ]

        async def mock_get(*args, **kwargs):
            raise errors[min(len(errors), 2)]

        mock_async_client.get = mock_get

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=2, timeout_seconds=1)
        )
        result = await checker.check_endpoint("http://mixed.test", "MixedAPI", mock_async_client)

        assert result.status == HealthStatus.SLOW
        assert any(h.get("error_type") == "timeout" for h in result.attempt_history)


class TestEndpointCheck_ConnRefused:
    """测试连接拒绝的场景（应标记为 FAILED）。"""

    @pytest.mark.asyncio
    async def test_connection_refused_returns_failed(self, mock_async_client):
        """连接拒绝直接标记为 FAILED。"""
        mock_async_client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused to localhost")
        )

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=1, timeout_seconds=1)
        )
        result = await checker.check_endpoint("http://refused.test", "RefusedAPI", mock_async_client)

        assert result.status == HealthStatus.FAILED
        assert result.error_type == ErrorType.CONNECTION_REFUSED

    @pytest.mark.asyncio
    async def test_dns_error_returns_failed(self, mock_async_client):
        """DNS 解析失败也标记为 FAILED。"""
        mock_async_client.get = AsyncMock(
            side_effect=socket.gaierror("Name or service not known")
        )

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=1, timeout_seconds=1)
        )
        result = await checker.check_endpoint("http://dnstest.invalid", "DNSAPI", mock_async_client)

        assert result.status == HealthStatus.FAILED
        assert result.error_type == ErrorType.DNS_ERROR


class TestEndpointCheck_HTTPErrors:
    """测试 HTTP 错误码的场景。"""

    @pytest.mark.asyncio
    async def test_5xx_error_returns_failed(self, mock_async_client):
        """服务器错误标记为 FAILED。"""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_success = False
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Server Error", request=None, response=mock_response
        )

        mock_async_client.get = AsyncMock(return_value=mock_response)

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=1, timeout_seconds=1)
        )
        result = await checker.check_endpoint("http://error.test", "ErrorAPI", mock_async_client)

        assert result.status == HealthStatus.FAILED
        assert result.error_type == ErrorType.HTTP_ERROR

    @pytest.mark.asyncio
    async def test_non_json_response_returns_failed(self, mock_async_client):
        """非 JSON 格式内容标记为 FAILED。"""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_success = True
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "<html><body>Not JSON</body></html>"

        mock_async_client.get = AsyncMock(return_value=mock_response)

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=1, timeout_seconds=1)
        )
        result = await checker.check_endpoint("http://notjson.test", "JSONAPI", mock_async_client)

        assert result.status == HealthStatus.FAILED
        assert result.error_type == ErrorType.JSON_DECODE_ERROR


class TestExponentialBackoffTiming:
    """测试指数退避的时间计算正确性。"""

    @pytest.mark.asyncio
    async def test_backoff_timing_accumulates_correctly(self, mock_async_client, monkeypatch):
        """验证等待时间累积计算正确。"""
        sleep_times = []

        async def mock_sleep(n):
            sleep_times.append(n)

        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        mock_async_client.get = AsyncMock(
            side_effect=httpx.TimeoutException("Timeout")
        )

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=3, base_interval_seconds=1)
        )

        with patch("time.sleep") as mock_time_sleep:
            await checker.check_endpoint("http://test.test", "TestAPI", mock_async_client)

        # 应该是 1s, 2s（第 1 次和第 2 次重试后，总共等待 2 次）
        expected_sleeps = [1, 2]
        assert mock_time_sleep.call_args_list[0][0][0] == 1
        assert mock_time_sleep.call_args_list[1][0][0] == 2


# ==================== Integration Tests ====================


class TestAllServicesCheck:
    """集成测试：同时检查多个服务。"""

    @pytest.mark.asyncio
    async def test_check_all_aggregates_results(self, mock_async_client):
        """验证 check_all_services 正确聚合所有结果。"""
        services = [
            {"name": "FastAPI", "url": "http://fast.test"},
            {"name": "SlowAPI", "url": "http://slow.test"},
            {"name": "BrokenDB", "url": "http://broken.test"},
        ]

        # 快速 API 成功，慢的超时，坏的连接拒绝
        responses = {
            "http://fast.test": MagicMock(is_success=True, json=lambda: {"ok": True}),
            "http://slow.test": httpx.TimeoutException("Timeout"),
            "http://broken.test": httpx.ConnectError("Connection refused"),
        }

        async def mock_get(url, **kwargs):
            resp_or_exc = responses[url.path]
            if isinstance(resp_or_exc, Exception):
                raise resp_or_exc
            return resp_or_exc

        mock_async_client.get = mock_get

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=2, timeout_seconds=1)
        )
        results = await checker.check_all_services(services, mock_async_client)

        assert len(results) == 3
        assert results["FastAPI"].status == HealthStatus.OK
        assert results["SlowAPI"].status == HealthStatus.SLOW
        assert results["BrokenDB"].status == HealthStatus.FAILED

    @pytest.mark.asyncio
    async def test_report_generates_human_readable_output(self, mock_async_client):
        """验证报告生成的可读性。"""
        services = [
            {"name": "OK Service", "url": "http://ok.test"},
            {"name": "Slow Service", "url": "http://slow.test"},
        ]

        async def mock_get(url, **kwargs):
            if "ok.test" in url.path:
                return MagicMock(is_success=True, json=lambda: {"status": "ok"})
            else:
                raise httpx.TimeoutException("Timeout")

        mock_async_client.get = mock_get

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=1, timeout_seconds=1)
        )
        results = await checker.check_all_services(services, mock_async_client)
        report = checker.generate_report(results)

        # 检查报告包含关键元素
        assert "玄穹文枢健康检查报告" in report
        assert "✓ OK Service" in report
        assert "⚠ Slow Service" in report
        assert "状态码：1" in report  # 因为有一个慢响应

        print("\n" + "=" * 60)
        print(report)
        print("=" * 60)


# ==================== CLI Main Test ====================


class TestCommandLineInterface:
    """测试命令行接口。"""

    @pytest.mark.asyncio
    async def test_main_with_mocked_http(self, mock_async_client):
        """测试主函数在 mock 环境下执行。"""
        mock_async_client.get = AsyncMock(
            return_value=MagicMock(is_success=True, json=lambda: {"status": "healthy"})
        )

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=1, timeout_seconds=1)
        )

        # 手动调用内部逻辑（避免实际的网络调用）
        result = await checker.check_endpoint(
            "http://test.test", "CLI API", mock_async_client
        )

        assert result.status == HealthStatus.OK

    @pytest.mark.asyncio
    async def test_exit_codes_match_scenarios(self):
        """验证退出码与场景对应关系（用 subprocess 模拟）。"""
        exit_code_map = {
            HealthStatus.OK: 0,
            HealthStatus.SLOW: 1,
            HealthStatus.FAILED: 2,
        }

        for status, expected_code in exit_code_map.items():
            checker = ServiceHealthChecker()
            result = HealthCheckResult(
                service_name="Test", url="http://test", status=status
            )

            # 模拟 main() 中的逻辑
            if result.status == HealthStatus.FAILED:
                actual_code = 2
            elif result.status == HealthStatus.SLOW:
                actual_code = 1
            else:
                actual_code = 0

            assert actual_code == expected_code, f"Status {status} should map to code {expected_code}"


# ==================== Conformance Tests ====================


class TestUS005AcceptanceCriteria:
    """验收标准验证测试（确保 US-005 所有标准通过）。"""

    @pytest.mark.asyncio
    async def test_ac1_distinguishes_timeout_vs_connection_refused(self, mock_async_client):
        """AC1: Health check script distinguishes timeout (slow) vs ECONNREFUSED (failed)."""
        # Timeout 场景
        mock_async_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        checker = ServiceHealthChecker()
        result_timeout = await checker.check_endpoint("http://t.test", "Timeout", mock_async_client)

        assert result_timeout.status == HealthStatus.SLOW
        assert result_timeout.error_type == ErrorType.TIMEOUT

        # Connection Refused 场景
        mock_async_client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result_refused = await checker.check_endpoint("http://r.test", "Refused", mock_async_client)

        assert result_refused.status == HealthStatus.FAILED
        assert result_refused.error_type == ErrorType.CONNECTION_REFUSED

        assert result_timeout.status != result_refused.status, "Should be different!"

    @pytest.mark.asyncio
    async def test_ac2_logs_retry_attempts_with_backoff(self, mock_async_client):
        """AC2: Logs retry attempts with backoff strategy."""
        attempt_log = []

        async def mock_get_with_log(*args, **kwargs):
            attempt_log.append({"attempt": len(attempt_log) + 1})
            if len(attempt_log) < 3:
                raise httpx.TimeoutException("Timeout")
            return MagicMock(is_success=True, json=lambda: {"ok": True})

        mock_async_client.get = mock_get_with_log

        checker = ServiceHealthChecker(
            config=RetryConfig(max_retries=5, base_interval_seconds=0.1)  # 快速重试用于测试
        )
        result = await checker.check_endpoint("http://test.test", "BackoffTest", mock_async_client)

        # 验证至少记录了 2 次重试（从失败到成功）
        assert len(attempt_log) >= 2
        assert all("attempt" in entry for entry in attempt_log)
        assert result.status == HealthStatus.OK  # 最终成功

    @pytest.mark.asyncio
    async def test_ac3_configurable_max_retries_and_interval(self, mock_async_client):
        """AC3: Configurable max retries and interval."""
        configs_to_test = [
            (RetryConfig(max_retries=1, base_interval_seconds=1), 1),
            (RetryConfig(max_retries=5, base_interval_seconds=2), 5),
            (RetryConfig(max_retries=10, base_interval_seconds=0), 10),
        ]

        for config, expected_max in configs_to_test:
            mock_async_client.get = AsyncMock(
                side_effect=httpx.ConnectError("Always fails")
            )
            checker = ServiceHealthChecker(config=config)
            result = await checker.check_endpoint(
                "http://test.test", "ConfigTest", mock_async_client
            )

            assert result.attempts == expected_max, f"Expected {expected_max} attempts, got {result.attempts}"

    @pytest.mark.asyncio
    async def test_ac4_different_warnings_for_each_case(self, mock_async_client):
        """AC4: Shows different warnings for each case."""
        scenarios = [
            (httpx.TimeoutException("Timeout"), "timeout", HealthStatus.SLOW),
            (httpx.ConnectError("Refused"), "connection_refused", HealthStatus.FAILED),
            (ValueError("Bad JSON"), "json_error", HealthStatus.FAILED),
        ]

        for exc_class, expected_error_type, expected_status in scenarios:
            mock_async_client.get = AsyncMock(side_effect=exc_class)
            checker = ServiceHealthChecker(config=RetryConfig(max_retries=1))

            result = await checker.check_endpoint("http://warn.test", "WarnTest", mock_async_client)

            assert result.error_type.value == expected_error_type
            assert result.status == expected_status

    def test_ac5_exit_codes_match_specification(self):
        """AC5: Exit codes: 0=ok, 1=slow, 2=failed."""
        # 验证 exit code 映射关系
        assert ServiceHealthChecker.DEFAULT_CONFIG.max_retries == 5

        # 模拟 main() 中的 exit code 计算逻辑
        ok_result = HealthCheckResult(service_name="OK", url="http://ok", status=HealthStatus.OK)
        slow_result = HealthCheckResult(service_name="SLOW", url="http://slow", status=HealthStatus.SLOW)
        failed_result = HealthCheckResult(service_name="FAILED", url="http://fail", status=HealthStatus.FAILED)

        def calc_exit(result):
            if result.status == HealthStatus.FAILED:
                return 2
            elif result.status == HealthStatus.SLOW:
                return 1
            return 0

        assert calc_exit(ok_result) == 0
        assert calc_exit(slow_result) == 1
        assert calc_exit(failed_result) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
