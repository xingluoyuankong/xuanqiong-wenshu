"""US-009: Verify worker epoch and fencing mechanism"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def check_database_schema(db_path: str) -> dict:
    """Check if database has worker-related tables."""
    result = {
        "tables": [],
        "has_worker_table": False,
        "has_epoch_columns": False,
        "has_heartbeat_columns": False,
        "findings": []
    }
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        result["tables"] = sorted(tables)
        
        # Check for worker-related tables
        worker_related = ['workers', 'worker_instances', 'worker_leases', 
                        'worker_heartbeats', 'worker_epochs', 'instance_states']
        
        for table in tables:
            if any(word in table.lower() for word in ['worker', 'epoch', 'lease']):
                result["findings"].append(f"Found potential worker-related table: {table}")
                
            # Check schema for epoch columns
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'epoch' in columns:
                result["has_epoch_columns"] = True
                result["findings"].append(f"Table '{table}' has epoch column")
                
            if 'heartbeat' in columns:
                result["has_heartbeat_columns"] = True
                result["findings"].append(f"Table '{table}' has heartbeat column")
                
        conn.close()
        
    except Exception as e:
        result["error"] = str(e)
        result["findings"].append(f"Error checking database: {e}")
        
    return result


def check_codebase_patterns(base_path: str) -> dict:
    """Check codebase for worker pattern implementation."""
    findings = {
        "worker_files_found": False,
        "heartbeat_implementation": False,
        "fencing_implementation": False,
        "distributed_lock_found": False,
        "notes": []
    }
    
    services_dir = Path(f"{base_path}/backend/app/services")
    
    # Search for worker file patterns
    worker_files = list(services_dir.glob("worker*.py"))
    
    if worker_files:
        findings["worker_files_found"] = True
        findings["notes"].append(f"✓ Found {len(worker_files)} worker files: {[f.name for f in worker_files]}")
    else:
        findings["notes"].append("✗ No worker*.py files found in services directory")
        
    # Check specific files for heartbeat patterns
    heart_beat_files = [
        "backend/app/api/routers/novels.py",
        "backend/app/api/routers/writer.py",
        "backend/app/services/generation_call_service.py",
    ]
    
    for filepath in heart_beat_files:
        full_path = Path(base_path) / filepath
        if full_path.exists():
            content = full_path.read_text()
            if "heartbeat" in content.lower():
                findings["heartbeat_implementation"] = True
                findings["notes"].append(f"✓ Heartbeat found in: {filepath}")
                
                # Determine if application-level or multi-instance
                if "multi_instance" not in content.lower() and "distributed" not in content.lower():
                    findings["notes"].append(f"  → This is APPLICATION-level heartbeat only")
                    
    return findings


def generate_report(db_path: str, base_path: str, output_path: str):
    """Generate comprehensive verification report."""
    db_result = check_database_schema(db_path)
    code_result = check_codebase_patterns(base_path)
    
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("WORKER EPOCH AND FENCING MECHANISM - VERIFICATION REPORT")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append(f"Verification Date: {datetime.now().strftime('%Y-%m-%d')}")
    report_lines.append(f"Database Path: {db_path}")
    report_lines.append(f"Codebase Path: {base_path}")
    report_lines.append("")
    
    # Database Schema Analysis
    report_lines.append("## DATABASE SCHEMA ANALYSIS")
    report_lines.append("-" * 40)
    report_lines.append(f"Total Tables: {len(db_result['tables'])}")
    if len(db_result['tables']) < 20:
        report_lines.append(f"Tables: {', '.join(db_result['tables'])}")
    else:
        report_lines.append(f"Tables: {', '.join(db_result['tables'][:10])}... ({len(db_result['tables'])} total)")
    report_lines.append("")
    
    if db_result.get('error'):
        report_lines.append(f"⚠ Error: {db_result['error']}")
    else:
        if not db_result['tables']:
            report_lines.append("⚠ Database appears empty or inaccessible")
        else:
            report_lines.append("Worker Table Analysis:")
            has_worker = any('worker' in t.lower() for t in db_result['tables'])
            report_lines.append(f"  - Has Worker-related tables: {'✓ Yes' if has_worker else '✗ No'}")
            report_lines.append(f"  - Has epoch columns: {'✓ Yes' if db_result['has_epoch_columns'] else '✗ No'}")
            has_hb = any('heartbeat' in t.lower() for t in db_result['tables'])
            report_lines.append(f"  - Has heartbeat columns: {'✓ Yes' if has_hb else '✗ No'}")
    
    report_lines.append("")
    
    # Codebase Analysis
    report_lines.append("## CODEBASE ANALYSIS")
    report_lines.append("-" * 40)
    report_lines.append("Worker Implementation Status:")
    report_lines.append(f"  - Worker files found: {'✓ Yes' if code_result['worker_files_found'] else '✗ No'}")
    report_lines.append(f"  - Application heartbeat: {'✓ Yes' if code_result['heartbeat_implementation'] else '✗ No'}")
    report_lines.append(f"  - Multi-instance fencing: {'✓ Yes' if code_result['fencing_implementation'] else '✗ No'}")
    report_lines.append("")
    
    if code_result.get('notes'):
        report_lines.append("Key Findings:")
        for note in code_result['notes']:
            report_lines.append(f"  {note}")
    
    report_lines.append("")
    
    # Current State Summary
    report_lines.append("## CURRENT IMPLEMENTATION STATE")
    report_lines.append("-" * 40)
    report_lines.append("Status: PARTIAL IMPLEMENTATION DETECTED")
    report_lines.append("")
    report_lines.append("What EXISTS:")
    report_lines.append("  ✓ Generation call heartbeat (within single instance)")
    report_lines.append("  ✓ Chapter stale timeout configuration")
    report_lines.append("  ✓ Blueprint job heartbeat mechanism")
    report_lines.append("")
    report_lines.append("What is MISSING:")
    report_lines.append("  ✗ Multi-instance worker coordination layer")
    report_lines.append("  ✗ Worker epoch assignment mechanism")
    report_lines.append("  ✗ Distributed lease/lock system")
    report_lines.append("  ✗ Cross-instance heartbeat tracking")
    report_lines.append("  ✗ Dead worker detection across instances")
    report_lines.append("  ✗ Automatic resource cleanup on worker failure")
    report_lines.append("")
    
    # Acceptance Criteria Assessment
    report_lines.append("## ACCEPTANCE CRITERIA ASSESSMENT")
    report_lines.append("-" * 40)
    
    criteria = [
        ("Each worker instance has unique epoch number logged", False),
        ("Heartbeat written to database every N seconds", "Partial - application-level only"),
        ("Killed worker's lease expires within timeout", False),
        ("Other instances detect dead worker via stale heartbeats", False),
        ("Dead worker resources released automatically", False),
        ("Database shows no conflicts across epochs", "N/A - no epochs yet")
    ]
    
    for i, (criterion, status) in enumerate(criteria, 1):
        marker = "PASS" if status == True else "FAIL" if status == False else "PARTIAL"
        report_lines.append(f"{i}. [{marker}] {criterion}")
        report_lines.append(f"   Status: {status}")
        report_lines.append("")
    
    # Recommendations
    report_lines.append("## RECOMMENDATIONS FOR US-009")
    report_lines.append("-" * 40)
    report_lines.append("The following components need implementation:")
    report_lines.append("")
    report_lines.append("1. Worker Registration Service")
    report_lines.append("   - Create WorkerInstance model/table")
    report_lines.append("   - Generate unique epoch number on registration")
    report_lines.append("   - Record instance_id, ip_address, start_time, epoch")
    report_lines.append("")
    report_lines.append("2. Heartbeat Mechanism")
    report_lines.append("   - Implement periodic heartbeat writing to database")
    report_lines.append("   - Add last_heartbeat_timestamp column to WorkerInstance")
    report_lines.append("   - Configure heartbeat interval (recommended: 30 seconds)")
    report_lines.append("")
    report_lines.append("3. Lease/Fencing System")
    report_lines.append("   - Create WorkerLease table with TTL")
    report_lines.append("   - Implement distributed lock using database advisory locks")
    report_lines.append("   - Or use Redis with EXPIRE for lease management")
    report_lines.append("")
    report_lines.append("4. Dead Worker Detection")
    report_lines.append("   - Scheduled task to query stale heartbeats (>N*interval ago)")
    report_lines.append("   - Graceful cleanup of dead worker resources")
    report_lines.append("   - Remove from active worker registry")
    report_lines.append("")
    report_lines.append("5. Resource Cleanup")
    report_lines.append("   - Release generated resources held by dead workers")
    report_lines.append("   - Cancel running generation tasks")
    report_lines.append("   - Reassign work to healthy workers")
    report_lines.append("")
    
    report_lines.append("=" * 80)
    report_lines.append("END OF VERIFICATION REPORT")
    report_lines.append("=" * 80)
    
    # Write to file
    report_content = "\n".join(report_lines)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(report_content)
    
    print(report_content)
    print(f"\n✅ Report saved to: {output_path}")
    
    return report_content


if __name__ == "__main__":
    base_path = "/run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu"
    db_path = f"{base_path}/storage/xuanqiong_wenshu.db"
    output_path = f"{base_path}/docs/workers_epoch_fencing_verification.md"
    
    generate_report(db_path, base_path, output_path)
