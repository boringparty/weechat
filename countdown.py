import weechat
import os
from datetime import datetime as dt_class, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

SCRIPT_NAME = "countdown"
SCRIPT_AUTHOR = "you"
SCRIPT_VERSION = "2.1"
SCRIPT_LICENSE = "GPL3"
SCRIPT_DESC = "Countdown to next F1 session from raceweek.txt, displays in local tz"

_cache = []
_timer_hook = None

def parse_dt(date_str, time_str, tz):
    date_parts = date_str.split("-")
    time_parts = time_str.split(":")
    return dt_class(
        int(date_parts[0]), int(date_parts[1]), int(date_parts[2]),
        int(time_parts[0]), int(time_parts[1]),
        tzinfo=tz
    )

def format_countdown(target):
    display_tz_str = weechat.config_get_plugin("display_timezone") or "UTC"
    try:
        display_tz = ZoneInfo(display_tz_str)
    except Exception:
        display_tz = timezone.utc

    now = dt_class.now(timezone.utc).astimezone(display_tz)
    target = target.astimezone(display_tz)

    diff = target - now
    total_seconds = int(diff.total_seconds())

    weeks = total_seconds // (7 * 86400)
    remainder = total_seconds % (7 * 86400)
    days = remainder // 86400
    remainder %= 86400
    hours = remainder // 3600
    remainder %= 3600
    minutes = remainder // 60
    seconds = remainder % 60

    if total_seconds <= 300:
        units = [("w", weeks), ("d", days), ("h", hours), ("m", minutes), ("s", f"{seconds:02d}")]
    else:
        units = [("w", weeks), ("d", days), ("h", hours), ("m", minutes)]

    first = next((i for i, (_, v) in enumerate(units) if v), None)
    last = max((i for i, (_, v) in enumerate(units) if v), default=None)

    if first is None:
        return "0s"

    parts = [f"{v}{u}" for u, v in units[first:last+1]]
    return " ".join(parts)

def get_interval_ms():
    now = dt_class.now(timezone.utc)
    for label, dt in _cache:
        if dt > now:
            diff = (dt - now).total_seconds()
            if diff <= 300:
                return 1000
            break
    interval = int(weechat.config_get_plugin("interval") or 60)
    return interval * 60 * 1000

def load_cache():
    global _cache
    filepath = weechat.config_get_plugin("file") or os.path.expanduser("~/.weechat/raceweek.txt")
    tz_str = weechat.config_get_plugin("file_timezone") or "UTC"

    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        weechat.prnt("", f"[countdown] unknown timezone: {tz_str}, falling back to UTC")
        tz = ZoneInfo("UTC")

    if not os.path.exists(filepath):
        weechat.prnt("", f"[countdown] file not found: {filepath}")
        _cache = []
        return

    now = dt_class.now(timezone.utc)
    future_events = []

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                parts = line.split(" ", 2)
                dt_aware = parse_dt(parts[0], parts[1], tz)
                label = parts[2] if len(parts) > 2 else parts[0]
                if dt_aware.astimezone(timezone.utc) > now:
                    future_events.append((label, dt_aware.astimezone(timezone.utc)))
            except (ValueError, IndexError) as e:
                weechat.prnt("", f"[countdown] couldn't parse line: {line} ({e})")

    future_events.sort(key=lambda x: x[1])
    _cache = future_events[:5]

def get_next_event():
    now = dt_class.now(timezone.utc)
    for label, dt in _cache:
        if dt > now:
            return label, dt
    return None, None

def bar_item_cb(data, item, window):
    label, target = get_next_event()
    if target:
        return f"{label}: {format_countdown(target)}"
    return "no events"

def tick_cb(data, remaining_calls):
    global _timer_hook
    weechat.bar_item_update("countdown")

    new_interval = get_interval_ms()
    current_interval = getattr(tick_cb, '_last_interval', None)

    if current_interval != new_interval:
        weechat.unhook(_timer_hook)
        _timer_hook = weechat.hook_timer(new_interval, 0, -1, "tick_cb", "")
        tick_cb._last_interval = new_interval

    return weechat.WEECHAT_RC_OK

def config_changed_cb(data, option, value):
    global _timer_hook
    if "interval" in option:
        if _timer_hook:
            weechat.unhook(_timer_hook)
        interval_ms = (int(value) or 60) * 60 * 1000
        _timer_hook = weechat.hook_timer(interval_ms, 0, -1, "tick_cb", "")
    weechat.bar_item_update("countdown")
    return weechat.WEECHAT_RC_OK

def main():
    global _timer_hook
    weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION,
                     SCRIPT_LICENSE, SCRIPT_DESC, "", "")

    # default configs
    if not weechat.config_is_set_plugin("file"):
        weechat.config_set_plugin("file", os.path.expanduser("~/.config/weechat/raceweek.txt"))
        weechat.config_set_desc_plugin("file", "Path to your raceweek.txt file")

    if not weechat.config_is_set_plugin("file_timezone"):
        weechat.config_set_plugin("file_timezone", "UTC")
        weechat.config_set_desc_plugin("file_timezone",
            "Timezone of the dates in the file (e.g. UTC, America/Vancouver)")

    if not weechat.config_is_set_plugin("display_timezone"):
        weechat.config_set_plugin("display_timezone", "America/Vancouver")
        weechat.config_set_desc_plugin("display_timezone",
            "Timezone to display countdowns in (e.g. America/Vancouver)")

    if not weechat.config_is_set_plugin("interval"):
        weechat.config_set_plugin("interval", "60")
        weechat.config_set_desc_plugin("interval",
            "How often to update the bar item, in minutes (default: 60)")

    weechat.hook_config("plugins.var.python.countdown.interval", "config_changed_cb", "")
    weechat.bar_item_new("countdown", "bar_item_cb", "")
    load_cache()

    _timer_hook = weechat.hook_timer(get_interval_ms(), 0, -1, "tick_cb", "")
    tick_cb._last_interval = get_interval_ms()

    weechat.bar_item_update("countdown")

main()
