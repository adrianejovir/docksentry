#!/usr/bin/env python3
"""Uptime monitor - checks HTTP endpoints and alerts if down."""

import json
import os
import threading
import time
import urllib.request
import urllib.error


class UptimeMonitor:
    def __init__(self, config, bot, check_interval=60):
        self.config = config
        self.bot = bot
        self.running = False
        self.thread = None
        self.check_interval = check_interval
        self.config_file = os.path.join(config.data_dir, "uptime_targets.json")
        self._load_targets()

    def _load_targets(self):
        """Load monitoring targets."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file) as f:
                    self.targets = json.load(f)
            except:
                self.targets = []
        else:
            self.targets = []

    def _save_targets(self):
        """Save targets to file."""
        with open(self.config_file, "w") as f:
            json.dump(self.targets, f)

    def add_target(self, name, url, expected_status=200):
        """Add a target to monitor."""
        for t in self.targets:
            if t["name"] == name:
                return False  # Already exists
        self.targets.append({
            "name": name,
            "url": url,
            "expected_status": expected_status
        })
        self._save_targets()
        return True

    def remove_target(self, name):
        """Remove a target."""
        self.targets = [t for t in self.targets if t["name"] != name]
        self._save_targets()

    def get_targets(self):
        """Get all targets."""
        return self.targets

    def start(self):
        """Start monitoring."""
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop monitoring."""
        self.running = False

    def _run(self):
        """Main monitoring loop."""
        while self.running:
            try:
                self._check_all()
            except Exception as e:
                if self.config.debug:
                    print(f"Uptime check error: {e}")
            time.sleep(self.check_interval)

    def _check_all(self):
        """Check all targets."""
        for target in self.targets:
            self._check_target(target)

    def _check_target(self, target):
        """Check a single target."""
        name = target["name"]
        url = target["url"]
        expected = target.get("expected_status", 200)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Docksentry-Uptime/1.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                actual = response.getcode()
                if actual != expected:
                    self._send_alert(name, url, expected, actual, "status")
        except urllib.error.HTTPError as e:
            self._send_alert(name, url, expected, e.code, "http_error")
        except urllib.error.URLError as e:
            self._send_alert(name, url, expected, str(e.reason), "down")
        except Exception as e:
            self._send_alert(name, url, expected, str(e), "error")

    def _send_alert(self, name, url, expected, actual, reason):
        """Send alert to Telegram."""
        if reason == "down":
            msg = f"🔴 *{name} is DOWN!*\n`{url}`\nError: {actual}"
        elif reason == "http_error":
            msg = f"⚠️ *{name} HTTP Error!*\n`{url}`\nExpected: {expected}, Got: {actual}"
        elif reason == "status":
            msg = f"⚠️ *{name} Status Mismatch!*\n`{url}`\nExpected: {expected}, Got: {actual}"
        else:
            msg = f"⚠️ *{name} Error!*\n`{url}`\n{actual}"
        
        try:
            self.bot.send_message(msg)
        except Exception as e:
            print(f"Uptime alert error: {e}")

    def check_now(self):
        """Check all targets and return results."""
        results = []
        for target in self.targets:
            name = target["name"]
            url = target["url"]
            expected = target.get("expected_status", 200)
            
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Docksentry-Uptime/1.0"})
                with urllib.request.urlopen(req, timeout=10) as response:
                    actual = response.getcode()
                    status = "✅" if actual == expected else "⚠️"
                    results.append({
                        "name": name,
                        "url": url,
                        "status": status,
                        "code": actual,
                        "expected": expected
                    })
            except urllib.error.HTTPError as e:
                results.append({
                    "name": name,
                    "url": url,
                    "status": "❌",
                    "code": e.code,
                    "expected": expected
                })
            except Exception as e:
                results.append({
                    "name": name,
                    "url": url,
                    "status": "❌",
                    "code": str(e)[:50],
                    "expected": expected
                })
        
        return results