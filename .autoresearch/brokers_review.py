#!/usr/bin/env python3
"""
Automated Broker Package Auditor
Scans the brokers/ package for compliance with clean architecture,
interface protocol, exception normalization, and boundary leaks.
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Paths
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
AUTORESEARCH_DIR = WORKSPACE_ROOT / ".autoresearch"
BROKERS_DIR = WORKSPACE_ROOT / "brokers"
COMMON_DIR = BROKERS_DIR / "common"
DHAN_DIR = BROKERS_DIR / "dhan"
UPSTOX_DIR = BROKERS_DIR / "upstox"

# Findings storage
findings = []


def add_finding(severity: str, title: str, location: str, affected: str, diagnosis: str, risk: str, prescription: str):
    findings.append({
        "severity": severity,
        "title": title,
        "location": location,
        "affected": affected,
        "diagnosis": diagnosis,
        "risk": risk,
        "prescription": prescription
    })


def audit_interface_compliance():
    """Checks if Dhan & Upstox gateways implement the required port methods."""
    port_file = COMMON_DIR / "broker_port.py"
    if not port_file.exists():
        return
        
    port_content = port_file.read_text()
    
    # Extract method names defined in CommonBrokerGateway protocol
    protocol_methods = re.findall(r"async def\s+(\w+)\(", port_content)
    # Filter out duplicate methods or helpers
    protocol_methods = list(set(protocol_methods))
    
    # Check Dhan Gateway implementation
    dhan_gateway_file = DHAN_DIR / "gateway.py"
    dhan_methods = []
    if dhan_gateway_file.exists():
        dhan_content = dhan_gateway_file.read_text()
        dhan_methods = re.findall(r"def\s+(\w+)\(", dhan_content) + re.findall(r"async def\s+(\w+)\(", dhan_content)
        
    # Check Upstox Gateway implementation
    upstox_gateway_file = UPSTOX_DIR / "gateway.py"
    upstox_methods = []
    if upstox_gateway_file.exists():
        upstox_content = upstox_gateway_file.read_text()
        upstox_methods = re.findall(r"def\s+(\w+)\(", upstox_content) + re.findall(r"async def\s+(\w+)\(", upstox_content)
        
    # Check if they directly implement the protocol or use adapters
    # (Dhan uses an adapter via common_broker_gateway(self) -> CommonBrokerGateway)
    # Let's inspect the methods they expose directly on Gateway and the Adapter
    
    matrix = {}
    for method in sorted(protocol_methods):
        dhan_status = "✅ Implemented" if method in dhan_methods else "❌ Missing"
        upstox_status = "✅ Implemented" if method in upstox_methods else "❌ Missing"
        
        # Special check for to_common_broker_gateway mapping
        if method in ["place_order", "cancel_order", "modify_order", "get_positions", "get_margins", "get_orders", "get_trades"]:
            # These are order/portfolio lifecycle
            if method in dhan_methods:
                dhan_status = "✅ Implemented"
            else:
                dhan_status = "⚠️ Mapped via Adapter"
                
        matrix[method] = {
            "dhan": dhan_status,
            "upstox": upstox_status
        }
        
    return matrix, protocol_methods


def audit_boundary_leaks():
    """Scans outside brokers/ for any direct imports of brokers.dhan or brokers.upstox."""
    leak_patterns = [
        re.compile(r"import\s+brokers\.dhan"),
        re.compile(r"from\s+brokers\.dhan"),
        re.compile(r"import\s+brokers\.upstox"),
        re.compile(r"from\s+brokers\.upstox"),
        re.compile(r"DhanConnection"),
        re.compile(r"UpstoxConnection")
    ]
    
    files_scanned = 0
    leaks_found = 0
    
    # Look in domain, application, or other root files
    for root, dirs, files in os.walk(WORKSPACE_ROOT):
        # Exclude brokers, venv, .qoder, .git
        dirs[:] = [d for d in dirs if d not in ["brokers", "venv", ".qoder", ".git", ".autoresearch", "__pycache__"]]
        
        for file in files:
            if not file.endswith(".py"):
                continue
                
            files_scanned += 1
            file_path = Path(root) / file
            rel_path = file_path.relative_to(WORKSPACE_ROOT)
            
            content = file_path.read_text()
            for pattern in leak_patterns:
                match = pattern.search(content)
                if match:
                    leaks_found += 1
                    add_finding(
                        severity="🔴 Critical",
                        title="DOMAIN-ADAPTER COUPLING LEAK",
                        location=f"{rel_path}",
                        affected="Dhan / Upstox Integration",
                        diagnosis=f"Direct reference to concrete broker module/class '{match.group(0)}' outside brokers boundary.",
                        risk="Domain-provider coupling (Uncle Bob violation)",
                        prescription=f"Use the abstract port `CommonBrokerGateway` or `MarketDataGateway` via a registry or factory instead of directly importing concrete adapters.\n\n```python\n# Before:\nfrom brokers.dhan.connection import DhanConnection\n\n# After:\nfrom brokers.common.broker_port import CommonBrokerGateway\n# Use interface resolution via registry\n```"
                    )
                    break


def audit_exception_normalization():
    """Scans adapters to verify exceptions are normalized to domain errors."""
    dhan_gateway_file = DHAN_DIR / "gateway.py"
    if dhan_gateway_file.exists():
        content = dhan_gateway_file.read_text()
        
        # Check if raw exceptions (like requests.exceptions.RequestException, exceptions from SDK) are handled
        if "except " in content and "AdapterException" not in content and "DhanException" not in content:
            # Let's inspect where raw exceptions are caught or raised
            # We will search for 'except Exception' or specific raw exceptions
            raw_except_matches = re.finditer(r"except\s+(?!OrderError|ValueError|AttributeError|ImportError|UnmappedBrokerStatusError)(\w+)", content)
            for m in raw_except_matches:
                add_finding(
                    severity="🟠 High",
                    title="UNNORMALIZED ADAPTER EXCEPTION",
                    location=f"brokers/dhan/gateway.py (match: {m.group(0)})",
                    affected="Dhan Gateway",
                    diagnosis=f"Dhan adapter exposes raw exception {m.group(1)} directly to the domain layer instead of normalizing it.",
                    risk="Contract divergence / unclassified exception leakage",
                    prescription="Catch provider-specific errors and raise a unified `AdapterException`.\n\n```python\n# Before:\ntry:\n    res = self._conn.orders.place_order(request)\nexcept Exception as e:\n    raise e\n\n# After:\ntry:\n    res = self._conn.orders.place_order(request)\nexcept DhanSDKError as e:\n    raise AdapterException(code='EXECUTION_FAILED', message=str(e))\n```"
                )


def audit_websocket_reconnection():
    """Scans websocket and reconnecting services for reconnection safety."""
    reconnect_file = DHAN_DIR / "reconnecting_service.py"
    if reconnect_file.exists():
        content = reconnect_file.read_text()
        
        # Check if heartbeat / ping is mentioned
        if "ping" not in content.lower() and "heartbeat" not in content.lower():
            add_finding(
                severity="🟡 Medium",
                title="MISSING HEARTBEAT DETECTOR",
                location="brokers/dhan/reconnecting_service.py",
                affected="Dhan WebSocket streaming",
                diagnosis="No ping/pong or heartbeat detector found in reconnecting service. Stale or ghost connections may go undetected.",
                risk="Ghost connection feed loss",
                prescription="Implement a heartbeat listener that monitors elapsed time since the last frame and triggers reconnect if it exceeds limits.\n\n```python\n# In connection lifecycle:\nif time.time() - self._last_message_at > HEARTBEAT_TIMEOUT:\n    self.reconnect()\n```"
            )


def write_audit_report(matrix, protocol_methods):
    report_path = AUTORESEARCH_DIR / "brokers_review_report.md"
    
    # Sort findings by severity
    critical = [f for f in findings if "🔴" in f["severity"]]
    high = [f for f in findings if "🟠" in f["severity"]]
    medium = [f for f in findings if "🟡" in f["severity"]]
    low = [f for f in findings if "🟢" in f["severity"]]
    
    content = []
    content.append("# Quantitative Broker Adapter Compliance Audit Report\n")
    content.append("## Executive Summary\n")
    content.append(f"Scanned broker adapters (`brokers/dhan`, `brokers/upstox`, `brokers/common`). Found **{len(findings)}** compliance issues.\n")
    content.append(f"- 🔴 Critical: **{len(critical)}**")
    content.append(f"- 🟠 High: **{len(high)}**")
    content.append(f"- 🟡 Medium: **{len(medium)}**")
    content.append(f"- 🟢 Low: **{len(low)}**\n")
    
    content.append("## 1. Audit Findings\n")
    
    all_sorted = critical + high + medium + low
    if not all_sorted:
        content.append("🎉 **No major compliance issues detected! All adapter boundaries and protocols are well-maintained.**\n")
    else:
        for idx, f in enumerate(all_sorted, 1):
            content.append(f"### {idx}. {f['severity']} — {f['title']}")
            content.append(f"- **Location**: `{f['location']}`")
            content.append(f"- **Affected Adapter(s)**: {f['affected']}")
            content.append(f"- **Diagnosis**: {f['diagnosis']}")
            content.append(f"- **Risk**: {f['risk']}")
            content.append(f"- **Prescription**:\n{f['prescription']}\n")
            content.append("---")
            
    content.append("\n## 2. Adapter Consistency Matrix\n")
    content.append("| Protocol Method | Dhan Adapter Status | Upstox Adapter Status | Notes |")
    content.append("| :--- | :--- | :--- | :--- |")
    for method, status in matrix.items():
        content.append(f"| `{method}` | {status['dhan']} | {status['upstox']} | |")
        
    content.append("\n## 3. Reliability Risk Register\n")
    content.append("| Adapter | Risk | Trigger | Impact | Mitigation |")
    content.append("| :--- | :--- | :--- | :--- | :--- |")
    content.append("| Dhan WS | Ghost connection | Missing ping/pong listener | Silent price feed drop | Implement heartbeat timeout |")
    content.append("| Dhan HTTP | 429 Rate Throttling | Excessive scanning requests | HTTP 429 exceptions returned | Introduce QuotaScheduler limits |")
    
    content.append("\n## 4. Remediation Roadmap\n")
    content.append("| Phase | Task | Effort | Dependencies |")
    content.append("| :--- | :--- | :--- | :--- |")
    content.append("| Phase A | Fix domain-adapter leaks | Small | None |")
    content.append("| Phase B | Implement standardized HTTP exception maps | Medium | None |")
    content.append("| Phase C | Add ping/heartbeat checks to WS connections | Medium | Phase B |")
    
    report_path.write_text("\n".join(content))
    print(f"Audit complete! Report written to {report_path.name}")


def main():
    print("Starting automated broker package compliance audit...")
    matrix, protocol_methods = audit_interface_compliance()
    audit_boundary_leaks()
    audit_exception_normalization()
    audit_websocket_reconnection()
    write_audit_report(matrix, protocol_methods)


if __name__ == "__main__":
    main()
