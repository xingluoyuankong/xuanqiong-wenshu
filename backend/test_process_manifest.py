"""
Test script for ProcessManifest functionality.
Run this to verify the manifest works correctly.
"""

import os
import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.process_manifest import ProcessManifest, launch_subprocess_with_manifest, cleanup_subprocess_with_manifest
from subprocess import Popen


def test_process_manifest():
    """Test basic process tracking."""
    print("=== Testing ProcessManifest ===")
    
    # Create manifest
    manifest = ProcessManifest()
    manifest.start_time = "2026-09-17T18:00:00"  # Fixed time for testing
    
    # Test adding processes (without actually running subprocess)
    record = manifest.add_process(
        pid=12345,
        command="python app.main:app --host 0.0.0.0 --port 8013",
        parent_pid=os.getpid(),
        process_type="backend",
        description="FastAPI backend server"
    )
    
    print(f"✓ Added test process PID={record['pid']}")
    
    # Add another completed process
    record2 = manifest.add_process(
        pid=67890,
        command="node frontend --host 0.0.0.0 --port 5174",
        parent_pid=os.getpid(),
        process_type="frontend",
        description="Vite dev server"
    )
    
    # Simulate completion
    manifest.remove_process(67890, 0, "completed_successfully")
    
    print(f"✓ Recorded process completion for PID={67890}")
    
    # Save manifest
    log_dir = Path("/tmp/test-manifest")
    log_dir.mkdir(exist_ok=True)
    
    filepath = manifest.save(log_dir / "test_current_run.json")
    print(f"✓ Manifest saved to: {filepath}")
    
    # Load and verify
    loaded = ProcessManifest.load(filepath)
    
    assert len(loaded.processes) == 2
    active = [p for p in loaded.processes if p["exit_code"] is None]
    completed = [p for p in loaded.processes if p["exit_code"] is not None]
    
    assert len(active) == 1, f"Expected 1 active, got {len(active)}"
    assert len(completed) == 1, f"Expected 1 completed, got {len(completed)}"
    
    print(f"✓ Manifest loaded successfully")
    print(f"  - Total processes: {loaded.total_processes}")
    print(f"  - Active count: {loaded.active_count}")
    print(f"  - Completed count: {loaded.completed_count}")
    
    # Print manifest content (truncated)
    print("\n=== Manifest Content (first process) ===")
    proc = loaded.processes[0]
    print(f"  PID: {proc['pid']}")
    print(f"  Command: {proc['command'][:50]}...")
    print(f"  Start: {proc['start_time']}")
    print(f"  Exit: {proc['exit_code']} ({proc['exit_reason']})")
    
    print("\n✅ All tests passed!")
    return True


if __name__ == "__main__":
    try:
        success = test_process_manifest()
        if success:
            print("\n🎉 ProcessManifest implementation verified!")
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
