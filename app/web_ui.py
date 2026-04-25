#!/usr/bin/env python3
"""Optional lightweight Web UI for configuration and status."""

import base64
import hashlib
import json
import os
import secrets
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


def create_handler(config, checker, bot, password=None):
    """Create a request handler with access to app components."""

    # Pre-compute password hash if set
    pw_hash = hashlib.sha256(password.encode()).hexdigest() if password else None

    class WebHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Suppress default logging

        def _check_auth(self):
            """Check Basic Auth if password is configured."""
            if not pw_hash:
                return True
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Basic "):
                return False
            try:
                decoded = base64.b64decode(auth[6:]).decode()
                user, pw = decoded.split(":", 1)
                return hashlib.sha256(pw.encode()).hexdigest() == pw_hash
            except Exception:
                return False

        def _send_auth_required(self):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Docksentry"')
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>401 - Login required</h1>")

        def _send_html(self, html, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())

        def _send_redirect(self, path="/"):
            self.send_response(303)
            self.send_header("Location", path)
            self.end_headers()

        def _get_path(self):
            """Return path without query string."""
            return urlparse(self.path).path

        def _get_containers(self):
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}|{{.Image}}|{{.Status}}"],
                capture_output=True, text=True
            )
            containers = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("|", 2)
                if len(parts) == 3:
                    containers.append({
                        "name": parts[0],
                        "image": parts[1],
                        "status": parts[2],
                    })
            return containers

        def _get_pending(self):
            if os.path.exists(config.pending_file):
                with open(config.pending_file) as f:
                    return json.load(f)
            return []

        def _render_page(self, content, active="status"):
            from i18n import get_translator
            from version import VERSION
            t = get_translator(config.language)

            nav_items = [
                ("status", f'📊 {t("web_nav_status")}', "/"),
                ("uptime", f'⏱️ Uptime', "/uptime"),
                ("history", f'📋 {t("web_nav_history")}', "/history"),
                ("logs", f'📜 {t("web_nav_logs")}', "/logs"),
                ("settings", f'⚙️ {t("web_nav_settings")}', "/settings"),
            ]
            nav_html = ""
            for key, label, href in nav_items:
                cls = ' class="active"' if key == active else ""
                nav_html += f'<a href="{href}"{cls}>{label}</a> '

            return f"""<!DOCTYPE html>
<html lang="{config.language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Docksentry</title>
<link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
    --bg-deep: #1f1633;
    --bg-darker: #150f23;
    --bg-surface: #241b44;
    --border: #362d59;
    --text: #ffffff;
    --text-muted: #a8a3b8;
    --accent: #c2ef4e;
    --accent-purple: #6a5fc1;
    --btn-bg: #79628c;
    --btn-hover: #8a739a;
    --radius: 8px;
    --radius-lg: 12px;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ touch-action: manipulation; }}
body {{ font-family: 'Rubik', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg-deep); color: var(--text); line-height: 1.5; min-height: 100vh; }}
.header {{ background: var(--bg-darker); border-bottom: 1px solid var(--border); padding: 16px 20px; position: sticky; top: 0; z-index: 100; }}
.header-content {{ max-width: 900px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }}
.header h1 {{ font-size: 18px; font-weight: 600; letter-spacing: -0.5px; }}
.menu-toggle {{ display: none; background: none; border: none; color: var(--text); font-size: 24px; cursor: pointer; padding: 4px; }}
nav {{ margin-top: 12px; }}
nav a {{ color: var(--text-muted); text-decoration: none; padding: 10px 14px; border-radius: var(--radius); font-size: 14px; font-weight: 500; display: inline-block; transition: all 0.2s; }}
nav a:hover {{ color: var(--text); background: var(--border); }}
nav a.active {{ color: var(--accent); background: rgba(194, 239, 78, 0.1); }}
.content {{ max-width: 900px; margin: 24px auto; padding: 0 16px 24px; }}
.card {{ background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px; margin-bottom: 16px; }}
.card h2 {{ font-size: 16px; margin-bottom: 16px; color: var(--accent); font-weight: 600; letter-spacing: -0.3px; }}
.table-wrapper {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; min-width: 500px; }}
th {{ text-align: left; padding: 10px 12px; color: var(--text-muted); border-bottom: 1px solid var(--border); font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
td {{ padding: 12px; border-bottom: 1px solid var(--border); }}
tr:hover {{ background: rgba(54, 45, 89, 0.3); }}
.code {{ font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace; font-size: 13px; color: #dcdcaa; word-break: break-all; }}
.badge {{ display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
.badge-green {{ background: rgba(63, 185, 80, 0.15); color: #3fb950; }}
.badge-yellow {{ background: rgba(210, 153, 34, 0.15); color: #d29922; }}
.badge-blue {{ background: rgba(88, 166, 255, 0.15); color: #58a6ff; }}
.badge-red {{ background: rgba(248, 81, 73, 0.15); color: #f85149; }}
.badge-purple {{ background: rgba(188, 140, 255, 0.15); color: #bc8cff; }}
.badge-accent {{ background: rgba(194, 239, 78, 0.15); color: var(--accent); }}
form {{ margin-top: 8px; }}
label {{ display: block; margin-bottom: 6px; font-size: 13px; color: var(--text-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }}
input, select {{ background: var(--bg-darker); border: 1px solid var(--border); color: var(--text); padding: 12px 14px;
    border-radius: var(--radius); font-size: 15px; width: 100%; margin-bottom: 16px; -webkit-appearance: none; }}
select {{ cursor: pointer; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23a8a3b8' d='M6 8L1 3h10z'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 12px center; padding-right: 36px; }}
input:focus, select:focus {{ outline: none; border-color: var(--accent-purple); box-shadow: 0 0 0 3px rgba(106, 95, 193, 0.2); }}
.checkbox-label {{ display: flex; align-items: center; gap: 10px; cursor: pointer; margin-bottom: 12px; }}
.checkbox-label input {{ width: auto; margin: 0; }}
.btn {{ background: var(--btn-bg); color: var(--text); border: none; padding: 12px 24px; border-radius: var(--radius);
    cursor: pointer; font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; transition: all 0.2s; width: 100%; }}
.btn:hover {{ background: var(--btn-hover); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
.btn-accent {{ background: var(--accent); color: var(--bg-deep); }}
.btn-accent:hover {{ background: #d4f06a; }}
.btn-outline {{ background: transparent; color: var(--text-muted); border: 1px solid var(--border); }}
.btn-outline:hover {{ color: var(--text); border-color: var(--text-muted); }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
@media (max-width: 600px) {{
    .grid {{ grid-template-columns: 1fr; }}
    nav {{ display: none; }}
    nav.open {{ display: block; margin-top: 16px; }}
    nav a {{ display: block; text-align: center; margin-bottom: 4px; }}
    .menu-toggle {{ display: block; }}
    .content {{ padding: 0 12px 24px; }}
    .card {{ padding: 16px; border-radius: var(--radius); }}
    .btn {{ padding: 14px 20px; font-size: 15px; }}
}}
.stat {{ text-align: center; padding: 16px; }}
.stat .num {{ font-size: 36px; font-weight: 700; color: var(--accent); line-height: 1; }}
.stat .label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 8px; }}
.btn-sm {{ padding: 8px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; border: none; cursor: pointer; text-transform: uppercase; letter-spacing: 0.3px; }}
.toggle {{ position: relative; display: inline-block; width: 44px; height: 24px; vertical-align: middle; }}
.toggle input {{ opacity: 0; width: 0; height: 0; position: absolute; }}
.toggle .slider {{ position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
    background: var(--border); border-radius: 24px; transition: 0.3s; }}
.toggle .slider:before {{ content: ""; position: absolute; height: 18px; width: 18px; left: 3px; bottom: 3px;
    background: var(--text); border-radius: 50%; transition: 0.3s; }}
.toggle input:checked + .slider {{ background: var(--accent); }}
.toggle input:checked + .slider:before {{ transform: translateX(20px); }}
.btn-green {{ background: #238636; color: #fff; }}
.btn-green:hover {{ background: #2ea043; }}
pre {{ background: var(--bg-darker); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px;
    overflow-x: auto; font-size: 12px; line-height: 1.6; color: #dcdcaa; font-family: 'JetBrains Mono', monospace; white-space: pre-wrap; }}
.footer {{ text-align: center; padding: 32px 16px; font-size: 12px; color: var(--text-muted); }}
.actions {{ display: flex; gap: 6px; flex-wrap: wrap; }}
</style>
<script>
function toggleMenu() {{ document.querySelector('nav').classList.toggle('open'); }}
</script>
</head>
<body>
<div class="header">
<div class="header-content">
<h1>Docksentry</h1>
<button class="menu-toggle" onclick="toggleMenu()">☰</button>
</div>
<nav>{nav_html}</nav>
</div>
<div class="content">
{content}
</div>
<div class="footer">Docksentry v{VERSION}</div>
</body>
</html>"""

        def do_GET(self):
            if not self._check_auth():
                return self._send_auth_required()
            path = self._get_path()
            if path == "/" or path == "/status":
                self._page_status()
            elif path == "/history":
                self._page_history()
            elif path == "/uptime":
                self._page_uptime()
            elif path == "/logs":
                self._page_logs()
            elif path == "/settings":
                self._page_settings()
            elif path == "/api/check":
                threading.Thread(target=self._api_check).start()
                self._send_redirect("/")
            else:
                self._send_html("<h1>404</h1>", 404)

        def do_POST(self):
            if not self._check_auth():
                return self._send_auth_required()
            path = self._get_path()
            if path == "/settings":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                params = parse_qs(body)

                # Update language
                if "language" in params:
                    from i18n import available_languages, get_translator
                    new_lang = params["language"][0]
                    if new_lang in available_languages():
                        config.language = new_lang
                        bot.t = get_translator(new_lang)

                # Update debug & auto_selfupdate (checkboxes)
                config.debug = "debug" in params
                config.auto_selfupdate = "auto_selfupdate" in params

                # Update cron schedule
                if "cron_schedule" in params and params["cron_schedule"][0].strip():
                    config.cron_schedule = params["cron_schedule"][0].strip()

                # Update exclude containers
                if "exclude_containers" in params:
                    raw = params["exclude_containers"][0].strip()
                    config.exclude_containers = [c.strip() for c in raw.split(",") if c.strip()] if raw else []

                # Update Discord webhook
                if "discord_webhook" in params:
                    config.discord_webhook = params["discord_webhook"][0].strip()

                # Update generic webhook
                if "webhook_url" in params:
                    config.webhook_url = params["webhook_url"][0].strip()

                # Update Telegram Topic ID
                if "telegram_topic_id" in params:
                    config.telegram_topic_id = params["telegram_topic_id"][0].strip()

                # Persist all changes
                config.save_persistent()

                self._send_redirect("/settings?saved=1")
            elif path == "/uptime":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                params = parse_qs(body)
                
                # Add new target
                if "url" in params and params["url"][0].strip():
                    url = params["url"][0].strip()
                    name = params.get("name", [url.split("://")[1].split("/")[0] if "://" in url else "site"])[0].strip() or url.split("//")[1].split("/")[0]
                    expected = int(params.get("expected", ["200"])[0])
                    if hasattr(bot, "_uptime_monitor"):
                        bot._uptime_monitor.add_target(name, url, expected)
                
                self._send_redirect("/uptime?added=1")
            elif path == "/api/remove-uptime":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                params = parse_qs(body)
                name = params.get("name", [""])[0]
                if name and hasattr(bot, "_uptime_monitor"):
                    bot._uptime_monitor.remove_target(name)
                self._send_redirect("/uptime")
            elif path == "/api/check-uptime":
                if hasattr(bot, "_uptime_monitor"):
                    threading.Thread(target=lambda: self._check_uptime_async(bot._uptime_monitor)).start()
                self._send_redirect("/uptime")
            elif path == "/api/update":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                params = parse_qs(body)
                name = params.get("name", [""])[0]
                if name:
                    threading.Thread(target=self._api_update, args=(name,)).start()
                self._send_redirect("/")
            elif path == "/api/pin":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                params = parse_qs(body)
                name = params.get("name", [""])[0]
                if name:
                    pinned = bot._get_pinned()
                    if name not in pinned:
                        pinned.append(name)
                        bot._save_pinned(pinned)
                self._send_redirect("/")
            elif path == "/api/unpin":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                params = parse_qs(body)
                name = params.get("name", [""])[0]
                if name:
                    pinned = bot._get_pinned()
                    if name in pinned:
                        pinned.remove(name)
                        bot._save_pinned(pinned)
                self._send_redirect("/")
            elif path == "/api/autoupdate":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                params = parse_qs(body)
                name = params.get("name", [""])[0]
                if name:
                    auto_list = bot._get_autoupdate()
                    if name in auto_list:
                        auto_list.remove(name)
                    else:
                        auto_list.append(name)
                    bot._save_autoupdate(auto_list)
                self._send_redirect("/")
            else:
                self._send_html("<h1>404</h1>", 404)

        def _page_status(self):
            containers = self._get_containers()
            pending = self._get_pending()
            pending_names = [u["name"] for u in pending]
            pinned = bot._get_pinned()
            auto_list = bot._get_autoupdate()

            from i18n import get_translator
            t = get_translator(config.language)

            rows = ""
            for c in containers:
                status_text = c["status"]
                if "healthy" in status_text.lower():
                    status_badge = '<span class="badge badge-green">healthy</span>'
                elif "starting" in status_text.lower():
                    status_badge = '<span class="badge badge-yellow">starting</span>'
                else:
                    status_badge = f'<span class="badge badge-blue">running</span>'

                # Badges
                badges = ""
                if c["name"] in pending_names:
                    badges += f' <span class="badge badge-yellow">update</span>'
                if c["name"] in pinned:
                    badges += f' <span class="badge badge-red">{t("web_pinned_badge")}</span>'
                if c["name"] in auto_list:
                    badges += f' <span class="badge badge-purple">{t("web_autoupdate_badge")}</span>'

                # Action buttons
                actions = ""
                if c["name"] in pending_names:
                    actions += f'<form method="POST" action="/api/update" style="display:inline"><input type="hidden" name="name" value="{c["name"]}"><button type="submit" class="btn-sm btn-green">{t("web_update")}</button></form> '
                if c["name"] in pinned:
                    actions += f'<form method="POST" action="/api/unpin" style="display:inline"><input type="hidden" name="name" value="{c["name"]}"><button type="submit" class="btn-sm btn-outline">{t("web_unpin")}</button></form> '
                else:
                    actions += f'<form method="POST" action="/api/pin" style="display:inline"><input type="hidden" name="name" value="{c["name"]}"><button type="submit" class="btn-sm btn-outline">{t("web_pin")}</button></form> '
                # Autoupdate toggle
                is_auto = c["name"] in auto_list
                checked = "checked" if is_auto else ""
                auto_title = t("web_autoupdate_disable") if is_auto else t("web_autoupdate_enable")
                actions += f'<form method="POST" action="/api/autoupdate" style="display:inline" title="{auto_title}"><input type="hidden" name="name" value="{c["name"]}"><label class="toggle"><input type="checkbox" {checked} onchange="this.form.submit()"><span class="slider"></span></label></form>'

                rows += f"""<tr>
<td>{c['name']}{badges}</td>
<td><span class="code">{c['image']}</span></td>
<td>{status_badge}</td>
<td><div class="actions">{actions}</div></td>
</tr>"""

            content = f"""
<div class="grid">
<div class="card stat">
    <div class="num">{len(containers)}</div>
    <div class="label">{t("web_containers")}</div>
</div>
<div class="card stat">
    <div class="num">{len(pending)}</div>
    <div class="label">{t("web_updates_available")}</div>
</div>
</div>

<div class="card">
<h2>{t("web_containers")}</h2>
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
<span style="font-size:12px;color:var(--text-muted)">{t("web_containers_running", count=len(containers))}</span>
<a href="/api/check" class="btn btn-accent">{t("web_check_updates")}</a>
</div>
<div class="table-wrapper">
<div class="table-wrapper">
<table>
<tr><th>{t("web_name")}</th><th>{t("web_image")}</th><th>{t("web_status")}</th><th>{t("web_actions")}</th></tr>
{rows}
</table>
</div>
</div>"""

            self._send_html(self._render_page(content, "status"))

        def _page_uptime(self):
            from i18n import get_translator
            t = get_translator(config.language)
            
            targets = []
            if hasattr(bot, "_uptime_monitor"):
                targets = bot._uptime_monitor.get_targets()
            
            # Run checks
            check_results = []
            if targets and hasattr(bot, "_uptime_monitor"):
                try:
                    check_results = bot._uptime_monitor.check_now()
                except:
                    pass
            
            # Build rows
            rows = ""
            checked_names = {r["name"]: r for r in check_results}
            for target in targets:
                name = target["name"]
                url = target["url"]
                expected = target.get("expected_status", 200)
                
                result = checked_names.get(name, {})
                status = result.get("status", "⏳")
                code = result.get("code", "pending")
                
                rows += f"""<tr>
<td>{name}</td>
<td><span class="code">{url}</span></td>
<td>{status} {code}</td>
<td>
<form method="POST" action="/api/remove-uptime" style="display:inline">
<input type="hidden" name="name" value="{name}">
<button type="submit" class="btn-sm btn-outline">Remove</button>
</form>
</td>
</tr>"""
            
            added = "?added=1" in self.path
            added_html = f'<div style="background:#1a3a2a;color:#3fb950;padding:10px;border-radius:6px;margin-bottom:16px">Target added!</div>' if added else ""
            
            content = f"""
{added_html}
<div class="card">
<h2>⏱️ Add Uptime Target</h2>
<form method="POST" action="/uptime">
<div class="grid">
<div>
<label>Name (optional)</label>
<input type="text" name="name" placeholder="My Website">
</div>
<div>
<label>URL *</label>
<input type="text" name="url" placeholder="https://example.com" required>
</div>
</div>
<div>
<label>Expected Status</label>
<input type="number" name="expected" value="200" style="max-width:100px">
</div>
<button type="submit" class="btn btn-accent">Add Target</button>
</form>
</div>

<div class="card">
<h2>📊 Monitored Sites ({len(targets)})</h2>
<a href="/api/check-uptime" class="btn btn-outline" style="margin-bottom:12px;display:inline-block">🔄 Check Now</a>
<table>
<tr><th>Name</th><th>URL</th><th>Status</th><th>Actions</th></tr>
{rows if targets else '<tr><td colspan="4">No targets configured. Add one above!</td></tr>'}
</table>
</div>"""
            
            self._send_html(self._render_page(content, "uptime"))

        def _check_uptime_async(self, uptime_monitor):
            """Run uptime check in background."""
            try:
                uptime_monitor.check_now()
            except Exception as e:
                print(f"Uptime check error: {e}")

        def _page_history(self):
            from i18n import get_translator
            t = get_translator(config.language)

            history = []
            if os.path.exists(config.history_file):
                try:
                    with open(config.history_file) as f:
                        history = json.load(f)
                except (json.JSONDecodeError, IOError):
                    pass

            if not history:
                content = f"""<div class="card">
<h2>{t("web_history")}</h2>
<p style="color:#8b949e">{t("web_history_empty")}</p>
</div>"""
            else:
                rows = ""
                for h in reversed(history):
                    icon = '<span class="badge badge-green">✅</span>' if h["success"] else '<span class="badge badge-yellow">❌</span>'
                    rows += f"""<tr>
<td>{h['timestamp']}</td>
<td>{h['container']}</td>
<td>{icon}</td>
<td style="font-size:12px">{h.get('detail', '')}</td>
</tr>"""

                content = f"""<div class="card">
<h2>{t("web_history")}</h2>
<table>
<tr><th>{t("web_date")}</th><th>{t("web_name")}</th><th>{t("web_result")}</th><th>{t("web_detail")}</th></tr>
{rows}
</table>
</div>"""

            self._send_html(self._render_page(content, "history"))

        def _page_settings(self):
            from i18n import available_languages, get_translator
            from version import VERSION
            t = get_translator(config.language)

            saved = "?saved=1" in self.path
            saved_html = f'<div style="background:#1a3a2a;color:#3fb950;padding:10px;border-radius:6px;margin-bottom:16px">{t("web_saved")}</div>' if saved else ""

            langs = available_languages()
            lang_names = {"en": "English", "de": "Deutsch", "fr": "Français", "es": "Español", "it": "Italiano", "nl": "Nederlands", "pt": "Português", "pl": "Polski", "tr": "Türkçe", "ru": "Русский", "uk": "Українська", "ar": "العربية", "hi": "हिन्दी", "ja": "日本語", "ko": "한국어", "zh": "中文"}
            lang_options = ""
            for l in langs:
                sel = 'selected' if l == config.language else ''
                name = lang_names.get(l, l.upper())
                lang_options += f'<option value="{l}" {sel}>{name}</option>\n'

            debug_checked = 'checked' if config.debug else ''
            auto_su_checked = 'checked' if config.auto_selfupdate else ''

            # Mask sensitive values
            token_masked = f"{config.bot_token[:4]}...{config.bot_token[-4:]}" if len(config.bot_token) > 8 else "***"
            chat_masked = f"{config.chat_id[:3]}...{config.chat_id[-3:]}" if len(config.chat_id) > 6 else "***"

            content = f"""
{saved_html}
<div class="card">
<h2>{t("web_settings")}</h2>
<form method="POST" action="/settings">

<div class="grid">
<div>
<label>{t("web_language")}</label>
<select name="language">
{lang_options}
</select>
</div>
<div>
<label>{t("web_cron_schedule")}</label>
<input type="text" name="cron_schedule" value="{config.cron_schedule}">
</div>
</div>

<div class="grid">
<div>
<label><input type="checkbox" name="debug" {debug_checked} style="width:auto;margin-right:8px"> {t("web_debug_mode")}</label>
</div>
<div>
<label><input type="checkbox" name="auto_selfupdate" {auto_su_checked} style="width:auto;margin-right:8px"> {t("web_auto_selfupdate")}</label>
</div>
</div>

<div style="margin-top:8px">
<label>{t("web_excluded")}</label>
<input type="text" name="exclude_containers" value="{', '.join(config.exclude_containers)}" placeholder="container1, container2">
</div>

<div style="margin-top:8px">
<label>Telegram Topic ID</label>
<input type="text" name="telegram_topic_id" value="{config.telegram_topic_id}" placeholder="{t("web_topic_id_placeholder")}">
</div>

<div style="margin-top:8px">
<label>Discord Webhook</label>
<input type="text" name="discord_webhook" value="{config.discord_webhook}" placeholder="https://discord.com/api/webhooks/...">
</div>

<div style="margin-top:8px">
<label>Webhook URL</label>
<input type="text" name="webhook_url" value="{config.webhook_url}" placeholder="https://your-service/webhook">
</div>

<div style="margin-top:16px">
<button type="submit" class="btn">{t("web_save")}</button>
</div>

</form>
</div>

<div class="card">
<h2>Info</h2>
<table>
<tr><td>Version</td><td><code>v{VERSION}</code></td></tr>
<tr><td>Bot Token</td><td><code>{token_masked}</code></td></tr>
<tr><td>Chat ID</td><td><code>{chat_masked}</code></td></tr>
<tr><td>Data Dir</td><td><code>{config.data_dir}</code></td></tr>
</table>
<p style="font-size:12px;color:#484f58;margin-top:8px">Bot Token and Chat ID can only be changed via environment variables.</p>
</div>"""

            self._send_html(self._render_page(content, "settings"))

        def _page_logs(self):
            from i18n import get_translator
            t = get_translator(config.language)

            query = parse_qs(urlparse(self.path).query)
            container = query.get("container", [""])[0]
            lines = int(query.get("lines", ["50"])[0])

            containers = self._get_containers()

            # Container dropdown
            options = ""
            for c in containers:
                sel = 'selected' if c["name"] == container else ''
                options += f'<option value="{c["name"]}" {sel}>{c["name"]}</option>\n'

            log_html = ""
            if container:
                result = subprocess.run(
                    ["docker", "logs", "--tail", str(lines), container],
                    capture_output=True, text=True, timeout=10
                )
                output = result.stdout or result.stderr
                if output.strip():
                    # Escape HTML
                    import html
                    log_html = f'<pre>{html.escape(output.strip())}</pre>'
                else:
                    log_html = f'<p style="color:#8b949e">No logs found.</p>'

            content = f"""
<div class="card">
<h2>{t("web_logs")}</h2>
<form method="GET" action="/logs" style="display:flex;gap:12px;align-items:end;margin-bottom:16px">
<div style="flex:1">
<label>Container</label>
<select name="container">{options}</select>
</div>
<div style="width:100px">
<label>{t("web_logs_lines")}</label>
<input type="number" name="lines" value="{lines}" min="10" max="500">
</div>
<button type="submit" class="btn btn-blue" style="height:38px">{t("web_logs_show")}</button>
</form>
{log_html}
</div>"""

            self._send_html(self._render_page(content, "logs"))

        def _api_update(self, name):
            """Trigger update for a single container from Web UI."""
            try:
                if not os.path.exists(config.pending_file):
                    return
                with open(config.pending_file) as f:
                    updates = json.load(f)
                target = next((u for u in updates if u["name"] == name), None)
                if not target:
                    return
                compose_kwargs = {k: target[k] for k in target if k.startswith("compose_")}
                success, msg = checker.update_container(name, target["image"], **compose_kwargs)
                status = "✅" if success else "❌"
                bot.send_message(f"{status} `{name}`: {msg}")
                if bot.notifier:
                    bot.notifier.send_update_result(name, target["image"], success, msg)
                # Remove from pending
                remaining = [u for u in updates if u["name"] != name]
                with open(config.pending_file, "w") as f:
                    json.dump(remaining, f)
            except Exception as e:
                print(f"Web UI update error: {e}")

        def _api_check(self):
            try:
                updates = checker.check_all(bot=bot)
                if updates:
                    bot.notify_updates(updates)
            except Exception as e:
                print(f"Web UI check error: {e}")

    return WebHandler


class WebUI:
    def __init__(self, config, checker, bot, port=8080, password=""):
        self.config = config
        self.port = port
        self.handler = create_handler(config, checker, bot, password or None)
        self.server = None
        self.thread = None

    def start(self):
        self.server = HTTPServer(("0.0.0.0", self.port), self.handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"Web UI started on port {self.port}")

    def stop(self):
        if self.server:
            self.server.shutdown()
