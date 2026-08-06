from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

import httpx

from ..core.secret_store import decrypt_secret
from ..models.research import ProjectResearchConfig


class ResearchSearchClient:
    """Web search client with rate-limiting, DNS validation, and multi-provider support."""
    
    # Rate limiting
    _rate_limit_window_s = 60.0
    _max_requests_per_window = 30
    _request_log: list = []
    
    @classmethod
    def _check_rate_limit(cls) -> bool:
        now = __import__("time").time()
        cls._request_log = [t for t in cls._request_log if now - t < cls._rate_limit_window_s]
        return len(cls._request_log) < cls._max_requests_per_window
    
    @classmethod
    def _record_request(cls) -> None:
        cls._request_log.append(__import__("time").time())
    
    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """Block private/internal IPs to prevent SSRF."""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                return False
            addr = ipaddress.ip_address(socket.gethostbyname(hostname))
            return not (addr.is_private or addr.is_loopback or addr.is_link_local)
        except Exception:
            return False
    
    
    @staticmethod
    async def _validate_outbound_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("search_base_url must be a credential-free HTTP(S) URL")
        host = parsed.hostname.lower().rstrip(".")
        if host == "localhost" or host.endswith(".localhost"):
            raise ValueError("search_base_url cannot target localhost")
        try:
            literal = ipaddress.ip_address(host)
            addresses = [literal]
        except ValueError:
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
        if not addresses or any(not address.is_global for address in addresses):
            raise ValueError("search_base_url resolved to a non-public network address")
        return url
    @staticmethod
    def _domain_matches(url: str, domains: Iterable[str]) -> bool:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return False
        values = []
        for item in domains:
            value = str(item).lower().strip()
            if not value:
                continue
            if "://" in value:
                value = (urlparse(value).hostname or "").lower()
            values.append(value.lstrip("."))
        return any(host == item or host.endswith(f".{item}") for item in values if item)

    @classmethod
    def _domain_blocked(cls, url: str, blocked: Iterable[str]) -> bool:
        return cls._domain_matches(url, blocked)

    @classmethod
    def _is_preferred(cls, url: str, preferred: Iterable[str]) -> bool:
        return cls._domain_matches(url, preferred)
    @staticmethod
    async def web_fetch(url, timeout=30.0, max_bytes=500000):
        """Fetch and extract text from a public URL."""
        await ResearchSearchClient._validate_outbound_url(url)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers={
                "User-Agent": "XuanqiongWenshu-Research/1.0",
                "Accept": "text/html,application/xhtml+xml"
            })
            response.raise_for_status()
            raw = response.text[:max_bytes]
            import re as _re
            text = _re.sub(r"<[^>]+>", " ", raw)
            text = _re.sub(r"\\s+", " ", text).strip()
            return {"url": url, "status": response.status_code, "text_length": len(text), "text_preview": text[:3000]}

    @staticmethod
    async def search_tavily(query, api_key, max_results=5, timeout=30.0):
        """Search via Tavily API."""
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "max_results": max_results, "search_depth": "advanced"},
            )
            response.raise_for_status()
            return response.json().get("results", [])

    @staticmethod
    async def search_and_summarize(query, tavily_api_key=None, max_results=5, fetch_timeout=30.0):
        """Search and fetch content from top results."""
        sources = []
        if tavily_api_key:
            try:
                results = await ResearchSearchClient.search_tavily(query, api_key=tavily_api_key, max_results=max_results)
                for sr in results[:max_results]:
                    sources.append({"title": sr.get("title",""), "url": sr.get("url",""), "content": sr.get("content",""), "score": sr.get("score",0)})
            except Exception:
                pass
        return {"query": query, "sources": sources, "source_count": len(sources)}


    async def search_one(self, config: ProjectResearchConfig, item: Dict[str, Any]) -> Dict[str, Any]:
        api_key = decrypt_secret(config.search_api_key_encrypted)
        if not api_key or config.search_provider == "none":
            return {**item, "status": "skipped", "error": "search_api_key_not_configured", "results": []}
        provider = str(config.search_provider or "tavily").lower()
        max_results = max(1, min(10, int(config.max_results_per_query or 5)))
        endpoint = await self._validate_outbound_url(config.search_base_url or {
            "tavily": "https://api.tavily.com/search",
            "serper": "https://google.serper.dev/search",
            "bing": "https://api.bing.microsoft.com/v7.0/search",
        }.get(provider, ""))
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=8.0), follow_redirects=False) as client:
            if provider == "tavily":
                response = await client.post(endpoint, json={
                    "api_key": api_key,
                    "query": item["query"],
                    "search_depth": "advanced" if max_results >= 5 else "basic",
                    "max_results": max_results,
                    "include_answer": False,
                    "include_raw_content": False,
                })
                response.raise_for_status()
                raw_results = response.json().get("results") or []
            elif provider == "serper":
                response = await client.post(
                    endpoint,
                    headers={"X-API-KEY": api_key},
                    json={"q": item["query"], "num": max_results},
                )
                response.raise_for_status()
                raw_results = response.json().get("organic") or []
            elif provider == "bing":
                response = await client.get(
                    endpoint,
                    headers={"Ocp-Apim-Subscription-Key": api_key},
                    params={"q": item["query"], "count": max_results, "mkt": "zh-CN"},
                )
                response.raise_for_status()
                raw_results = ((response.json().get("webPages") or {}).get("value") or [])
            else:
                raise ValueError(f"unsupported search provider: {provider}")
        results: List[Dict[str, Any]] = []
        for source_index, raw in enumerate(raw_results):
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or raw.get("link") or "").strip()
            if self._domain_blocked(url, config.blocked_domains or []):
                continue
            results.append({
                "title": str(raw.get("title") or raw.get("name") or "")[:300],
                "url": url,
                "snippet": str(raw.get("content") or raw.get("snippet") or raw.get("description") or "")[:1800],
                "score": raw.get("score"),
                "preferred_domain": self._is_preferred(url, config.preferred_domains or []),
                "source_index": source_index,
                "category": item["category"],
                "query": item["query"],
            })
        def score_value(result: Dict[str, Any]) -> float:
            try:
                return float(result.get("score") or 0)
            except (TypeError, ValueError):
                return 0.0

        results.sort(key=lambda result: (
            not bool(result.get("preferred_domain")),
            -score_value(result),
            int(result.get("source_index") or 0),
        ))
        for result in results:
            result.pop("source_index", None)
        return {**item, "status": "successful", "results": results}

    async def search_all(self, config: ProjectResearchConfig, plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        semaphore = asyncio.Semaphore(max(1, min(8, int(config.max_parallel_queries or 4))))

        async def run(item: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                try:
                    return await self.search_one(config, item)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    return {**item, "status": "failed", "error": str(exc)[:500], "results": []}

        return list(await asyncio.gather(*(run(item) for item in plan)))
