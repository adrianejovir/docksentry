#!/usr/bin/env python3
"""Health monitor - alerts when containers go down or unhealthy."""

import json
import os
import subprocess
import threading
import time


class HealthMonitor:
    def __init__(self, config, bot, check_interval=60):
        self.config = config
        self.bot = bot
        self.running = False
        self.thread = None
        self.check_interval = check_interval  # seconds
        self.state_file = os.path.join(config.data_dir, "health_state.json")
        self_alert_config_file = os.path.join(config.data_dir, "alert_config.json")
        self._load_state()
        self._load_alert_config()

    def _load_state(self):
        """Load previous container state."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file) as f:
                    self.prev_state = json.load(f)
            except:
                self.prev_state = {}
        else:
            self.prev_state = {}

    def _save_state(self):
        """Save current container state."""
        with open(self.state_file, "w") as f:
            json.dump(self.prev_state, f)

    def _load_alert_config(self):
        """Load alert configuration."""
        if os.path.exists(self_alert_config_file):
            try:
                with open(self_alert_config_file) as f:
                    self.alert_config = json.load(f)
            except:
                self.alert_config = {"enabled": True, "ignore": []}
        else:
            self.alert_config = {"enabled": True, "ignore": []}

    def start(self):
        """Start health monitoring."""
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop health monitoring."""
        self.running = False

    def _run(self):
        """Main monitoring loop."""
        while self.running:
            try:
                self._check_health()
            except Exception as e:
                if self.config.debug:
                    print(f"Health check error: {e}")
            time.sleep(self.check_interval)

    def _check_health(self):
        """Check health of all containers."""
        if not self.alert_config.get("enabled", True):
            return

        # Get all containers
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}|{{.Status}}|{{.State}}"],
            capture_output=True, text=True, timeout=30
        )
        if not result.stdout:
            return

        current_state = {}
        alert_sent = False

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            name = parts[0] if len(parts) > 0 else ""
            status = parts[1] if len(parts) > 1 else ""
            state = parts[2] if len(parts) > 2 else "unknown"

            # Skip ignored containers
            if name in self.alert_config.get("ignore", []):
                continue

            current_state[name] = state

            # Check if was running but now stopped/exited
            prev_state = self.prev_state.get(name, "unknown")
            if prev_state in ("running", "created") and state in ("exited", "dead", "removing"):
                # Container went down!
                self._send_alert(name, prev_state, status)
                alert_sent = True

            # Check for unhealthy
            if "unhealthy" in status.lower() and prev_state != "unhealthy":
                self._send_alert(name, "healthy", status, unhealthy=True)
                alert_sent = True

        # Update state
        self.prev_state = current_state
        self._save_state()

    def _send_alert(self, container, prev_state, current_status, unhealthy=False):
        """Send alert to Telegram."""
        if unhealthy:
            msg = f"⚠️ *Unhealthy Container:*\n`{container}`\n{current_status}"
        else:
            msg = f"🔴 *Container Down!*\n`{container}`\nWas: {prev_state}\nNow: {current_status}"
        
        try:
            self.bot.send_message(msg)
        except Exception as e:
            print(f"Alert send error: {e}")

    def add_ignore(self, container):
        """Add container to ignore list."""
        if "ignore" not in self.alert_config:
            self.alert_config["ignore"] = []
        if container not in self.alert_config["ignore"]:
            self.alert_config["ignore"].append(container)
            self._save_alert_config()

    def remove_ignore(self, container):
        """Remove container from ignore list."""
        if "ignore" in self.alert_config and container in self.alert_config["ignore"]:
            self.alert_config["ignore"].remove(container)
            self._save_alert_config()

    def _save_alert_config(self):
        """Save alert configuration."""
        with open(self_alert_config_file, "w") as f:
            json.dump(self.alert_config, f)