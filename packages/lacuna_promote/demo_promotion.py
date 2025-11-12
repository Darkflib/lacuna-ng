#!/usr/bin/env python3
"""
Demo script showing the lacuna_promote promotion flow with example logging.

This script demonstrates the complete promotion flow without requiring Caddy
to be installed, using mocked subprocess calls.
"""

import json
import tempfile
from pathlib import Path
from unittest import mock

from lacuna_promote import PromoteOptions, compile_and_promote


def mock_caddy_commands(*args, **kwargs):
    """Mock Caddy commands to simulate successful promotion."""
    cmd = args[0]

    if cmd[0] == "git":
        # Mock git for metadata
        return mock.Mock(returncode=0, stdout="abc1234\n", stderr="")
    elif cmd[0] == "caddy":
        if cmd[1] == "validate":
            # Validation succeeds
            print(f"    [MOCK] Caddy validate: SUCCESS")
            return mock.Mock(returncode=0, stdout="Valid configuration", stderr="")
        elif cmd[1] == "reload":
            # Reload succeeds
            print(f"    [MOCK] Caddy reload: SUCCESS")
            return mock.Mock(returncode=0, stdout="Configuration reloaded", stderr="")

    return mock.Mock(returncode=0, stdout="", stderr="")


def main():
    """Run the demo."""
    print("=" * 80)
    print("LACUNA PROMOTE DEMONSTRATION")
    print("=" * 80)
    print()
    print("This demo shows the double-buffer promotion flow with example logging.")
    print("Caddy commands are mocked (no actual Caddy installation required).")
    print()

    # Create a temporary directory for the demo
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create example YAML config
        yaml_path = tmppath / "config.yaml"
        yaml_content = """version: 1
defaults:
  hsts: true
  keep_query: true
hosts:
  - host: demo.example.com
    rules:
      - id: homepage
        match: exact
        from: /
        to: https://www.example.com/
        status: 308
      - id: blog
        match: prefix
        from: /blog
        to: https://blog.example.com
        status: 301
"""
        yaml_path.write_text(yaml_content)

        print(f"Created example YAML config: {yaml_path}")
        print()

        # Setup promotion options
        out_dir = tmppath / "config"
        opts = PromoteOptions(out_dir=out_dir)

        print(f"Output directory: {out_dir}")
        print()
        print("=" * 80)
        print("STARTING PROMOTION WITH DOUBLE-BUFFER")
        print("=" * 80)
        print()

        # Run promotion with mocked Caddy
        with mock.patch("subprocess.run", side_effect=mock_caddy_commands):
            try:
                active_path = compile_and_promote(yaml_path, opts)

                print()
                print("=" * 80)
                print("PROMOTION SUCCESSFUL!")
                print("=" * 80)
                print()
                print(f"Active config: {active_path}")
                print()

                # Show the config files created
                print("Config files created:")
                for file in sorted(out_dir.glob("*.json")):
                    size = file.stat().st_size
                    print(f"  - {file.name} ({size} bytes)")

                # Show a snippet of the generated config
                print()
                print("Active config metadata:")
                with open(active_path) as f:
                    config_data = json.load(f)
                    if "_meta" in config_data:
                        print(json.dumps(config_data["_meta"], indent=2))

            except Exception as e:
                print(f"ERROR: {e}")
                return 1

    return 0


if __name__ == "__main__":
    exit(main())
