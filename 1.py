#!/usr/bin/env python3
import argparse
import base64
import concurrent.futures
import csv
import curses
import difflib
import hashlib
import html as html_module
import json
import math
import os
import random
import re
import signal
import socket
import sqlite3
import ssl
import sys
import tarfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict, Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO


class Telemetry:
    def __init__(self):
        self.sink = None
        self.verbose = True
        self.lock = threading.Lock()
        self.max_line = 600
        self._seen = set()
        self._seen_lock = threading.Lock()

    def bind(self, sink):
        with self.lock:
            self.sink = sink

    def unbind(self):
        with self.lock:
            self.sink = None

    def emit(self, tag, msg, dedupe=False):
        if not self.verbose and tag not in ("PHASE", "REPORT", "ERROR", "WARN", "SAVE", "PHASES", "PROXY", "CKPT", "DIFF", "CRED", "CACHE", "RAW", "COVERAGE", "SELECT", "JITTER", "RATE"):
            return
        line = f"[{tag}] {msg}" if tag else str(msg)
        if len(line) > self.max_line:
            line = line[: self.max_line - 3] + "..."
        if dedupe:
            with self._seen_lock:
                if line in self._seen:
                    return
                if len(self._seen) > 50000:
                    self._seen = set(list(self._seen)[-25000:])
                self._seen.add(line)
        with self.lock:
            if self.sink:
                try:
                    self.sink(line)
                except Exception:
                    pass
            else:
                try:
                    print(line)
                except Exception:
                    pass


TELEMETRY = Telemetry()


def T(tag, msg, dedupe=False):
    TELEMETRY.emit(tag, msg, dedupe=dedupe)


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Fedora; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Arch Linux; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Debian; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; openSUSE; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) Gecko/20100101 Firefox/118.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:117.0) Gecko/20100101 Firefox/117.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:116.0) Gecko/20100101 Firefox/116.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Arch Linux; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Android 14; Mobile; rv:124.0) Gecko/124.0 Firefox/124.0",
    "Mozilla/5.0 (Android 13; Mobile; rv:123.0) Gecko/123.0 Firefox/123.0",
    "Mozilla/5.0 (Android 14; Tablet; rv:122.0) Gecko/122.0 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 OPR/107.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 OPR/107.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Brave/121",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Vivaldi/6.6.3271.53",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Vivaldi/6.5.3206.63",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Arc/1.29.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-A536B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; SM-A515F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; CPH2451) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36 OPR/76.2.4027.73374",
    "Mozilla/5.0 (Linux; Android 13; V2254) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36 UC Browser/13.8.2.1323",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPod touch; CPU iPhone OS 15_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 DuckDuckGo/7",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Yandex/1.9.0",
    "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36 Yandex/23.9.1",
    "Mozilla/5.0 (Linux; U; Android 4.4.2; en-us; SCH-I535 Build/KOT49H) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30",
    "Mozilla/5.0 (Linux; U; Android 4.0.3; de-ch; HTC Sensation Build/IML74K) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Avast/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Whale/3.22.205.18",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Chromium/120.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/119.0.6045.199 Chrome/119.0.6045.199 Safari/537.36",
    "Mozilla/5.0 (X11; CrOS x86_64 15662.76.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko",
    "Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/6.0)",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)",
    "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/49.0.2623.112 Safari/537.36",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "Mozilla/5.0 (compatible; DuckDuckBot/1.0; +http://duckduckgo.com/duckduckbot.html)",
    "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
    "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
    "Mozilla/5.0 (compatible; Sogou web spider/4.0; +http://www.sogou.com/docs/help/webmasters.htm#07)",
    "Mozilla/5.0 (compatible; Exabot/3.0; +http://www.exabot.com/go/robot)",
    "Mozilla/5.0 (compatible; archive.org_bot; +http://archive.org/details/archive.org_bot)",
    "Mozilla/5.0 (compatible; archive.org_bot; Wayback Machine Live Record; +http://archive.org/details/archive.org_bot)",
    "Mozilla/5.0 (compatible; Stratascan/4.0; +research/osint)",
    "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)",
    "Mozilla/5.0 (compatible; SemrushBot/7~bl; +http://www.semrush.com/bot.html)",
    "Mozilla/5.0 (compatible; MJ12bot/v1.4.8; http://mj12bot.com/)",
    "Mozilla/5.0 (compatible; DotBot/1.2; +https://opensiteexplorer.org/dotbot)",
    "Mozilla/5.0 (compatible; PetalBot; +https://webmaster.petalsearch.com/site/petalbot)",
    "Mozilla/5.0 (compatible; YisouSpider/5.0; +http://www.yisou.com)",
    "Mozilla/5.0 (compatible; Applebot/0.3; +http://www.apple.com/go/applebot)",
    "Mozilla/5.0 (compatible; Yeti/1.1; +http://naver.me/spd)",
    "Mozilla/5.0 (compatible; SeznamBot/3.2; +http://fulltext.sblog.cz/)",
    "Mozilla/5.0 (compatible; Qwantify/2.4w; +https://www.qwant.com/)",
    "Mozilla/5.0 (compatible; 008/0.83; http://www.80legs.com/webcrawler.html)",
    "curl/8.5.0",
    "curl/8.4.0",
    "curl/8.3.0",
    "curl/8.2.0",
    "curl/8.1.0",
    "curl/8.0.1",
    "curl/7.88.1",
    "curl/7.86.0",
    "curl/7.84.0",
    "Wget/1.21.4 (linux-gnu)",
    "Wget/1.21.3",
    "Wget/1.21.2",
    "Wget/1.21.1",
    "Wget/1.20.3 (linux-gnu)",
    "Wget/1.19.5 (linux-gnu)",
    "python-requests/2.31.0",
    "python-requests/2.30.0",
    "python-requests/2.29.0",
    "python-requests/2.28.2",
    "python-urllib3/2.1.0",
    "python-urllib3/2.0.7",
    "Go-http-client/2.0",
    "Go-http-client/1.1",
    "Java/1.8.0_292",
    "Java/11.0.20",
    "Java/17.0.9",
    "Java/21.0.1",
    "Apache-HttpClient/4.5.14 (Java/17)",
    "Apache-HttpClient/5.3.1 (Java/21)",
    "PostmanRuntime/7.36.0",
    "PostmanRuntime/7.35.0",
    "PostmanRuntime/7.34.0",
    "Insomnia/8.5.1",
    "Insomnia/2023.5.8",
    "okhttp/4.12.0",
    "okhttp/4.11.0",
    "okhttp/4.10.0",
    "axios/1.6.7",
    "axios/1.6.5",
    "axios/1.6.2",
    "node-fetch/1.0 (+https://github.com/bitinn/node-fetch)",
    "got/14.2.1",
    "undici/6.6.1",
    "dart/3.3 (dart:io)",
    "Ruby/3.3.0 (Net::HTTP)",
    "PHP/8.3.3",
    "LuaSocket/3.0",
    "Perl/5.38.2",
    "Roku/DVP-12.5 (12.5.0.4178)",
    "Roku4640X/DVP-7.70 (297.70E04154A)",
    "AppleCoreMedia/1.0.0.15E148 (iPhone; U; CPU OS 11_2_6 like Mac OS X; en_us)",
    "iTunes/12.12.10 (Windows 10)",
    "Spotify/1.0",
    "NSPlayer/12.00.19041.0000 WMFSDK/12.00.19041.0000",
    "Adobe Flash Player 32.0.0.465",
    "GSA/238.6.14.23.arm64 (iPhone; iOS 17.4; Scale/3.00)",
    "GSA/231.2.12.22.arm64 (iPhone; iOS 17.2; Scale/3.00)",
    "FBAV/438.0.0.34.117 (iPhone; iOS 17.4; Scale/3.00)",
    "Instagram 322.0.0.35.101 (iPhone; iOS 17.4; Scale/3.00)",
    "TikTok 32.5.5 (iPhone; iOS 17.4; Scale/3.00)",
    "WhatsApp/2.24.3.77 (iPhone; iOS 17.4; Scale/3.00)",
    "Snapchat/12.74.0.41 (iPhone; iOS 17.4; Scale/3.00)",
    "Telegram/10.7.1 (iPhone; iOS 17.4; Scale/3.00)",
    "Discord/220.0 (iPhone; iOS 17.4; Scale/3.00)",
    "Reddit/2024.12.0 (iPhone; iOS 17.4; Scale/3.00)",
    "LinkedInApp/4.1.806 (iPhone; iOS 17.4; Scale/3.00)",
    "Twitterrific/5.4.8 (iPhone; iOS 17.4; Scale/3.00)",
    "Mozilla/5.0 (compatible; Nmap Scripting Engine; https://nmap.org/book/nse.html)",
    "Mozilla/5.0 (compatible; masscan/1.3; +https://github.com/robertdavidgraham/masscan)",
    "Mozilla/5.0 (compatible; zgrab/2.1.0)",
    "Mozilla/5.0 (compatible; Nuclei - Open-source project (github.com/projectdiscovery/nuclei))",
    "Mozilla/5.0 (compatible; httpx - Open-source project (github.com/projectdiscovery/httpx))",
    "Mozilla/5.0 (compatible; gau - Open-source project (github.com/lc/gau))",
    "Mozilla/5.0 (compatible; waybackurls - Open-source project (github.com/tomnomnom/waybackurls))",
    "Mozilla/5.0 (compatible; wafw00f/2.2.0)",
    "Mozilla/5.0 (compatible; WhatWeb/0.5.5)",
    "Mozilla/5.0 (compatible; nikto/2.5.0)",
    "Mozilla/5.0 (compatible; sqlmap/1.8.2#stable)",
    "Mozilla/5.0 (compatible; DirBuster/1.0.2)",
    "Mozilla/5.0 (compatible; gobuster/3.6)",
    "Mozilla/5.0 (compatible; ffuf/2.1.0)",
    "Mozilla/5.0 (compatible; feroxbuster/2.10.4)",
    "Mozilla/5.0 (compatible; subfinder/2.6.3)",
    "Mozilla/5.0 (compatible; amass/4.2.0)",
    "Mozilla/5.0 (compatible; assetfinder/0.1.1)",
    "Mozilla/5.0 (compatible; findomain/9.0.4)",
    "Mozilla/5.0 (compatible; httprobe/0.2)",
    "Mozilla/5.0 (compatible; dnsx/1.2.1)",
    "Mozilla/5.0 (compatible; shuffledns/1.0.6)",
    "Mozilla/5.0 (compatible; puredns/2.1.1)",
    "Mozilla/5.0 (compatible; massdns/1.1.0)",
    "Mozilla/5.0 (compatible; zdns/1.0.0)",
]

UA_MODE = "rotate"
UA_FIXED_INDEX = 0
_UA_LOCK = threading.Lock()
_UA_COUNTER = 0


def get_user_agent():
    global _UA_COUNTER
    if UA_MODE == "fixed":
        return USER_AGENTS[UA_FIXED_INDEX % len(USER_AGENTS)]
    if UA_MODE == "random":
        return random.choice(USER_AGENTS)
    with _UA_LOCK:
        ua = USER_AGENTS[_UA_COUNTER % len(USER_AGENTS)]
        _UA_COUNTER += 1
        return ua


def set_ua_mode(mode, fixed_index=None):
    global UA_MODE, UA_FIXED_INDEX
    mode = (mode or "").strip().lower()
    if mode not in ("rotate", "random", "fixed"):
        return False
    UA_MODE = mode
    if mode == "fixed" and fixed_index is not None:
        try:
            UA_FIXED_INDEX = max(0, min(len(USER_AGENTS) - 1, int(fixed_index)))
        except (ValueError, TypeError):
            return False
    T("UA", f"mode set -> {UA_MODE}" + (f" [idx={UA_FIXED_INDEX}]" if UA_MODE == "fixed" else ""))
    return True


class ProxyPool:
    def __init__(self):
        self.list = []
        self.enabled = False
        self.mode = "rotate"
        self.index = 0
        self.failed = set()
        self.lock = threading.Lock()
        self.source_file = None

    def add(self, url):
        url = (url or "").strip()
        if not url:
            return False
        if not re.match(r"^(https?|socks[45])://", url):
            url = "http://" + url
        with self.lock:
            if url in self.list:
                return False
            self.list.append(url)
        return True

    def load_file(self, path, default_scheme="http"):
        p = Path(path).expanduser()
        if not p.exists():
            return -1, f"file not found: {p}"
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return -1, f"read failed: {e}"
        added = 0
        skipped = 0
        with self.lock:
            for raw in text.splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if not re.match(r"^(https?|socks[45])://", line):
                    line = f"{default_scheme}://{line}"
                if line in self.list:
                    skipped += 1
                    continue
                self.list.append(line)
                added += 1
        self.source_file = str(p)
        return added, skipped

    def clear(self):
        with self.lock:
            self.list.clear()
            self.failed.clear()
            self.enabled = False
            self.index = 0
            self.source_file = None

    def next(self):
        with self.lock:
            if not self.list or not self.enabled:
                return None
            available = [p for p in self.list if p not in self.failed]
            if not available:
                self.failed.clear()
                available = list(self.list)
            if self.mode == "random":
                return random.choice(available)
            if self.mode == "fixed":
                return available[0] if available else None
            if not available:
                return None
            p = available[self.index % len(available)]
            self.index = (self.index + 1) % len(available)
            return p

    def mark_failed(self, proxy):
        with self.lock:
            if proxy:
                self.failed.add(proxy)

    def status(self):
        with self.lock:
            return {
                "enabled": self.enabled,
                "mode": self.mode,
                "count": len(self.list),
                "failed": len(self.failed),
                "source_file": self.source_file,
                "list": list(self.list),
            }


PROXIES = ProxyPool()
DIRECT_OPENER = urllib.request.build_opener()


def _build_opener_for(proxy_url):
    if not proxy_url:
        return DIRECT_OPENER
    try:
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        return urllib.request.build_opener(handler)
    except Exception as e:
        T("PROXY", f"opener build failed: {e}")
        return DIRECT_OPENER


def _current_opener():
    p = PROXIES.next()
    return _build_opener_for(p), p


CDX_URL = "https://web.archive.org/cdx/search/cdx"
AVAILABILITY_URL = "https://archive.org/wayback/available"
SPARKLINE_URL = "https://web.archive.org/__wb/sparkline"
CALENDAR_URL = "https://web.archive.org/__wb/calendarcaptures/2"
ANCHOR_URL = "https://web.archive.org/__wb/search/anchor"
TIMEMAP_URL = "https://web.archive.org/web/timemap/link"
TIMEMAP_JSON_URL = "https://web.archive.org/web/timemap/json"
CRT_SH_URL = "https://crt.sh/"
ARCHIVE_TODAY = "https://archive.ph/newest/"
MEMENTO_AGG = "https://timetravel.mementoweb.org/timemap/link/"
COMMON_CRAWL_INDEX = "https://index.commoncrawl.org/"
ROBTEX_URL = "https://freeapi.robtex.com/"
DOH_GOOGLE_URL = "https://dns.google/resolve"
HACKERTARGET_URL = "https://api.hackertarget.com/"
MNEMONIC_PDNS_URL = "https://passivedns.mnemonic.no/search/"
RDAP_URL = "https://rdap.org/domain/"
HSTS_PRELOAD_URL = "https://hstspreload.org/api/v2/status"
IPINFO_URL = "https://ipinfo.io/"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:(?<=\bphone)|(?<=\bfax)|(?<=\btel)|(?<=\bmobile)|(?<=\bcell)|(?<=\bcall)|(?<=\bwhatsapp)|(?<=\bcontact))"
    r"[^\S\n]*[:\-]?[^\S\n]*"
    r"(\+?\d[\d\s().-]{6,}\d)",
    re.IGNORECASE,
)
PHONE_INTL_RE = re.compile(r"\+\d{1,3}[\s.\-]\(?\d{1,4}\)?[\s.\-]\d{2,4}[\s.\-]\d{2,4}(?:[\s.\-]\d{0,4})?")
SOCIAL_RE = re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com|linkedin\.com|facebook\.com|instagram\.com|youtube\.com|github\.com|tiktok\.com|reddit\.com|mastodon\.[a-z]+|threads\.net|bsky\.app|tumblr\.com|pinterest\.com|snapchat\.com|telegram\.org|t\.me|discord\.gg|medium\.com|dev\.to|stackoverflow\.com|gitlab\.com|bitbucket\.org|gitea\.com|keybase\.io|signal\.org|whatsapp\.com|wechat\.com|line\.me|viber\.com|skype\.com|zoom\.us|meet\.google\.com|twitch\.tv|vimeo\.com|dailymotion\.com|soundcloud\.com|spotify\.com|bandcamp\.com|patreon\.com|ko-fi\.com|buymeacoffee\.com)/[^\s\"'<>]+", re.IGNORECASE)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META_GEN_RE = re.compile(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)
LANG_RE = re.compile(r'<html[^>]+lang=["\']([^"\']+)["\']', re.IGNORECASE)
COPYRIGHT_RE = re.compile(r"(?:©|&copy;|Copyright)\s*(\d{4})", re.IGNORECASE)
LINK_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
SCRIPT_SRC_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
FAVICON_RE = re.compile(r'<link[^>]+rel=["\'](?:shortcut icon|icon)["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
META_RE = re.compile(r'<meta\s+([^>]+?)/?>', re.IGNORECASE | re.DOTALL)
META_NAME_RE = re.compile(r'(?:name|property|http-equiv)=["\']([^"\']+)["\']', re.IGNORECASE)
META_CONTENT_RE = re.compile(r'content=["\']([^"\']*)["\']', re.IGNORECASE)
CANONICAL_RE = re.compile(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
ROBOTS_META_RE = re.compile(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)
H_TAG_RE = re.compile(r'<h([1-6])[^>]*>(.*?)</h\1>', re.IGNORECASE | re.DOTALL)
IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
IMG_ALT_RE = re.compile(r'<img[^>]+alt=["\']([^"\']+)["\']', re.IGNORECASE)
IFRAME_SRC_RE = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
FORM_RE = re.compile(r'<form\b([^>]*)>(.*?)</form>', re.IGNORECASE | re.DOTALL)
FORM_ACTION_RE = re.compile(r'action=["\']([^"\']*)["\']', re.IGNORECASE)
INPUT_RE = re.compile(r'<input\b([^>]*?)/?>', re.IGNORECASE)
INPUT_NAME_RE = re.compile(r'name=["\']([^"\']+)["\']', re.IGNORECASE)
INPUT_TYPE_RE = re.compile(r'type=["\']([^"\']+)["\']', re.IGNORECASE)
INPUT_PLACEHOLDER_RE = re.compile(r'placeholder=["\']([^"\']+)["\']', re.IGNORECASE)
STYLESHEET_RE = re.compile(r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
INLINE_SCRIPT_RE = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
INLINE_STYLE_RE = re.compile(r'<style[^>]*>(.*?)</style>', re.IGNORECASE | re.DOTALL)
HTML_COMMENT_RE = re.compile(r'<!--(?!\[if)(.*?)-->', re.DOTALL)
CSS_COMMENT_RE = re.compile(r'/\*(.*?)\*/', re.DOTALL)
JS_LINE_COMMENT_RE = re.compile(r'//([^\n]*)')
JS_BLOCK_COMMENT_RE = re.compile(r'/\*(.*?)\*/', re.DOTALL)
JSONLD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
JSON_BLOB_RE = re.compile(r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
OG_RE = re.compile(r'<meta[^>]+property=["\']og:([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']', re.IGNORECASE)
TWITTER_CARD_RE = re.compile(r'<meta[^>]+name=["\']twitter:([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']', re.IGNORECASE)
HREFLANG_RE = re.compile(r'<link[^>]+rel=["\']alternate["\'][^>]+hreflang=["\']([^"\']+)["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
FEED_RE = re.compile(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
MANIFEST_RE = re.compile(r'<link[^>]+rel=["\']manifest["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
META_REFRESH_RE = re.compile(r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)
SRI_RE = re.compile(r'integrity=["\']([^"\']+)["\']', re.IGNORECASE)
BASE_HREF_RE = re.compile(r'<base[^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
HIDDEN_STYLE_RE = re.compile(r'(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:[;\s]|$)|font-size\s*:\s*0|height\s*:\s*0|width\s*:\s*0|position\s*:\s*absolute\s*;\s*left\s*:\s*-\d{3,})', re.IGNORECASE)
WHITE_ON_WHITE_RE = re.compile(r'color\s*:\s*(?:#fff(?:fff)?|white|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))', re.IGNORECASE)
DATA_ATTR_RE = re.compile(r'data-([a-z0-9\-]+)=["\']([^"\']+)["\']', re.IGNORECASE)
ARIA_LABEL_RE = re.compile(r'aria-(?:label|description)=["\']([^"\']+)["\']', re.IGNORECASE)
TITLE_ATTR_RE = re.compile(r'title=["\']([^"\']{4,})["\']', re.IGNORECASE)
TEMPLATE_TAG_RE = re.compile(r'<template[^>]*>(.*?)</template>', re.IGNORECASE | re.DOTALL)
NOSCRIPT_RE = re.compile(r'<noscript[^>]*>(.*?)</noscript>', re.IGNORECASE | re.DOTALL)
DETAILS_RE = re.compile(r'<details[^>]*>(.*?)</details>', re.IGNORECASE | re.DOTALL)
DIALOG_RE = re.compile(r'<dialog[^>]*>(.*?)</dialog>', re.IGNORECASE | re.DOTALL)
OPTION_RE = re.compile(r'<option[^>]*value=["\']([^"\']+)["\'][^>]*>([^<]*)</option>', re.IGNORECASE)
MEDIA_PRINT_RE = re.compile(r'@media\s+print\s*\{([^}]*)\}', re.IGNORECASE)
DARK_MODE_RE = re.compile(r'@media[^{]*prefers-color-scheme\s*:\s*dark[^{]*\{([^}]*)\}', re.IGNORECASE)
HOVER_RE = re.compile(r':hover\s*\{([^}]*)\}', re.IGNORECASE)
FOCUS_RE = re.compile(r':focus\s*\{([^}]*)\}', re.IGNORECASE)
INITIAL_STATE_RE = re.compile(r'window\.__[A-Z_]+__\s*=\s*(\{.*?\});', re.DOTALL)
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
NUXT_DATA_RE = re.compile(r'window\.__NUXT__\s*=\s*(\{.*?\});', re.DOTALL)
DATA_URI_RE = re.compile(r'data:([^;]+);base64,([A-Za-z0-9+/=]{4,})')
SVG_INLINE_RE = re.compile(r'<svg[^>]*>(.*?)</svg>', re.DOTALL | re.IGNORECASE)
NONCE_RE = re.compile(r'nonce=["\']([^"\']+)["\']', re.IGNORECASE)
PINGBACK_LINK_RE = re.compile(r'<link[^>]+rel=["\'](pingback|webmention|micropub|indieauth|author|me|license)["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
PRECONNECT_RE = re.compile(r'<link[^>]+rel=["\'](preconnect|dns-prefetch|prefetch|preload|prerender)["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
TRACK_CALL_RE = re.compile(r'(?:track|send|log|report)\(\s*["\']([^"\']+)["\']', re.IGNORECASE)
JS_ERROR_RE = re.compile(r'throw\s+new\s+Error\(\s*["\']([^"\']+)["\']', re.IGNORECASE)
WS_URL_RE = re.compile(r'wss?://[^\s"\'<>]+', re.IGNORECASE)
GQL_QUERY_RE = re.compile(r'(?:query|mutation)\s+(\w+)\s*[\(\{]', re.IGNORECASE)
ENV_NAME_RE = re.compile(r'["\'](production|staging|stage|dev|development|test|qa|uat|internal|preprod)["\']', re.IGNORECASE)
VERSION_NUM_RE = re.compile(r'["\']v?(\d+\.\d+\.\d+)["\']')
CONSOLE_LOG_RE = re.compile(r'console\.log\(([^)]{4,200})\)', re.IGNORECASE)
SOURCE_MAP_URL_RE = re.compile(r'sourceMappingURL=([^\s*]+)')

ATOB_RE = re.compile(r'atob\(\s*["\']([A-Za-z0-9+/=]{16,})["\']')
BUFFER_FROM_B64_RE = re.compile(r'Buffer\.from\(\s*["\']([A-Za-z0-9+/=]{16,})["\']\s*,\s*["\']base64["\']')
UINT8_FROM_ATOB_RE = re.compile(r'Uint8Array\.from\(\s*atob\(\s*["\']([A-Za-z0-9+/=]{16,})["\']')
ENV_LINE_RE = re.compile(r'^([A-Z][A-Z0-9_]{2,})\s*=\s*(.+)$', re.MULTILINE)
SENSITIVE_KEY_RE = re.compile(r'(?i)(PASS|PWD|SECRET|KEY|TOKEN|CREDENTIAL|AUTH|DSN|DATABASE_URL|REDIS_URL|AMQP_URL|SMTP_|MAIL_|AWS_|GCP_|AZURE_|JWT|SESSION|COOKIE|SALT|PRIVATE|CLIENT_ID|CLIENT_SECRET)')
WP_CONST_RE = re.compile(r"define\(\s*['\"]([A-Z_]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]\s*\)")
DJANGO_DB_RE = re.compile(r"'PASSWORD'\s*:\s*'([^']+)'")
DOCKER_ENV_KEY_RE = re.compile(r'^\s*-?\s*([A-Z][A-Z0-9_]{2,})\s*[:=]\s*["\']?([^"\'#\n]+)["\']?\s*$', re.MULTILINE)
JWT_PART_RE = re.compile(r'^eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*$')
URL_PARAM_SECRET_RE = re.compile(r'[?&](?:token|key|api_key|apikey|auth|password|pwd|secret|access_token|session|sig|signature)=([^&#\s]{8,200})', re.IGNORECASE)
AUTH_BASIC_IN_URL_RE = re.compile(r'https?://([^:/\s]+):([^@/\s]+)@')
CLOUD_METADATA_RE = re.compile(r'169\.254\.169\.254')
CF_BOT_COOKIE_RE = re.compile(r'__cf_bm=([^;\s]+)')
STACK_TRACE_RE = re.compile(r'(?:Traceback \(most recent call last\)|at [\w$.]+\([\w$.]+\.java:\d+\)|File "[^"]+", line \d+|#\d+\s+[\w\\/.:]+\(\d+\))')

HASH_PATTERNS = {
    "bcrypt": re.compile(r'\$2[abxy]?\$\d{2}\$[./A-Za-z0-9]{53}'),
    "argon2": re.compile(r'\$argon2(?:id|i|d)\$v=\d+\$m=\d+,t=\d+,p=\d+\$[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+'),
    "scrypt": re.compile(r'\$7\$[A-Za-z0-9./]{11,}\$[A-Za-z0-9./]{43,}'),
    "sha512crypt": re.compile(r'\$6\$(?:rounds=\d+\$)?[A-Za-z0-9./]{1,16}\$[A-Za-z0-9./]{86}'),
    "sha256crypt": re.compile(r'\$5\$(?:rounds=\d+\$)?[A-Za-z0-9./]{1,16}\$[A-Za-z0-9./]{43}'),
    "md5crypt": re.compile(r'\$1\$[A-Za-z0-9./]{1,8}\$[A-Za-z0-9./]{22}'),
    "django_pbkdf2": re.compile(r'pbkdf2_sha256\$\d+\$[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+'),
    "werkzeug": re.compile(r'pbkdf2:sha256:\d+\$[A-Za-z0-9]+\$[A-Fa-f0-9]+'),
    "mysql_native": re.compile(r'\*[A-F0-9]{40}'),
    "phpass": re.compile(r'\$P\$[A-Za-z0-9./]{31}'),
    "joomla": re.compile(r'\$2y\$10\$[A-Za-z0-9./]{53}'),
}

GA_RE = re.compile(r'UA-\d{4,10}-\d{1,4}')
GA4_RE = re.compile(r'G-[A-Z0-9]{8,12}')
GTM_RE = re.compile(r'GTM-[A-Z0-9]{4,8}')
FB_PIXEL_RE = re.compile(r'fbq\(\s*[\'"]init[\'"]\s*,\s*[\'"](\d{10,20})[\'"]')
HOTJAR_RE = re.compile(r'hjid\s*[:=]\s*[\'"]?(\d{4,10})')
SEGMENT_RE = re.compile(r'analytics\.load\(\s*[\'"]([A-Za-z0-9]{10,40})[\'"]')
MIXPANEL_RE = re.compile(r'mixpanel\.init\(\s*[\'"]([a-f0-9]{20,40})[\'"]')
MATOMO_RE = re.compile(r'_paq\.push\(\[[\'"]setSiteId[\'"]\s*,\s*[\'"](\d+)[\'"]')
ADSENSE_RE = re.compile(r'pub-\d{10,20}')
DOUBLECLICK_RE = re.compile(r'ca-pub-\d{10,20}')
CLARITY_RE = re.compile(r'clarity\.ms/tag/([a-z0-9]{10,})', re.IGNORECASE)
FULLSTORY_RE = re.compile(r'fullstory\.com/s/([A-Z0-9]{10,})', re.IGNORECASE)
PLAUSIBLE_RE = re.compile(r'plausible\.io/js/(?:script\.)?([a-z0-9.\-]+)\.js', re.IGNORECASE)
FATHOM_ID_RE = re.compile(r'data-site=["\']([A-Z]{8})["\']', re.IGNORECASE)
AMPLITUDE_RE = re.compile(r'amplitude\.getInstance\(\)\.init\(\s*[\'"]([a-f0-9]{32})[\'"]', re.IGNORECASE)
HEAP_RE = re.compile(r'heap\.load\(\s*[\'"](\d{8,12})[\'"]', re.IGNORECASE)
PENDO_RE = re.compile(r'pendo\.initialize\(\s*[\'"]([a-f0-9\-]{36})[\'"]', re.IGNORECASE)
LOGROCKET_RE = re.compile(r'LogRocket\.init\(\s*[\'"]([a-z0-9/]+)[\'"]', re.IGNORECASE)
INTERCOM_RE = re.compile(r'intercomSettings\s*=\s*\{[^}]*app_id\s*:\s*[\'"]([a-z0-9]{8})[\'"]', re.IGNORECASE)
DRIFT_RE = re.compile(r'drift\.load\(\s*[\'"]([a-z0-9]{11})[\'"]', re.IGNORECASE)
ZENDESK_RE = re.compile(r'zE\(\s*[\'"]([a-f0-9\-]+)[\'"]', re.IGNORECASE)
CRISP_RE = re.compile(r'CRISP_WEBSITE_ID\s*=\s*[\'"]([a-f0-9\-]{36})[\'"]', re.IGNORECASE)
TAWK_RE = re.compile(r's\.src\s*=\s*[\'"]https://embed\.tawk\.to/([a-f0-9]+)', re.IGNORECASE)
LIVECHAT_RE = re.compile(r'__lc\.license\s*=\s*(\d+)', re.IGNORECASE)
HUBSPOT_RE = re.compile(r'hs-scripts\.com/(\d{6,10})\.js', re.IGNORECASE)
MARKETO_RE = re.compile(r'Munchkin\.init\(\s*[\'"]([0-9]{3}-[A-Z]{3}-[0-9]{3})[\'"]', re.IGNORECASE)
PARDOT_RE = re.compile(r'pi\.pardot\.com/piA\?pi_act=([0-9]+)', re.IGNORECASE)
KLAVIYO_RE = re.compile(r'static\.klaviyo\.com/onsite/js/klaviyo\.js\?company_id=([A-Za-z0-9]{6})', re.IGNORECASE)
MAILCHIMP_RE = re.compile(r'chimpstatic\.com/mcjs-connected/js/users/([a-f0-9]{32})', re.IGNORECASE)
ACTIVECAMPAIGN_RE = re.compile(r'trackcmp\.us/([a-f0-9]+)', re.IGNORECASE)
CONVERTKIT_RE = re.compile(r'convertkit\.com/forms/(\d+)/', re.IGNORECASE)
DRIP_RE = re.compile(r'drip\.com/_dcs\.js\?a=(\d+)', re.IGNORECASE)
SENDINBLUE_RE = re.compile(r'sibautomation\.com/([a-z0-9]{20})/', re.IGNORECASE)
CUSTOMERIO_RE = re.compile(r'customerio\.com/([a-z0-9]{20})/', re.IGNORECASE)
ITERABLE_RE = re.compile(r'iterable\.com/api/([a-f0-9]{32})', re.IGNORECASE)
BRAZE_RE = re.compile(r'braze\.com/api/([a-f0-9\-]{36})', re.IGNORECASE)
ONESIGNAL_RE = re.compile(r'onesignal\.com/sdks/web/v16/OneSignalSDK\.page\.js.*?appId["\']?\s*[:=]\s*["\']([a-f0-9\-]{36})', re.IGNORECASE)
PUSHER_RE = re.compile(r'pusher\.com.*?key["\']?\s*[:=]\s*["\']([a-f0-9]{20})', re.IGNORECASE)
ABLY_RE = re.compile(r'ably\.com.*?key["\']?\s*[:=]\s*["\']([A-Za-z0-9_\-\.]+)', re.IGNORECASE)
PUBSUB_RE = re.compile(r'pubnub\.com.*?subscribe_key["\']?\s*[:=]\s*["\']([a-z0-9\-]{30,40})', re.IGNORECASE)
AGORA_RE = re.compile(r'agora\.io.*?appId["\']?\s*[:=]\s*["\']([a-f0-9]{32})', re.IGNORECASE)
PAYPAL_CLIENT_RE = re.compile(r'paypal\.com/sdk/js\?client-id=([A-Za-z0-9_\-]+)', re.IGNORECASE)
BRAINTREE_RE = re.compile(r'braintree.*?tokenizationKey["\']?\s*[:=]\s*["\']([a-z0-9]+_b2c_[a-z0-9]+)', re.IGNORECASE)
SQUARE_APP_RE = re.compile(r'squareup\.com.*?applicationId["\']?\s*[:=]\s*["\']([a-z0-9\-]+)', re.IGNORECASE)
RECURLY_RE = re.compile(r'recurly\.com.*?publicKey["\']?\s*[:=]\s*["\']([a-z0-9]{30,40})', re.IGNORECASE)
CHARGEBEE_RE = re.compile(r'chargebee\.com.*?site["\']?\s*[:=]\s*["\']([a-z0-9\-]+)', re.IGNORECASE)
PADDLE_RE = re.compile(r'paddle\.com.*?vendor["\']?\s*[:=]\s*["\'](\d+)', re.IGNORECASE)
LEMON_RE = re.compile(r'lemonsqueezy\.com.*?store["\']?\s*[:=]\s*["\'](\d+)', re.IGNORECASE)
GUMROAD_RE = re.compile(r'gumroad\.com.*?product["\']?\s*[:=]\s*["\']([a-z0-9]+)', re.IGNORECASE)

DOC_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".rtf", ".txt", ".csv", ".tsv",
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".rar", ".7z",
    ".sql", ".db", ".sqlite", ".mdb", ".bak", ".backup", ".old", ".orig",
    ".conf", ".cfg", ".ini", ".env", ".yaml", ".yml", ".toml", ".json", ".xml",
    ".php", ".asp", ".aspx", ".jsp", ".py", ".rb", ".js", ".ts",
    ".log", ".pem", ".crt", ".key", ".p12", ".pfx",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tiff",
    ".mp4", ".mp3", ".wav", ".avi", ".mov", ".mkv", ".flv", ".webm", ".ogg",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".rss", ".atom", ".ics", ".torrent",
    ".exe", ".dmg", ".apk", ".deb", ".rpm", ".msi",
    ".map", ".min.js", ".min.css",
}

SECURITY_HEADERS = [
    "strict-transport-security", "content-security-policy", "x-frame-options",
    "x-content-type-options", "referrer-policy", "permissions-policy",
    "x-xss-protection", "cross-origin-opener-policy", "cross-origin-resource-policy",
    "cross-origin-embedder-policy", "expect-ct", "feature-policy",
]

CMS_SIGNATURES = {
    "WordPress": [r"wp-content", r"wp-includes", r"/wp-json/"],
    "Shopify": [r"cdn\.shopify\.com", r"Shopify\.theme"],
    "Wix": [r"static\.wixstatic\.com", r"wix\.com"],
    "Squarespace": [r"squarespace\.com", r"static1\.squarespace\.com"],
    "Drupal": [r"/sites/default/files", r"Drupal\.settings"],
    "Joomla": [r"/media/jui/", r"Joomla!"],
    "Magento": [r"/skin/frontend/", r"Mage\.Cookies"],
    "Webflow": [r"webflow\.com", r"data-wf-page"],
    "Ghost": [r"ghost\.org", r"content/themes/"],
    "Next.js": [r"__NEXT_DATA__", r"/_next/"],
    "Nuxt": [r"__NUXT__", r"/_nuxt/"],
    "React": [r"react(?:\.min)?\.js", r"data-reactroot"],
    "Vue": [r"vue(?:\.min)?\.js", r"data-v-"],
    "Angular": [r"ng-version", r"angular(?:\.min)?\.js"],
    "Svelte": [r"svelte-"],
    "Bootstrap": [r"bootstrap(?:\.min)?\.(?:js|css)"],
    "Tailwind": [r"tailwind"],
    "jQuery": [r"jquery(?:-\d|\.min)?\.js"],
    "Cloudflare": [r"cloudflare", r"__cfduid"],
    "Nginx": [r"nginx"],
    "Apache": [r"apache"],
    "IIS": [r"microsoft-iis"],
    "PHP": [r"\.php"],
    "ASP.NET": [r"__VIEWSTATE", r"asp\.net"],
    "Ruby on Rails": [r"rails", r"_rails"],
    "Django": [r"csrfmiddlewaretoken", r"django"],
    "Laravel": [r"laravel_session", r"XSRF-TOKEN"],
    "Astro": [r"astro-", r"astro-island"],
    "Remix": [r"__remixContext", r"/build/"],
    "SolidJS": [r"solid-js", r"data-solid"],
    "Qwik": [r"qwik", r"q:container"],
    "Alpine.js": [r"x-data", r"alpine"],
    "HTMX": [r"hx-get", r"hx-post", r"htmx"],
    "Stimulus": [r"data-controller", r"stimulus"],
    "Ember": [r"ember-view", r"ember\.js"],
    "Backbone": [r"backbone(?:\.min)?\.js"],
    "Preact": [r"preact(?:\.min)?\.js"],
    "Lit": [r"lit-element", r"lit-html"],
    "Gatsby": [r"gatsby-", r"___gatsby"],
    "Hugo": [r"hugo", r"generator.*Hugo"],
    "Jekyll": [r"jekyll", r"generator.*Jekyll"],
    "Docusaurus": [r"docusaurus"],
    "Vite": [r"/@vite/", r"vite/client"],
    "Webpack": [r"webpackJsonp", r"__webpack_require__"],
    "Rollup": [r"rollup"],
    "Parcel": [r"parcel"],
    "ESBuild": [r"esbuild"],
    "Babel": [r"babel"],
    "TypeScript": [r"typescript"],
    "FastAPI": [r"fastapi", r"swagger"],
    "Flask": [r"flask", r"werkzeug"],
    "Express": [r"express", r"x-powered-by.*Express"],
    "NestJS": [r"nestjs"],
    "Spring": [r"spring", r"whitelabel"],
    "Fastify": [r"fastify"],
    "Koa": [r"koa"],
    "Hapi": [r"hapi"],
    "Sails": [r"sails"],
    "Meteor": [r"meteor"],
    "Adonis": [r"adonis"],
    "Phoenix": [r"phoenix", r"csrf-token"],
    "Rocket": [r"rocket"],
    "Actix": [r"actix"],
    "Axum": [r"axum"],
    "Gin": [r"gin-gonic"],
    "Echo": [r"echo"],
    "Fiber": [r"gofiber"],
    "Chi": [r"chi"],
    "Buffalo": [r"buffalo"],
    "Revel": [r"revel"],
    "Beego": [r"beego"],
    "Traefik": [r"traefik"],
    "Envoy": [r"envoy"],
    "HAProxy": [r"haproxy"],
    "Caddy": [r"caddy"],
    "LiteSpeed": [r"litespeed"],
    "OpenResty": [r"openresty"],
    "Gunicorn": [r"gunicorn"],
    "uWSGI": [r"uwsgi"],
    "Puma": [r"puma"],
    "Unicorn": [r"unicorn"],
    "Passenger": [r"passenger"],
    "Tomcat": [r"tomcat", r"coyote"],
    "Jetty": [r"jetty"],
    "Undertow": [r"undertow"],
    "Netty": [r"netty"],
    "Kestrel": [r"kestrel"],
    "IIS Express": [r"iis express"],
    "lighttpd": [r"lighttpd"],
    "Cherokee": [r"cherokee"],
    "thttpd": [r"thttpd"],
    "Boa": [r"boa"],
    "Mathopd": [r"mathopd"],
    "Zeus": [r"zeus"],
    "Yaws": [r"yaws"],
    "Mongrel": [r"mongrel"],
    "WEBrick": [r"webrick"],
    "SimpleHTTP": [r"simplehttp"],
    "Twisted": [r"twisted"],
    "Tornado": [r"tornado"],
    "aiohttp": [r"aiohttp"],
    "Sanic": [r"sanic"],
    "Quart": [r"quart"],
    "Starlette": [r"starlette"],
    "Uvicorn": [r"uvicorn"],
    "Hypercorn": [r"hypercorn"],
    "Daphne": [r"daphne"],
    "Gunicorn": [r"gunicorn"],
    "Meinheld": [r"meinheld"],
    "Bjoern": [r"bjoern"],
    "Waitress": [r"waitress"],
    "CherryPy": [r"cherrypy"],
    "Bottle": [r"bottle"],
    "Falcon": [r"falcon"],
    "Pyramid": [r"pyramid"],
    "Turbogears": [r"turbogears"],
    "Zope": [r"zope"],
    "Plone": [r"plone"],
    "Werkzeug": [r"werkzeug"],
}

COMMON_PORTS = [
    (21, "ftp"), (22, "ssh"), (23, "telnet"), (25, "smtp"), (53, "dns"),
    (80, "http"), (81, "http-alt"), (110, "pop3"), (111, "rpcbind"),
    (135, "msrpc"), (139, "netbios-ssn"), (143, "imap"), (443, "https"),
    (445, "microsoft-ds"), (465, "smtps"), (514, "syslog"), (515, "printer"),
    (587, "submission"), (631, "ipp"), (636, "ldaps"), (873, "rsync"),
    (993, "imaps"), (995, "pop3s"), (1080, "socks"), (1433, "mssql"),
    (1521, "oracle"), (1723, "pptp"), (2049, "nfs"), (2181, "zookeeper"),
    (2375, "docker"), (2376, "docker-tls"), (3000, "grafana"), (3306, "mysql"),
    (3389, "rdp"), (4444, "metasploit"), (5000, "upnp"), (5432, "postgres"),
    (5601, "kibana"), (5672, "amqp"), (5900, "vnc"), (5984, "couchdb"),
    (6379, "redis"), (7001, "weblogic"), (7002, "weblogic-ssl"),
    (8000, "http-alt"), (8008, "http-alt"), (8080, "http-proxy"),
    (8081, "http-alt"), (8443, "https-alt"), (8888, "http-alt"),
    (9000, "php-fpm"), (9090, "prometheus"), (9200, "elasticsearch"),
    (9300, "elasticsearch"), (9418, "git"), (11211, "memcached"),
    (15672, "rabbitmq-mgmt"), (27017, "mongodb"), (27018, "mongodb"),
    (50000, "sap"), (50070, "hadoop"),
    (10000, "webmin"), (10001, "webmin-ssl"), (10010, "webmin"),
    (18080, "http-alt"), (18081, "http-alt"), (28017, "mongodb-web"),
    (50030, "hadoop-jobtracker"), (50060, "hadoop-tasktracker"),
    (50075, "hadoop-datanode"), (50090, "hadoop-secondary"),
    (60010, "hbase-master"), (60030, "hbase-regionserver"),
    (8088, "hadoop-yarn"), (8090, "http-alt"), (8091, "http-alt"),
    (8092, "http-alt"), (8093, "http-alt"), (8094, "http-alt"),
    (8095, "http-alt"), (8096, "http-alt"), (8097, "http-alt"),
    (8098, "http-alt"), (8099, "http-alt"), (8180, "http-alt"),
    (8280, "http-alt"), (8380, "http-alt"), (8480, "http-alt"),
    (8580, "http-alt"), (8680, "http-alt"), (8780, "http-alt"),
    (8880, "http-alt"), (8980, "http-alt"), (9080, "http-alt"),
    (9180, "http-alt"), (9280, "http-alt"), (9380, "http-alt"),
    (9480, "http-alt"), (9580, "http-alt"), (9680, "http-alt"),
    (9780, "http-alt"), (9880, "http-alt"), (9980, "http-alt"),
    (10443, "https-alt"), (12443, "https-alt"), (14443, "https-alt"),
    (16443, "https-alt"), (18443, "https-alt"), (20443, "https-alt"),
    (22443, "https-alt"), (24443, "https-alt"), (26443, "https-alt"),
    (28443, "https-alt"), (30443, "https-alt"), (32443, "https-alt"),
    (34443, "https-alt"), (36443, "https-alt"), (38443, "https-alt"),
    (40443, "https-alt"), (42443, "https-alt"), (44443, "https-alt"),
]

FRAMEWORK_ENDPOINTS = {
    "Spring Boot": ["actuator", "actuator/env", "actuator/health", "actuator/heapdump", "actuator/mappings", "actuator/beans", "actuator/configprops", "actuator/metrics", "actuator/loggers", "actuator/threaddump", "actuator/auditevents", "actuator/conditions", "actuator/flyway", "actuator/liquibase", "actuator/scheduledtasks", "actuator/sessions", "actuator/shutdown", "actuator/caches", "actuator/integrationgraph", "actuator/quartz", "actuator/httptrace", "actuator/httpexchanges"],
    "Django": ["admin/", "__debug__/", "_debug_/", "static/", "media/", "accounts/", "api/", "docs/", "redoc/", "swagger/", "schema/", "graphql/"],
    "Flask": ["console", "debug", "__debugger__/", "admin/", "api/", "docs/", "swagger/"],
    "Rails": ["rails/info", "rails/info/properties", "rails/info/routes", "sidekiq", "admin/", "api/", "assets/", "packs/", "cable/", "up", "health", "ready"],
    "Laravel": ["telescope", "telescope/requests", "horizon", "horizon/api/stats", "_ignition/health-check", "api/", "admin/", "docs/", "storage/", "build/"],
    "Next.js": ["_next/data", "api/", "_next/static", "_next/image", "_next/webpack-hmr", "sitemap.xml", "robots.txt", "manifest.json"],
    "Nuxt": ["_nuxt/", "api/", "_payload.json", "__nuxt/", "sitemap.xml", "robots.txt"],
    "WordPress": ["wp-json/", "wp-json/wp/v2/users", "wp-admin/", "xmlrpc.php", "wp-login.php", "wp-cron.php", "wp-content/", "wp-includes/", "readme.html", "license.txt", "wp-config.php"],
    "Drupal": ["user/login", "user/register", "admin/", "jsonapi/", "core/", "sites/default/", "CHANGELOG.txt", "README.txt"],
    "Joomla": ["administrator/", "api/", "index.php?option=com_users", "components/", "modules/", "plugins/", "templates/", "cache/", "logs/", "tmp/"],
    "Magento": ["admin", "rest/V1/", "rest/default/V1/", "rest/all/V1/", "graphql", "customer/", "checkout/", "catalog/", "sales/", "downloadable/"],
    "Shopify": ["admin", "cart.js", "products.json", "collections.json", "blogs.json", "pages.json", "sitemap.xml", "robots.txt", "meta.json"],
    "Grafana": ["api/health", "api/dashboards/home", "login", "api/datasources", "api/org", "api/user", "api/search", "api/annotations", "api/alert-notifications"],
    "Kibana": ["api/status", "app/", "api/saved_objects/_find", "api/spaces/space", "api/console", "api/kibana/settings", "api/security/role"],
    "Prometheus": ["metrics", "graph", "api/v1/status/config", "api/v1/targets", "api/v1/rules", "api/v1/alerts", "api/v1/query", "api/v1/labels", "api/v1/series", "api/v1/metadata"],
    "Jenkins": ["script", "manage", "api/json", "cli", "jnlpJars/jenkins-cli.jar", "computer/", "credentials/", "job/", "view/", "systemInfo", "log/", "whoAmI/api/json"],
    "GitLab": ["-/metrics", "-/health", "-/readiness", "-/liveness", "api/v4/projects", "api/v4/users", "api/v4/groups", "api/v4/version", "api/v4/jobs", "api/v4/pipelines", "api/v4/merge_requests", "api/v4/repositories"],
    "SonarQube": ["api/system/status", "api/system/health", "web_api/", "api/authentication/validate", "api/components/search", "api/issues/search", "api/measures/component", "api/projects/search", "api/qualitygates/list"],
    "Nexus": ["service/rest/v1/status", "service/rest/v1/repositories", "service/rest/v1/components", "service/rest/v1/assets", "service/rest/v1/security/users", "service/rest/v1/security/roles", "service/rest/v1/tasks"],
    "Artifactory": ["api/system/ping", "api/v1/ping", "api/repositories", "api/storage", "api/build", "api/security", "api/users", "api/groups", "api/permissions"],
    "RabbitMQ": ["api/overview", "api/nodes", "cli/", "api/queues", "api/exchanges", "api/connections", "api/channels", "api/users", "api/vhosts", "api/permissions", "api/parameters"],
    "Kubernetes": ["api/", "apis/", "healthz", "version", "api/v1/namespaces", "api/v1/pods", "api/v1/services", "api/v1/nodes", "api/v1/secrets", "api/v1/configmaps", "api/v1/endpoints", "api/v1/events", "apis/apps/v1/deployments", "apis/batch/v1/jobs", "apis/networking.k8s.io/v1/ingresses"],
    "Docker": ["version", "info", "containers/json", "images/json", "networks", "volumes", "events", "system/df", "swarm", "nodes", "services", "tasks", "secrets", "configs"],
    "etcd": ["v2/keys/", "v3/kv/range", "version", "health", "v2/machines", "v2/members", "v2/stats/self", "v3/maintenance/status", "v3/lease/leases"],
    "Consul": ["v1/agent/self", "v1/catalog/services", "ui/", "v1/status/leader", "v1/status/peers", "v1/catalog/nodes", "v1/catalog/datacenters", "v1/agent/members", "v1/agent/services", "v1/agent/checks", "v1/acl/tokens", "v1/kv/"],
    "Vault": ["v1/sys/health", "v1/sys/seal-status", "ui/", "v1/sys/mounts", "v1/sys/auth", "v1/sys/audit", "v1/sys/policies", "v1/sys/leases", "v1/sys/leader", "v1/sys/replication/status"],
    "Metabase": ["api/health", "api/session/properties", "api/database", "api/card", "api/dashboard", "api/user", "api/collection", "api/segment", "api/metric", "api/permissions", "api/setting"],
    "Superset": ["api/v1/health", "health", "api/v1/database", "api/v1/chart", "api/v1/dashboard", "api/v1/dataset", "api/v1/security", "api/v1/user", "api/v1/query"],
    "Redash": ["api/health", "api/queries", "api/dashboards", "api/data_sources", "api/users", "api/groups", "api/alerts", "api/destinations", "api/query_results"],
    "Airflow": ["admin/", "api/v1/health", "api/v1/dags", "api/v1/dagRuns", "api/v1/taskInstances", "api/v1/variables", "api/v1/connections", "api/v1/pools", "api/v1/users", "api/v1/roles", "api/v1/config"],
    "Jupyter": ["api/", "tree", "api/kernels", "api/sessions", "api/contents", "api/terminals", "api/nbconvert", "api/config", "api/status", "lab", "notebooks"],
    "Swagger": ["swagger-ui", "swagger-ui/", "swagger-ui.html", "v2/api-docs", "v3/api-docs", "swagger-resources", "swagger.json", "swagger.yaml", "openapi.json", "openapi.yaml", "api-docs", "docs", "redoc", "redoc.html"],
    "GraphQL": ["graphql", "graphiql", "graphql/console", "graphql-playground", "graphql/schema", "graphql/introspection", "api/graphql", "v1/graphql", "query", "gql"],
    "OpenAPI": ["openapi.json", "openapi.yaml", "swagger.json", "swagger.yaml", "api-docs", "api-docs.json", "api-docs.yaml", "openapi/v1", "openapi/v2", "openapi/v3", "docs/openapi.json", "docs/swagger.json"],
    "HashiCorp Nomad": ["v1/status/leader", "v1/status/peers", "v1/nodes", "v1/jobs", "v1/allocations", "v1/deployments", "v1/evaluations", "v1/agent/self", "v1/agent/members", "v1/regions", "v1/namespaces", "v1/acl/tokens", "v1/acl/policies"],
    "Apache Kafka": ["topics", "brokers", "consumers", "partitions", "config", "cluster", "acls", "connect", "connectors", "ksql", "streams", "schema-registry", "subjects", "schemas"],
    "Elasticsearch": ["_cluster/health", "_cat/indices", "_cat/nodes", "_cat/shards", "_cat/aliases", "_cat/allocation", "_nodes", "_stats", "_search", "_mapping", "_settings", "_alias", "_template", "_snapshot", "_recovery"],
    "Logstash": ["_node/stats", "_node/pipelines", "_node/os", "_node/jvm", "_node/hot_threads", "_health_report", "_node/plugins"],
    "Beats": ["/", "/stats", "/state", "/config", "/transactions", "/v2/transactions"],
    "CouchDB": ["_all_dbs", "_utils", "_active_tasks", "_membership", "_config", "_stats", "_system", "_replicator", "_users", "_session"],
    "MongoDB": ["/", "/serverStatus", "/dbstats", "/replSetGetStatus", "/isMaster", "/listDatabases", "/currentOp", "/profiler", "/shardCollection", "/balancerStart"],
    "Redis": ["/", "/info", "/config", "/cluster", "/keys", "/slaves", "/sentinel", "/slowlog", "/memory", "/client", "/debug"],
    "Memcached": ["/", "/stats", "/stats/items", "/stats/slabs", "/stats/sizes", "/stats/settings", "/stats/conns", "/version"],
    "Cassandra": ["/", "/jmx", "/metrics", "/keyspaces", "/columnfamilies", "/tables", "/snapshots", "/nodetool", "/status", "/gossipinfo"],
    "Neo4j": ["/", "/browser", "/db", "/db/data", "/db/manage", "/db/console", "/jmx", "/metrics", "/health", "/status"],
    "InfluxDB": ["/ping", "/health", "/metrics", "/query", "/write", "/debug/vars", "/debug/pprof", "/api/v2", "/api/v1", "/orgs", "/buckets", "/tasks"],
    "TimescaleDB": ["/", "/health", "/metrics", "/status", "/pg", "/timescale", "/hypertables", "/chunks", "/continuous_aggregates"],
    "ClickHouse": ["/", "/ping", "/replicas", "/metrics", "/status", "/query", "/play", "/dashboard", "/tables", "/databases"],
    "Druid": ["/status", "/health", "/metrics", "/datasources", "/tasks", "/workers", "/servers", "/coordinator", "/overlord", "/broker", "/historical", "/middleManager"],
    "Presto": ["/", "/v1/info", "/v1/status", "/v1/node", "/v1/query", "/v1/task", "/v1/stage", "/v1/cluster", "/ui", "/metrics"],
    "Trino": ["/", "/v1/info", "/v1/status", "/v1/node", "/v1/query", "/v1/task", "/v1/stage", "/v1/cluster", "/ui", "/metrics"],
    "Hive": ["/", "/conf", "/jmx", "/metrics", "/status", "/version", "/sessions", "/operations", "/databases", "/tables"],
    "HBase": ["/", "/master-status", "/regionserver-status", "/jmx", "/metrics", "/conf", "/status", "/version", "/tables", "/regions"],
    "Spark": ["/", "/metrics", "/json", "/api/v1", "/applications", "/history", "/stages", "/tasks", "/storage", "/environment", "/executors", "/jobs"],
    "Flink": ["/", "/config", "/jobs", "/jobs/overview", "/taskmanagers", "/jobmanager", "/metrics", "/overview", "/savepoints"],
    "Storm": ["/", "/api/v1", "/api/v1/cluster", "/api/v1/topology", "/api/v1/worker", "/api/v1/supervisor", "/api/v1/nimbus", "/api/v1/history", "/api/v1/metrics"],
    "Zookeeper": ["/", "/commands", "/conf", "/cons", "/crst", "/dump", "/envi", "/ruok", "/srvr", "/stat", "/wchs", "/wchc", "/wchp", "/mntr", "/gtmk", "/stmk"],
    "Kong": ["/", "/status", "/metrics", "/config", "/routes", "/services", "/consumers", "/plugins", "/certificates", "/snis", "/upstreams", "/targets", "/vitals"],
    "Traefik": ["/", "/api", "/api/rawdata", "/api/overview", "/api/entrypoints", "/api/http/routers", "/api/http/services", "/api/http/middlewares", "/api/tcp/routers", "/api/tcp/services", "/api/udp/routers", "/api/udp/services", "/api/tls/certificates", "/dashboard", "/health", "/ping", "/metrics"],
    "HAProxy": ["/", "/stats", "/stats;csv", "/metrics", "/health", "/status", "/haproxy", "/admin", "/config", "/info"],
    "Envoy": ["/", "/stats", "/stats/prometheus", "/config_dump", "/clusters", "/listeners", "/server_info", "/ready", "/healthz", "/certs", "/runtime", "/memory", "/hot_restart_version"],
    "Nginx": ["/", "/nginx_status", "/status", "/stub_status", "/metrics", "/health", "/server-status", "/server-info", "/basic_status"],
    "Apache": ["/", "/server-status", "/server-info", "/status", "/metrics", "/health", "/balancer-manager", "/mod_status", "/cgi-bin/status", "/cgi-bin/info"],
    "IIS": ["/", "/iisstart.htm", "/welcome.png", "/trace.axd", "/elmah.axd", "/Glimpse.axd", "/status", "/health", "/metrics"],
    "Tomcat": ["/", "/manager", "/manager/html", "/host-manager", "/host-manager/html", "/docs", "/examples", "/status", "/health", "/metrics"],
    "Jetty": ["/", "/stats", "/metrics", "/status", "/health", "/jmx", "/contexts", "/servlets", "/sessions", "/threads"],
    "Glassfish": ["/", "/management", "/management/domain", "/common", "/status", "/health", "/metrics", "/jmx", "/applications", "/resources"],
    "WildFly": ["/", "/management", "/management/domain", "/console", "/status", "/health", "/metrics", "/jmx", "/deployments", "/datasources"],
    "WebLogic": ["/", "/console", "/console/login/LoginForm.jsp", "/management", "/wls-management-services", "/bea_wls_internal", "/status", "/health", "/metrics", "/jmx"],
    "WebSphere": ["/", "/ibm/console", "/admin", "/status", "/health", "/metrics", "/jmx", "/wsadmin", "/applications", "/resources"],
    "JBoss": ["/", "/jmx-console", "/web-console", "/admin-console", "/status", "/health", "/metrics", "/jmx", "/deployments", "/datasources"],
    "OpenShift": ["/", "/console", "/oauth", "/api", "/apis", "/healthz", "/readyz", "/livez", "/metrics", "/version", "/status"],
    "Rancher": ["/", "/v3", "/v1", "/dashboard", "/api", "/health", "/metrics", "/status", "/version", "/clusters", "/projects", "/nodes"],
    "Portainer": ["/", "/api", "/api/endpoints", "/api/stacks", "/api/containers", "/api/images", "/api/volumes", "/api/networks", "/api/users", "/api/status"],
    "Rundeck": ["/", "/api", "/api/1", "/api/2", "/api/3", "/api/4", "/api/5", "/api/6", "/api/7", "/api/8", "/api/9", "/api/10", "/api/11", "/api/12", "/api/13", "/api/14", "/api/15", "/api/16", "/api/17", "/api/18", "/api/19", "/api/20", "/api/21", "/api/22", "/api/23", "/api/24", "/api/25", "/api/26", "/api/27", "/api/28", "/api/29", "/api/30", "/api/31", "/api/32", "/api/33", "/api/34", "/api/35", "/api/36", "/api/37", "/api/38", "/api/39", "/api/40", "/api/41", "/api/42", "/api/43", "/api/44", "/api/45", "/api/46", "/api/47", "/api/48", "/api/49", "/api/50"],
    "Ansible AWX": ["/", "/api", "/api/v2", "/api/v2/me", "/api/v2/users", "/api/v2/organizations", "/api/v2/projects", "/api/v2/inventories", "/api/v2/job_templates", "/api/v2/jobs", "/api/v2/credentials", "/api/v2/execution_environments", "/api/v2/settings", "/api/v2/config"],
    "Terraform Enterprise": ["/", "/api", "/api/v2", "/api/v2/account", "/api/v2/organizations", "/api/v2/workspaces", "/api/v2/runs", "/api/v2/plans", "/api/v2/applies", "/api/v2/state-versions", "/api/v2/variables", "/api/v2/policies", "/api/v2/agents"],
    "Vaultwarden": ["/", "/api", "/api/accounts", "/api/ciphers", "/api/organizations", "/api/sync", "/api/config", "/api/hibp", "/api/now", "/api/version", "/identity", "/admin", "/notifications"],
    "Keycloak": ["/", "/auth", "/auth/admin", "/auth/realms", "/auth/realms/master", "/auth/realms/master/.well-known/openid-configuration", "/auth/realms/master/protocol/openid-connect/certs", "/auth/realms/master/protocol/openid-connect/token", "/auth/realms/master/protocol/openid-connect/userinfo", "/auth/realms/master/protocol/openid-connect/logout", "/auth/realms/master/protocol/openid-connect/auth", "/auth/resources", "/auth/js", "/auth/welcome-content"],
    "Authentik": ["/", "/if", "/if/admin", "/if/user", "/api", "/api/v3", "/api/v3/core", "/api/v3/flows", "/api/v3/stages", "/api/v3/policies", "/api/v3/providers", "/api/v3/applications", "/api/v3/sources", "/api/v3/outposts", "/api/v3/crypto", "/api/v3/events", "/api/v3/rbac", "/api/v3/admin", "/api/v3/root", "/api/v3/managed", "/api/v3/tasks", "/api/v3/tenants", "/api/v3/blueprints", "/api/v3/brands"],
    "Authelia": ["/", "/api", "/api/health", "/api/verify", "/api/consent", "/api/firstfactor", "/api/secondfactor", "/api/logout", "/api/reset-password", "/api/user/info", "/api/state", "/api/configuration"],
    "OAuth2 Proxy": ["/", "/oauth2", "/oauth2/sign_in", "/oauth2/sign_out", "/oauth2/callback", "/oauth2/userinfo", "/oauth2/auth", "/oauth2/start", "/oauth2/healthz", "/ping", "/metrics"],
    "Dex": ["/", "/auth", "/auth/callback", "/auth/healthz", "/auth/token", "/auth/keys", "/auth/userinfo", "/auth/approval", "/auth/device", "/auth/.well-known/openid-configuration", "/auth/.well-known/jwks.json", "/auth/discovery", "/auth/static", "/auth/theme", "/auth/local"],
    "Hydra": ["/", "/health", "/health/alive", "/health/ready", "/version", "/metrics", "/oauth2", "/oauth2/auth", "/oauth2/token", "/oauth2/revoke", "/oauth2/introspect", "/oauth2/flush", "/oauth2/sessions", "/oauth2/sessions/logout", "/userinfo", "/.well-known/openid-configuration", "/.well-known/jwks.json", "/clients", "/keys", "/consent", "/login", "/logout", "/sessions", "/jwks"],
    "Keto": ["/", "/health", "/health/alive", "/health/ready", "/version", "/metrics", "/relation-tuples", "/expand", "/check", "/engines/acp", "/engines/acp/ory", "/engines/acp/ory/exact", "/engines/acp/ory/exact/relation-tuples", "/engines/acp/ory/exact/check", "/engines/acp/ory/exact/expand"],
    "Kratos": ["/", "/health", "/health/alive", "/health/ready", "/version", "/metrics", "/self-service", "/self-service/login", "/self-service/login/browser", "/self-service/login/api", "/self-service/login/flows", "/self-service/registration", "/self-service/registration/browser", "/self-service/registration/api", "/self-service/registration/flows", "/self-service/settings", "/self-service/settings/browser", "/self-service/settings/api", "/self-service/settings/flows", "/self-service/recovery", "/self-service/recovery/browser", "/self-service/recovery/api", "/self-service/recovery/flows", "/self-service/verification", "/self-service/verification/browser", "/self-service/verification/api", "/self-service/verification/flows", "/sessions", "/sessions/whoami", "/identities", "/identities/credentials", "/identities/credentials/password", "/identities/credentials/oidc", "/identities/credentials/webauthn", "/identities/credentials/totp", "/identities/credentials/lookup_secret", "/schemas", "/.well-known/openid-configuration", "/.well-known/jwks.json"],
    "Keto": ["/", "/health", "/health/alive", "/health/ready", "/version", "/metrics", "/relation-tuples", "/expand", "/check", "/engines/acp", "/engines/acp/ory", "/engines/acp/ory/exact", "/engines/acp/ory/exact/relation-tuples", "/engines/acp/ory/exact/check", "/engines/acp/ory/exact/expand"],
    "Terraform Cloud": ["/", "/api", "/api/v2", "/api/v2/account", "/api/v2/organizations", "/api/v2/workspaces", "/api/v2/runs", "/api/v2/plans", "/api/v2/applies", "/api/v2/state-versions", "/api/v2/variables", "/api/v2/policies", "/api/v2/agents", "/api/v2/cost-estimates", "/api/v2/notification-configurations", "/api/v2/oauth-clients", "/api/v2/oauth-tokens", "/api/v2/ssh-keys", "/api/v2/team-tokens", "/api/v2/user-tokens", "/api/v2/users", "/api/v2/teams", "/api/v2/organization-memberships", "/api/v2/workspace-memberships"],
    "Bitbucket": ["/", "/api", "/api/2.0", "/api/2.0/repositories", "/api/2.0/workspaces", "/api/2.0/users", "/api/2.0/teams", "/api/2.0/projects", "/api/2.0/pullrequests", "/api/2.0/issues", "/api/2.0/downloads", "/api/2.0/hooks", "/api/2.0/addon", "/api/2.0/branch-restrictions", "/api/2.0/commit", "/api/2.0/diff", "/api/2.0/pipelines", "/api/2.0/snippets", "/api/2.0/ssh", "/api/2.0/webhooks"],
    "GitHub Enterprise": ["/", "/api", "/api/v3", "/api/v3/repos", "/api/v3/users", "/api/v3/orgs", "/api/v3/teams", "/api/v3/issues", "/api/v3/pulls", "/api/v3/actions", "/api/v3/apps", "/api/v3/installations", "/api/v3/marketplace", "/api/v3/projects", "/api/v3/reactions", "/api/v3/repos", "/api/v3/search", "/api/v3/teams", "/api/v3/users", "/api/v3/rate_limit", "/api/v3/enterprise", "/api/v3/admin", "/api/v3/settings"],
    "GitLab EE": ["/", "/api", "/api/v4", "/api/v4/projects", "/api/v4/users", "/api/v4/groups", "/api/v4/version", "/api/v4/jobs", "/api/v4/pipelines", "/api/v4/merge_requests", "/api/v4/repositories", "/api/v4/namespaces", "/api/v4/snippets", "/api/v4/events", "/api/v4/issues", "/api/v4/labels", "/api/v4/milestones", "/api/v4/boards", "/api/v4/epics", "/api/v4/features", "/api/v4/applications", "/api/v4/audit_events", "/api/v4/avatar", "/api/v4/broadcast_messages", "/api/v4/deployments", "/api/v4/environments", "/api/v4/keys", "/api/v4/packages", "/api/v4/pages", "/api/v4/personal_access_tokens", "/api/v4/projects", "/api/v4/runners", "/api/v4/search", "/api/v4/settings", "/api/v4/sidekiq", "/api/v4/system_hooks", "/api/v4/todos", "/api/v4/unleashes", "/api/v4/users", "/api/v4/webhooks", "/api/v4/wikis"],
    "Gitea": ["/", "/api", "/api/v1", "/api/v1/version", "/api/v1/users", "/api/v1/repos", "/api/v1/orgs", "/api/v1/teams", "/api/v1/issues", "/api/v1/pulls", "/api/v1/actions", "/api/v1/packages", "/api/v1/settings", "/api/v1/admin", "/api/v1/markdown", "/api/v1/signin", "/api/v1/user", "/api/v1/repos/search", "/api/v1/users/search", "/api/v1/orgs", "/api/v1/teams", "/api/v1/notifications", "/api/v1/repos/issues/search", "/api/v1/repos/{owner}/{repo}/issues", "/api/v1/repos/{owner}/{repo}/pulls", "/api/v1/repos/{owner}/{repo}/branches", "/api/v1/repos/{owner}/{repo}/commits", "/api/v1/repos/{owner}/{repo}/contents", "/api/v1/repos/{owner}/{repo}/releases", "/api/v1/repos/{owner}/{repo}/tags", "/api/v1/repos/{owner}/{repo}/hooks", "/api/v1/repos/{owner}/{repo}/keys", "/api/v1/repos/{owner}/{repo}/collaborators", "/api/v1/repos/{owner}/{repo}/forks", "/api/v1/repos/{owner}/{repo}/stargazers", "/api/v1/repos/{owner}/{repo}/subscribers", "/api/v1/repos/{owner}/{repo}/watchers", "/api/v1/repos/{owner}/{repo}/topics", "/api/v1/repos/{owner}/{repo}/languages", "/api/v1/repos/{owner}/{repo}/git", "/api/v1/repos/{owner}/{repo}/archive", "/api/v1/repos/{owner}/{repo}/mirrors", "/api/v1/repos/{owner}/{repo}/releases", "/api/v1/repos/{owner}/{repo}/stats", "/api/v1/repos/{owner}/{repo}/times"],
    "Gogs": ["/", "/api", "/api/v1", "/api/v1/version", "/api/v1/users", "/api/v1/repos", "/api/v1/orgs", "/api/v1/teams", "/api/v1/issues", "/api/v1/pulls", "/api/v1/user", "/api/v1/repos/search", "/api/v1/users/search", "/api/v1/admin", "/api/v1/markdown", "/api/v1/signin", "/api/v1/notifications", "/api/v1/repos/{owner}/{repo}/issues", "/api/v1/repos/{owner}/{repo}/pulls", "/api/v1/repos/{owner}/{repo}/branches", "/api/v1/repos/{owner}/{repo}/commits", "/api/v1/repos/{owner}/{repo}/contents", "/api/v1/repos/{owner}/{repo}/releases", "/api/v1/repos/{owner}/{repo}/tags", "/api/v1/repos/{owner}/{repo}/hooks", "/api/v1/repos/{owner}/{repo}/keys", "/api/v1/repos/{owner}/{repo}/collaborators", "/api/v1/repos/{owner}/{repo}/forks", "/api/v1/repos/{owner}/{repo}/stargazers", "/api/v1/repos/{owner}/{repo}/subscribers", "/api/v1/repos/{owner}/{repo}/watchers", "/api/v1/repos/{owner}/{repo}/topics", "/api/v1/repos/{owner}/{repo}/languages", "/api/v1/repos/{owner}/{repo}/git", "/api/v1/repos/{owner}/{repo}/archive", "/api/v1/repos/{owner}/{repo}/mirrors", "/api/v1/repos/{owner}/{repo}/releases", "/api/v1/repos/{owner}/{repo}/stats", "/api/v1/repos/{owner}/{repo}/times"],
    "Phabricator": ["/", "/api", "/api/user.whoami", "/api/user.search", "/api/project.search", "/api/maniphest.search", "/api/differential.revision.search", "/api/repository.search", "/api/commit.search", "/api/phriction.search", "/api/file.search", "/api/token.give", "/api/user.query", "/api/project.query", "/api/maniphest.query", "/api/differential.query", "/api/repository.query", "/api/commit.query", "/api/file.query", "/api/phriction.query", "/api/feed.query", "/api/flag.query", "/api/paste.query", "/api/slowvote.query", "/api/harbormaster.query", "/api/diviner.query", "/api/badge.query", "/api/xhpast.query", "/api/typeahead.query"],
    "Redmine": ["/", "/projects", "/issues", "/users", "/time_entries", "/news", "/documents", "/files", "/wiki", "/settings", "/admin", "/account", "/login", "/logout", "/my", "/api", "/api/v1", "/api/v1/projects", "/api/v1/issues", "/api/v1/users", "/api/v1/time_entries", "/api/v1/news", "/api/v1/documents", "/api/v1/files", "/api/v1/wikis", "/api/v1/settings", "/api/v1/account", "/api/v1/search", "/api/v1/enumerations", "/api/v1/issue_statuses", "/api/v1/trackers", "/api/v1/roles", "/api/v1/groups", "/api/v1/custom_fields", "/api/v1/queries", "/api/v1/attachments", "/api/v1/versions", "/api/v1/wiki_pages", "/api/v1/projects/{id}/memberships", "/api/v1/projects/{id}/versions", "/api/v1/projects/{id}/issue_categories", "/api/v1/projects/{id}/time_entry_activities", "/api/v1/projects/{id}/news", "/api/v1/projects/{id}/documents", "/api/v1/projects/{id}/files", "/api/v1/projects/{id}/wikis", "/api/v1/projects/{id}/boards", "/api/v1/projects/{id}/repository", "/api/v1/projects/{id}/issues", "/api/v1/projects/{id}/memberships"],
    "Trac": ["/", "/wiki", "/ticket", "/report", "/query", "/timeline", "/roadmap", "/browser", "/log", "/newticket", "/admin", "/login", "/logout", "/prefs", "/search", "/about", "/attachment", "/changeset", "/diff", "/export", "/file", "/graph", "/home", "/interface", "/milestone", "/notification", "/prefs", "/query", "/report", "/roadmap", "/search", "/settings", "/timeline", "/ticket", "/timeline", "/version", "/wiki", "/admin", "/api", "/jsonrpc", "/xmlrpc"],
    "MantisBT": ["/", "/login_page.php", "/view_all_bug_page.php", "/bug_report_page.php", "/my_view_page.php", "/summary_page.php", "/changelog_page.php", "/roadmap_page.php", "/view.php", "/api/rest", "/api/rest/issues", "/api/rest/projects", "/api/rest/users", "/api/rest/config", "/api/rest/lang", "/api/rest/pages", "/api/rest/version", "/api/rest/swagger", "/api/rest/openapi"],
    "Bugzilla": ["/", "/index.cgi", "/enter_bug.cgi", "/query.cgi", "/buglist.cgi", "/show_bug.cgi", "/report.cgi", "/userprefs.cgi", "/editparams.cgi", "/editusers.cgi", "/editproducts.cgi", "/editcomponents.cgi", "/editversions.cgi", "/editmilestones.cgi", "/editkeywords.cgi", "/editflagtypes.cgi", "/editgroups.cgi", "/editclassifications.cgi", "/admin.cgi", "/config.cgi", "/api", "/rest", "/rest/bug", "/rest/bug/{id}", "/rest/user", "/rest/user/{id}", "/rest/product", "/rest/component", "/rest/version", "/rest/classification", "/rest/group", "/rest/flag", "/rest/field", "/rest/attachment", "/rest/comment", "/rest/bug/{id}/attachment", "/rest/bug/{id}/comment", "/rest/bug/{id}/history", "/rest/bug/{id}/field", "/rest/bug/{id}/flag", "/rest/bug/{id}/group", "/rest/bug/{id}/see_also", "/rest/bug/{id}/duplicates", "/rest/bug/{id}/tags", "/rest/bug/{id}/whiteboard", "/rest/bug/{id}/work_time", "/rest/bug/{id}/keywords", "/rest/bug/{id}/cc", "/rest/bug/{id}/alias", "/rest/bug/{id}/depends_on", "/rest/bug/{id}/blocks", "/rest/bug/{id}/regressed_by", "/rest/bug/{id}/regresses", "/rest/bug/{id}/duplicates", "/rest/bug/{id}/votes", "/rest/bug/{id}/comments", "/rest/bug/{id}/attachments", "/rest/bug/{id}/history", "/rest/bug/{id}/field", "/rest/bug/{id}/flag", "/rest/bug/{id}/group", "/rest/bug/{id}/see_also", "/rest/bug/{id}/duplicates", "/rest/bug/{id}/tags", "/rest/bug/{id}/whiteboard", "/rest/bug/{id}/work_time", "/rest/bug/{id}/keywords", "/rest/bug/{id}/cc", "/rest/bug/{id}/alias", "/rest/bug/{id}/depends_on", "/rest/bug/{id}/blocks", "/rest/bug/{id}/regressed_by", "/rest/bug/{id}/regresses", "/rest/bug/{id}/duplicates", "/rest/bug/{id}/votes", "/rest/bug/{id}/comments", "/rest/bug/{id}/attachments", "/rest/bug/{id}/history"],
    "OTRS": ["/", "/otrs", "/otrs/index.pl", "/otrs/customer.pl", "/otrs/public.pl", "/otrs/api", "/otrs/api/v1", "/otrs/api/v1/tickets", "/otrs/api/v1/users", "/otrs/api/v1/queues", "/otrs/api/v1/priorities", "/otrs/api/v1/states", "/otrs/api/v1/dynamic_fields", "/otrs/api/v1/roles", "/otrs/api/v1/groups", "/otrs/api/v1/customers", "/otrs/api/v1/config", "/otrs/api/v1/version", "/otrs/api/v1/swagger", "/otrs/api/v1/openapi"],
    "Zammad": ["/", "/api", "/api/v1", "/api/v1/tickets", "/api/v1/users", "/api/v1/organizations", "/api/v1/groups", "/api/v1/roles", "/api/v1/ticket_articles", "/api/v1/ticket_states", "/api/v1/ticket_priorities", "/api/v1/ticket_categories", "/api/v1/tags", "/api/v1/links", "/api/v1/online_notifications", "/api/v1/activity_stream", "/api/v1/sessions", "/api/v1/settings", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/status", "/api/v1/health", "/api/v1/metrics", "/api/v1/monitoring", "/api/v1/taskbar", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/recent_view", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/slas", "/api/v1/calendars", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/doorkeeper", "/api/v1/ldap", "/api/v1/cache", "/api/v1/logs", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring", "/api/v1/health", "/api/v1/metrics"],
    "osTicket": ["/", "/scp", "/scp/login.php", "/scp/index.php", "/scp/admin.php", "/scp/api", "/scp/api/tickets", "/scp/api/users", "/scp/api/agents", "/scp/api/teams", "/scp/api/departments", "/scp/api/help_topics", "/scp/api/ticket_status", "/scp/api/ticket_priorities", "/scp/api/slas", "/scp/api/faqs", "/scp/api/filters", "/scp/api/forms", "/scp/api/lists", "/scp/api/logs", "/scp/api/version", "/scp/api/swagger", "/scp/api/openapi", "/scp/api/config", "/scp/api/health", "/scp/api/metrics", "/scp/api/monitoring", "/scp/api/tasks", "/scp/api/attachments", "/scp/api/mentions", "/scp/api/history", "/scp/api/stats", "/scp/api/reports", "/scp/api/jobs", "/scp/api/schedulers", "/scp/api/triggers", "/scp/api/overviews", "/scp/api/templates", "/scp/api/text_modules", "/scp/api/macros", "/scp/api/webhooks", "/scp/api/integrations", "/scp/api/channels", "/scp/api/imports", "/scp/api/exports", "/scp/api/search", "/scp/api/objects", "/scp/api/translations", "/scp/api/oauth", "/scp/api/applications", "/scp/api/authorizations", "/scp/api/ldap", "/scp/api/cache", "/scp/api/sessions", "/scp/api/password", "/scp/api/two_factor", "/scp/api/webauthn", "/scp/api/security", "/scp/api/compliance", "/scp/api/audit", "/scp/api/reports", "/scp/api/monitoring"],
    "LibreNMS": ["/", "/api", "/api/v0", "/api/v0/devices", "/api/v0/ports", "/api/v0/users", "/api/v0/alerts", "/api/v0/logs", "/api/v0/inventory", "/api/v0/bills", "/api/v0/routing", "/api/v0/switching", "/api/v0/services", "/api/v0/health", "/api/v0/metrics", "/api/v0/version", "/api/v0/swagger", "/api/v0/openapi", "/api/v0/config", "/api/v0/status", "/api/v0/monitoring", "/api/v0/tasks", "/api/v0/attachments", "/api/v0/mentions", "/api/v0/history", "/api/v0/stats", "/api/v0/reports", "/api/v0/jobs", "/api/v0/schedulers", "/api/v0/triggers", "/api/v0/overviews", "/api/v0/templates", "/api/v0/text_modules", "/api/v0/macros", "/api/v0/webhooks", "/api/v0/integrations", "/api/v0/channels", "/api/v0/imports", "/api/v0/exports", "/api/v0/search", "/api/v0/objects", "/api/v0/translations", "/api/v0/oauth", "/api/v0/applications", "/api/v0/authorizations", "/api/v0/ldap", "/api/v0/cache", "/api/v0/sessions", "/api/v0/password", "/api/v0/two_factor", "/api/v0/webauthn", "/api/v0/security", "/api/v0/compliance", "/api/v0/audit", "/api/v0/reports", "/api/v0/monitoring"],
    "Observium": ["/", "/api", "/api/v0", "/api/v0/devices", "/api/v0/ports", "/api/v0/users", "/api/v0/alerts", "/api/v0/logs", "/api/v0/inventory", "/api/v0/bills", "/api/v0/routing", "/api/v0/switching", "/api/v0/services", "/api/v0/health", "/api/v0/metrics", "/api/v0/version", "/api/v0/swagger", "/api/v0/openapi", "/api/v0/config", "/api/v0/status", "/api/v0/monitoring", "/api/v0/tasks", "/api/v0/attachments", "/api/v0/mentions", "/api/v0/history", "/api/v0/stats", "/api/v0/reports", "/api/v0/jobs", "/api/v0/schedulers", "/api/v0/triggers", "/api/v0/overviews", "/api/v0/templates", "/api/v0/text_modules", "/api/v0/macros", "/api/v0/webhooks", "/api/v0/integrations", "/api/v0/channels", "/api/v0/imports", "/api/v0/exports", "/api/v0/search", "/api/v0/objects", "/api/v0/translations", "/api/v0/oauth", "/api/v0/applications", "/api/v0/authorizations", "/api/v0/ldap", "/api/v0/cache", "/api/v0/sessions", "/api/v0/password", "/api/v0/two_factor", "/api/v0/webauthn", "/api/v0/security", "/api/v0/compliance", "/api/v0/audit", "/api/v0/reports", "/api/v0/monitoring"],
    "Nagios": ["/", "/nagios", "/nagios/cgi-bin", "/nagios/cgi-bin/status.cgi", "/nagios/cgi-bin/statusjson.cgi", "/nagios/cgi-bin/objectjson.cgi", "/nagios/cgi-bin/availability.cgi", "/nagios/cgi-bin/histogram.cgi", "/nagios/cgi-bin/history.cgi", "/nagios/cgi-bin/notifications.cgi", "/nagios/cgi-bin/trends.cgi", "/nagios/cgi-bin/summary.cgi", "/nagios/cgi-bin/config.cgi", "/nagios/cgi-bin/extinfo.cgi", "/nagios/cgi-bin/cmd.cgi", "/nagios/cgi-bin/outages.cgi", "/nagios/cgi-bin/showlog.cgi", "/nagios/cgi-bin/tac.cgi", "/nagios/cgi-bin/statusmap.cgi", "/nagios/cgi-bin/trends.cgi", "/nagios/cgi-bin/avail.cgi", "/nagios/cgi-bin/notifications.cgi", "/nagios/cgi-bin/histogram.cgi", "/nagios/cgi-bin/history.cgi", "/nagios/cgi-bin/summary.cgi", "/nagios/cgi-bin/config.cgi", "/nagios/cgi-bin/extinfo.cgi", "/nagios/cgi-bin/cmd.cgi", "/nagios/cgi-bin/outages.cgi", "/nagios/cgi-bin/showlog.cgi", "/nagios/cgi-bin/tac.cgi", "/nagios/cgi-bin/statusmap.cgi", "/nagios/cgi-bin/trends.cgi", "/nagios/cgi-bin/avail.cgi"],
    "Icinga": ["/", "/icinga", "/icinga/cgi-bin", "/icinga/cgi-bin/status.cgi", "/icinga/cgi-bin/statusjson.cgi", "/icinga/cgi-bin/objectjson.cgi", "/icinga/cgi-bin/availability.cgi", "/icinga/cgi-bin/histogram.cgi", "/icinga/cgi-bin/history.cgi", "/icinga/cgi-bin/notifications.cgi", "/icinga/cgi-bin/trends.cgi", "/icinga/cgi-bin/summary.cgi", "/icinga/cgi-bin/config.cgi", "/icinga/cgi-bin/extinfo.cgi", "/icinga/cgi-bin/cmd.cgi", "/icinga/cgi-bin/outages.cgi", "/icinga/cgi-bin/showlog.cgi", "/icinga/cgi-bin/tac.cgi", "/icinga/cgi-bin/statusmap.cgi", "/icinga/cgi-bin/trends.cgi", "/icinga/cgi-bin/avail.cgi", "/icinga/cgi-bin/notifications.cgi", "/icinga/cgi-bin/histogram.cgi", "/icinga/cgi-bin/history.cgi", "/icinga/cgi-bin/summary.cgi", "/icinga/cgi-bin/config.cgi", "/icinga/cgi-bin/extinfo.cgi", "/icinga/cgi-bin/cmd.cgi", "/icinga/cgi-bin/outages.cgi", "/icinga/cgi-bin/showlog.cgi", "/icinga/cgi-bin/tac.cgi", "/icinga/cgi-bin/statusmap.cgi", "/icinga/cgi-bin/trends.cgi", "/icinga/cgi-bin/avail.cgi"],
    "Zabbix": ["/", "/zabbix", "/zabbix/index.php", "/zabbix/api_jsonrpc.php", "/zabbix/api", "/zabbix/api/v1", "/zabbix/api/v1/host", "/zabbix/api/v1/item", "/zabbix/api/v1/trigger", "/zabbix/api/v1/event", "/zabbix/api/v1/action", "/zabbix/api/v1/graph", "/zabbix/api/v1/map", "/zabbix/api/v1/screen", "/zabbix/api/v1/template", "/zabbix/api/v1/user", "/zabbix/api/v1/usergroup", "/zabbix/api/v1/mediatype", "/zabbix/api/v1/script", "/zabbix/api/v1/proxy", "/zabbix/api/v1/maintenance", "/zabbix/api/v1/hostgroup", "/zabbix/api/v1/application", "/zabbix/api/v1/httptest", "/zabbix/api/v1/webcheck", "/zabbix/api/v1/dashboard", "/zabbix/api/v1/configuration", "/zabbix/api/v1/history", "/zabbix/api/v1/trend", "/zabbix/api/v1/version", "/zabbix/api/v1/swagger", "/zabbix/api/v1/openapi", "/zabbix/api/v1/config", "/zabbix/api/v1/status", "/zabbix/api/v1/monitoring", "/zabbix/api/v1/tasks", "/zabbix/api/v1/attachments", "/zabbix/api/v1/mentions", "/zabbix/api/v1/stats", "/zabbix/api/v1/reports", "/zabbix/api/v1/jobs", "/zabbix/api/v1/schedulers", "/zabbix/api/v1/triggers", "/zabbix/api/v1/overviews", "/zabbix/api/v1/templates", "/zabbix/api/v1/text_modules", "/zabbix/api/v1/macros", "/zabbix/api/v1/webhooks", "/zabbix/api/v1/integrations", "/zabbix/api/v1/channels", "/zabbix/api/v1/imports", "/zabbix/api/v1/exports", "/zabbix/api/v1/search", "/zabbix/api/v1/objects", "/zabbix/api/v1/translations", "/zabbix/api/v1/oauth", "/zabbix/api/v1/applications", "/zabbix/api/v1/authorizations", "/zabbix/api/v1/ldap", "/zabbix/api/v1/cache", "/zabbix/api/v1/sessions", "/zabbix/api/v1/password", "/zabbix/api/v1/two_factor", "/zabbix/api/v1/webauthn", "/zabbix/api/v1/security", "/zabbix/api/v1/compliance", "/zabbix/api/v1/audit", "/zabbix/api/v1/reports", "/zabbix/api/v1/monitoring"],
    "Centreon": ["/", "/centreon", "/centreon/index.php", "/centreon/api", "/centreon/api/v1", "/centreon/api/v1/hosts", "/centreon/api/v1/services", "/centreon/api/v1/metrics", "/centreon/api/v1/status", "/centreon/api/v1/version", "/centreon/api/v1/swagger", "/centreon/api/v1/openapi", "/centreon/api/v1/config", "/centreon/api/v1/health", "/centreon/api/v1/monitoring", "/centreon/api/v1/tasks", "/centreon/api/v1/attachments", "/centreon/api/v1/mentions", "/centreon/api/v1/history", "/centreon/api/v1/stats", "/centreon/api/v1/reports", "/centreon/api/v1/jobs", "/centreon/api/v1/schedulers", "/centreon/api/v1/triggers", "/centreon/api/v1/overviews", "/centreon/api/v1/templates", "/centreon/api/v1/text_modules", "/centreon/api/v1/macros", "/centreon/api/v1/webhooks", "/centreon/api/v1/integrations", "/centreon/api/v1/channels", "/centreon/api/v1/imports", "/centreon/api/v1/exports", "/centreon/api/v1/search", "/centreon/api/v1/objects", "/centreon/api/v1/translations", "/centreon/api/v1/oauth", "/centreon/api/v1/applications", "/centreon/api/v1/authorizations", "/centreon/api/v1/ldap", "/centreon/api/v1/cache", "/centreon/api/v1/sessions", "/centreon/api/v1/password", "/centreon/api/v1/two_factor", "/centreon/api/v1/webauthn", "/centreon/api/v1/security", "/centreon/api/v1/compliance", "/centreon/api/v1/audit", "/centreon/api/v1/reports", "/centreon/api/v1/monitoring"],
    "Checkmk": ["/", "/check_mk", "/check_mk/index.py", "/check_mk/api", "/check_mk/api/v1", "/check_mk/api/v1/hosts", "/check_mk/api/v1/services", "/check_mk/api/v1/metrics", "/check_mk/api/v1/status", "/check_mk/api/v1/version", "/check_mk/api/v1/swagger", "/check_mk/api/v1/openapi", "/check_mk/api/v1/config", "/check_mk/api/v1/health", "/check_mk/api/v1/monitoring", "/check_mk/api/v1/tasks", "/check_mk/api/v1/attachments", "/check_mk/api/v1/mentions", "/check_mk/api/v1/history", "/check_mk/api/v1/stats", "/check_mk/api/v1/reports", "/check_mk/api/v1/jobs", "/check_mk/api/v1/schedulers", "/check_mk/api/v1/triggers", "/check_mk/api/v1/overviews", "/check_mk/api/v1/templates", "/check_mk/api/v1/text_modules", "/check_mk/api/v1/macros", "/check_mk/api/v1/webhooks", "/check_mk/api/v1/integrations", "/check_mk/api/v1/channels", "/check_mk/api/v1/imports", "/check_mk/api/v1/exports", "/check_mk/api/v1/search", "/check_mk/api/v1/objects", "/check_mk/api/v1/translations", "/check_mk/api/v1/oauth", "/check_mk/api/v1/applications", "/check_mk/api/v1/authorizations", "/check_mk/api/v1/ldap", "/check_mk/api/v1/cache", "/check_mk/api/v1/sessions", "/check_mk/api/v1/password", "/check_mk/api/v1/two_factor", "/check_mk/api/v1/webauthn", "/check_mk/api/v1/security", "/check_mk/api/v1/compliance", "/check_mk/api/v1/audit", "/check_mk/api/v1/reports", "/check_mk/api/v1/monitoring"],
    "Prometheus Alertmanager": ["/", "/api", "/api/v1", "/api/v1/status", "/api/v1/receivers", "/api/v1/silences", "/api/v1/alerts", "/api/v1/alertgroups", "/api/v1/metrics", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/health", "/api/v1/monitoring", "/api/v1/tasks", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/ldap", "/api/v1/cache", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring"],
    "Thanos": ["/", "/api", "/api/v1", "/api/v1/status", "/api/v1/stores", "/api/v1/rules", "/api/v1/alerts", "/api/v1/query", "/api/v1/query_range", "/api/v1/labels", "/api/v1/series", "/api/v1/metadata", "/api/v1/targets", "/api/v1/metrics", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/health", "/api/v1/monitoring", "/api/v1/tasks", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/ldap", "/api/v1/cache", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring"],
    "Cortex": ["/", "/api", "/api/v1", "/api/v1/status", "/api/v1/stores", "/api/v1/rules", "/api/v1/alerts", "/api/v1/query", "/api/v1/query_range", "/api/v1/labels", "/api/v1/series", "/api/v1/metadata", "/api/v1/targets", "/api/v1/metrics", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/health", "/api/v1/monitoring", "/api/v1/tasks", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/ldap", "/api/v1/cache", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring"],
    "Loki": ["/", "/api", "/api/v1", "/api/v1/status", "/api/v1/labels", "/api/v1/label", "/api/v1/series", "/api/v1/query", "/api/v1/query_range", "/api/v1/tail", "/api/v1/metrics", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/health", "/api/v1/monitoring", "/api/v1/tasks", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/ldap", "/api/v1/cache", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring"],
    "Tempo": ["/", "/api", "/api/v1", "/api/v1/status", "/api/v1/traces", "/api/v1/search", "/api/v1/tags", "/api/v1/metrics", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/health", "/api/v1/monitoring", "/api/v1/tasks", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/ldap", "/api/v1/cache", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring"],
    "Mimir": ["/", "/api", "/api/v1", "/api/v1/status", "/api/v1/stores", "/api/v1/rules", "/api/v1/alerts", "/api/v1/query", "/api/v1/query_range", "/api/v1/labels", "/api/v1/series", "/api/v1/metadata", "/api/v1/targets", "/api/v1/metrics", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/health", "/api/v1/monitoring", "/api/v1/tasks", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/ldap", "/api/v1/cache", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring"],
    "Pyroscope": ["/", "/api", "/api/v1", "/api/v1/status", "/api/v1/metrics", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/health", "/api/v1/monitoring", "/api/v1/tasks", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/ldap", "/api/v1/cache", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring"],
    "OpenTelemetry Collector": ["/", "/metrics", "/health", "/status", "/version", "/config", "/debug", "/pprof", "/debug/pprof", "/debug/pprof/heap", "/debug/pprof/goroutine", "/debug/pprof/profile", "/debug/pprof/trace", "/debug/pprof/block", "/debug/pprof/mutex", "/debug/pprof/threadcreate", "/debug/pprof/cmdline", "/debug/pprof/symbol", "/debug/pprof/allocs"],
    "Fluentd": ["/", "/api", "/api/v1", "/api/v1/status", "/api/v1/metrics", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/health", "/api/v1/monitoring", "/api/v1/tasks", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/ldap", "/api/v1/cache", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring"],
    "Fluent Bit": ["/", "/api", "/api/v1", "/api/v1/status", "/api/v1/metrics", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/health", "/api/v1/monitoring", "/api/v1/tasks", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/ldap", "/api/v1/cache", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring"],
    "Vector": ["/", "/api", "/api/v1", "/api/v1/status", "/api/v1/metrics", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/health", "/api/v1/monitoring", "/api/v1/tasks", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/ldap", "/api/v1/cache", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring"],
    "Logstash": ["/", "/api", "/api/v1", "/api/v1/status", "/api/v1/metrics", "/api/v1/version", "/api/v1/swagger", "/api/v1/openapi", "/api/v1/config", "/api/v1/health", "/api/v1/monitoring", "/api/v1/tasks", "/api/v1/attachments", "/api/v1/mentions", "/api/v1/history", "/api/v1/stats", "/api/v1/reports", "/api/v1/jobs", "/api/v1/schedulers", "/api/v1/triggers", "/api/v1/overviews", "/api/v1/templates", "/api/v1/text_modules", "/api/v1/macros", "/api/v1/webhooks", "/api/v1/integrations", "/api/v1/channels", "/api/v1/imports", "/api/v1/exports", "/api/v1/search", "/api/v1/objects", "/api/v1/translations", "/api/v1/oauth", "/api/v1/applications", "/api/v1/authorizations", "/api/v1/ldap", "/api/v1/cache", "/api/v1/sessions", "/api/v1/password", "/api/v1/two_factor", "/api/v1/webauthn", "/api/v1/security", "/api/v1/compliance", "/api/v1/audit", "/api/v1/reports", "/api/v1/monitoring"],
}

DKIM_SELECTORS = [
    "default", "google", "k1", "k2", "k3", "s1", "s2", "mail", "dkim",
    "selector1", "selector2", "mandrill", "sendgrid", "mailchimp",
    "amazonses", "postmark", "sparkpost", "proofpoint", "mimecast",
    "cm", "ctct", "constantcontact", "hubspot", "marketo", "pardot",
    "salesforce", "zendesk", "freshdesk", "intercom", "drift", "crisp",
    "outlook", "microsoft", "office365", "exchange", "googlemail",
    "gmail", "yahoo", "hotmail", "aol", "icloud", "me", "mac",
    "protonmail", "proton", "zoho", "yandex", "mailru", "qq",
    "163", "126", "sina", "sohu", "aliyun", "tencent", "netease",
    "sendinblue", "brevo", "mailgun", "mailjet", "postmarkapp",
    "elasticemail", "socketlabs", "pepipost", "smtp2go", "sendpulse",
    "mailerlite", "convertkit", "drip", "klaviyo", "customerio",
    "iterable", "braze", "onesignal", "pusher", "ably", "pubnub",
    "agora", "twilio", "nexmo", "vonage", "messagebird", "plivo",
    "bandwidth", "telesign", "sinch", "infobip", "clickatell",
]

SRV_TARGETS = [
    "_sip._tcp", "_sip._udp", "_sips._tcp",
    "_xmpp-server._tcp", "_xmpp-client._tcp",
    "_autodiscover._tcp", "_caldavs._tcp", "_carddavs._tcp",
    "_imap._tcp", "_imaps._tcp", "_submission._tcp",
    "_ldap._tcp", "_kerberos._tcp", "_kpasswd._udp",
    "_http._tcp", "_https._tcp",
    "_smtp._tcp", "_smtps._tcp", "_pop3._tcp", "_pop3s._tcp",
    "_ftp._tcp", "_ftps._tcp", "_ssh._tcp", "_telnet._tcp",
    "_vnc._tcp", "_rdp._tcp", "_mysql._tcp", "_postgresql._tcp",
    "_mongodb._tcp", "_redis._tcp", "_memcached._tcp",
    "_elasticsearch._tcp", "_kibana._tcp", "_logstash._tcp",
    "_prometheus._tcp", "_grafana._tcp", "_jenkins._tcp",
    "_gitlab._tcp", "_github._tcp", "_bitbucket._tcp",
    "_jira._tcp", "_confluence._tcp", "_wiki._tcp",
    "_nfs._tcp", "_nfs._udp", "_smb._tcp", "_cifs._tcp",
    "_afpovertcp._tcp", "_apple-ichat._tcp", "_apple-mobdev._tcp",
    "_presence._tcp", "_presence._udp", "_stun._tcp", "_stun._udp",
    "_turn._tcp", "_turn._udp", "_stuns._tcp", "_turns._tcp",
    "_stun.tcp", "_stun.udp", "_turn.tcp", "_turn.udp",
]

SPECIAL_FILES = [
    "robots.txt", "sitemap.xml", "sitemap_index.xml", "sitemap.txt",
    "humans.txt", "security.txt", ".well-known/security.txt",
    ".well-known/change-password", ".well-known/openid-configuration",
    ".well-known/assetlinks.json", ".well-known/apple-app-site-association",
    ".well-known/jwks.json", ".well-known/webfinger", ".well-known/mta-sts.txt",
    ".well-known/gpc.json", ".well-known/dnt-policy.txt", ".well-known/nodeinfo",
    ".well-known/terraform.json", ".well-known/did.json",
    ".well-known/ai-plugin.json", ".well-known/matrix/server", ".well-known/matrix/client",
    ".well-known/coap", ".well-known/est/", ".well-known/caldav", ".well-known/carddav",
    ".well-known/timezone", ".well-known/pki-validation/",
    ".well-known/oauth-authorization-server",
    ".well-known/apple-developer-merchantid-domain-association",
    ".well-known/autoconfig/mail/config-v1.1.xml", ".well-known/mail-v1.xml",
    ".well-known/host-meta", ".well-known/host-meta.json",
    ".well-known/uma2-configuration", ".well-known/oauth-protected-resource",
    ".well-known/mercure", ".well-known/ni", ".well-known/dnt",
    ".well-known/rootcertificates", ".well-known/traffic-advice",
    ".well-known/private-network-access", ".well-known/csaf/",
    ".well-known/blockchain/", ".well-known/nostr.json",
    ".well-known/void", ".well-known/posh", ".well-known/sgx",
    "crossdomain.xml", "clientaccesspolicy.xml",
    "manifest.json", "manifest.webmanifest", "browserconfig.xml",
    "favicon.ico", "apple-touch-icon.png",
    ".git/config", ".git/HEAD", ".gitignore", ".git/logs/HEAD",
    ".git/index", ".git/COMMIT_EDITMSG", ".git/description",
    ".git/info/exclude", ".git/refs/heads/main", ".git/refs/heads/master",
    ".env", ".env.local", ".env.production", ".env.backup", ".env.dev", ".env.staging",
    ".env.example", ".env.sample", ".env.test", ".env.development",
    ".env.prod", ".env.ci", ".env.travis", ".env.circleci",
    ".DS_Store", "Thumbs.db",
    "wp-config.php.bak", "wp-config.php~", "wp-config.php.old", "wp-config.php.save",
    "wp-config.php.txt", "wp-config.php.dist", "wp-config.php.orig",
    "config.php.bak", "config.json", "config.yml", "config.yaml", "config.xml",
    "config.php~", "config.php.old", "config.php.save", "config.php.txt",
    "settings.py", "settings.py.bak", "local_settings.py",
    "settings.py~", "settings.py.old", "settings.py.save",
    "backup.zip", "backup.tar.gz", "backup.sql", "dump.sql", "db.sql",
    "database.sql", "site.sql", "database.zip", "backup.rar", "backup.7z",
    "backup.tar", "backup.tgz", "backup.bz2", "backup.tar.bz2",
    "phpinfo.php", "info.php", "test.php", "server-status", "server-info",
    "admin/", "login/", "wp-admin/", "wp-login.php", "phpmyadmin/",
    "test/", "dev/", "staging/", "demo/", "beta/", "old/", "new/", "backup/",
    "api/", "api/v1/", "api/v2/", "api/v3/", "graphql", "gql",
    "swagger.json", "swagger.yaml", "openapi.json", "openapi.yaml",
    "api-docs", "docs/", "README.md", "readme.txt", "CHANGELOG.md",
    "package.json", "package-lock.json", "yarn.lock",
    "composer.json", "composer.lock", "Gemfile", "Gemfile.lock",
    "requirements.txt", "Pipfile", "Pipfile.lock", "poetry.lock",
    "go.mod", "go.sum", "Cargo.toml", "Cargo.lock",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore",
    ".htaccess", ".htpasswd", "web.config",
    ".svn/entries", ".hg/requires", ".bzr/README",
    "error.log", "access.log", "debug.log", "app.log", "server.log",
    "CHANGELOG", "LICENSE", "COPYING",
    ".travis.yml", ".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml",
    ".github/workflows/main.yml", ".github/workflows/ci.yml",
    "terraform.tfstate", "terraform.tfvars",
    "k8s.yaml", "k8s.yml", "deployment.yaml", "service.yaml", "secrets.yaml",
    "vault.json", "secrets.json", "credentials.json",
    "id_rsa", "id_rsa.pub", "id_ed25519", "authorized_keys",
    "known_hosts", "ssh_config",
    "composer.phar", "artisan", "wp-cron.php",
    "sitemap.xml.gz", "sitemap_index.xml.gz",
    "firebase-config.js", "firebase.json", "firebase-messaging-sw.js",
    "google-services.json", "GoogleService-Info.plist",
    "asset-manifest.json", "precache-manifest.js", "service-worker.js",
    "sw.js", "workbox-config.js", "ngsw.json", "ngsw-worker.js",
    "robots.txt.bak", "sitemap.xml.bak", "sitemap.xml.old",
    "php.ini", "php.ini.bak", "php.ini.old", "php.ini.save",
    "my.cnf", "my.cnf.bak", "my.cnf.old",
    "httpd.conf", "httpd.conf.bak", "nginx.conf", "nginx.conf.bak",
    "apache2.conf", "apache2.conf.bak",
    "web.config.bak", "web.config.old",
    ".npmrc", ".yarnrc", ".babelrc", ".eslintrc", ".prettierrc",
    "tsconfig.json", "jsconfig.json", "vite.config.js", "vite.config.ts",
    "webpack.config.js", "rollup.config.js", "next.config.js",
    "nuxt.config.js", "gatsby-config.js", "vue.config.js",
    "angular.json", "nest-cli.json", "tslint.json",
    "jest.config.js", "cypress.json", "playwright.config.js",
    "Makefile", "CMakeLists.txt", "configure", "configure.ac",
    "meson.build", "build.gradle", "pom.xml", "build.xml",
    "build.sbt", "project.clj", "mix.exs", "rebar.config",
    "stack.yaml", "cabal.project", "Package.swift",
    "Podfile", "Podfile.lock", "Cartfile", "Cartfile.resolved",
    "pubspec.yaml", "pubspec.lock", "Package.resolved",
    "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
    "SECURITY.md", "SUPPORT.md", "GOVERNANCE.md", "ROADMAP.md",
    "AUTHORS", "CONTRIBUTORS", "NOTICE", "PATENTS",
    "Dockerfile.dev", "Dockerfile.prod", "Dockerfile.test",
    "docker-compose.dev.yml", "docker-compose.prod.yml",
    "docker-compose.test.yml", "docker-compose.override.yml",
    "docker-compose.ci.yml", "docker-compose.staging.yml",
    "docker-bake.hcl", "docker-bake.json",
    ".dockerignore", ".gitattributes", ".gitmodules",
    ".editorconfig", ".prettierignore", ".eslintignore",
    ".stylelintrc", ".stylelintignore", ".sass-lint.yml",
    ".markdownlint.json", ".markdownlintrc",
    ".yamllint", ".yamllint.yml", ".yaml-lint.yml",
    ".hadolint.yaml", ".hadolint.yml",
    ".shellcheckrc", ".flake8", ".pylintrc", ".isort.cfg",
    ".mypy.ini", ".bandit", ".safety-policy.yml",
    ".rubocop.yml", ".rubocop_todo.yml", ".reek",
    ".php_cs", ".php_cs.dist", ".php-cs-fixer.php",
    ".php-cs-fixer.dist.php", ".phpcs.xml", ".phpcs.xml.dist",
    ".psalm.xml", ".psalm.xml.dist", ".phpstan.neon",
    ".phpstan.neon.dist", ".phan/config.php",
    ".swiftlint.yml", ".swiftformat", ".clang-format",
    ".clang-tidy", ".cppcheck", ".cpplint",
    ".golangci.yml", ".golangci.yaml", ".golangci.toml",
    ".goreleaser.yml", ".goreleaser.yaml",
    ".golangci.yml", ".golangci.yaml", ".golangci.toml",
    "go.work", "go.work.sum",
    "vendor/modules.txt", "vendor/vendor.json",
    "Gopkg.toml", "Gopkg.lock", "glide.yaml", "glide.lock",
    "dep.toml", "dep.lock",
    "bower.json", ".bowerrc", "bower_components/",
    "component.json", "component-lock.json",
    "jspm.json", "jspm.lock", "systemjs.config.js",
    "karma.conf.js", "protractor.conf.js", "nightwatch.conf.js",
    "wdio.conf.js", "codecept.conf.js", "testcafe.json",
    "cypress.json", "cypress.env.json", "cypress.config.js",
    "playwright.config.js", "playwright.config.ts",
    "vitest.config.js", "vitest.config.ts",
    "jest.config.js", "jest.config.ts", "jest.setup.js",
    "mocha.opts", ".mocharc.yml", ".mocharc.json",
    "ava.config.js", "ava.config.cjs", "ava.config.mjs",
    "tape.config.js", "tap.config.js", ".taprc",
    "karma.conf.js", "karma.conf.coffee", "karma.conf.ts",
    "protractor.conf.js", "protractor.conf.coffee", "protractor.conf.ts",
    "nightwatch.conf.js", "nightwatch.conf.ts",
    "wdio.conf.js", "wdio.conf.ts",
    "codecept.conf.js", "codecept.conf.ts",
    "testcafe.json", ".testcaferc.json",
]

SECRET_PATTERNS = {
    "aws_access_key":          (r'\bAKIA[0-9A-Z]{16}\b', None, "critical", None),
    "aws_secret_key":          (r'(?i)aws[_\-]?secret[_\-]?(?:access[_\-]?)?key[\'"\s:=]{1,4}([A-Za-z0-9/+=]{40})', None, "critical", None),
    "aws_session_token":       (r'(?i)aws[_\-]?session[_\-]?token[\'"\s:=]{1,4}([A-Za-z0-9/+=]{100,})', None, "critical", None),
    "aws_mws_auth":            (r'amzn\.mws\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', None, "critical", None),
    "aws_s3_bucket":           (r'(?:s3[.\-][a-z0-9\-]+\.amazonaws\.com|[a-z0-9.\-]{3,63}\.s3\.amazonaws\.com|s3://[a-z0-9.\-/]+)', None, "medium", None),
    "gcp_service_account":     (r'"type"\s*:\s*"service_account"', None, "critical", None),
    "gcp_api_key":             (r'\bAIza[0-9A-Za-z\-_]{35}\b', None, "high", None),
    "gcp_oauth_secret":        (r'\bGOCSPX-[A-Za-z0-9_\-]{28,}\b', None, "critical", None),
    "gcp_oauth_client_id":     (r'\b[0-9]{12}-[a-z0-9]{32}\.apps\.googleusercontent\.com\b', None, "medium", None),
    "azure_storage_key":       (r'(?i)AccountKey=([A-Za-z0-9+/=]{88})', None, "critical", None),
    "azure_sas_token":         (r'[?&]sig=([A-Za-z0-9%+/=]{40,})', None, "high", None),
    "azure_connection_string": (r'(?i)DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[^;]+', None, "critical", None),
    "digitalocean_token":      (r'\bdop_v1_[a-f0-9]{64}\b', None, "critical", None),
    "cloudflare_token":        (r'(?i)cloudflare[a-z_]*token[\'"\s:=]{1,4}([A-Za-z0-9\-_]{40})', None, "critical", None),
    "cloudflare_api_key":      (r'(?i)cloudflare[a-z_]*key[\'"\s:=]{1,4}([A-Za-z0-9\-_]{37})', None, "critical", None),
    "firebase_io":             (r'\b[a-z0-9\-]+\.firebaseio\.com\b', None, "low", None),
    "firebase_database":       (r'(?i)firebase[a-z_]*url[\'"\s:=]{1,4}(https://[a-z0-9\-]+\.firebaseio\.com)', None, "medium", None),
    "slack_token":             (r'\bxox[baprs]-[0-9A-Za-z\-]{10,72}\b', None, "critical", None),
    "slack_webhook":           (r'hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+', None, "high", None),
    "github_token":            (r'\bgh[pousr]_[A-Za-z0-9]{36,255}\b', None, "critical", None),
    "github_oauth":            (r'\b[a-f0-9]{40}\b', None, "low", None),
    "gitlab_token":            (r'\bglpat-[A-Za-z0-9\-_]{20,}\b', None, "critical", None),
    "gitlab_pipeline_token":   (r'\bglptt-[A-Za-z0-9\-_]{20,}\b', None, "critical", None),
    "stripe_live":             (r'\bsk_live_[0-9a-zA-Z]{24,}\b', None, "critical", None),
    "stripe_test":             (r'\bsk_test_[0-9a-zA-Z]{24,}\b', None, "medium", None),
    "stripe_publishable":      (r'\bpk_(?:live|test)_[0-9a-zA-Z]{24,}\b', None, "low", None),
    "stripe_webhook_secret":   (r'\bwhsec_[A-Za-z0-9]{32,}\b', None, "high", None),
    "square_token":            (r'\bsq0atp-[A-Za-z0-9_\-]{22}\b', None, "critical", None),
    "square_oauth":            (r'\bsq0csp-[A-Za-z0-9_\-]{43}\b', None, "critical", None),
    "shopify_token":           (r'\bshpat_[a-f0-9]{32}\b', None, "critical", None),
    "shopify_private":         (r'\bshppa_[a-f0-9]{32}\b', None, "critical", None),
    "shopify_shared":          (r'\bshpss_[a-f0-9]{32}\b', None, "critical", None),
    "twilio_sid":              (r'\bAC[a-f0-9]{32}\b', None, "high", None),
    "twilio_api_key":          (r'\bSK[a-f0-9]{32}\b', None, "high", None),
    "sendgrid_key":            (r'\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b', None, "critical", None),
    "mailgun_key":             (r'\bkey-[a-f0-9]{32}\b', None, "high", None),
    "mailchimp_key":           (r'\b[a-f0-9]{32}-us[0-9]{1,2}\b', None, "high", None),
    "openai_key":              (r'\bsk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}\b', None, "critical", None),
    "openai_project":          (r'\bsk-proj-[A-Za-z0-9_\-]{40,}\b', None, "critical", None),
    "anthropic_key":           (r'\bsk-ant-[A-Za-z0-9\-_]{95,}\b', None, "critical", None),
    "huggingface_token":       (r'\bhf_[A-Za-z0-9]{34,}\b', None, "high", None),
    "discord_bot_token":       (r'\b[MN][A-Za-z\d]{23}\.[\w\-]{6}\.[\w\-]{27,}\b', None, "critical", None),
    "discord_webhook":         (r'discord(?:app)?\.com/api/webhooks/\d+/[\w\-]+', None, "high", None),
    "telegram_bot_token":      (r'\b\d{8,10}:[A-Za-z0-9_\-]{35}\b', None, "critical", None),
    "facebook_access_token":   (r'\bEAA[A-Za-z0-9]{100,}\b', None, "critical", None),
    "facebook_app_secret":     (r'(?i)facebook[a-z_]*secret[\'"\s:=]{1,4}([a-f0-9]{32})', None, "critical", None),
    "instagram_token":         (r'\bIGQVJ[A-Za-z0-9_\-]{50,}\b', None, "high", None),
    "dropbox_token":           (r'\bsl\.[A-Za-z0-9_\-]{130,}\b', None, "high", None),
    "atlassian_token":         (r'\bATATT3[A-Za-z0-9_\-]{50,}\b', None, "high", None),
    "notion_token":            (r'\bsecret_[A-Za-z0-9]{43}\b', None, "high", None),
    "airtable_pat":            (r'\bpat[A-Za-z0-9]{14}\.[a-f0-9]{64}\b', None, "high", None),
    "mapbox_token":            (r'\bpk\.[A-Za-z0-9\-_]{60,}\.[A-Za-z0-9\-_]{22}\b', None, "medium", None),
    "mapbox_secret":           (r'\bsk\.[A-Za-z0-9\-_]{60,}\.[A-Za-z0-9\-_]{22}\b', None, "high", None),
    "npm_token":               (r'\bnpm_[A-Za-z0-9]{36}\b', None, "high", None),
    "pypi_token":              (r'\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9\-_]{50,}\b', None, "high", None),
    "docker_pat":              (r'\bdckr_pat_[A-Za-z0-9_\-]{27,}\b', None, "high", None),
    "newrelic_key":            (r'\bNRAK-[A-Z0-9]{27}\b', None, "high", None),
    "sentry_dsn":              (r'https://[a-f0-9]{32}@[a-z0-9.\-]+/\d+', None, "medium", None),
    "mongodb_uri":             (r'mongodb(?:\+srv)?://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "postgres_uri":            (r'postgres(?:ql)?://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "mysql_uri":               (r'mysql://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "redis_uri":               (r'redis://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "amqp_uri":                (r'amqp://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "kafka_uri":               (r'kafka://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "cassandra_uri":           (r'cassandra://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "couchdb_uri":             (r'couchdb://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "elasticsearch_uri":       (r'elasticsearch://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "neo4j_uri":               (r'neo4j://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "influxdb_uri":            (r'influxdb://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "clickhouse_uri":          (r'clickhouse://[^:\s/@]+:[^@\s]+@[^\s"\'<>]+', None, "critical", None),
    "private_key_rsa":         (r'-----BEGIN RSA PRIVATE KEY-----', None, "critical", None),
    "private_key_ec":          (r'-----BEGIN EC PRIVATE KEY-----', None, "critical", None),
    "private_key_openssh":     (r'-----BEGIN OPENSSH PRIVATE KEY-----', None, "critical", None),
    "private_key_pgp":         (r'-----BEGIN PGP PRIVATE KEY BLOCK-----', None, "critical", None),
    "private_key_dsa":         (r'-----BEGIN DSA PRIVATE KEY-----', None, "critical", None),
    "private_key_putty":       (r'PuTTY-User-Key-File-\d+', None, "critical", None),
    "jwt_token":               (r'\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b', None, "high", None),
    "bearer_token":            (r'(?i)bearer\s+[A-Za-z0-9\-_.=]{20,}', None, "high", None),
    "flask_secret_key":        (r'SECRET_KEY\s*=\s*[\'"]([^\'"]{16,})[\'"]', None, "critical", None),
    "django_secret_key":       (r'SECRET_KEY\s*=\s*[\'"]([^\'"]{40,})[\'"]', None, "critical", None),
    "rails_secret_base":       (r'secret_key_base:\s*([a-f0-9]{64,})', None, "critical", None),
    "laravel_app_key":         (r'APP_KEY=base64:[A-Za-z0-9+/=]{40,}', None, "critical", None),
    "jwt_secret":              (r'(?i)jwt[_\-]?secret[\'"\s:=]{1,4}([A-Za-z0-9\-_]{16,})', None, "critical", None),
    "generic_api_key":         (r'(?i)(?:api[_-]?key|apikey|access[_-]?token)["\']?\s*[:=]\s*["\']([A-Za-z0-9\-_]{20,})["\']', None, "high", None),
    "generic_secret":          (r'(?i)(?:secret|private[_-]?key)["\']?\s*[:=]\s*["\']([A-Za-z0-9\-_]{16,})["\']', None, "high", None),
    "generic_password":        (r'(?i)(?:password|passwd|pwd)["\']?\s*[:=]\s*["\']([^"\']{8,})["\']', None, "high", None),
    "generic_token":           (r'(?i)(?:token|auth[_-]?token)["\']?\s*[:=]\s*["\']([A-Za-z0-9\-_\.]{20,})["\']', None, "high", None),
    "s3_bucket":               (r'(?:s3[.\-][a-z0-9\-]+\.amazonaws\.com|[a-z0-9.\-]{3,63}\.s3\.amazonaws\.com|s3://[a-z0-9.\-/]+)', None, "medium", None),
    "internal_ip":             (r'\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b', None, "medium", None),
    "ipv4":                    (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', None, "low", None),
    "ipv6":                    (r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b', None, "low", None),
    "webhook_slack":           (r'https?://hooks\.slack\.com/services/[^\s"\'<>]+', None, "high", None),
    "webhook_discord":         (r'https?://discord(?:app)?\.com/api/webhooks/[^\s"\'<>]+', None, "high", None),
    "webhook_teams":           (r'https?://[a-z0-9\-]+\.webhook\.office\.com/[^\s"\'<>]+', None, "high", None),
    "webhook_generic":         (r'https?://[^\s"\'<>]*(?:webhook|hook|callback)[^\s"\'<>]*', None, "medium", None),
    "tor_onion":               (r'\b[a-z2-7]{16}\.onion\b|\b[a-z2-7]{56}\.onion\b', None, "low", None),
    "magnet_link":             (r'magnet:\?xt=urn:btih:[a-fA-F0-9]{40}', None, "low", None),
    "ssn":                     (r'\b\d{3}-\d{2}-\d{4}\b', None, "high", None),
    "iban":                    (r'\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b', None, "medium", None),
    "credit_card":             (r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})\b', None, "high", None),
    "session_cookie_names":    (r'\b(?:PHPSESSID|JSESSIONID|ASP\.NET_SessionId|connect\.sid|laravel_session|ci_session|_session_id|rack\.session|django_session)\b', None, "low", None),
    "csrf_token":              (r'(?i)(?:csrf|xsrf)[_\-]?token["\']?\s*[:=]\s*["\']([^"\']{16,})["\']', None, "medium", None),
    "password_reset_token":    (r'(?i)(?:reset|forgot|recover)[^\s"\']*[?&]token=([A-Za-z0-9\-_]{20,})', None, "high", None),
    "dns_txt":                 (r'v=spf1[^\s"\'<>]+|v=DKIM1[^\s"\'<>]+|v=DMARC1[^\s"\'<>]+', None, "low", None),
    "ssh_private_key":         (r'-----BEGIN (?:RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----', None, "critical", None),
    "pgp_private_key":         (r'-----BEGIN PGP PRIVATE KEY BLOCK-----', None, "critical", None),
    "x509_certificate":        (r'-----BEGIN CERTIFICATE-----', None, "low", None),
    "certificate_request":     (r'-----BEGIN CERTIFICATE REQUEST-----', None, "low", None),
    "pgp_public_key":          (r'-----BEGIN PGP PUBLIC KEY BLOCK-----', None, "low", None),
    "ssh_public_key":          (r'ssh-(?:rsa|dss|ed25519|ecdsa) [A-Za-z0-9+/=]+', None, "low", None),
    "putty_private_key":       (r'PuTTY-User-Key-File-\d+: [^\n]+', None, "critical", None),
    "kubernetes_secret":       (r'(?i)kind:\s*Secret', None, "high", None),
    "kubernetes_config":       (r'(?i)apiVersion:\s*v1\s*\nkind:\s*Config', None, "medium", None),
    "docker_config":           (r'(?i)"auths"\s*:\s*\{', None, "high", None),
    "npmrc_auth":              (r'//registry\.npmjs\.org/:_authToken=[A-Za-z0-9\-_]+', None, "high", None),
    "pypirc_auth":             (r'\[pypi\]\s*\nusername\s*=\s*[^\n]+\npassword\s*=\s*[^\n]+', None, "high", None),
    "gem_credentials":         (r':rubygems_api_key:\s*[a-f0-9]{48}', None, "high", None),
    "netrc_credentials":       (r'machine\s+\S+\s+login\s+\S+\s+password\s+\S+', None, "high", None),
    "htpasswd_entry":          (r'^[a-zA-Z0-9._\-]+:\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$', re.MULTILINE, "high", None),
    "shadow_entry":            (r'^[a-zA-Z0-9._\-]+:\$[0-9]\$[A-Za-z0-9./]+\$[A-Za-z0-9./]+:\d+:\d+:\d+:\d+:\d+:\d+:\d+$', re.MULTILINE, "high", None),
    "passwd_entry":            (r'^[a-zA-Z0-9._\-]+:x:\d+:\d+:[^:]*:[^:]*:[^:]*$', re.MULTILINE, "low", None),
}

COMPILED_SECRETS = {}
for _name, _spec in SECRET_PATTERNS.items():
    _pat, _flags, _sev, _val = _spec
    COMPILED_SECRETS[_name] = (re.compile(_pat, 0 if not _flags else _flags), _sev, _val)

SECRET_FALSE_POSITIVES = {
    "your_api_key_here", "changeme", "example.com", "example.org",
    "xxxxxxxxxxxxxxxxxxxx", "aaaaaaaaaaaaaaaaaaaa", "0000000000000000000",
    "your_api_key", "your_password_here", "insert_your_key", "insert_api_key",
    "replace_me", "change_me", "todo", "fixme", "tbd", "test", "demo",
    "password", "secret", "apikey", "api_key", "token", "null", "none",
    "undefined", "false", "true", "placeholder", "sample", "yourapikey",
    "your-key-here", "your_secret_key", "your-secret-key", "insert-here",
    "replace-with", "change-this", "your_token", "your-token",
    "yourpassword", "your_password", "your-password", "your_pass",
    "your_secret", "your-secret", "your_apikey", "your-apikey",
    "your_api", "your-api", "your_key", "your-key",
    "mysupersecret", "supersecret", "topsecret", "verysecret",
    "notasecret", "not_a_secret", "not-a-secret", "thisisasecret",
    "this_is_a_secret", "this-is-a-secret", "secretvalue",
    "secret_value", "secret-value", "secretkey", "secret_key",
    "secret-key", "privatekey", "private_key", "private-key",
    "publickey", "public_key", "public-key", "accesskey", "access_key",
    "access-key", "apikeyhere", "api_key_here", "api-key-here",
    "your_api_key_here", "your-api-key-here", "insertyourkey",
    "insert_your_key", "insert-your-key", "putyourkeyhere",
    "put_your_key_here", "put-your-key-here",
    "mysupersecretkey", "my_super_secret_key", "my-super-secret-key",
    "supersecretkey", "super_secret_key", "super-secret-key",
    "topsecretkey", "top_secret_key", "top-secret-key",
    "verysecretkey", "very_secret_key", "very-secret-key",
    "notarealkey", "not_a_real_key", "not-a-real-key",
    "fakekey", "fake_key", "fake-key", "dummykey", "dummy_key",
    "dummy-key", "samplekey", "sample_key", "sample-key",
    "testkey", "test_key", "test-key", "testkey123", "test_key_123",
    "testkey123", "test-key-123", "testkey12345", "test_key_12345",
    "test-key-12345", "testkey123456", "test_key_123456",
    "test-key-123456", "testkey1234567", "test_key_1234567",
    "test-key-1234567", "testkey12345678", "test_key_12345678",
    "test-key-12345678", "testkey123456789", "test_key_123456789",
    "test-key-123456789", "testkey1234567890", "test_key_1234567890",
    "test-key-1234567890", "testkey12345678901", "test_key_12345678901",
    "test-key-12345678901", "testkey123456789012", "test_key_123456789012",
    "test-key-123456789012", "testkey1234567890123", "test_key_1234567890123",
    "test-key-1234567890123", "testkey12345678901234", "test_key_12345678901234",
    "test-key-12345678901234", "testkey123456789012345", "test_key_123456789012345",
    "test-key-123456789012345", "testkey1234567890123456", "test_key_1234567890123456",
    "test-key-1234567890123456", "testkey12345678901234567", "test_key_12345678901234567",
    "test-key-12345678901234567", "testkey123456789012345678", "test_key_123456789012345678",
    "test-key-123456789012345678", "testkey1234567890123456789", "test_key_1234567890123456789",
    "test-key-1234567890123456789", "testkey12345678901234567890", "test_key_12345678901234567890",
    "test-key-12345678901234567890",
}

CONTEXT_ALLOWLIST = re.compile(
    r'(?i)(placeholder|label|required|hint|example|your_|enter_|i18n|translation|'
    r'message|validate|error|sample|dummy|fake|test_|mock|fixme|todo|'
    r'aria-label|title=|data-tip|tooltip)'
)

IGNORE_DEFAULTS = """# .stratascan_ignore
# One pattern per line. Lines starting with # are comments.
# Any candidate secret whose value contains one of these (case-insensitive) is dropped.
example
placeholder
your_api_key
your-key
yourkey
changeme
change-me
insert
replace-me
xxxxxxxx
aaaaaaaa
00000000
11111111
12345678
test
demo
sample
dummy
fake
mock
lorem
ipsum
foobar
foo
bar
baz
qux
test123
password123
admin123
"""


JITTER_CONFIG = {
    "enabled": True,
    "min": 5.0,
    "max": 8.0,
    "hosts": {"web.archive.org", "archive.org"},
    "adaptive_backoff": 1.0,
    "lock": threading.Lock(),
}


def jitter_status():
    with JITTER_CONFIG["lock"]:
        return {
            "enabled": JITTER_CONFIG["enabled"],
            "min": JITTER_CONFIG["min"],
            "max": JITTER_CONFIG["max"],
            "hosts": sorted(JITTER_CONFIG["hosts"]),
            "adaptive_backoff": JITTER_CONFIG["adaptive_backoff"],
        }


def set_jitter(enabled=None, jmin=None, jmax=None):
    with JITTER_CONFIG["lock"]:
        if enabled is not None:
            JITTER_CONFIG["enabled"] = bool(enabled)
        if jmin is not None:
            try:
                JITTER_CONFIG["min"] = max(0.0, float(jmin))
            except (ValueError, TypeError):
                pass
        if jmax is not None:
            try:
                JITTER_CONFIG["max"] = max(0.0, float(jmax))
            except (ValueError, TypeError):
                pass
        if JITTER_CONFIG["min"] > JITTER_CONFIG["max"]:
            JITTER_CONFIG["min"], JITTER_CONFIG["max"] = JITTER_CONFIG["max"], JITTER_CONFIG["min"]


def _maybe_jitter_sleep(url, reason="throttle"):
    host = urllib.parse.urlparse(url).netloc.split(":")[0]
    with JITTER_CONFIG["lock"]:
        enabled = JITTER_CONFIG["enabled"]
        hosts = set(JITTER_CONFIG["hosts"])
        lo = JITTER_CONFIG["min"]
        hi = JITTER_CONFIG["max"]
        backoff = JITTER_CONFIG["adaptive_backoff"]
    if not enabled or host not in hosts:
        return
    base = random.uniform(lo, hi) * backoff
    if backoff > 1.0:
        T("JITTER", f"adaptive x{backoff:.2f} -> sleep {base:.2f}s for {host} ({reason})", dedupe=True)
    else:
        T("JITTER", f"jitter {base:.2f}s for {host} ({reason})", dedupe=True)
    remaining = base
    step = 0.2
    while remaining > 0:
        chunk = min(step, remaining)
        time.sleep(chunk)
        remaining -= chunk


def _bump_backoff():
    with JITTER_CONFIG["lock"]:
        JITTER_CONFIG["adaptive_backoff"] = min(8.0, JITTER_CONFIG["adaptive_backoff"] * 1.5)


def _reset_backoff():
    with JITTER_CONFIG["lock"]:
        JITTER_CONFIG["adaptive_backoff"] = 1.0


class LocalCache:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.conn = None
        try:
            self.conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30)
            self._init_schema()
        except Exception as e:
            T("CACHE", f"sqlite init failed: {e}")
            self.conn = None

    def _init_schema(self):
        with self.lock:
            c = self.conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS cdx (urlkey TEXT, timestamp TEXT, original TEXT, statuscode TEXT, mimetype TEXT, digest TEXT, length TEXT, redirect TEXT, fetched_at REAL, PRIMARY KEY (urlkey, timestamp, digest))")
            c.execute("CREATE TABLE IF NOT EXISTS bodies (archive_url TEXT PRIMARY KEY, body BLOB, mimetype TEXT, fetched_at REAL)")
            c.execute("CREATE TABLE IF NOT EXISTS findings (id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT, pattern TEXT, value TEXT, severity TEXT, source TEXT, source_url TEXT, ts TEXT, decoded_from TEXT, entropy REAL, length INTEGER, context TEXT, matched_at REAL)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_findings_domain ON findings(domain)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_findings_pattern ON findings(pattern)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_findings_value ON findings(value)")
            self.conn.commit()

    def store_snapshot(self, s):
        if not self.conn:
            return
        try:
            with self.lock:
                self.conn.execute(
                    "INSERT OR IGNORE INTO cdx VALUES (?,?,?,?,?,?,?,?,?)",
                    (s.get("urlkey"), s.get("timestamp"), s.get("original"),
                     s.get("statuscode"), s.get("mimetype"), s.get("digest"),
                     s.get("length"), s.get("redirect"), time.time()))
                self.conn.commit()
        except Exception:
            pass

    def load_snapshots(self, domain):
        if not self.conn:
            return []
        try:
            with self.lock:
                cur = self.conn.execute(
                    "SELECT urlkey,timestamp,original,statuscode,mimetype,digest,length,redirect FROM cdx WHERE original LIKE ?",
                    (f"%{domain}%",))
                rows = cur.fetchall()
            out = []
            for r in rows:
                out.append({
                    "urlkey": r[0], "timestamp": r[1], "original": r[2],
                    "statuscode": r[3], "mimetype": r[4], "digest": r[5],
                    "length": r[6], "redirect": r[7],
                })
            return out
        except Exception:
            return []

    def store_body(self, archive_url, body_bytes, mimetype=""):
        if not self.conn or body_bytes is None:
            return
        try:
            with self.lock:
                self.conn.execute(
                    "INSERT OR REPLACE INTO bodies VALUES (?,?,?,?)",
                    (archive_url, sqlite3.Binary(body_bytes), mimetype, time.time()))
                self.conn.commit()
        except Exception:
            pass

    def load_body(self, archive_url):
        if not self.conn:
            return None
        try:
            with self.lock:
                cur = self.conn.execute("SELECT body FROM bodies WHERE archive_url = ?", (archive_url,))
                row = cur.fetchone()
            return bytes(row[0]) if row else None
        except Exception:
            return None

    def store_finding(self, domain, pattern, value, severity, source, source_url, ts, decoded_from, entropy, length, context):
        if not self.conn:
            return
        try:
            with self.lock:
                self.conn.execute(
                    "INSERT INTO findings (domain, pattern, value, severity, source, source_url, ts, decoded_from, entropy, length, context, matched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (domain, pattern, value, severity, source, source_url, ts, decoded_from, entropy, length, context, time.time()))
                self.conn.commit()
        except Exception:
            pass

    def all_findings_for(self, domain):
        if not self.conn:
            return []
        try:
            with self.lock:
                cur = self.conn.execute(
                    "SELECT pattern,value,severity,source,source_url,ts,decoded_from,entropy,length,context FROM findings WHERE domain = ?",
                    (domain,))
                rows = cur.fetchall()
            return [{
                "pattern": r[0], "value": r[1], "severity": r[2], "source": r[3],
                "source_url": r[4], "ts": r[5], "decoded_from": r[6],
                "entropy": r[7], "length": r[8], "context": r[9],
            } for r in rows]
        except Exception:
            return []

    def value_history(self, value):
        if not self.conn:
            return []
        try:
            with self.lock:
                cur = self.conn.execute(
                    "SELECT domain,pattern,severity,source_url,ts FROM findings WHERE value = ? ORDER BY ts",
                    (value,))
                rows = cur.fetchall()
            return [{"domain": r[0], "pattern": r[1], "severity": r[2], "source_url": r[3], "ts": r[4]} for r in rows]
        except Exception:
            return []

    def all_values_for_pattern(self, domain, pattern):
        if not self.conn:
            return []
        try:
            with self.lock:
                cur = self.conn.execute(
                    "SELECT value,ts,source_url FROM findings WHERE domain = ? AND pattern = ? ORDER BY ts",
                    (domain, pattern))
                rows = cur.fetchall()
            return [{"value": r[0], "ts": r[1], "source_url": r[2]} for r in rows]
        except Exception:
            return []


CACHE = {"conn": None, "lock": threading.Lock()}


def _bind_cache(path):
    with CACHE["lock"]:
        try:
            if CACHE["conn"] is not None:
                CACHE["conn"].conn.close()
        except Exception:
            pass
        CACHE["conn"] = LocalCache(path)


def cache():
    with CACHE["lock"]:
        return CACHE["conn"]


class RawSink:
    def __init__(self, out_dir, enabled=False, max_total_bytes=200 * 1024 * 1024):
        self.out_dir = Path(out_dir)
        self.snapshots_dir = self.out_dir / "raw_snapshots"
        self.enabled = enabled
        self.max_total_bytes = max_total_bytes
        self.used_bytes = 0
        self.lock = threading.Lock()
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            if enabled:
                self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def save_body(self, archive_url, body_bytes, mimetype=""):
        if not self.enabled or body_bytes is None:
            return None
        if self.used_bytes + len(body_bytes) > self.max_total_bytes:
            return None
        h = hashlib.sha1(body_bytes).hexdigest()[:16]
        name = re.sub(r"[^a-zA-Z0-9._-]", "_", archive_url.split("/")[-1])[:80] or "body"
        fn = f"{h}_{name}"
        p = self.snapshots_dir / fn
        try:
            with self.lock:
                p.write_bytes(body_bytes)
                self.used_bytes += len(body_bytes)
        except Exception:
            return None
        return str(p)


class FindingsWriter:
    def __init__(self, path, enabled=False):
        self.path = Path(path)
        self.enabled = enabled
        self.lock = threading.Lock()
        if enabled:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

    def write(self, finding):
        if not self.enabled:
            return
        try:
            line = json.dumps(finding, default=str)
        except Exception:
            return
        with self.lock:
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass


RAW_SINK = {"sink": None, "lock": threading.Lock()}
FINDINGS_WRITER = {"writer": None, "lock": threading.Lock()}


def _bind_raw(out_dir, enabled):
    with RAW_SINK["lock"]:
        RAW_SINK["sink"] = RawSink(out_dir, enabled=enabled)


def _bind_findings(path, enabled):
    with FINDINGS_WRITER["lock"]:
        FINDINGS_WRITER["writer"] = FindingsWriter(path, enabled=enabled)


def _raw_write(finding):
    with FINDINGS_WRITER["lock"]:
        w = FINDINGS_WRITER["writer"]
    if w:
        w.write(finding)


def _raw_save_body(archive_url, body_bytes, mimetype=""):
    with RAW_SINK["lock"]:
        s = RAW_SINK["sink"]
    if s:
        return s.save_body(archive_url, body_bytes, mimetype)
    return None


def _unbind_raw():
    with RAW_SINK["lock"]:
        RAW_SINK["sink"] = None
    with FINDINGS_WRITER["lock"]:
        FINDINGS_WRITER["writer"] = None


IGNORE_PATTERNS = set()
_IGNORE_LOCK = threading.Lock()


def _ensure_ignore_file(out_dir):
    p = Path(out_dir) / ".stratascan_ignore"
    if not p.exists():
        try:
            p.write_text(IGNORE_DEFAULTS, encoding="utf-8")
            T("CRED", f"wrote default ignore file -> {p}")
        except Exception:
            pass
    return p


def _load_ignore(out_dir):
    global IGNORE_PATTERNS
    p = _ensure_ignore_file(out_dir)
    pats = set()
    try:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    pats.add(line.lower())
    except Exception:
        pass
    with _IGNORE_LOCK:
        IGNORE_PATTERNS = pats
    T("CRED", f"loaded {len(pats)} ignore patterns")


def _is_ignored(value):
    vl = str(value).lower()
    with _IGNORE_LOCK:
        for pat in IGNORE_PATTERNS:
            if pat in vl:
                return True
    return False


def _entropy(s):
    if not s:
        return 0.0
    freq = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _looks_like_real_secret(value, key_name=""):
    v = str(value).strip()
    if len(v) < 8:
        return False
    if v.lower() in SECRET_FALSE_POSITIVES:
        return False
    if _is_ignored(v):
        return False
    if CONTEXT_ALLOWLIST.search(key_name):
        return False
    if v.count("_") > 4 or v.count("-") > 4:
        return False
    if v.isdigit():
        return False
    if v.isalpha() and len(set(v.lower())) <= 3:
        return False
    return _entropy(v) >= 3.2


def _extract_env_lines(text):
    out = {}
    for m in ENV_LINE_RE.finditer(text or ""):
        key, val = m.group(1), m.group(2).strip()
        if val.startswith("#"):
            continue
        val = val.strip("\"'")
        if not val or val.lower() in SECRET_FALSE_POSITIVES:
            continue
        if not SENSITIVE_KEY_RE.search(key):
            continue
        out[key] = val
    return out


def _extract_wp_config(text):
    out = {}
    for m in WP_CONST_RE.finditer(text or ""):
        key, val = m.group(1), m.group(2)
        if key in ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST",
                   "AUTH_KEY", "SECURE_AUTH_KEY", "LOGGED_IN_KEY",
                   "NONCE_KEY", "AUTH_SALT", "SECURE_AUTH_SALT",
                   "LOGGED_IN_SALT", "NONCE_SALT"):
            if val and len(val) >= 4:
                out[key] = val
    return out


def _extract_django_db(text):
    out = {}
    for m in DJANGO_DB_RE.finditer(text or ""):
        v = m.group(1)
        if v and len(v) >= 4 and v.lower() not in SECRET_FALSE_POSITIVES:
            out.setdefault("DATABASE_PASSWORD", []).append(v)
    return {k: sorted(set(v)) for k, v in out.items()}


def _extract_docker_env(text):
    out = {}
    for m in DOCKER_ENV_KEY_RE.finditer(text or ""):
        key, val = m.group(1), m.group(2).strip()
        if not SENSITIVE_KEY_RE.search(key):
            continue
        if not val or val.lower() in SECRET_FALSE_POSITIVES:
            continue
        out[key] = val
    return out


def _walk_json_for_secrets(obj, path="", depth=0, max_dict_keys=2000):
    out = {}
    if depth > 12:
        return out
    if isinstance(obj, dict):
        items = list(obj.items())[:max_dict_keys]
        for k, v in items:
            kpath = f"{path}.{k}" if path else str(k)
            if isinstance(v, (dict, list)):
                out.update(_walk_json_for_secrets(v, kpath, depth + 1, max_dict_keys))
            elif isinstance(v, str) and SENSITIVE_KEY_RE.search(str(k)):
                if _looks_like_real_secret(v, str(k)):
                    out.setdefault(str(k), []).append(v)
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:200]):
            out.update(_walk_json_for_secrets(item, f"{path}[{i}]", depth + 1, max_dict_keys))
    return {k: sorted(set(v))[:50] for k, v in out.items()}


def _extract_source_map_content(text, max_total_bytes=20 * 1024 * 1024):
    try:
        data = json.loads(text)
    except Exception:
        return []
    out = []
    sources = data.get("sources", []) or []
    contents = data.get("sourcesContent", []) or []
    used = 0
    for i, content in enumerate(contents):
        if not content:
            continue
        if used + len(content) > max_total_bytes:
            break
        used += len(content)
        name = sources[i] if i < len(sources) else f"source_{i}"
        out.append((name, content))
        if len(out) >= 200:
            break
    return out


def _extract_basic_auth_url(text):
    out = []
    for m in AUTH_BASIC_IN_URL_RE.finditer(text or ""):
        user, pwd = m.group(1), m.group(2)
        if len(pwd) >= 4 and pwd.lower() not in SECRET_FALSE_POSITIVES:
            out.append((user, pwd))
    return out


def _decode_jwt_claims(token):
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        raw = base64.urlsafe_b64decode(payload)
        return json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return {}


def _scan_atob_blobs(text):
    out = {}
    for rx in (ATOB_RE, BUFFER_FROM_B64_RE, UINT8_FROM_ATOB_RE):
        for m in rx.finditer(text or ""):
            blob = m.group(1)
            try:
                decoded = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=False).decode("utf-8", errors="ignore")
            except Exception:
                continue
            if len(decoded) < 16:
                continue
            hits = scan_secrets(decoded, source_label="[atob-decoded]", emit=False)
            for k, v in hits.items():
                out.setdefault(k, {"severity": v["severity"], "values": []})["values"].extend(v["values"])
    for k, v in out.items():
        v["values"] = sorted(set(v["values"]))[:50]
    return out


def _scan_url_params_for_creds(url):
    out = {}
    for m in URL_PARAM_SECRET_RE.finditer(url or ""):
        v = m.group(1)
        if _looks_like_real_secret(v):
            out.setdefault("url_param_secret", []).append({"url": url, "value": v})
    return out


def _scan_cookie_values(headers):
    out = {}
    for u, d in (headers or {}).items():
        h = {k.lower(): v for k, v in (d.get("headers") or {}).items()}
        raw = h.get("set-cookie", "")
        if not raw:
            continue
        for cookie in re.split(r',\s*(?=[A-Za-z_][A-Za-z0-9_\-]*=)', raw):
            if "=" not in cookie:
                continue
            name, _, value = cookie.partition("=")
            value = value.split(";")[0].strip()
            if len(value) >= 20 and JWT_PART_RE.match(value):
                claims = _decode_jwt_claims(value)
                if claims:
                    out.setdefault("jwt_in_cookie", []).append({
                        "url": u, "cookie": name.strip(), "claims": claims,
                    })
            elif len(value) >= 40 and _entropy(value) >= 3.5:
                out.setdefault("high_entropy_cookie", []).append({
                    "url": u, "cookie": name.strip(), "value": value[:100],
                })
    return out


def _scan_headers_for_secrets(headers):
    out = {}
    for u, d in (headers or {}).items():
        h = {k.lower(): v for k, v in (d.get("headers") or {}).items()}
        for k, v in h.items():
            if k.startswith("x-") and any(x in k for x in ("key", "token", "secret", "auth", "api", "amz-security", "goog-api", "storage")):
                if _looks_like_real_secret(v, k):
                    out.setdefault(f"header_{k}", []).append({"url": u, "value": str(v)[:200]})
            if k == "authorization" and str(v).lower().startswith("basic "):
                try:
                    raw = base64.b64decode(str(v).split(" ", 1)[1]).decode("utf-8", errors="ignore")
                    if ":" in raw:
                        out.setdefault("authorization_basic", []).append({"url": u, "creds": raw})
                except Exception:
                    pass
    return out


def _scan_stack_traces(text):
    out = []
    for m in STACK_TRACE_RE.finditer(text or ""):
        out.append(m.group(0)[:300])
    return out[:50]


def _parse_phpinfo_table(text):
    out = {}
    rows = re.findall(r'<tr>\s*<td class="e">([^<]+)</td>\s*<td class="v">([^<]*)</td>', text or "")
    for k, v in rows:
        k = k.strip()
        v = v.strip()
        if not k or not v:
            continue
        if SENSITIVE_KEY_RE.search(k) or k in ("DOCUMENT_ROOT", "SCRIPT_FILENAME", "PATH", "HTTP_HOST"):
            out[k] = v[:300]
    return out


def _scan_hashed_passwords(text):
    out = {}
    for name, rx in HASH_PATTERNS.items():
        matches = rx.findall(text or "")
        if matches:
            uniq = sorted(set(matches))[:20]
            out[name] = uniq
    return out


class RateLimiter:
    def __init__(self, rate=8.0, capacity=16):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last = time.time()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.time()
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens < 1:
                wait = (1 - self.tokens) / self.rate
                time.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= 1


_RATE_LIMITERS = {"web.archive.org": RateLimiter(rate=1.5, capacity=4)}
_RATE_LIMITERS_LOCK = threading.Lock()


def _rate_limit_for(url):
    host = urllib.parse.urlparse(url).netloc.split(":")[0]
    with _RATE_LIMITERS_LOCK:
        rl = _RATE_LIMITERS.get(host)
        if rl is None:
            rl = RateLimiter(rate=6.0, capacity=12)
            _RATE_LIMITERS[host] = rl
        return rl


class JsonlSink:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.buf = []
        self.buf_size = 0
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def write(self, kind, payload):
        try:
            line = json.dumps({"kind": kind, "ts": time.time(), "data": payload}, default=str)
        except Exception:
            return
        with self.lock:
            self.buf.append(line)
            self.buf_size += len(line)
            if self.buf_size >= 65536 or len(self.buf) >= 256:
                self._flush_locked()

    def _flush_locked(self):
        if not self.buf:
            return
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write("\n".join(self.buf) + "\n")
        except Exception:
            pass
        self.buf = []
        self.buf_size = 0

    def close(self):
        with self.lock:
            self._flush_locked()


JSONL_SINK = {"sink": None, "lock": threading.Lock()}


def _bind_jsonl(path):
    with JSONL_SINK["lock"]:
        old = JSONL_SINK["sink"]
        JSONL_SINK["sink"] = JsonlSink(path)
    if old:
        try:
            old.close()
        except Exception:
            pass


def _unbind_jsonl():
    with JSONL_SINK["lock"]:
        old = JSONL_SINK["sink"]
        JSONL_SINK["sink"] = None
    if old:
        try:
            old.close()
        except Exception:
            pass


def _ckpt(kind, payload):
    with JSONL_SINK["lock"]:
        s = JSONL_SINK["sink"]
    if s:
        s.write(kind, payload)


def normalize_domain(domain):
    if not domain:
        return domain
    d = domain.strip().lower()
    if "://" in d:
        parsed = urllib.parse.urlparse(d)
        d = parsed.netloc or parsed.path
    d = d.split("/")[0].split("?")[0].split("#")[0]
    if ":" in d:
        d = d.split(":")[0]
    d = d.strip(".")
    return d


def _is_transient_connection_error(err_str):
    s = (err_str or "").lower()
    markers = (
        "remote end closed",
        "connection reset",
        "connection aborted",
        "connectionrefused",
        "connection refused",
        "eof occurred",
        "broken pipe",
        "timed out",
        "timeout",
        "temporarily unavailable",
        "remote disconnected",
        "urlopen error",
        "ssl",
        "certificate",
        "handshake",
    )
    return any(m in s for m in markers)


def http_get(url, timeout=30, retries=3, return_headers=False, max_bytes=None):
    rl = _rate_limit_for(url)
    last_err = None
    for attempt in range(retries):
        if rl:
            rl.acquire()
        _maybe_jitter_sleep(url, reason="pre-request")
        ua = get_user_agent()
        opener, proxy = _current_opener()
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": ua,
                "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "identity",
                "Connection": "close",
            })
            with opener.open(req, timeout=timeout) as r:
                raw = r.read(max_bytes) if max_bytes else r.read()
                body = raw.decode("utf-8", errors="replace")
                T("HTTP", f"OK {getattr(r, 'status', '?')} {url[:140]} ({len(body)}b)" + (f" via {proxy}" if proxy else ""))
                _reset_backoff()
                if return_headers:
                    return body, dict(r.headers)
                return body
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} {e.reason}"
            T("HTTP", f"ERR {last_err} {url[:140]}" + (f" via {proxy}" if proxy else ""))
            if e.code in (429, 503):
                _bump_backoff()
                if proxy:
                    PROXIES.mark_failed(proxy)
                _maybe_jitter_sleep(url, reason=f"http-{e.code}")
                continue
            if e.code in (500, 502, 504):
                _bump_backoff()
                _maybe_jitter_sleep(url, reason=f"http-{e.code}")
                if attempt == retries - 1:
                    break
                continue
            if attempt == retries - 1:
                break
            time.sleep(1.5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
            last_err = f"{type(e).__name__}: {e}"
            if _is_transient_connection_error(last_err):
                _bump_backoff()
            if proxy:
                PROXIES.mark_failed(proxy)
            T("HTTP", f"ERR {last_err} {url[:140]}" + (f" via {proxy}" if proxy else ""))
            _maybe_jitter_sleep(url, reason="connection-fail")
            if attempt == retries - 1:
                break
            continue
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            if _is_transient_connection_error(last_err):
                _bump_backoff()
            if proxy:
                PROXIES.mark_failed(proxy)
            T("HTTP", f"ERR {last_err} {url[:140]}" + (f" via {proxy}" if proxy else ""))
            if attempt == retries - 1:
                break
            continue
    T("HTTP", f"GIVE UP {url[:140]} - {last_err}")
    if return_headers:
        return None, {}
    return None


def http_get_bytes(url, timeout=30, retries=2, max_bytes=25 * 1024 * 1024):
    c = cache()
    if c:
        cached_body = c.load_body(url)
        if cached_body is not None:
            T("CACHE", f"body HIT {url[:140]} ({len(cached_body)}b)", dedupe=True)
            return cached_body
    rl = _rate_limit_for(url)
    for attempt in range(retries):
        if rl:
            rl.acquire()
        _maybe_jitter_sleep(url, reason="pre-request-bytes")
        ua = get_user_agent()
        opener, proxy = _current_opener()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Connection": "close"})
            with opener.open(req, timeout=timeout) as r:
                body = r.read(max_bytes)
                if c and body:
                    c.store_body(url, body)
                _reset_backoff()
                return body
        except Exception as e:
            err_str = f"{type(e).__name__}: {e}"
            if _is_transient_connection_error(err_str):
                _bump_backoff()
            if proxy:
                PROXIES.mark_failed(proxy)
            _maybe_jitter_sleep(url, reason="bytes-fail")
            if attempt == retries - 1:
                return None
            continue
    return None


def http_get_json(url, timeout=20):
    rl = _rate_limit_for(url)
    if rl:
        rl.acquire()
    _maybe_jitter_sleep(url, reason="pre-request-json")
    ua = get_user_agent()
    opener, proxy = _current_opener()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json", "Connection": "close"})
        with opener.open(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
            _reset_backoff()
            return data
    except Exception as e:
        err_str = f"{type(e).__name__}: {e}"
        if _is_transient_connection_error(err_str):
            _bump_backoff()
        if proxy:
            PROXIES.mark_failed(proxy)
        return None


def http_head_full(url, timeout=10, retries=2):
    rl = _rate_limit_for(url)
    for attempt in range(retries):
        if rl:
            rl.acquire()
        _maybe_jitter_sleep(url, reason="pre-request-head")
        ua = get_user_agent()
        opener, proxy = _current_opener()
        try:
            req = urllib.request.Request(url, method="HEAD", headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "close",
            })
            with opener.open(req, timeout=timeout) as r:
                _reset_backoff()
                return r.status, dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers) if e.headers else {}
        except Exception as e:
            err_str = f"{type(e).__name__}: {e}"
            if _is_transient_connection_error(err_str):
                _bump_backoff()
            if proxy:
                PROXIES.mark_failed(proxy)
            _maybe_jitter_sleep(url, reason="head-fail")
            if attempt == retries - 1:
                return None, {}
            continue
    return None, {}


def http_get_range(url, bytes_range="0-1023", timeout=10):
    rl = _rate_limit_for(url)
    if rl:
        rl.acquire()
    _maybe_jitter_sleep(url, reason="pre-request-range")
    ua = get_user_agent()
    opener, proxy = _current_opener()
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": ua,
            "Range": f"bytes={bytes_range}",
            "Connection": "close",
        })
        with opener.open(req, timeout=timeout) as r:
            body = r.read()
            _reset_backoff()
            return r.status, dict(r.headers), body
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, dict(e.headers) if e.headers else {}, body
    except Exception as e:
        err_str = f"{type(e).__name__}: {e}"
        if _is_transient_connection_error(err_str):
            _bump_backoff()
        if proxy:
            PROXIES.mark_failed(proxy)
        return None, {}, b""


def cdx_query(params, timeout=120, follow_pagination=True, max_pages=20):
    base_params = dict(params)
    results = []
    resume_key = None
    page = 0
    while page < max_pages:
        p = dict(base_params)
        if follow_pagination:
            p["limit"] = p.get("limit", "10000")
            p.pop("collapse", None)
        if resume_key:
            p["resumeKey"] = resume_key
        url = CDX_URL + "?" + urllib.parse.urlencode(p)
        body = http_get(url, timeout=timeout)
        if body is None:
            T("CDX", f"request failed - {url[:200]}")
            break
        if not body.strip():
            T("CDX", f"empty response - {url[:200]}")
            break
        try:
            rows = json.loads(body)
        except json.JSONDecodeError:
            T("CDX", f"non-JSON reply: {body[:200]!r}")
            break
        if not rows or len(rows) < 2:
            T("CDX", f"CDX returned {len(rows)} row(s) - {url[:200]}")
            break
        header = rows[0]
        page_rows = [dict(zip(header, row)) for row in rows[1:]]
        results.extend(page_rows)
        c = cache()
        if c:
            for r in page_rows:
                c.store_snapshot(r)
        for r in page_rows:
            _ckpt("snapshot", r)
        if not follow_pagination:
            break
        if len(page_rows) == 0:
            break
        try:
            if rows[-1] and isinstance(rows[-1], list) and len(rows[-1]) == 1:
                resume_key = rows[-1][0]
            else:
                break
        except Exception:
            break
        page += 1
    return results


def fetch_all_snapshots(domain, date_from=None, date_to=None, limit=None):
    domain = normalize_domain(domain)
    fields = "urlkey,timestamp,original,statuscode,mimetype,digest,length,redirect"
    all_snaps = []
    targets = [domain]
    if not domain.startswith("www."):
        targets.append("www." + domain)
    for target in targets:
        params = {"url": target, "matchType": "domain", "output": "json", "fl": fields}
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        if limit:
            params["limit"] = str(limit)
        T("PHASE", f"CDX index fetch for {target}")
        snaps = cdx_query(params, timeout=90, follow_pagination=False)
        T("CDX", f"{target} -> {len(snaps)} snapshot(s)")
        all_snaps.extend(snaps)
    seen = set()
    unique = []
    for s in all_snaps:
        key = (s.get("timestamp"), s.get("original"), s.get("digest"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    return unique


def fetch_cdx_timeline(url, date_from=None, date_to=None):
    params = {
        "url": url, "matchType": "exact", "output": "json",
        "fl": "urlkey,timestamp,original,statuscode,mimetype,digest,length,redirect",
    }
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    return cdx_query(params, timeout=60, follow_pagination=False)


def fetch_cdx_full_fields(domain, date_from=None, date_to=None, limit=None):
    fields = "urlkey,timestamp,original,mimetype,statuscode,digest,length,offset,filename,redirect"
    params = {"url": domain, "matchType": "domain", "output": "json", "fl": fields}
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    if limit:
        params["limit"] = str(limit)
    return cdx_query(params, timeout=90, follow_pagination=False)


def fetch_cdx_filtered(domain, filters, date_from=None, date_to=None, limit=None):
    params = {
        "url": domain, "matchType": "domain", "output": "json",
        "fl": "timestamp,original,statuscode,mimetype,digest,length,redirect",
    }
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    if limit:
        params["limit"] = str(limit)
    if filters:
        params["filter"] = filters
    return cdx_query(params, timeout=90, follow_pagination=False)


def fetch_cdx_prefix(prefix, date_from=None, date_to=None, limit=None):
    params = {
        "url": prefix, "matchType": "prefix", "output": "json",
        "fl": "timestamp,original,statuscode,mimetype,digest,length",
    }
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    if limit:
        params["limit"] = str(limit)
    return cdx_query(params, timeout=90, follow_pagination=False)


def fetch_calendar_captures(domain):
    url = CALENDAR_URL + "?" + urllib.parse.urlencode({"url": domain, "output": "json"})
    body = http_get(url, timeout=30)
    if not body:
        return {}
    try:
        return json.loads(body)
    except Exception:
        return {}


def fetch_anchor_search(query):
    url = ANCHOR_URL + "?" + urllib.parse.urlencode({"q": query})
    body = http_get(url, timeout=30)
    if not body:
        return []
    try:
        return json.loads(body)
    except Exception:
        return []


def fetch_timemap_json(domain):
    url = TIMEMAP_JSON_URL + "?" + urllib.parse.urlencode({"url": domain})
    body = http_get(url, timeout=30)
    if not body:
        return {}
    try:
        return json.loads(body)
    except Exception:
        return {}


def fetch_memento_aggregator(domain):
    url = MEMENTO_AGG + domain
    body = http_get(url, timeout=30)
    if not body:
        return []
    entries = []
    for line in body.splitlines():
        if line.startswith("<"):
            m = re.match(r'<([^>]+)>;\s*rel="([^"]+)";\s*datetime="([^"]+)"', line)
            if m:
                entries.append({"url": m.group(1), "rel": m.group(2), "datetime": m.group(3)})
    return entries


def fetch_archive_today(domain):
    url = ARCHIVE_TODAY + domain
    status, headers = http_head_full(url, timeout=10)
    location = headers.get("Location") if headers else None
    return {"status": status, "url": url, "redirect": location}


def fetch_common_crawl(domain):
    url = COMMON_CRAWL_INDEX + "collinfo.json"
    body = http_get(url, timeout=20)
    if not body:
        return {}
    try:
        colls = json.loads(body)
    except Exception:
        return {}
    if not colls:
        return {}
    latest = colls[0].get("id") if isinstance(colls[0], dict) else None
    if not latest:
        return {}
    query_url = f"{COMMON_CRAWL_INDEX}{latest}-index?url={urllib.parse.quote(domain)}&output=json"
    result_body = http_get(query_url, timeout=60)
    if not result_body:
        return {"latest_crawl": latest, "results": []}
    results = []
    for line in result_body.strip().splitlines():
        try:
            results.append(json.loads(line))
        except Exception:
            continue
    return {"latest_crawl": latest, "results": results[:500]}


def fetch_crt_sh(domain):
    url = CRT_SH_URL + "?" + urllib.parse.urlencode({"q": "%." + domain, "output": "json"})
    body = http_get(url, timeout=60)
    if not body:
        return []
    try:
        rows = json.loads(body)
    except Exception:
        return []
    names = set()
    serials = set()
    for r in rows:
        sn = r.get("serial_number")
        if sn in serials:
            continue
        serials.add(sn)
        for n in (r.get("name_value") or "").split("\n"):
            n = n.strip().lower()
            if n and n.endswith(domain) and "*" not in n:
                names.add(n)
    return sorted(names)


def fetch_rdap(domain):
    url = f"{RDAP_URL}{domain}"
    data = http_get_json(url, timeout=20)
    if not data:
        return {}
    events = {e.get("eventAction"): e.get("eventDate") for e in data.get("events", [])}
    entities = []
    for ent in data.get("entities", []):
        roles = ent.get("roles", [])
        vcard = ent.get("vcardArray", [None, []])[1] if ent.get("vcardArray") else []
        name = email = None
        for item in vcard:
            if item[0] == "fn":
                name = item[3]
            elif item[0] == "email":
                email = item[3]
        entities.append({"roles": roles, "name": name, "email": email})
    return {
        "handle": data.get("handle"),
        "ldhName": data.get("ldhName"),
        "status": data.get("status", []),
        "events": events,
        "nameservers": [ns.get("ldhName") for ns in data.get("nameservers", [])],
        "entities": entities,
    }


def fetch_availability(domain):
    url = AVAILABILITY_URL + "?" + urllib.parse.urlencode({"url": domain})
    body = http_get(url, timeout=20)
    if not body:
        return {}
    try:
        return json.loads(body)
    except Exception:
        return {}


def fetch_sparkline(domain):
    url = SPARKLINE_URL + "?" + urllib.parse.urlencode({"url": domain, "output": "json"})
    body = http_get(url, timeout=30)
    if not body:
        return {}
    try:
        return json.loads(body)
    except Exception:
        return {}


def fetch_timemap(domain):
    url = TIMEMAP_URL + "/" + domain
    body = http_get(url, timeout=30)
    if not body:
        return []
    entries = []
    for line in body.splitlines():
        if line.startswith("<"):
            m = re.match(r'<([^>]+)>;\s*rel="([^"]+)";\s*datetime="([^"]+)"', line)
            if m:
                entries.append({"url": m.group(1), "rel": m.group(2), "datetime": m.group(3)})
    return entries


def wayback_snapshot_url(timestamp, original):
    return f"https://web.archive.org/web/{timestamp}/{original}"


def wayback_raw_url(timestamp, original):
    return f"https://web.archive.org/web/{timestamp}id_/{original}"


def _html_unescape(s):
    if s is None:
        return None
    try:
        return html_module.unescape(s)
    except Exception:
        return s


def _find_match_context(text, start, end, window=100):
    before = text[max(0, start - window):start]
    after = text[end:end + window]
    try:
        return (before.replace("\x00", ""), after.replace("\x00", ""))
    except Exception:
        return (str(before), str(after))


def scan_secrets(text, source_label="", emit=False, source_url="", decoded_from="raw", ts="", domain=""):
    if not text:
        return {}
    found = {}
    c = cache()
    for name, (rx, sev, validator) in COMPILED_SECRETS.items():
        try:
            matches = list(rx.finditer(text))
        except Exception:
            continue
        flat = []
        seen_vals = set()
        for m in matches:
            v = m.group(0)
            if not v:
                continue
            v = str(v).strip()
            if not _looks_like_real_secret(v, name):
                continue
            if v in seen_vals:
                continue
            seen_vals.add(v)
            ent = _entropy(v)
            before, after = _find_match_context(text, m.start(), m.end(), window=100)
            record = {
                "pattern": name,
                "severity": sev,
                "value": v,
                "length": len(v),
                "entropy": round(ent, 4),
                "source": source_label,
                "source_url": source_url,
                "snapshot_timestamp": ts,
                "decoded_from": decoded_from,
                "match_start": m.start(),
                "match_end": m.end(),
                "context_before": before,
                "context_after": after,
            }
            _raw_write(record)
            if c and domain:
                c.store_finding(domain, name, v, sev, source_label, source_url, ts, decoded_from, round(ent, 4), len(v), (before + "|" + after)[:400])
            flat.append(v)
        if flat:
            uniq = sorted(set(flat))[:50]
            found[name] = {"severity": sev, "values": uniq, "source": source_url or source_label}
            for v in uniq:
                _ckpt("secret", {"name": name, "severity": sev, "value": v, "source": source_url or source_label})
            if emit:
                T("SECRET", f"!! [{sev}] {name} ({len(uniq)}) in {source_label or 'source'}")
    return found


def try_decode_and_scan(text, source_label="", source_url=""):
    extras = {}
    if not text:
        return extras
    for m in re.finditer(r'\b[A-Za-z0-9+/]{40,}={0,2}\b', text):
        blob = m.group(0)
        try:
            raw = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=False)
            decoded = raw.decode("utf-8", errors="ignore")
        except Exception:
            continue
        if len(decoded) < 20:
            continue
        hits = scan_secrets(decoded, source_label + " [base64]", source_url=source_url, decoded_from="base64")
        for k, v in hits.items():
            extras.setdefault("base64_" + k, {"severity": v["severity"], "values": [], "source": source_url or source_label})["values"].extend(v["values"])
        nested = re.search(r'[A-Za-z0-9+/]{60,}={0,2}', decoded)
        if nested:
            try:
                raw2 = base64.b64decode(nested.group(0) + "=" * (-len(nested.group(0)) % 4), validate=False)
                dec2 = raw2.decode("utf-8", errors="ignore")
                hits2 = scan_secrets(dec2, source_label + " [base64x2]", source_url=source_url, decoded_from="base64x2")
                for k, v in hits2.items():
                    extras.setdefault("base64x2_" + k, {"severity": v["severity"], "values": [], "source": source_url or source_label})["values"].extend(v["values"])
            except Exception:
                pass
    for m in re.finditer(r'\b(?:[0-9a-fA-F]{2}){20,}\b', text):
        blob = m.group(0)
        try:
            decoded = bytes.fromhex(blob).decode("utf-8", errors="ignore")
        except Exception:
            continue
        hits = scan_secrets(decoded, source_label + " [hex]", source_url=source_url, decoded_from="hex")
        for k, v in hits.items():
            extras.setdefault("hex_" + k, {"severity": v["severity"], "values": [], "source": source_url or source_label})["values"].extend(v["values"])
    for k, v in _scan_atob_blobs(text).items():
        extras.setdefault("atob_" + k, {"severity": v["severity"], "values": v["values"], "source": source_url or source_label})
    for k, v in _scan_hashed_passwords(text).items():
        extras.setdefault("hash_" + k, {"severity": "high", "values": v, "source": source_url or source_label})
    for k, v in extras.items():
        v["values"] = sorted(set(v["values"]))[:50]
    return extras


def _structural_secret_extract(text, source_url=""):
    out = {}
    env = _extract_env_lines(text)
    if env:
        out["env_lines"] = {"severity": "critical", "values": [f"{k}={v[:60]}" for k, v in env.items()]}
    wp = _extract_wp_config(text)
    if wp:
        out["wp_config"] = {"severity": "critical", "values": [f"{k}={v[:60]}" for k, v in wp.items()]}
    dj = _extract_django_db(text)
    for k, v in dj.items():
        out[f"django_{k.lower()}"] = {"severity": "critical", "values": v}
    docker_env = _extract_docker_env(text)
    if docker_env:
        out["docker_env"] = {"severity": "critical", "values": [f"{k}={v[:60]}" for k, v in docker_env.items()]}
    if text.strip().startswith("{"):
        try:
            data = json.loads(text)
            walk = _walk_json_for_secrets(data)
            for k, v in walk.items():
                out[f"json_{k}"] = {"severity": "high", "values": v}
        except Exception:
            pass
    return out


def _strip_html(html_text):
    if not html_text:
        return ""
    s = re.sub(r'<script[^>]*>.*?</script>', ' ', html_text, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r'<style[^>]*>.*?</style>', ' ', s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = html_module.unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


def extract_hidden_elements(html):
    hidden = []
    for m in re.finditer(r'<([a-z][a-z0-9]*)\b([^>]*)>', html, re.IGNORECASE):
        tag = m.group(1)
        attrs = m.group(2)
        style_m = re.search(r'style=["\']([^"\']*)["\']', attrs, re.I)
        aria_m = re.search(r'aria-hidden=["\']true["\']', attrs, re.I)
        if not (style_m or aria_m):
            continue
        style = style_m.group(1) if style_m else "aria-hidden=true"
        if not (HIDDEN_STYLE_RE.search(style) or WHITE_ON_WHITE_RE.search(style) or aria_m):
            continue
        close_pat = re.compile(rf'</{re.escape(tag)}\s*>', re.IGNORECASE)
        rest = html[m.end():m.end() + 8000]
        cm = close_pat.search(rest)
        if not cm:
            continue
        txt = _strip_html(rest[:cm.start()])[:300]
        if txt:
            hidden.append({"tag": tag, "style": style[:200], "text": txt})
    for m in INPUT_RE.finditer(html):
        attrs = m.group(1)
        if re.search(r'type=["\']hidden["\']', attrs, re.I):
            nm = INPUT_NAME_RE.search(attrs)
            val = re.search(r'value=["\']([^"\']*)["\']', attrs)
            if nm and val and val.group(1):
                hidden.append({"tag": "input[hidden]", "name": nm.group(1), "value": val.group(1)[:300]})
    return hidden[:100]


def extract_comments_with_context(html, window=80):
    out = []
    for m in HTML_COMMENT_RE.finditer(html):
        start, end = m.start(), m.end()
        out.append({
            "comment": m.group(1).strip()[:500],
            "before": html[max(0, start - window):start][-window:],
            "after": html[end:end + window],
        })
    return out[:200]


def parse_csp_header(csp):
    if not csp:
        return {}
    directives = {}
    for part in csp.split(";"):
        part = part.strip()
        if not part:
            continue
        bits = part.split()
        if bits:
            directives[bits[0]] = bits[1:]
    return directives


def deobfuscate_js(js_text):
    hits = {}
    if not js_text:
        return hits
    for m in re.finditer(r'["\']([^"\']+)["\']', js_text):
        s = m.group(1)
        if len(s) >= 4 and re.match(r'^https?://', s):
            hits.setdefault("urls", set()).add(s)
        elif s.startswith("/") and len(s) >= 4:
            hits.setdefault("paths", set()).add(s)
    for m in re.finditer(r'atob\(\s*["\']([A-Za-z0-9+/=]{20,})["\']', js_text):
        try:
            decoded = base64.b64decode(m.group(1) + "=" * (-len(m.group(1)) % 4)).decode("utf-8", errors="ignore")
            hits.setdefault("atob_decoded", set()).add(decoded[:200])
        except Exception:
            pass
    return {k: sorted(v)[:500] for k, v in hits.items()}


def fetch_archived_headers(timestamp, original, timeout=15):
    url = f"https://web.archive.org/web/{timestamp}if_/{original}"
    try:
        body, headers = http_get(url, timeout=timeout, return_headers=True)
        if headers:
            orig = {}
            for k, v in headers.items():
                kl = k.lower()
                if kl.startswith("x-archive-orig-") or kl in ("x-archive-src", "x-archive-wayback-runtime",
                                                               "x-archive-guessed-content-type", "x-archive-guessed-encoding",
                                                               "x-archive-served-by", "x-archive-cache"):
                    orig[kl] = str(v)
            return orig
    except Exception:
        return {}
    return {}


def diff_archived_headers(by_url, workers=6, limit=50):
    out = {}
    targets = []
    for u, caps in by_url.items():
        if len(caps) < 2:
            continue
        targets.append((u, caps[0]["timestamp"], caps[-1]["timestamp"]))
        if len(targets) >= limit:
            break

    def work(item):
        u, t1, t2 = item
        h1 = fetch_archived_headers(t1, u)
        h2 = fetch_archived_headers(t2, u)
        diffs = {}
        for k in set(h1) | set(h2):
            v1, v2 = h1.get(k, ""), h2.get(k, "")
            if v1 != v2:
                diffs[k] = {"first": v1, "last": v2}
        return u, diffs

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, t) for t in targets]
        for fut in concurrent.futures.as_completed(futures):
            try:
                u, diffs = fut.result()
            except Exception:
                continue
            if diffs:
                out[u] = diffs
    return out


def fetch_snapshot_content(timestamp, original, timeout=20, max_bytes=5 * 1024 * 1024):
    raw = wayback_raw_url(timestamp, original)
    body = http_get_bytes(raw, timeout=timeout, max_bytes=max_bytes)
    if body:
        _raw_save_body(raw, body)
    return body.decode("utf-8", errors="replace") if body else None


def enrich_with_content(by_url, sample_per_url="latest", workers=6, only_urls=None):
    targets = []
    for u, caps in by_url.items():
        if only_urls is not None and u not in only_urls:
            continue
        html_caps = [c for c in caps if "html" in c.get("mimetype", "")]
        if not html_caps:
            continue
        for c in ([html_caps[-1]] if sample_per_url == "latest" else html_caps[:1]):
            targets.append((u, c))

    T("PHASE", f"content extraction for {len(targets)} snapshot(s)")
    results = {}

    def work(item):
        u, cap = item
        html = fetch_snapshot_content(cap["timestamp"], u)
        return u, cap["timestamp"], extract_page_intel(html, u) if html else {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, t) for t in targets]
        for fut in concurrent.futures.as_completed(futures):
            try:
                u, ts, intel = fut.result()
            except Exception:
                continue
            results.setdefault(u, {})[ts] = intel
    return results


def extract_page_intel(html, base_url):
    if not html:
        return {}
    intel = {}
    m = TITLE_RE.search(html)
    intel["title"] = _html_unescape(re.sub(r"\s+", " ", m.group(1)).strip()) if m else None
    m = LANG_RE.search(html)
    intel["lang"] = m.group(1) if m else None
    m = META_GEN_RE.search(html)
    intel["generator"] = _html_unescape(m.group(1)) if m else None
    m = COPYRIGHT_RE.search(html)
    intel["copyright_year"] = m.group(1) if m else None
    m = CANONICAL_RE.search(html)
    intel["canonical"] = urllib.parse.urljoin(base_url, m.group(1)) if m else None
    m = ROBOTS_META_RE.search(html)
    intel["robots_meta"] = m.group(1) if m else None
    m = BASE_HREF_RE.search(html)
    intel["base_href"] = m.group(1) if m else None
    m = META_REFRESH_RE.search(html)
    intel["meta_refresh"] = m.group(1) if m else None

    meta_map = {}
    for tag in META_RE.findall(html):
        nm = META_NAME_RE.search(tag)
        ct = META_CONTENT_RE.search(tag)
        if nm:
            meta_map.setdefault(nm.group(1).lower(), []).append(ct.group(1) if ct else "")
    intel["all_meta"] = {k: v[:5] for k, v in list(meta_map.items())[:40]}
    intel["og_tags"] = dict(OG_RE.findall(html))
    intel["twitter_card"] = dict(TWITTER_CARD_RE.findall(html))

    headings = []
    for level, text in H_TAG_RE.findall(html):
        clean = re.sub(r'<[^>]+>', '', text)
        clean = _html_unescape(re.sub(r'\s+', ' ', clean).strip())
        if clean:
            headings.append({"level": int(level), "text": clean[:200]})
    intel["headings"] = headings[:50]

    intel["emails"] = sorted(set(EMAIL_RE.findall(html)))[:100]
    text_only = _strip_html(html)
    intel["phones"] = sorted(set(PHONE_RE.findall(text_only) + PHONE_INTL_RE.findall(text_only)))[:50]
    intel["social_links"] = sorted(set(SOCIAL_RE.findall(html)))[:100]

    favm = FAVICON_RE.search(html)
    intel["favicon"] = urllib.parse.urljoin(base_url, favm.group(1)) if favm else None

    links = LINK_RE.findall(html)
    internal, external = [], []
    domain_root = urllib.parse.urlparse(base_url).netloc
    for l in links:
        if l.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        full = urllib.parse.urljoin(base_url, l)
        if domain_root in urllib.parse.urlparse(full).netloc:
            internal.append(full)
        else:
            external.append(full)
    intel["internal_links"] = sorted(set(internal))[:500]
    intel["external_links"] = sorted(set(external))[:500]

    intel["script_srcs"] = sorted(set(urllib.parse.urljoin(base_url, s) for s in SCRIPT_SRC_RE.findall(html)))[:200]
    intel["stylesheet_srcs"] = sorted(set(urllib.parse.urljoin(base_url, s) for s in STYLESHEET_RE.findall(html)))[:200]

    inline_scripts = INLINE_SCRIPT_RE.findall(html)
    intel["inline_script_count"] = len(inline_scripts)
    intel["inline_style_count"] = len(INLINE_STYLE_RE.findall(html))

    intel["image_srcs"] = sorted(set(urllib.parse.urljoin(base_url, i) for i in IMG_SRC_RE.findall(html)))[:200]
    intel["iframe_srcs"] = sorted(set(urllib.parse.urljoin(base_url, i) for i in IFRAME_SRC_RE.findall(html)))[:100]

    forms = []
    for attrs, body in FORM_RE.findall(html):
        action_m = FORM_ACTION_RE.search(attrs)
        action = action_m.group(1) if action_m else ""
        inputs = []
        for inp_attrs in INPUT_RE.findall(body):
            nm = INPUT_NAME_RE.search(inp_attrs)
            tp = INPUT_TYPE_RE.search(inp_attrs)
            inputs.append({"name": nm.group(1) if nm else None, "type": tp.group(1) if tp else "text"})
        meth = re.search(r'method=["\']([^"\']+)["\']', attrs, re.I)
        forms.append({
            "action": urllib.parse.urljoin(base_url, action) if action else base_url,
            "method": meth.group(1) if meth else "get",
            "inputs": inputs[:30],
        })
    intel["forms"] = forms[:20]

    login_forms = []
    for f in forms:
        action = (f.get("action") or "").lower()
        has_pw = any((i.get("type") or "").lower() == "password" for i in f.get("inputs", []))
        if has_pw or any(x in action for x in ("login", "signin", "auth", "session", "admin")):
            login_forms.append(f)
    intel["login_forms"] = login_forms[:20]

    api_hits = re.findall(r'["\'](/api/[^"\']+|/v[0-9]+/[^"\']+|https?://[^"\']*api[^"\']*)["\']', html)
    intel["possible_api_endpoints"] = sorted(set(api_hits))[:200]
    intel["graphql_endpoints"] = sorted(set(re.findall(r'["\'](/graphql|/gql|/query)["\']', html)))[:20]

    cms_hits = []
    for cms, patterns in CMS_SIGNATURES.items():
        if any(re.search(p, html, re.IGNORECASE) for p in patterns):
            cms_hits.append(cms)
    intel["cms_signatures"] = cms_hits

    intel["google_analytics_ids"] = sorted(set(GA_RE.findall(html)))[:20]
    intel["google_analytics4_ids"] = sorted(set(GA4_RE.findall(html)))[:20]
    intel["gtm_ids"] = sorted(set(GTM_RE.findall(html)))[:20]
    intel["facebook_pixel_ids"] = sorted(set(FB_PIXEL_RE.findall(html)))[:20]
    intel["hotjar_ids"] = sorted(set(HOTJAR_RE.findall(html)))[:20]
    intel["segment_write_keys"] = sorted(set(SEGMENT_RE.findall(html)))[:20]
    intel["mixpanel_tokens"] = sorted(set(MIXPANEL_RE.findall(html)))[:20]
    intel["matomo_site_ids"] = sorted(set(MATOMO_RE.findall(html)))[:20]
    intel["adsense_ids"] = sorted(set(ADSENSE_RE.findall(html)))[:20]
    intel["doubleclick_ids"] = sorted(set(DOUBLECLICK_RE.findall(html)))[:20]
    intel["clarity_ids"] = sorted(set(CLARITY_RE.findall(html)))[:20]
    intel["fullstory_ids"] = sorted(set(FULLSTORY_RE.findall(html)))[:20]
    intel["plausible_domains"] = sorted(set(PLAUSIBLE_RE.findall(html)))[:20]
    intel["fathom_ids"] = sorted(set(FATHOM_ID_RE.findall(html)))[:20]
    intel["amplitude_keys"] = sorted(set(AMPLITUDE_RE.findall(html)))[:20]
    intel["heap_ids"] = sorted(set(HEAP_RE.findall(html)))[:20]
    intel["pendo_ids"] = sorted(set(PENDO_RE.findall(html)))[:20]
    intel["logrocket_ids"] = sorted(set(LOGROCKET_RE.findall(html)))[:20]
    intel["intercom_ids"] = sorted(set(INTERCOM_RE.findall(html)))[:20]
    intel["drift_ids"] = sorted(set(DRIFT_RE.findall(html)))[:20]
    intel["zendesk_ids"] = sorted(set(ZENDESK_RE.findall(html)))[:20]
    intel["crisp_ids"] = sorted(set(CRISP_RE.findall(html)))[:20]
    intel["tawk_ids"] = sorted(set(TAWK_RE.findall(html)))[:20]
    intel["livechat_licenses"] = sorted(set(LIVECHAT_RE.findall(html)))[:20]
    intel["hubspot_portals"] = sorted(set(HUBSPOT_RE.findall(html)))[:20]
    intel["marketo_ids"] = sorted(set(MARKETO_RE.findall(html)))[:20]
    intel["pardot_ids"] = sorted(set(PARDOT_RE.findall(html)))[:20]
    intel["klaviyo_ids"] = sorted(set(KLAVIYO_RE.findall(html)))[:20]
    intel["mailchimp_list_ids"] = sorted(set(MAILCHIMP_RE.findall(html)))[:20]
    intel["activecampaign_ids"] = sorted(set(ACTIVECAMPAIGN_RE.findall(html)))[:20]
    intel["convertkit_ids"] = sorted(set(CONVERTKIT_RE.findall(html)))[:20]
    intel["drip_ids"] = sorted(set(DRIP_RE.findall(html)))[:20]
    intel["sendinblue_ids"] = sorted(set(SENDINBLUE_RE.findall(html)))[:20]
    intel["customerio_ids"] = sorted(set(CUSTOMERIO_RE.findall(html)))[:20]
    intel["iterable_ids"] = sorted(set(ITERABLE_RE.findall(html)))[:20]
    intel["braze_ids"] = sorted(set(BRAZE_RE.findall(html)))[:20]
    intel["onesignal_ids"] = sorted(set(ONESIGNAL_RE.findall(html)))[:20]
    intel["pusher_keys"] = sorted(set(PUSHER_RE.findall(html)))[:20]
    intel["ably_keys"] = sorted(set(ABLY_RE.findall(html)))[:20]
    intel["pubnub_keys"] = sorted(set(PUBSUB_RE.findall(html)))[:20]
    intel["agora_app_ids"] = sorted(set(AGORA_RE.findall(html)))[:20]
    intel["paypal_client_ids"] = sorted(set(PAYPAL_CLIENT_RE.findall(html)))[:20]
    intel["braintree_keys"] = sorted(set(BRAINTREE_RE.findall(html)))[:20]
    intel["square_app_ids"] = sorted(set(SQUARE_APP_RE.findall(html)))[:20]
    intel["recurly_public_keys"] = sorted(set(RECURLY_RE.findall(html)))[:20]
    intel["chargebee_sites"] = sorted(set(CHARGEBEE_RE.findall(html)))[:20]
    intel["paddle_vendor_ids"] = sorted(set(PADDLE_RE.findall(html)))[:20]
    intel["lemon_squeezy_ids"] = sorted(set(LEMON_RE.findall(html)))[:20]
    intel["gumroad_product_ids"] = sorted(set(GUMROAD_RE.findall(html)))[:20]

    secrets = scan_secrets(html, source_label=base_url, source_url=base_url)
    secrets2 = scan_secrets(text_only, source_label=base_url + " [text]", source_url=base_url)
    for k, v in secrets2.items():
        if k in secrets:
            secrets[k]["values"] = sorted(set(secrets[k]["values"]) | set(v["values"]))[:50]
        else:
            secrets[k] = v
    decoded = try_decode_and_scan(html, source_label=base_url, source_url=base_url)
    for k, v in decoded.items():
        if k in secrets:
            secrets[k]["values"] = sorted(set(secrets[k]["values"]) | set(v["values"]))[:50]
        else:
            secrets[k] = v
    structural = _structural_secret_extract(html, source_url=base_url)
    for k, v in structural.items():
        if k in secrets:
            secrets[k]["values"] = sorted(set(secrets[k]["values"]) | set(v["values"]))[:50]
        else:
            secrets[k] = v
    hashes = _scan_hashed_passwords(html)
    for k, v in hashes.items():
        key = f"hash_{k}"
        if key in secrets:
            secrets[key]["values"] = sorted(set(secrets[key]["values"]) | set(v))[:50]
        else:
            secrets[key] = {"severity": "high", "values": v, "source": base_url}
    intel["secrets"] = secrets

    intel["hidden_elements"] = extract_hidden_elements(html)
    comments = extract_comments_with_context(html)
    intel["html_comments"] = [c["comment"][:300] for c in comments[:30]]
    intel["html_comments_ctx"] = comments[:30]
    intel["sourcemap_refs"] = sorted(set(SOURCE_MAP_URL_RE.findall(html)))[:50]

    intel["css_comments"] = [c.strip()[:300] for c in CSS_COMMENT_RE.findall(html) if c.strip()][:50]
    intel["js_line_comments"] = [c.strip()[:300] for c in JS_LINE_COMMENT_RE.findall(html) if c.strip()][:50]
    intel["js_block_comments"] = [c.strip()[:300] for c in JS_BLOCK_COMMENT_RE.findall(html) if c.strip()][:50]

    data_attrs = {}
    for k, v in DATA_ATTR_RE.findall(html):
        data_attrs.setdefault(k, []).append(v[:200])
    intel["data_attributes"] = {k: v[:10] for k, v in list(data_attrs.items())[:30]}

    intel["aria_labels"] = sorted(set(ARIA_LABEL_RE.findall(html)))[:50]
    intel["title_attrs"] = sorted(set(TITLE_ATTR_RE.findall(html)))[:50]
    intel["img_alt_text"] = sorted(set(IMG_ALT_RE.findall(html)))[:100]
    intel["placeholders"] = sorted(set(INPUT_PLACEHOLDER_RE.findall(html)))[:50]

    for script in inline_scripts[:20]:
        m_state = INITIAL_STATE_RE.search(script)
        if m_state:
            intel["initial_state"] = m_state.group(1)[:5000]
            walk = _walk_json_for_secrets(m_state.group(1))
            if walk:
                intel["initial_state_secrets"] = walk
            break
    m = NEXT_DATA_RE.search(html)
    if m:
        intel["next_data"] = m.group(1)[:5000]
        try:
            j = json.loads(m.group(1))
            walk = _walk_json_for_secrets(j)
            if walk:
                intel["next_data_secrets"] = walk
        except Exception:
            pass
    m = NUXT_DATA_RE.search(html)
    if m:
        intel["nuxt_data"] = m.group(1)[:5000]

    data_uris = DATA_URI_RE.findall(html)
    intel["data_uri_count"] = len(data_uris)
    intel["data_uri_types"] = list(set(t for t, _ in data_uris))[:20]

    intel["nonces"] = sorted(set(NONCE_RE.findall(html)))[:20]
    pingbacks = PINGBACK_LINK_RE.findall(html)
    intel["pingback_links"] = [{"rel": r, "href": urllib.parse.urljoin(base_url, h)} for r, h in pingbacks][:20]
    preconnects = PRECONNECT_RE.findall(html)
    intel["preconnect_links"] = [{"rel": r, "href": urllib.parse.urljoin(base_url, h)} for r, h in preconnects][:50]

    intel["analytics_events"] = sorted(set(TRACK_CALL_RE.findall(html)))[:50]
    intel["js_error_messages"] = sorted(set(JS_ERROR_RE.findall(html)))[:50]
    intel["websocket_urls"] = sorted(set(WS_URL_RE.findall(html)))[:50]
    intel["graphql_queries"] = sorted(set(GQL_QUERY_RE.findall(html)))[:50]
    intel["environment_names"] = sorted(set(ENV_NAME_RE.findall(html)))[:20]
    intel["version_numbers"] = sorted(set(VERSION_NUM_RE.findall(html)))[:50]
    intel["console_logs"] = [c.strip()[:200] for c in CONSOLE_LOG_RE.findall(html)][:30]

    parsed_ld = []
    for blk in JSONLD_RE.findall(html)[:20]:
        try:
            parsed_ld.append(json.loads(blk.strip()))
        except Exception:
            parsed_ld.append({"_raw": blk.strip()[:500]})
    intel["jsonld"] = parsed_ld

    csp_parsed = {}
    for m in META_RE.finditer(html):
        tag = m.group(1)
        if "content-security-policy" in tag.lower():
            ct = META_CONTENT_RE.search(tag)
            if ct:
                csp_parsed = parse_csp_header(ct.group(1))
    intel["csp_meta"] = csp_parsed

    css_urls = []
    for style in INLINE_STYLE_RE.findall(html):
        css_urls.extend(re.findall(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', style, re.IGNORECASE))
    intel["css_urls"] = sorted(set(css_urls))[:100]

    intel["feed_links"] = sorted(set(FEED_RE.findall(html)))[:10]
    m = MANIFEST_RE.search(html)
    intel["manifest"] = urllib.parse.urljoin(base_url, m.group(1)) if m else None
    intel["hreflang"] = [{"lang": l, "href": urllib.parse.urljoin(base_url, h)} for l, h in HREFLANG_RE.findall(html)][:20]
    intel["sri_hashes"] = sorted(set(SRI_RE.findall(html)))[:20]

    if STACK_TRACE_RE.search(html):
        intel["stack_traces"] = _scan_stack_traces(html)

    if "phpinfo" in base_url.lower() and "<table" in html.lower():
        pi = _parse_phpinfo_table(html)
        if pi:
            intel["phpinfo_data"] = pi

    if CLOUD_METADATA_RE.search(html):
        intel["cloud_metadata_leak"] = True

    basic_auth = _extract_basic_auth_url(html)
    if basic_auth:
        intel["basic_auth_urls"] = basic_auth[:20]

    url_creds = _scan_url_params_for_creds(base_url)
    if url_creds:
        intel["url_param_creds"] = url_creds

    return intel


def fetch_and_scan_file(url, label="file"):
    body_bytes = http_get_bytes(url, timeout=20)
    if not body_bytes:
        return {}
    body = body_bytes.decode("utf-8", errors="replace")
    hits = scan_secrets(body, source_label=label, source_url=url)
    decoded = try_decode_and_scan(body, source_label=label, source_url=url)
    for k, v in decoded.items():
        if k in hits:
            hits[k]["values"] = sorted(set(hits[k]["values"]) | set(v["values"]))[:50]
        else:
            hits[k] = v
    structural = _structural_secret_extract(body, source_url=url)
    for k, v in structural.items():
        if k in hits:
            hits[k]["values"] = sorted(set(hits[k]["values"]) | set(v["values"]))[:50]
        else:
            hits[k] = v
    hashes = _scan_hashed_passwords(body)
    for k, v in hashes.items():
        key = f"hash_{k}"
        if key in hits:
            hits[key]["values"] = sorted(set(hits[key]["values"]) | set(v))[:50]
        else:
            hits[key] = {"severity": "high", "values": v, "source": url}
    endpoints = sorted(set(re.findall(r'["\'](/[a-z0-9\-_/]{4,}(?:\?[^"\']*)?)["\']', body, re.IGNORECASE)))[:100]
    if endpoints:
        hits["_endpoints"] = {"severity": "info", "values": endpoints, "source": url}
    return hits


def harvest_js_bundles(by_url, workers=6, limit=200):
    priority = []
    other = []
    for u, caps in by_url.items():
        if u.lower().endswith((".js", ".min.js", ".mjs")):
            entry = (u, caps[-1]["timestamp"])
            low = u.lower()
            if any(x in low for x in ("config", "env", "secret", "key", "auth",
                                      "firebase", "fire", "admin", "main", "app",
                                      "vendor", "runtime", "polyfill", "chunk")):
                priority.append(entry)
            else:
                other.append(entry)
    ordered = (priority + other)[:limit]
    findings = {}

    def work(item):
        u, ts = item
        return u, fetch_and_scan_file(wayback_raw_url(ts, u), label=f"js:{u[:80]}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, x) for x in ordered]
        for fut in concurrent.futures.as_completed(futures):
            try:
                u, hits = fut.result()
            except Exception:
                continue
            if hits:
                findings[u] = hits
    return findings


def harvest_source_maps(page_intel, workers=6, limit=50):
    maps = set()
    for u, ts_map in page_intel.items():
        for ts, intel in ts_map.items():
            for ref in intel.get("sourcemap_refs", []) or []:
                if ref.startswith("data:"):
                    continue
                maps.add((urllib.parse.urljoin(u, ref), ts))
    maps = list(maps)[:limit]
    findings = {}

    def work(item):
        u, ts = item
        raw = wayback_raw_url(ts, u)
        body_bytes = http_get_bytes(raw, timeout=20)
        if not body_bytes:
            return u, {}
        body = body_bytes.decode("utf-8", errors="replace")
        per_source = _extract_source_map_content(body)
        hits = fetch_and_scan_file(raw, label=f"map:{u[:80]}")
        for name, content in per_source:
            sub = scan_secrets(content, source_label=f"{u}::{name}", source_url=raw, decoded_from=f"sourcemap:{name}")
            for k, v in sub.items():
                key = k
                existing = hits.get(key)
                if existing:
                    existing["values"] = sorted(set(existing["values"]) | set(v["values"]))[:50]
                else:
                    hits[key] = {"severity": v["severity"], "values": v["values"], "source": f"{u}::{name}"}
        if per_source:
            hits["_source_files"] = {"severity": "info", "values": [n for n, _ in per_source[:200]]}
        return u, hits

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, x) for x in maps]
        for fut in concurrent.futures.as_completed(futures):
            try:
                u, hits = fut.result()
            except Exception:
                continue
            if hits:
                findings[u] = hits
    return findings


def harvest_js_deobfuscation(by_url, workers=6, limit=100):
    js_urls = []
    for u, caps in by_url.items():
        if u.lower().endswith((".js", ".min.js", ".mjs")):
            js_urls.append((u, caps[-1]["timestamp"]))
            if len(js_urls) >= limit:
                break
    findings = {}

    def work(item):
        u, ts = item
        body = http_get(wayback_raw_url(ts, u), timeout=20)
        return u, deobfuscate_js(body) if body else {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, x) for x in js_urls]
        for fut in concurrent.futures.as_completed(futures):
            try:
                u, hits = fut.result()
            except Exception:
                continue
            if hits:
                findings[u] = hits
    return findings


def scan_special_file_contents(special_files, workers=6, limit=200):
    targets = []
    for fname, snaps in special_files.items():
        latest = sorted(snaps, key=lambda s: s["timestamp"])[-1]
        targets.append((fname, latest["timestamp"], latest["url"]))
    targets = targets[:limit]
    findings = {}

    def work(item):
        fname, ts, url = item
        raw = wayback_raw_url(ts, url)
        hits = fetch_and_scan_file(raw, label=f"special:{fname}")
        body = http_get(raw, timeout=15, max_bytes=200000)
        preview = (body or "")[:2000]
        extra = {}
        if body:
            if fname.endswith(".env") or ".env" in fname:
                env = _extract_env_lines(body)
                if env:
                    extra["env_lines"] = env
            if "wp-config" in fname:
                wp = _extract_wp_config(body)
                if wp:
                    extra["wp_config"] = wp
            if fname.endswith(".json"):
                try:
                    data = json.loads(body)
                    walk = _walk_json_for_secrets(data)
                    if walk:
                        extra["json_walk"] = walk
                except Exception:
                    pass
            if fname.startswith("docker-compose") or fname.endswith(".yml") or fname.endswith(".yaml"):
                de = _extract_docker_env(body)
                if de:
                    extra["docker_env"] = de
            hashes = _scan_hashed_passwords(body)
            if hashes:
                extra["hashes"] = hashes
        return fname, hits, preview, extra

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, x) for x in targets]
        for fut in concurrent.futures.as_completed(futures):
            try:
                fname, hits, preview, extra = fut.result()
            except Exception:
                continue
            findings[fname] = {"secrets": hits, "preview": preview, "structural": extra}
    return findings


def probe_framework_endpoints(base_host, workers=8):
    findings = {}
    tasks = []
    for framework, paths in FRAMEWORK_ENDPOINTS.items():
        for p in paths:
            tasks.append((framework, p))

    def work(item):
        framework, p = item
        url = f"https://{base_host}/{p.lstrip('/')}"
        status, _, _ = http_get_range(url, "0-255", timeout=6)
        return framework, p, url, status

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, t) for t in tasks]
        for fut in concurrent.futures.as_completed(futures):
            try:
                framework, p, url, status = fut.result()
            except Exception:
                continue
            if status and status < 400:
                findings.setdefault(framework, []).append({"path": p, "status": status, "url": url})
    return findings


def fetch_whois(domain):
    result = {"raw": "", "referral": "", "registrar_raw": ""}
    try:
        s = socket.create_connection(("whois.iana.org", 43), timeout=10)
        s.sendall((domain + "\r\n").encode())
        data = b""
        s.settimeout(10)
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > 100000:
                break
        s.close()
        text = data.decode("utf-8", errors="replace")
        result["raw"] = text
        referral = ""
        for line in text.splitlines():
            if line.lower().startswith("refer:"):
                referral = line.split(":", 1)[1].strip()
                break
        if referral:
            result["referral"] = referral
            try:
                s2 = socket.create_connection((referral, 43), timeout=10)
                s2.sendall((domain + "\r\n").encode())
                s2.settimeout(10)
                data2 = b""
                while True:
                    chunk = s2.recv(4096)
                    if not chunk:
                        break
                    data2 += chunk
                    if len(data2) > 200000:
                        break
                s2.close()
                result["registrar_raw"] = data2.decode("utf-8", errors="replace")
            except Exception:
                pass
    except Exception:
        pass
    return result


def fetch_dns_records(domain):
    out = {}
    for rtype in ["A", "AAAA", "CNAME", "MX", "NS", "SOA", "TXT", "CAA"]:
        try:
            data = http_get_json(f"{DOH_GOOGLE_URL}?name={urllib.parse.quote(domain)}&type={rtype}", timeout=10)
            if data and data.get("Answer"):
                out[rtype] = [a.get("data") for a in data["Answer"]]
        except Exception:
            continue
    return out


def fetch_dns_srv(domain):
    out = {}
    for target in SRV_TARGETS:
        name = f"{target}.{domain}"
        try:
            data = http_get_json(f"{DOH_GOOGLE_URL}?name={urllib.parse.quote(name)}&type=SRV", timeout=8)
            if data and data.get("Answer"):
                out[name] = [a.get("data") for a in data["Answer"]]
        except Exception:
            continue
    return out


def fetch_dns_tlsa(domain):
    out = {}
    for port, proto in [("443", "tcp"), ("25", "tcp"), ("993", "tcp"), ("465", "tcp")]:
        name = f"_{port}._{proto}.{domain}"
        try:
            data = http_get_json(f"{DOH_GOOGLE_URL}?name={urllib.parse.quote(name)}&type=TLSA", timeout=8)
            if data and data.get("Answer"):
                out[name] = [a.get("data") for a in data["Answer"]]
        except Exception:
            continue
    return out


def fetch_dns_smimea(domain):
    out = {}
    for selector in ["default", "email", "smime"]:
        name = f"{selector}._smimecert.{domain}"
        try:
            data = http_get_json(f"{DOH_GOOGLE_URL}?name={urllib.parse.quote(name)}&type=SMIMEA", timeout=8)
            if data and data.get("Answer"):
                out[name] = [a.get("data") for a in data["Answer"]]
        except Exception:
            continue
    return out


def fetch_dkim_selectors(domain):
    out = {}
    for sel in DKIM_SELECTORS:
        name = f"{sel}._domainkey.{domain}"
        try:
            data = http_get_json(f"{DOH_GOOGLE_URL}?name={urllib.parse.quote(name)}&type=TXT", timeout=8)
            if data and data.get("Answer"):
                out[sel] = [a.get("data") for a in data["Answer"]]
        except Exception:
            continue
    return out


def fetch_bimi(domain):
    name = f"default._bimi.{domain}"
    try:
        data = http_get_json(f"{DOH_GOOGLE_URL}?name={urllib.parse.quote(name)}&type=TXT", timeout=8)
        if data and data.get("Answer"):
            return {"name": name, "records": [a.get("data") for a in data["Answer"]]}
    except Exception:
        pass
    return {}


def fetch_dnssec_status(domain):
    data = http_get_json(f"{DOH_GOOGLE_URL}?name={urllib.parse.quote(domain)}&type=A&do=1", timeout=10)
    return bool(data and data.get("AD"))


def attempt_zone_transfer(domain):
    ns_records = []
    try:
        data = http_get_json(f"{DOH_GOOGLE_URL}?name={urllib.parse.quote(domain)}&type=NS", timeout=10)
        if data and data.get("Answer"):
            ns_records = [a.get("data") for a in data["Answer"]]
    except Exception:
        pass
    results = []
    for ns in ns_records[:5]:
        ns = ns.rstrip(".")
        try:
            s = socket.create_connection((ns, 53), timeout=5)
            s.close()
            results.append({"ns": ns, "reachable": True})
        except Exception:
            results.append({"ns": ns, "reachable": False})
    return results


def reverse_dns_lookup(ip):
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except Exception:
        return None


def check_wildcard_dns(domain):
    random_sub = f"stratascan-wildcard-{random.randint(100000,999999)}.{domain}"
    try:
        socket.gethostbyname(random_sub)
        return True
    except Exception:
        return False


def fetch_asn_geoip(ip):
    return http_get_json(f"{IPINFO_URL}{ip}/json", timeout=10) or {}


def probe_tcp_port(host, port, timeout=3, send_probe=False):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        banner = b""
        try:
            s.settimeout(2)
            if send_probe:
                s.sendall(b"\r\n")
            banner = s.recv(256)
        except Exception:
            pass
        s.close()
        return True, banner.decode("utf-8", errors="replace")[:200]
    except Exception:
        return False, ""


def scan_ports(host, ports=None, workers=20):
    ports = ports or COMMON_PORTS
    results = {}

    def work(item):
        port, service = item
        send_probe = port in (21, 22, 23, 25, 110, 143, 587, 993, 995, 3306, 5432, 6379, 27017)
        ok, banner = probe_tcp_port(host, port, send_probe=send_probe)
        return port, service, ok, banner

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, p) for p in ports]
        for fut in concurrent.futures.as_completed(futures):
            try:
                port, service, ok, banner = fut.result()
            except Exception:
                continue
            if ok:
                results[port] = {"service": service, "banner": banner}
    return results


def check_tls_versions(host, port=443):
    out = {}
    versions = []
    if hasattr(ssl.TLSVersion, "TLSv1"):
        versions.append(("TLS1.0", ssl.TLSVersion.TLSv1))
    if hasattr(ssl.TLSVersion, "TLSv1_1"):
        versions.append(("TLS1.1", ssl.TLSVersion.TLSv1_1))
    if hasattr(ssl.TLSVersion, "TLSv1_2"):
        versions.append(("TLS1.2", ssl.TLSVersion.TLSv1_2))
    if hasattr(ssl.TLSVersion, "TLSv1_3"):
        versions.append(("TLS1.3", ssl.TLSVersion.TLSv1_3))
    for label, proto in versions:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            try:
                ctx.minimum_version = proto
                ctx.maximum_version = proto
            except Exception:
                out[label] = False
                continue
            with socket.create_connection((host, port), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=host):
                    out[label] = True
        except Exception:
            out[label] = False
    return out


def check_tls_ciphers(host, port=443):
    ciphers_tested = [
        ("ECDHE-RSA-AES128-GCM-SHA256", "modern"),
        ("ECDHE-RSA-AES256-GCM-SHA384", "modern"),
        ("ECDHE-ECDSA-AES128-GCM-SHA256", "modern"),
        ("ECDHE-ECDSA-AES256-GCM-SHA384", "modern"),
        ("AES128-GCM-SHA256", "modern"),
        ("AES256-GCM-SHA384", "modern"),
        ("AES128-SHA", "legacy"),
        ("AES256-SHA", "legacy"),
        ("DES-CBC3-SHA", "weak"),
        ("RC4-SHA", "weak"),
        ("RC4-MD5", "weak"),
        ("NULL-SHA", "weak"),
        ("NULL-MD5", "weak"),
        ("EXP-RC4-MD5", "weak"),
        ("EXP-DES-CBC-SHA", "weak"),
        ("EXP-RC2-CBC-MD5", "weak"),
        ("ADH-AES128-SHA", "weak"),
        ("ADH-AES256-SHA", "weak"),
        ("AECDH-AES128-SHA", "weak"),
        ("AECDH-AES256-SHA", "weak"),
    ]
    out = {}
    for cipher_name, strength in ciphers_tested:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
            try:
                ctx.set_ciphers(cipher_name)
            except ssl.SSLError:
                out[cipher_name] = {"supported": False, "strength": strength}
                continue
            with socket.create_connection((host, port), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    negotiated = ssock.cipher()
                    out[cipher_name] = {
                        "supported": bool(negotiated and negotiated[0] == cipher_name),
                        "strength": strength,
                    }
        except Exception:
            out[cipher_name] = {"supported": False, "strength": strength}
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.maximum_version = ssl.TLSVersion.TLSv1_3
        with socket.create_connection((host, port), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                negotiated = ssock.cipher()
                if negotiated:
                    out[negotiated[0]] = {"supported": True, "strength": "modern-tls13"}
    except Exception:
        pass
    return out


def fetch_cert_chain(host, port=443):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert(binary_form=False)
                valid = True
                issues = []
                try:
                    ssl_ctx = ssl.create_default_context()
                    with socket.create_connection((host, port), timeout=8) as s2:
                        with ssl_ctx.wrap_socket(s2, server_hostname=host):
                            pass
                except ssl.SSLCertVerificationError as e:
                    valid = False
                    issues.append(str(e))
                except Exception as e:
                    valid = False
                    issues.append(str(e))
                return {"valid": valid, "issues": issues, "has_peer": bool(cert)}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def check_hsts_preload(domain):
    return http_get_json(f"{HSTS_PRELOAD_URL}?domain={domain}", timeout=15) or {}


def check_ocsp(host, port=443):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert(binary_form=True)
                if not cert:
                    return {"has_ocsp": False, "has_crl": False}
                has_ocsp = b"\x06\x09\x2b\x06\x01\x05\x05\x07\x30\x01" in cert
                has_crl = b"\x06\x09\x2b\x06\x01\x05\x05\x07\x30\x02" in cert
                return {"has_ocsp": has_ocsp, "has_crl": has_crl}
    except Exception as e:
        return {"error": str(e)}


def fingerprint_waf(headers):
    h = {k.lower(): str(v).lower() for k, v in (headers or {}).items()}
    signatures = {
        "cloudflare": ["cf-ray", "cf-cache-status", "__cfduid"],
        "akamai": ["x-akamai-transformed", "akamai-grn"],
        "sucuri": ["x-sucuri-id", "x-sucuri-cache"],
        "imperva": ["x-iinfo", "x-cdn"],
        "fastly": ["x-served-by", "x-fastly-request-id"],
        "aws_cloudfront": ["x-amz-cf-id", "x-amz-cf-pop"],
        "azure": ["x-azure-ref"],
        "f5": ["x-wa-info"],
        "fortinet": ["fortiwafsid"],
        "barracuda": ["barra_counter_session", "barracuda"],
        "citrix": ["citrix_ns_id", "ns_af"],
        "radware": ["x-rdwr"],
        "stackpath": ["x-sp-url", "x-sp-cache"],
        "keycdn": ["x-keycdn"],
        "bunnycdn": ["x-bunnycdn"],
        "gcore": ["x-gcore"],
        "section.io": ["x-section-io"],
        "limelight": ["x-llid"],
        "highwinds": ["x-hw"],
        "level3": ["x-level3"],
        "cdn77": ["x-cdn77"],
        "belugacdn": ["x-belugacdn"],
        "cachefly": ["x-cachefly"],
        "edgecast": ["x-ec"],
        "chinacache": ["x-chinacache"],
        "wscloudcdn": ["x-wscloudcdn"],
        "aliyun": ["x-aliyun"],
        "tencent": ["x-tencent"],
        "baidu": ["x-baidu"],
        "qiniu": ["x-qiniu"],
        "upyun": ["x-upyun"],
        "kingsoft": ["x-kingsoft"],
        "wangsu": ["x-wangsu"],
        "chinanetcenter": ["x-chinanetcenter"],
        "cloudfront": ["x-amz-cf-id"],
        "incapsula": ["x-iinfo"],
        "modsecurity": ["mod_security", "modsecurity"],
        "wordfence": ["wordfence"],
        "sitelock": ["sitelock"],
        "cloudbric": ["cloudbric"],
        "comodo": ["x-cdn"],
        "zenedge": ["x-zenedge"],
        "distil": ["x-distil"],
        "shapesecurity": ["x-shape"],
        "signalciences": ["x-signal"],
        "perimeterx": ["x-px"],
        "datadome": ["x-datadome"],
        "kasada": ["x-kasada"],
        "human": ["x-human"],
        "whiteops": ["x-whiteops"],
        "forter": ["x-forter"],
        "ravelin": ["x-ravelin"],
        "sift": ["x-sift"],
        "riskified": ["x-riskified"],
        "signifyd": ["x-signifyd"],
        "kount": ["x-kount"],
        "accertify": ["x-accertify"],
        "cybersource": ["x-cybersource"],
        "worldpay": ["x-worldpay"],
        "stripe": ["x-stripe"],
        "braintree": ["x-braintree"],
        "paypal": ["x-paypal"],
        "square": ["x-square"],
        "adyen": ["x-adyen"],
        "checkout": ["x-checkout"],
        "revolut": ["x-revolut"],
        "klarna": ["x-klarna"],
        "afterpay": ["x-afterpay"],
        "affirm": ["x-affirm"],
        "sezzle": ["x-sezzle"],
        "zip": ["x-zip"],
        "quadpay": ["x-quadpay"],
        "splitit": ["x-splitit"],
        "paybright": ["x-paybright"],
        "payright": ["x-payright"],
        "humm": ["x-humm"],
        "latitude": ["x-latitude"],
        "openpay": ["x-openpay"],
        "partpay": ["x-partpay"],
        "laybuy": ["x-laybuy"],
        "clearpay": ["x-clearpay"],
    }
    hits = []
    for waf, keys in signatures.items():
        for k in keys:
            if k in h:
                hits.append(waf)
                break
    return sorted(set(hits))


def check_http2(host):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_alpn_protocols(["h2", "http/1.1"])
        with socket.create_connection((host, 443), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                return ssock.selected_alpn_protocol()
    except Exception:
        return None


def check_cors(headers):
    h = {k.lower(): v for k, v in (headers or {}).items()}
    acao = h.get("access-control-allow-origin", "")
    acac = h.get("access-control-allow-credentials", "")
    if acao == "*" and acac.lower() == "true":
        return {"vulnerable": True, "acao": acao, "acac": acac}
    if acao:
        return {"vulnerable": False, "acao": acao}
    return {}


def check_rate_limit_headers(headers):
    h = {k.lower(): v for k, v in (headers or {}).items()}
    out = {}
    for k in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "retry-after"):
        if k in h:
            out[k] = h[k]
    return out


def parse_robots_txt(content):
    if not content:
        return {}
    disallow, allow, sitemaps, agents, crawl_delay = [], [], [], [], {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "disallow" and v:
            disallow.append(v)
        elif k == "allow" and v:
            allow.append(v)
        elif k == "sitemap":
            sitemaps.append(v)
        elif k == "user-agent":
            agents.append(v)
        elif k == "crawl-delay":
            crawl_delay[agents[-1] if agents else "*"] = v
    return {"user_agents": agents, "disallow": disallow, "allow": allow, "sitemaps": sitemaps, "crawl_delay": crawl_delay}


def parse_sitemap_xml(content):
    if not content:
        return {"urls": [], "sitemaps": []}
    urls = re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', content)
    sub_sitemaps = re.findall(r'<sitemap>.*?<loc>\s*([^<\s]+)\s*</loc>', content, re.DOTALL)
    lastmods = re.findall(r'<lastmod>\s*([^<\s]+)\s*</lastmod>', content)
    return {"urls": urls[:5000], "sitemaps": sub_sitemaps[:200], "lastmods": lastmods[:200]}


def fetch_special_file_history(domain, filename, date_from=None, date_to=None):
    target = domain.rstrip("/") + "/" + filename
    snaps = fetch_all_snapshots(target, date_from, date_to)
    history = []
    for s in snaps:
        html = fetch_snapshot_content(s["timestamp"], s["original"], max_bytes=100000)
        history.append({
            "timestamp": s["timestamp"],
            "url": wayback_snapshot_url(s["timestamp"], s["original"]),
            "content_preview": (html or "")[:2000],
            "length": len(html) if html else 0,
        })
    return history


def fetch_all_special_files(domain, date_from=None, date_to=None, workers=6):
    T("PHASE", f"special file probing ({len(SPECIAL_FILES)} candidates)")

    def work(fname):
        target = domain.rstrip("/") + "/" + fname
        snaps = cdx_query({
            "url": target, "matchType": "exact", "output": "json",
            "fl": "timestamp,original,statuscode,mimetype,digest,length",
            "collapse": "digest",
        }, timeout=45, follow_pagination=False)
        return fname, [{
            "file": fname, "timestamp": s["timestamp"], "url": s["original"],
            "statuscode": s.get("statuscode"), "mimetype": s.get("mimetype"),
            "archive": wayback_snapshot_url(s["timestamp"], s["original"]),
        } for s in snaps]

    findings = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, f) for f in SPECIAL_FILES]
        for fut in concurrent.futures.as_completed(futures):
            try:
                fname, snaps = fut.result()
            except Exception:
                continue
            if snaps:
                findings[fname] = snaps
    return findings


def group_by_url(snapshots):
    by_url = defaultdict(list)
    for s in snapshots:
        by_url[s["original"]].append(s)
    for caps in by_url.values():
        caps.sort(key=lambda c: c["timestamp"])
    return by_url


def check_live_status(by_url, workers=8, limit=None):
    urls = list(by_url.keys())
    if limit:
        urls = urls[:limit]
    T("PHASE", f"live status probing ({len(urls)} urls, {workers} workers)")
    status_map = {}

    def probe(u):
        return u, http_head_full(u)[0]

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(probe, u) for u in urls]
        for fut in concurrent.futures.as_completed(futures):
            try:
                u, status = fut.result()
            except Exception:
                continue
            status_map[u] = status
    return status_map


def classify_deletion(status_map):
    out = {}
    for u, st in (status_map or {}).items():
        if st is None:
            out[u] = "offline"
        elif st == 404:
            out[u] = "removed"
        elif st == 410:
            out[u] = "gone"
        elif st == 451:
            out[u] = "legal"
        elif st == 403:
            out[u] = "blocked"
        elif 300 <= st < 400:
            out[u] = "redirected"
        elif st >= 500:
            out[u] = "server_error"
        elif st == 200:
            out[u] = "live"
        else:
            out[u] = f"status_{st}"
    return out


def build_url_timelines(by_url, workers=8, limit=200):
    urls = list(by_url.keys())[:limit]
    T("PHASE", f"building CDX timelines for {len(urls)} urls")
    out = {}

    def work(u):
        return u, fetch_cdx_timeline(u)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, u) for u in urls]
        for fut in concurrent.futures.as_completed(futures):
            try:
                u, snaps = fut.result()
            except Exception:
                continue
            timeline = [{
                "timestamp": s.get("timestamp"),
                "status": s.get("statuscode"),
                "digest": s.get("digest"),
                "length": s.get("length"),
                "redirect": s.get("redirect"),
            } for s in snaps]
            timeline.sort(key=lambda x: x["timestamp"] or "")
            out[u] = timeline
    return out


def detect_deletion_windows(timelines):
    out = {}
    mass_events = defaultdict(list)
    for u, tl in timelines.items():
        first_ok = last_ok = first_bad = deletion_type = None
        for entry in tl:
            st = entry.get("status")
            ts = entry.get("timestamp")
            try:
                st_num = int(st) if st is not None else 0
            except Exception:
                st_num = 0
            if st_num == 200 and ts:
                last_ok = ts
                if first_ok is None:
                    first_ok = ts
            elif ts and first_bad is None and last_ok:
                first_bad = ts
                if st_num == 410:
                    deletion_type = "gone"
                elif st_num == 451:
                    deletion_type = "legal"
                elif st_num == 404:
                    deletion_type = "removed"
                elif st_num == 403:
                    deletion_type = "blocked"
                elif 300 <= st_num < 400:
                    deletion_type = "redirected"
                elif st_num >= 500:
                    deletion_type = "server_error"
                else:
                    deletion_type = f"status_{st_num}"
        if first_bad and last_ok:
            out[u] = {
                "last_ok": last_ok,
                "first_bad": first_bad,
                "type": deletion_type or "unknown",
                "total_snapshots": len(tl),
            }
            mass_events[first_bad].append(u)
    clusters = []
    for ts, urls in mass_events.items():
        if len(urls) >= 3:
            clusters.append({"timestamp": ts, "count": len(urls), "sample": urls[:10]})
    clusters.sort(key=lambda x: -x["count"])
    return out, clusters


def diff_first_last(by_url, timelines, workers=6, limit=200):
    out = {}
    targets = []
    for u, tl in timelines.items():
        if not tl:
            continue
        first, last = tl[0]["timestamp"], tl[-1]["timestamp"]
        if first and last and first != last:
            targets.append((u, first, last))
        if len(targets) >= limit:
            break

    def work(item):
        u, t1, t2 = item
        h1 = fetch_snapshot_content(t1, u) or ""
        h2 = fetch_snapshot_content(t2, u) or ""
        return u, list(difflib.unified_diff(h1.splitlines(), h2.splitlines(), fromfile=t1, tofile=t2, lineterm="", n=1))[:200]

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, t) for t in targets]
        for fut in concurrent.futures.as_completed(futures):
            try:
                u, d = fut.result()
            except Exception:
                continue
            if d:
                out[u] = d
    return out


def diff_adjacent_snapshots(by_url, workers=6, limit=50):
    out = {}
    targets = []
    for u, caps in by_url.items():
        html_caps = [c for c in caps if "html" in c.get("mimetype", "")]
        if len(html_caps) < 2:
            continue
        for i in range(1, min(len(html_caps), 5)):
            targets.append((u, html_caps[i-1]["timestamp"], html_caps[i]["timestamp"]))
        if len(targets) >= limit:
            break

    def work(item):
        u, t1, t2 = item
        h1 = fetch_snapshot_content(t1, u) or ""
        h2 = fetch_snapshot_content(t2, u) or ""
        return f"{u}@{t1}->{t2}", list(difflib.unified_diff(h1.splitlines(), h2.splitlines(), fromfile=t1, tofile=t2, lineterm="", n=0))[:100]

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, t) for t in targets]
        for fut in concurrent.futures.as_completed(futures):
            try:
                k, d = fut.result()
            except Exception:
                continue
            if d:
                out[k] = d
    return out


def diff_wayback_live(by_url, workers=6, limit=30):
    out = {}
    targets = []
    for u, caps in by_url.items():
        if len(targets) >= limit:
            break
        latest = caps[-1]
        if "html" in latest.get("mimetype", ""):
            targets.append((u, latest["timestamp"]))

    def work(item):
        u, ts = item
        archived = fetch_snapshot_content(ts, u) or ""
        live = http_get(u, timeout=15) or ""
        if not archived or not live:
            return u, None
        return u, list(difflib.unified_diff(archived.splitlines(), live.splitlines(),
                                            fromfile=f"archived@{ts}", tofile="live", lineterm="", n=1))[:200]

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, t) for t in targets]
        for fut in concurrent.futures.as_completed(futures):
            try:
                u, d = fut.result()
            except Exception:
                continue
            if d:
                out[u] = d
    return out


def extract_subdomains(snapshots, root_domain):
    subs = set()
    root = root_domain.replace("www.", "")
    for s in snapshots:
        try:
            netloc = urllib.parse.urlparse(s["original"]).netloc or s["original"].split("/")[0]
        except Exception:
            continue
        if root in netloc and netloc not in (root, f"www.{root}"):
            subs.add(netloc)
    return sorted(subs)


def subdomain_first_last_seen(snapshots, root_domain):
    root = root_domain.replace("www.", "")
    stats = defaultdict(lambda: {"first": None, "last": None, "count": 0})
    for s in snapshots:
        try:
            netloc = urllib.parse.urlparse(s["original"]).netloc or s["original"].split("/")[0]
        except Exception:
            continue
        if root not in netloc or netloc == root:
            continue
        d = stats[netloc]
        ts = s["timestamp"]
        if d["first"] is None or ts < d["first"]:
            d["first"] = ts
        if d["last"] is None or ts > d["last"]:
            d["last"] = ts
        d["count"] += 1
    return {k: v for k, v in sorted(stats.items())}


def detect_subdomain_takeover(subdomains, workers=8):
    findings = []

    def work(sub):
        try:
            _, _, ips = socket.gethostbyname_ex(sub)
            return sub, ips, None
        except Exception as e:
            return sub, [], str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, s) for s in subdomains]
        for fut in concurrent.futures.as_completed(futures):
            try:
                sub, ips, err = fut.result()
            except Exception:
                continue
            if err and ("not known" in err.lower() or "nodename" in err.lower()):
                findings.append({"subdomain": sub, "reason": "nxdomain"})
    return findings


def permute_subdomains(root_domain):
    prefixes = ["dev", "staging", "stage", "test", "qa", "uat", "prod", "api", "app",
                "admin", "portal", "internal", "intranet", "vpn", "mail", "smtp",
                "webmail", "ftp", "sftp", "ssh", "git", "gitlab", "jenkins",
                "ci", "cd", "monitor", "grafana", "prometheus", "kibana",
                "elastic", "logs", "status", "health", "beta", "alpha", "demo",
                "sandbox", "backup", "bak", "old", "new", "v2", "v3",
                "devops", "sre", "platform", "infra", "cloud", "aws", "gcp",
                "azure", "k8s", "docker", "registry", "nexus", "artifactory",
                "sonar", "sonarqube", "jira", "confluence", "wiki", "docs",
                "support", "help", "faq", "kb", "crm", "erp", "hr", "finance",
                "legal", "compliance", "audit", "security", "soc", "noc",
                "dba", "db", "database", "mysql", "postgres", "mongo", "redis",
                "cache", "cdn", "static", "assets", "media", "images", "img",
                "video", "audio", "files", "download", "uploads", "storage",
                "backup", "archive", "cold", "warm", "hot", "edge", "origin",
                "proxy", "gateway", "router", "switch", "firewall", "vpn",
                "dns", "ns1", "ns2", "ns3", "ns4", "mx", "mx1", "mx2",
                "smtp", "pop", "imap", "exchange", "owa", "autodiscover",
                "lync", "skype", "teams", "zoom", "meet", "webex",
                "sharepoint", "onedrive", "dropbox", "box", "gdrive",
                "salesforce", "hubspot", "marketo", "pardot", "mailchimp",
                "sendgrid", "mailgun", "postmark", "sparkpost", "ses",
                "twilio", "nexmo", "plivo", "messagebird", "sinch",
                "stripe", "paypal", "braintree", "square", "adyen",
                "shopify", "woocommerce", "magento", "prestashop",
                "wordpress", "wp", "drupal", "joomla", "typo3",
                "phpmyadmin", "pma", "adminer", "phppgadmin",
                "cpanel", "whm", "plesk", "webmin", "vesta",
                "directadmin", "ispconfig", "froxlor", "ajenti",
                "grafana", "kibana", "prometheus", "alertmanager",
                "zabbix", "nagios", "icinga", "checkmk", "sensu",
                "datadog", "newrelic", "appdynamics", "dynatrace",
                "splunk", "elk", "efk", "graylog", "fluentd",
                "logstash", "filebeat", "metricbeat", "heartbeat",
                "packetbeat", "auditbeat", "journalbeat", "winlogbeat",
                "redis", "memcached", "rabbitmq", "kafka", "zookeeper",
                "activemq", "rocketmq", "pulsar", "nats", "nsq",
                "etcd", "consul", "vault", "nomad", "terraform",
                "ansible", "puppet", "chef", "salt", "rundeck",
                "awx", "tower", "jenkins", "teamcity", "bamboo",
                "buildkite", "circleci", "travis", "drone", "argo",
                "tekton", "spinnaker", "flux", "argocd", "helm",
                "kustomize", "skaffold", "tilt", "devspace",
                "telepresence", "garden", "okteto", "gitpod",
                "codeanywhere", "cloud9", "c9", "eclipse",
                "intellij", "vscode", "atom", "sublime",
                "vim", "emacs", "nano", "jupyter", "zeppelin",
                "rstudio", "spyder", "pycharm", "webstorm",
                "phpstorm", "rubymine", "goland", "clion",
                "datagrip", "rider", "fleet", "space",
                "youTrack", "upSource", "teamcity", "hub",
                "jetbrains", "atlassian", "slack", "discord",
                "mattermost", "rocket.chat", "zulip", "matrix",
                "element", "riot", "synapse", "dendrite",
                "nextcloud", "owncloud", "seafile", "pydio",
                "dropbox", "box", "egnyte", "sharefile",
                "citrix", "vmware", "horizon", "view",
                "xen", "xenserver", "xcp", "proxmox",
                "openstack", "cloudstack", "eucalyptus",
                "opennebula", "oVirt", "virtuozzo",
                "docker", "podman", "containerd", "cri-o",
                "kubernetes", "k8s", "k3s", "k0s", "microk8s",
                "minikube", "kind", "kubeadm", "kubespray",
                "rancher", "openshift", "okd", "tanzu",
                "eks", "aks", "gke", "do", "linode",
                "digitalocean", "vultr", "hetzner", "ovh",
                "scaleway", "upcloud", "packet", "equinix",
                "metal", "bare", "dedicated", "vps", "vm",
                "cloud", "public", "private", "hybrid",
                "multi", "cross", "inter", "intra", "extra",
                "meta", "data", "info", "app", "web",
                "mobile", "tablet", "desktop", "tv", "iot",
                "edge", "fog", "mist", "dew", "cloud",
                "quantum", "ai", "ml", "dl", "nlp",
                "vision", "speech", "voice", "chat", "bot",
                "agent", "assistant", "copilot", "pilot",
                "auto", "autoML", "autoDL", "autoAI",
                "MLOps", "DevOps", "DataOps", "AIOps",
                "GitOps", "CloudOps", "SecOps", "NetOps",
                "FinOps", "MarketingOps", "SalesOps",
                "RevOps", "BizOps", "HRops", "LegalOps",
                "ITOps", "TechOps", "SysOps", "NetOps",
                "SecOps", "DevSecOps", "MLSecOps",
                "AISecOps", "CloudSecOps", "DataSecOps",
                "AppSecOps", "ContainerSecOps",
                "KubernetesSecOps", "ServerlessSecOps",
                "EdgeSecOps", "IoTSecOps", "OTSecOps",
                "ITSecOps", "OTSecOps", "ICS", "SCADA",
                "PLC", "RTU", "HMI", "DCS", "SIS",
                "MES", "ERP", "CRM", "SCM", "WMS",
                "TMS", "YMS", "LMS", "CMS", "DMS",
                "PIM", "DAM", "MRM", "BPM", "RPA",
                "IPA", "API", "SDK", "CLI", "GUI",
                "UX", "UI", "CX", "DX", "EX",
                "B2B", "B2C", "B2B2C", "C2C", "D2C",
                "P2P", "O2O", "OMO", "X2X", "M2M",
                "IoT", "IIoT", "AIoT", "IoB", "IoH",
                "IoV", "IoD", "IoE", "IoP", "IoM",
                "IoA", "IoS", "IoR", "IoF", "IoW",
                "IoG", "IoN", "IoC", "IoE", "IoI"]
    out = []
    for p in prefixes:
        out.append(f"{p}.{root_domain}")
        out.append(f"{p}-{root_domain}")
    return out


def brute_subdomains(root_domain, wordlist=None, workers=12):
    wordlist = wordlist or ["www", "mail", "ftp", "webmail", "smtp", "pop", "ns1", "ns2",
                             "dev", "test", "staging", "api", "app", "admin", "portal",
                             "blog", "shop", "store", "cdn", "static", "assets",
                             "login", "auth", "sso", "vpn", "git", "jenkins", "ci",
                             "monitor", "grafana", "prometheus", "kibana", "elastic",
                             "logs", "status", "health", "docs", "wiki", "help",
                             "support", "m", "mobile", "secure", "internal",
                             "devops", "sre", "platform", "infra", "cloud",
                             "aws", "gcp", "azure", "k8s", "docker",
                             "registry", "nexus", "artifactory", "sonar",
                             "jira", "confluence", "wiki", "docs", "support",
                             "help", "faq", "kb", "crm", "erp", "hr",
                             "finance", "legal", "compliance", "audit",
                             "security", "soc", "noc", "dba", "db",
                             "database", "mysql", "postgres", "mongo",
                             "redis", "cache", "cdn", "static", "assets",
                             "media", "images", "img", "video", "audio",
                             "files", "download", "uploads", "storage",
                             "backup", "archive", "cold", "warm", "hot",
                             "edge", "origin", "proxy", "gateway", "router",
                             "switch", "firewall", "vpn", "dns", "ns1",
                             "ns2", "ns3", "ns4", "mx", "mx1", "mx2",
                             "smtp", "pop", "imap", "exchange", "owa",
                             "autodiscover", "lync", "skype", "teams",
                             "zoom", "meet", "webex", "sharepoint",
                             "onedrive", "dropbox", "box", "gdrive",
                             "salesforce", "hubspot", "marketo", "pardot",
                             "mailchimp", "sendgrid", "mailgun", "postmark",
                             "sparkpost", "ses", "twilio", "nexmo", "plivo",
                             "messagebird", "sinch", "stripe", "paypal",
                             "braintree", "square", "adyen", "shopify",
                             "woocommerce", "magento", "prestashop",
                             "wordpress", "wp", "drupal", "joomla", "typo3",
                             "phpmyadmin", "pma", "adminer", "phppgadmin",
                             "cpanel", "whm", "plesk", "webmin", "vesta",
                             "directadmin", "ispconfig", "froxlor", "ajenti",
                             "grafana", "kibana", "prometheus", "alertmanager",
                             "zabbix", "nagios", "icinga", "checkmk", "sensu",
                             "datadog", "newrelic", "appdynamics", "dynatrace",
                             "splunk", "elk", "efk", "graylog", "fluentd",
                             "logstash", "filebeat", "metricbeat", "heartbeat",
                             "packetbeat", "auditbeat", "journalbeat",
                             "winlogbeat", "redis", "memcached", "rabbitmq",
                             "kafka", "zookeeper", "activemq", "rocketmq",
                             "pulsar", "nats", "nsq", "etcd", "consul",
                             "vault", "nomad", "terraform", "ansible",
                             "puppet", "chef", "salt", "rundeck", "awx",
                             "tower", "jenkins", "teamcity", "bamboo",
                             "buildkite", "circleci", "travis", "drone",
                             "argo", "tekton", "spinnaker", "flux",
                             "argocd", "helm", "kustomize", "skaffold",
                             "tilt", "devspace", "telepresence", "garden",
                             "okteto", "gitpod", "codeanywhere", "cloud9",
                             "c9", "eclipse", "intellij", "vscode", "atom",
                             "sublime", "vim", "emacs", "nano", "jupyter",
                             "zeppelin", "rstudio", "spyder", "pycharm",
                             "webstorm", "phpstorm", "rubymine", "goland",
                             "clion", "datagrip", "rider", "fleet", "space",
                             "youTrack", "upSource", "teamcity", "hub",
                             "jetbrains", "atlassian", "slack", "discord",
                             "mattermost", "rocket.chat", "zulip", "matrix",
                             "element", "riot", "synapse", "dendrite",
                             "nextcloud", "owncloud", "seafile", "pydio",
                             "dropbox", "box", "egnyte", "sharefile",
                             "citrix", "vmware", "horizon", "view",
                             "xen", "xenserver", "xcp", "proxmox",
                             "openstack", "cloudstack", "eucalyptus",
                             "opennebula", "oVirt", "virtuozzo",
                             "docker", "podman", "containerd", "cri-o",
                             "kubernetes", "k8s", "k3s", "k0s", "microk8s",
                             "minikube", "kind", "kubeadm", "kubespray",
                             "rancher", "openshift", "okd", "tanzu",
                             "eks", "aks", "gke", "do", "linode",
                             "digitalocean", "vultr", "hetzner", "ovh",
                             "scaleway", "upcloud", "packet", "equinix",
                             "metal", "bare", "dedicated", "vps", "vm",
                             "cloud", "public", "private", "hybrid",
                             "multi", "cross", "inter", "intra", "extra",
                             "meta", "data", "info", "app", "web",
                             "mobile", "tablet", "desktop", "tv", "iot",
                             "edge", "fog", "mist", "dew", "cloud",
                             "quantum", "ai", "ml", "dl", "nlp",
                             "vision", "speech", "voice", "chat", "bot",
                             "agent", "assistant", "copilot", "pilot",
                             "auto", "autoML", "autoDL", "autoAI",
                             "MLOps", "DevOps", "DataOps", "AIOps",
                             "GitOps", "CloudOps", "SecOps", "NetOps",
                             "FinOps", "MarketingOps", "SalesOps",
                             "RevOps", "BizOps", "HRops", "LegalOps",
                             "ITOps", "TechOps", "SysOps", "NetOps",
                             "SecOps", "DevSecOps", "MLSecOps",
                             "AISecOps", "CloudSecOps", "DataSecOps",
                             "AppSecOps", "ContainerSecOps",
                             "KubernetesSecOps", "ServerlessSecOps",
                             "EdgeSecOps", "IoTSecOps", "OTSecOps",
                             "ITSecOps", "OTSecOps", "ICS", "SCADA",
                             "PLC", "RTU", "HMI", "DCS", "SIS",
                             "MES", "ERP", "CRM", "SCM", "WMS",
                             "TMS", "YMS", "LMS", "CMS", "DMS",
                             "PIM", "DAM", "MRM", "BPM", "RPA",
                             "IPA", "API", "SDK", "CLI", "GUI",
                             "UX", "UI", "CX", "DX", "EX",
                             "B2B", "B2C", "B2B2C", "C2C", "D2C",
                             "P2P", "O2O", "OMO", "X2X", "M2M",
                             "IoT", "IIoT", "AIoT", "IoB", "IoH",
                             "IoV", "IoD", "IoE", "IoP", "IoM",
                             "IoA", "IoS", "IoR", "IoF", "IoW",
                             "IoG", "IoN", "IoC", "IoE", "IoI"]
    found = []

    def work(sub):
        host = f"{sub}.{root_domain}"
        try:
            _, _, ips = socket.gethostbyname_ex(host)
            return host, ips
        except Exception:
            return host, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, s) for s in wordlist]
        for fut in concurrent.futures.as_completed(futures):
            try:
                host, ips = fut.result()
            except Exception:
                continue
            if ips:
                found.append({"host": host, "ips": ips})
    return found


def enumerate_case_variants(snapshots):
    variants = defaultdict(set)
    for s in snapshots:
        p = urllib.parse.urlparse(s["original"]).path
        if p:
            variants[p.lower()].add(p)
    return {k: sorted(v) for k, v in variants.items() if len(v) > 1}


def enumerate_slash_variants(snapshots):
    variants = defaultdict(set)
    for s in snapshots:
        path = urllib.parse.urlparse(s["original"]).path
        if not path:
            continue
        if path.endswith("/") and path != "/":
            variants[path.rstrip("/")].add(path)
        else:
            variants[path].add(path)
    return {k: sorted(v) for k, v in variants.items() if len(v) > 1}


def enumerate_scheme_variants(snapshots):
    variants = defaultdict(set)
    for s in snapshots:
        parsed = urllib.parse.urlparse(s["original"])
        if parsed.netloc:
            variants[parsed.netloc + parsed.path].add(parsed.scheme)
    return {k: sorted(v) for k, v in variants.items() if len(v) > 1}


def enumerate_port_variants(snapshots):
    variants = defaultdict(set)
    for s in snapshots:
        try:
            parsed = urllib.parse.urlparse(s["original"])
            if parsed.netloc and ":" in parsed.netloc and parsed.hostname:
                try:
                    port = parsed.port
                except ValueError:
                    continue
                variants[parsed.hostname + parsed.path].add(port)
        except Exception:
            continue
    return {k: sorted(v) for k, v in variants.items() if len(v) > 1}


def find_redirect_history(by_url):
    redirects = []
    for u, caps in by_url.items():
        for c in caps:
            code = c.get("statuscode", "")
            if code in ("301", "302", "303", "307", "308"):
                redirects.append({
                    "url": u, "timestamp": c["timestamp"], "statuscode": code,
                    "redirect_target": c.get("redirect", ""),
                })
    return redirects


def harvest_documents(by_url):
    docs = []
    for u, caps in by_url.items():
        ext = Path(urllib.parse.urlparse(u).path).suffix.lower()
        if ext in DOC_EXTENSIONS:
            latest = caps[-1]
            docs.append({
                "url": u, "extension": ext,
                "last_captured": latest["timestamp"], "first_captured": caps[0]["timestamp"],
                "archive_link": wayback_snapshot_url(latest["timestamp"], u),
                "snapshot_count": len(caps),
            })
    return docs


def extract_pdf_metadata(body_bytes):
    if not body_bytes:
        return {}
    out = {}
    text = body_bytes[:500000].decode("latin-1", errors="ignore")
    for field in ("Author", "Creator", "Producer", "Title", "Subject", "Keywords", "CreationDate", "ModDate"):
        m = re.search(rf'/{field}\s*\(([^)]{{0,500}})\)', text)
        if m:
            out[field] = m.group(1)[:500]
    if b"%%EOF" in body_bytes:
        out["complete"] = True
    if re.search(rb'/JavaScript|/JS', body_bytes):
        out["has_javascript"] = True
    if re.search(rb'/EmbeddedFile', body_bytes):
        out["has_embedded_files"] = True
    if re.search(rb'/AcroForm', body_bytes):
        out["has_forms"] = True
    if re.search(rb'/Launch', body_bytes):
        out["has_launch_action"] = True
    if re.search(rb'/OpenAction', body_bytes):
        out["has_open_action"] = True
    if re.search(rb'/AA', body_bytes):
        out["has_additional_actions"] = True
    if re.search(rb'/Names', body_bytes):
        out["has_names_dict"] = True
    if re.search(rb'/Outlines', body_bytes):
        out["has_outlines"] = True
    if re.search(rb'/PageMode\s*/UseOutlines', body_bytes):
        out["page_mode"] = "UseOutlines"
    if re.search(rb'/PageMode\s*/UseThumbs', body_bytes):
        out["page_mode"] = "UseThumbs"
    if re.search(rb'/PageMode\s*/FullScreen', body_bytes):
        out["page_mode"] = "FullScreen"
    if re.search(rb'/PageLayout\s*/SinglePage', body_bytes):
        out["page_layout"] = "SinglePage"
    if re.search(rb'/PageLayout\s*/OneColumn', body_bytes):
        out["page_layout"] = "OneColumn"
    if re.search(rb'/PageLayout\s*/TwoColumnLeft', body_bytes):
        out["page_layout"] = "TwoColumnLeft"
    if re.search(rb'/PageLayout\s*/TwoColumnRight', body_bytes):
        out["page_layout"] = "TwoColumnRight"
    if re.search(rb'/Encrypt', body_bytes):
        out["encrypted"] = True
    if re.search(rb'/Linearized', body_bytes):
        out["linearized"] = True
    return out


def extract_office_metadata(body_bytes, ext):
    if not body_bytes:
        return {}
    out = {}
    if ext in (".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp") and body_bytes[:2] == b"PK":
        out["is_zip"] = True
        try:
            with zipfile.ZipFile(BytesIO(body_bytes)) as zf:
                names = zf.namelist()
                if any("vbaProject.bin" in n for n in names):
                    out["has_macros"] = True
                if "docProps/core.xml" in names:
                    core = zf.read("docProps/core.xml").decode("utf-8", errors="replace")
                    for field in ("creator", "lastModifiedBy", "title", "subject", "description", "keywords", "category", "contentStatus", "created", "modified", "lastPrinted", "revision"):
                        m = re.search(rf'<[^>]*{field}[^>]*>([^<]{{0,500}})</', core, re.IGNORECASE)
                        if m:
                            out[field] = m.group(1)
                if "docProps/app.xml" in names:
                    app = zf.read("docProps/app.xml").decode("utf-8", errors="replace")
                    for field in ("Company", "Manager", "Template", "TotalTime", "Pages", "Words", "Characters", "Lines", "Paragraphs", "Slides", "Notes", "HiddenSlides", "MMClips", "ScaleCrop", "HeadingPairs", "TitlesOfParts", "LinksUpToDate", "CharactersWithSpaces", "SharedDoc", "HyperlinkBase", "HLinks", "HyperlinksChanged", "AppVersion", "DocSecurity", "Application"):
                        m = re.search(rf'<{field}>([^<]{{0,500}})</{field}>', app, re.IGNORECASE)
                        if m:
                            out[field.lower()] = m.group(1)
                if "docProps/custom.xml" in names:
                    cust = zf.read("docProps/custom.xml").decode("utf-8", errors="replace")
                    props = re.findall(r'<property[^>]*name="([^"]+)"[^>]*>.*?<vt:lpwstr>([^<]+)</vt:lpwstr>', cust, re.DOTALL)
                    out["custom_properties"] = {k: v for k, v in props[:20]}
                if "word/document.xml" in names:
                    doc = zf.read("word/document.xml").decode("utf-8", errors="replace")
                    tracked = len(re.findall(r'<w:(?:ins|del)\b', doc))
                    if tracked:
                        out["tracked_changes"] = tracked
                if "word/comments.xml" in names:
                    comments = zf.read("word/comments.xml").decode("utf-8", errors="replace")
                    out["comments"] = re.findall(r'<w:t[^>]*>([^<]+)</w:t>', comments)[:20]
                if "word/settings.xml" in names:
                    settings = zf.read("word/settings.xml").decode("utf-8", errors="replace")
                    if "w:documentProtection" in settings:
                        out["document_protection"] = True
                    if "w:trackRevisions" in settings:
                        out["track_revisions"] = True
                if "xl/workbook.xml" in names:
                    wb = zf.read("xl/workbook.xml").decode("utf-8", errors="replace")
                    sheets = re.findall(r'<sheet[^>]*name="([^"]+)"', wb)
                    if sheets:
                        out["sheets"] = sheets[:50]
                if "ppt/presentation.xml" in names:
                    pres = zf.read("ppt/presentation.xml").decode("utf-8", errors="replace")
                    slides = len(re.findall(r'<p:sldId\b', pres))
                    if slides:
                        out["slide_count"] = slides
        except Exception:
            pass
    return out


def extract_exif(body_bytes):
    if not body_bytes or len(body_bytes) < 20 or body_bytes[:3] != b"\xff\xd8\xff":
        return {}
    idx = 2
    iterations = 0
    while idx < len(body_bytes) - 4 and iterations < 200:
        iterations += 1
        if body_bytes[idx] != 0xFF:
            break
        marker = body_bytes[idx + 1]
        if marker == 0xE1:
            seg_len = int.from_bytes(body_bytes[idx + 2:idx + 4], "big")
            seg = body_bytes[idx + 4:idx + 2 + seg_len]
            if seg[:6] == b"Exif\x00\x00":
                tiff = seg[6:]
                text = tiff.decode("latin-1", errors="ignore")
                out = {"exif_present": True}
                for tag in ("Software", "Make", "Model", "DateTime", "Artist", "Copyright", "ImageDescription", "UserComment", "GPSLatitude", "GPSLongitude", "GPSAltitude", "GPSDateStamp", "GPSTimeStamp", "GPSProcessingMethod", "GPSAreaInformation"):
                    m = re.search(tag + r"[^\x00]{0,500}", text)
                    if m:
                        out[tag] = m.group(0)[:500]
                gps = re.search(r'GPS[\x20-\x7e]{0,500}', text)
                if gps:
                    out["GPS"] = gps.group(0)[:500]
                return out
        if marker in (0xD8, 0xD9):
            idx += 2
            continue
        if idx + 4 > len(body_bytes):
            break
        seg_len = int.from_bytes(body_bytes[idx + 2:idx + 4], "big")
        if seg_len <= 0:
            break
        idx += 2 + seg_len
    return {}


def extract_png_chunks(body_bytes):
    if not body_bytes or body_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        return {}
    out = {"chunks": []}
    idx = 8
    while idx < len(body_bytes) - 12:
        length = int.from_bytes(body_bytes[idx:idx + 4], "big")
        chunk_type = body_bytes[idx + 4:idx + 8].decode("latin-1", errors="replace")
        chunk_data = body_bytes[idx + 8:idx + 8 + length]
        if chunk_type in ("tEXt", "iTXt", "zTXt"):
            try:
                out["chunks"].append({"type": chunk_type, "text": chunk_data.decode("utf-8", errors="replace")[:500]})
            except Exception:
                pass
        elif chunk_type == "eXIf":
            out["has_exif"] = True
        elif chunk_type == "gAMA":
            out["gamma"] = int.from_bytes(chunk_data, "big")
        elif chunk_type == "pHYs":
            out["physical_dimensions"] = int.from_bytes(chunk_data[:4], "big")
        elif chunk_type == "tIME":
            out["last_modified"] = chunk_data.hex()
        idx += 12 + length
    return out


def list_zip_contents(body_bytes):
    if not body_bytes or body_bytes[:4] != b"PK\x03\x04":
        return []
    try:
        with zipfile.ZipFile(BytesIO(body_bytes)) as zf:
            return zf.namelist()[:500]
    except Exception:
        return []


def list_tar_contents(body_bytes):
    if not body_bytes:
        return []
    try:
        with tarfile.open(fileobj=BytesIO(body_bytes), mode="r:*") as tf:
            return [m.name for m in tf.getmembers()[:500]]
    except Exception:
        return []


def parse_sql_dump(body_text):
    if not body_text:
        return {}
    tables = re.findall(r'CREATE\s+TABLE\s+[`"\']?(\w+)[`"\']?', body_text, re.IGNORECASE)
    inserts = re.findall(r'INSERT\s+INTO\s+[`"\']?(\w+)[`"\']?', body_text, re.IGNORECASE)
    hashes = _scan_hashed_passwords(body_text)
    return {"tables": tables[:200], "inserts": list(set(inserts))[:200], "hashes": hashes}


def parse_log_file(body_text):
    if not body_text:
        return {}
    ips = set(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', body_text))
    paths = set(re.findall(r'(?:GET|POST|PUT|DELETE)\s+(/[^\s]+)', body_text))
    users = set(re.findall(r'\buser[=:\s]+([A-Za-z0-9_\-\.]+)', body_text, re.IGNORECASE))
    return {"ips": sorted(ips)[:200], "paths": sorted(paths)[:200], "users": sorted(users)[:100]}


def parse_pem(body_text):
    if not body_text:
        return {}
    out = {}
    if "-----BEGIN CERTIFICATE-----" in body_text:
        out["certificate"] = True
    if "-----BEGIN PRIVATE KEY-----" in body_text or "-----BEGIN RSA PRIVATE KEY-----" in body_text:
        out["private_key"] = True
    if "-----BEGIN PUBLIC KEY-----" in body_text:
        out["public_key"] = True
    if "-----BEGIN CERTIFICATE REQUEST-----" in body_text:
        out["csr"] = True
    if out.get("certificate") and out.get("private_key"):
        out["key_matches_cert_candidate"] = True
    return out


def parse_pgp_key(body_text):
    if not body_text:
        return {}
    out = {}
    if "-----BEGIN PGP PUBLIC KEY BLOCK-----" in body_text:
        out["pgp_public"] = True
    if "-----BEGIN PGP PRIVATE KEY BLOCK-----" in body_text:
        out["pgp_private"] = True
    uid_matches = re.findall(r'(?:Comment|Name|Email):\s*([^\n]+)', body_text)
    if uid_matches:
        out["uids"] = uid_matches[:10]
    return out


def fingerprint_ssh_key(body_text):
    if not body_text:
        return {}
    out = {}
    if "ssh-rsa " in body_text:
        out["type"] = "RSA"
        m = re.search(r'ssh-rsa\s+([A-Za-z0-9+/=]+)', body_text)
        if m:
            try:
                raw = base64.b64decode(m.group(1) + "=" * (-len(m.group(1)) % 4))
                out["bits"] = (len(raw) - 11) * 8
                digest = hashlib.sha256(raw).digest()
                out["sha256_fingerprint"] = "SHA256:" + base64.b64encode(digest).decode().rstrip("=")
            except Exception:
                pass
    elif "ssh-ed25519 " in body_text:
        out["type"] = "ED25519"
        out["bits"] = 256
        m = re.search(r'ssh-ed25519\s+([A-Za-z0-9+/=]+)', body_text)
        if m:
            try:
                raw = base64.b64decode(m.group(1) + "=" * (-len(m.group(1)) % 4))
                digest = hashlib.sha256(raw).digest()
                out["sha256_fingerprint"] = "SHA256:" + base64.b64encode(digest).decode().rstrip("=")
            except Exception:
                pass
    elif "ecdsa-sha2-" in body_text:
        out["type"] = "ECDSA"
        m = re.search(r'ecdsa-sha2-(\w+)\s+([A-Za-z0-9+/=]+)', body_text)
        if m:
            try:
                raw = base64.b64decode(m.group(2) + "=" * (-len(m.group(2)) % 4))
                digest = hashlib.sha256(raw).digest()
                out["sha256_fingerprint"] = "SHA256:" + base64.b64encode(digest).decode().rstrip("=")
                out["curve"] = m.group(1)
            except Exception:
                pass
    elif "ssh-dss " in body_text:
        out["type"] = "DSA"
    elif "ssh-rsa-cert" in body_text:
        out["type"] = "RSA-CERT"
    elif "ssh-ed25519-cert" in body_text:
        out["type"] = "ED25519-CERT"
    return out


def parse_torrent(body_bytes):
    if not body_bytes or body_bytes[:1] != b"d":
        return {}
    text = body_bytes[:100000].decode("latin-1", errors="ignore")
    out = {}
    announce = re.findall(r'8:announce\d+:([^\d]+)', text)
    if announce:
        out["trackers"] = announce[:20]
    name = re.findall(r'4:name(\d+):([^\d]+)', text)
    if name:
        out["name"] = name[0][1][:200]
    return out


def parse_ics(body_text):
    if not body_text or "BEGIN:VCALENDAR" not in body_text:
        return {}
    events = re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', body_text, re.DOTALL)
    out = {"events": []}
    for ev in events[:100]:
        summary = re.search(r'SUMMARY:(.*?)[\r\n]', ev)
        dtstart = re.search(r'DTSTART[^:]*:(.*?)[\r\n]', ev)
        organizer = re.search(r'ORGANIZER[^:]*:(.*?)[\r\n]', ev)
        attendee = re.findall(r'ATTENDEE[^:]*:(.*?)[\r\n]', ev)
        out["events"].append({
            "summary": summary.group(1) if summary else None,
            "start": dtstart.group(1) if dtstart else None,
            "organizer": organizer.group(1) if organizer else None,
            "attendees": attendee[:50],
        })
    return out


def parse_rss(body_text):
    if not body_text:
        return {}
    if "<rss" in body_text.lower():
        items = re.findall(r'<item>(.*?)</item>', body_text, re.DOTALL | re.IGNORECASE)
        titles = re.findall(r'<title[^>]*>(.*?)</title>', body_text, re.DOTALL | re.IGNORECASE)
        return {"type": "RSS", "items": len(items), "titles": [t[:200] for t in titles[:50]]}
    if "<feed" in body_text.lower():
        entries = re.findall(r'<entry>(.*?)</entry>', body_text, re.DOTALL | re.IGNORECASE)
        return {"type": "Atom", "entries": len(entries)}
    return {}


def analyze_documents(docs, workers=6, limit=100):
    findings = {}

    def work(d):
        raw = wayback_raw_url(d["last_captured"], d["url"])
        body = http_get_bytes(raw, timeout=20, max_bytes=20 * 1024 * 1024)
        if not body:
            return d["url"], {}
        ext = d["extension"]
        if ext == ".pdf":
            return d["url"], extract_pdf_metadata(body)
        if ext in (".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".doc", ".xls", ".ppt"):
            return d["url"], extract_office_metadata(body, ext)
        if ext in (".jpg", ".jpeg"):
            return d["url"], extract_exif(body)
        if ext == ".png":
            return d["url"], extract_png_chunks(body)
        if ext in (".zip", ".docx", ".xlsx", ".pptx"):
            return d["url"], {"zip_contents": list_zip_contents(body)}
        if ext in (".tar", ".gz", ".tgz"):
            return d["url"], {"tar_contents": list_tar_contents(body)}
        if ext == ".sql":
            return d["url"], parse_sql_dump(body.decode("utf-8", errors="replace"))
        if ext == ".log":
            return d["url"], parse_log_file(body.decode("utf-8", errors="replace"))
        if ext in (".pem", ".crt", ".key"):
            return d["url"], parse_pem(body.decode("utf-8", errors="replace"))
        if ext == ".asc" or b"-----BEGIN PGP" in body[:200]:
            return d["url"], parse_pgp_key(body.decode("utf-8", errors="replace"))
        if ext == ".pub" and b"ssh-" in body[:200]:
            return d["url"], fingerprint_ssh_key(body.decode("utf-8", errors="replace"))
        if ext == ".torrent":
            return d["url"], parse_torrent(body)
        if ext == ".ics":
            return d["url"], parse_ics(body.decode("utf-8", errors="replace"))
        if ext in (".rss", ".atom", ".xml"):
            return d["url"], parse_rss(body.decode("utf-8", errors="replace"))
        return d["url"], {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, d) for d in docs[:limit]]
        for fut in concurrent.futures.as_completed(futures):
            try:
                u, meta = fut.result()
            except Exception:
                continue
            if meta:
                findings[u] = meta
    return findings


def content_type_breakdown(snapshots):
    return Counter(s.get("mimetype", "unknown") for s in snapshots)


def status_code_breakdown(snapshots):
    return Counter(s.get("statuscode", "unknown") for s in snapshots)


def url_depth_distribution(urls):
    depths = Counter()
    for u in urls:
        depths[len([x for x in urllib.parse.urlparse(u).path.split("/") if x])] += 1
    return dict(sorted(depths.items()))


def extract_query_params(urls):
    params = Counter()
    for u in urls:
        q = urllib.parse.urlparse(u).query
        if not q:
            continue
        for k, _ in urllib.parse.parse_qsl(q, keep_blank_values=True):
            params[k] += 1
    return dict(params.most_common())


def extract_file_extensions(urls):
    exts = Counter()
    for u in urls:
        ext = Path(urllib.parse.urlparse(u).path).suffix.lower() or "(none)"
        exts[ext] += 1
    return dict(exts.most_common())


def capture_timeline(snapshots):
    by_month = Counter()
    for s in snapshots:
        by_month[s["timestamp"][:6]] += 1
    return dict(sorted(by_month.items()))


def find_capture_gaps(timeline, gap_threshold_months=6):
    months = sorted(timeline.keys())
    gaps = []
    for i in range(1, len(months)):
        y1, m1 = int(months[i-1][:4]), int(months[i-1][4:6])
        y2, m2 = int(months[i][:4]), int(months[i][4:6])
        diff = (y2 - y1) * 12 + (m2 - m1)
        if diff >= gap_threshold_months:
            gaps.append({"from": months[i-1], "to": months[i], "months_gap": diff})
    return gaps


def first_last_seen(snapshots):
    if not snapshots:
        return {}
    ts_sorted = sorted(s["timestamp"] for s in snapshots)
    return {
        "first": ts_sorted[0], "last": ts_sorted[-1],
        "total": len(ts_sorted),
        "unique_digests": len(set(s.get("digest", "") for s in snapshots)),
    }


def digest_change_rate(snapshots):
    if not snapshots:
        return 0.0
    digests = [s.get("digest", "") for s in snapshots if s.get("digest")]
    if not digests:
        return 0.0
    return round(len(set(digests)) / len(digests), 4)


def digest_clustering(by_url):
    digest_to_urls = defaultdict(set)
    for u, caps in by_url.items():
        for c in caps:
            d = c.get("digest")
            if d:
                digest_to_urls[d].add(u)
    return {d: sorted(urls) for d, urls in digest_to_urls.items() if len(urls) > 1}


def urlkey_analysis(snapshots):
    urlkeys = Counter()
    for s in snapshots:
        uk = s.get("urlkey")
        if uk:
            urlkeys[uk] += 1
    return dict(urlkeys.most_common(500))


def snapshot_count_ranking(by_url):
    counts = [(u, len(caps)) for u, caps in by_url.items()]
    counts.sort(key=lambda x: -x[1])
    return counts[:200]


def detect_revisit_records(snapshots):
    return [s for s in snapshots if "revisit" in (s.get("mimetype", "") or "").lower()]


def extract_archive_src(header_map):
    out = {}
    for u, d in header_map.items():
        h = {k.lower(): v for k, v in (d.get("headers") or {}).items()}
        src = h.get("x-archive-src")
        if src:
            out[u] = src
    return out


def harvest_live_headers(by_url, workers=8, limit=500):
    urls = list(by_url.keys())
    if limit:
        urls = urls[:limit]
    T("PHASE", f"live header harvest for {len(urls)} url(s)")
    out = {}

    def work(u):
        status, headers = http_head_full(u)
        return u, status, headers

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, u) for u in urls]
        for fut in concurrent.futures.as_completed(futures):
            try:
                u, status, headers = fut.result()
            except Exception:
                continue
            out[u] = {"status": status, "headers": headers}
    return out


def summarize_headers(header_map):
    servers = Counter()
    powered_by = Counter()
    generators = Counter()
    security_present = Counter()
    cdn_hits = Counter()
    cookies = Counter()
    tech_signals = set()
    cookie_flags = Counter()

    for u, d in header_map.items():
        h = {k.lower(): v for k, v in (d.get("headers") or {}).items()}
        if "server" in h:
            servers[h["server"]] += 1
        if "x-powered-by" in h:
            powered_by[h["x-powered-by"]] += 1
        if "x-generator" in h:
            generators[h["x-generator"]] += 1
        for sh in SECURITY_HEADERS:
            if sh in h:
                security_present[sh] += 1
        for ck in ("cf-ray", "x-amz-cf-id", "x-vercel-id", "x-netlify-request-id", "x-fastly-request-id", "x-served-by", "x-varnish", "x-cache"):
            if ck in h:
                cdn_hits[ck] += 1
        if "set-cookie" in h:
            for cookie in re.split(r',\s*(?=[A-Za-z_][A-Za-z0-9_\-]*=)', h["set-cookie"]):
                name = cookie.split("=")[0].strip()
                if name:
                    cookies[name] += 1
                if "secure" in cookie.lower():
                    cookie_flags["Secure"] += 1
                if "httponly" in cookie.lower():
                    cookie_flags["HttpOnly"] += 1
                if "samesite" in cookie.lower():
                    ss = re.search(r'samesite=(\w+)', cookie, re.I)
                    if ss:
                        cookie_flags[f"SameSite={ss.group(1)}"] += 1
        server_str = (h.get("server", "") + " " + h.get("x-powered-by", "")).lower()
        for tech in ("nginx", "apache", "iis", "cloudflare", "gunicorn", "express", "php", "asp.net", "openresty", "litespeed", "caddy", "envoy", "traefik", "tomcat", "jetty", "undertow", "netty", "kestrel", "puma", "unicorn", "passenger", "uwsgi", "gunicorn", "waitress", "cherrypy", "bottle", "falcon", "pyramid", "turbogears", "zope", "plone", "werkzeug", "django", "flask", "fastapi", "starlette", "uvicorn", "hypercorn", "daphne", "meinheld", "bjoern", "twisted", "tornado", "aiohttp", "sanic", "quart", "express", "koa", "hapi", "sails", "meteor", "adonis", "nestjs", "fastify", "spring", "springboot"):
            if tech in server_str:
                tech_signals.add(tech)

    return {
        "servers": dict(servers.most_common()),
        "powered_by": dict(powered_by.most_common()),
        "generators": dict(generators.most_common()),
        "security_headers_present": dict(security_present.most_common()),
        "security_headers_missing": [h for h in SECURITY_HEADERS if h not in security_present],
        "cdn_headers": dict(cdn_hits.most_common()),
        "cookie_names": dict(cookies.most_common()),
        "cookie_flags": dict(cookie_flags.most_common()),
        "tech_signals": sorted(tech_signals),
    }


def fetch_cert_info(host, port=443):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return {"error": "no cert"}
                return {
                    "subject": dict(x[0] for x in cert.get("subject", [])),
                    "issuer": dict(x[0] for x in cert.get("issuer", [])),
                    "version": cert.get("version"),
                    "serialNumber": cert.get("serialNumber"),
                    "notBefore": cert.get("notBefore"),
                    "notAfter": cert.get("notAfter"),
                    "subjectAltName": cert.get("subjectAltName", []),
                }
    except Exception as e:
        return {"error": str(e)}


def resolve_dns(host):
    out = {}
    try:
        out["ipv4"] = sorted(set(socket.gethostbyname_ex(host)[2]))
    except Exception as e:
        out["ipv4_error"] = str(e)
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET6)
        out["ipv6"] = sorted(set(i[4][0] for i in infos))
    except Exception:
        out["ipv6"] = []
    return out


def diff_robots_sitemaps(domain, date_from=None, date_to=None):
    out = {}
    try:
        robots_history = fetch_special_file_history(domain, "robots.txt", date_from, date_to)
        if len(robots_history) >= 2:
            first = parse_robots_txt(robots_history[0]["content_preview"])
            last = parse_robots_txt(robots_history[-1]["content_preview"])
            out["robots"] = {
                "added_disallow": list(set(last.get("disallow", [])) - set(first.get("disallow", []))),
                "removed_disallow": list(set(first.get("disallow", [])) - set(last.get("disallow", []))),
            }
    except Exception:
        pass
    try:
        sitemap_history = fetch_special_file_history(domain, "sitemap.xml", date_from, date_to)
        if len(sitemap_history) >= 2:
            first = parse_sitemap_xml(sitemap_history[0]["content_preview"])
            last = parse_sitemap_xml(sitemap_history[-1]["content_preview"])
            out["sitemap"] = {
                "added_urls": list(set(last.get("urls", [])) - set(first.get("urls", []))),
                "removed_urls": list(set(first.get("urls", [])) - set(last.get("urls", []))),
            }
    except Exception:
        pass
    return out


def cross_reference_disallow(robots_parsed, snapshots):
    if not robots_parsed or not robots_parsed.get("disallow"):
        return []
    disallowed = set()
    for d in robots_parsed["disallow"]:
        d = d.strip()
        if not d or d == "/":
            continue
        if "*" in d:
            d = d.replace("*", "")
        disallowed.add(d)
    hits = []
    for s in snapshots:
        u = s.get("original", "")
        path = urllib.parse.urlparse(u).path
        for d in disallowed:
            if d and (path == d or path.startswith(d)):
                hits.append({"url": u, "rule": d, "timestamp": s.get("timestamp")})
                break
        if len(hits) >= 500:
            break
    return hits


def detect_archive_exclusions(header_map):
    excluded = []
    for u, d in header_map.items():
        h = {k.lower(): v for k, v in (d.get("headers") or {}).items()}
        tag = h.get("x-robots-tag", "")
        if tag and any(x in tag.lower() for x in ("noarchive", "unavailable_after", "noindex", "nofollow")):
            excluded.append({"url": u, "x_robots_tag": tag})
    return excluded


def filter_results(results, path_contains=None, mimetype=None, only_removed=False):
    out = results
    if path_contains:
        out = [r for r in out if path_contains in r["original"]]
    if mimetype:
        out = [r for r in out if mimetype in r.get("mimetype", "")]
    if only_removed:
        out = [r for r in out if r.get("likely_removed")]
    return out


def build_url_results(by_url, status_map=None, deletion_classes=None):
    results = []
    for u, caps in by_url.items():
        latest = caps[-1]
        live = status_map.get(u) if status_map else None
        likely_removed = None if status_map is None else ((live is None) or (live >= 400))
        row = {
            **latest,
            "live_status": live,
            "likely_removed": likely_removed,
            "snapshot_count": len(caps),
            "first_captured": caps[0]["timestamp"],
            "last_captured": caps[-1]["timestamp"],
        }
        if deletion_classes:
            row["deletion_class"] = deletion_classes.get(u)
        results.append(row)
    return results


def build_path_tree(urls):
    tree = {}
    for u in urls:
        path = urllib.parse.urlparse(u).path
        node = tree
        for part in [p for p in path.split("/") if p]:
            node = node.setdefault(part, {})
    return tree


def build_external_domain_graph(page_intel):
    graph = {}
    for u, ts_map in page_intel.items():
        for ts, intel in ts_map.items():
            for l in (intel.get("external_links") or []):
                host = urllib.parse.urlparse(l).netloc
                if not host:
                    continue
                e = graph.setdefault(host, {"first": ts, "last": ts, "hits": 0})
                if ts < e["first"]:
                    e["first"] = ts
                if ts > e["last"]:
                    e["last"] = ts
                e["hits"] += 1
    return graph


def build_form_endpoint_history(page_intel):
    out = {}
    for u, ts_map in page_intel.items():
        for ts, intel in ts_map.items():
            for form in (intel.get("forms") or []):
                action = form.get("action")
                if action:
                    out.setdefault(action, []).append({"timestamp": ts, "url": u})
    return out


def build_query_param_evolution(by_url):
    out = {}
    for u, caps in by_url.items():
        path = urllib.parse.urlparse(u).path
        series = out.setdefault(path, [])
        for c in caps:
            q = urllib.parse.urlparse(c["original"]).query
            if q:
                params = sorted(set(k for k, _ in urllib.parse.parse_qsl(q, keep_blank_values=True)))
                series.append({"timestamp": c["timestamp"], "params": params})
    return out


def build_secret_age_estimation(page_intel):
    seen = {}
    for u, ts_map in page_intel.items():
        for ts, intel in ts_map.items():
            for name, data in (intel.get("secrets") or {}).items():
                vals = data.get("values", []) if isinstance(data, dict) else data
                for v in vals:
                    key = (name, v)
                    e = seen.setdefault(key, {"first": ts, "last": ts})
                    if ts < e["first"]:
                        e["first"] = ts
                    if ts > e["last"]:
                        e["last"] = ts
    out = {}
    for (name, v), info in seen.items():
        out.setdefault(name, []).append({"value": v, "first": info["first"], "last": info["last"]})
    return out


def build_redirect_chains(by_url):
    chains = {}
    for u, caps in by_url.items():
        seen = []
        for c in caps:
            code = c.get("statuscode", "")
            if code in ("301", "302", "303", "307", "308"):
                tgt = c.get("redirect") or ""
                if tgt:
                    seen.append({"timestamp": c["timestamp"], "status": code, "target": tgt})
        if len(seen) >= 2:
            chains[u] = seen
    return chains


def correlate_passive_crawl(cdx_snaps, common_crawl):
    cdx_urls = set()
    for s in cdx_snaps:
        u = s.get("original")
        if u:
            cdx_urls.add(u)
    cc_urls = set()
    for r in (common_crawl or {}).get("results", []):
        u = r.get("url")
        if u:
            cc_urls.add(u)
    only_cdx = sorted(cdx_urls - cc_urls)[:500]
    only_cc = sorted(cc_urls - cdx_urls)[:500]
    both = sorted(cdx_urls & cc_urls)[:500]
    return {"only_in_cdx": only_cdx, "only_in_cc": only_cc, "in_both": both,
            "cdx_count": len(cdx_urls), "cc_count": len(cc_urls)}


def _flatten_secrets_for_report(secrets_obj):
    out = {}
    for k, v in (secrets_obj or {}).items():
        if isinstance(v, dict):
            out[k] = v
        else:
            out[k] = {"severity": "info", "values": list(v)}
    return out


def _dedupe_secrets_across(secrets_by_source):
    agg = {}
    for src, secrets in secrets_by_source.items():
        for name, data in _flatten_secrets_for_report(secrets).items():
            entry = agg.setdefault(name, {"severity": data.get("severity", "info"), "values": set(), "sources": set()})
            entry["values"].update(data.get("values", []))
            entry["sources"].add(src)
    return {
        name: {
            "severity": e["severity"],
            "values": sorted(e["values"])[:200],
            "sources": sorted(e["sources"])[:50],
        }
        for name, e in agg.items()
    }


_CRED_SECTION_CACHE = {}
_CRED_CACHE_LOCK = threading.Lock()


def build_credential_section(aggregated_secrets, source_map, domain=""):
    key = (id(aggregated_secrets), id(source_map), domain)
    with _CRED_CACHE_LOCK:
        cached = _CRED_SECTION_CACHE.get(key)
    if cached is not None:
        return cached
    out = {}
    c = cache()
    for name, data in aggregated_secrets.items():
        sev = data.get("severity", "info")
        values = data.get("values", [])
        sources = data.get("sources", [])
        first_seen = None
        last_seen = None
        for src in sources:
            entry = source_map.get(src)
            if not entry:
                continue
            ts = entry.get("_ts") if isinstance(entry, dict) else None
            if not ts:
                continue
            if first_seen is None or ts < first_seen:
                first_seen = ts
            if last_seen is None or ts > last_seen:
                last_seen = ts
        rotation_count = 0
        value_history = {}
        if c and domain:
            hist = c.all_values_for_pattern(domain, name)
            vals = set()
            for h in hist:
                vals.add(h["value"])
            rotation_count = max(0, len(vals) - 1)
            for h in hist:
                value_history.setdefault(h["value"], []).append(h["ts"])
        context = "unknown"
        joined = " ".join(str(s) for s in sources).lower()
        if "prod" in joined:
            context = "production"
        elif "stag" in joined:
            context = "staging"
        elif "dev" in joined or "test" in joined:
            context = "dev"
        score = sev
        if rotation_count == 0 and sev in ("critical", "high"):
            score = sev + "+"
        if context == "production" and sev in ("critical", "high"):
            score = sev + "++"
        out[name] = {
            "severity": sev,
            "score": score,
            "count": len(values),
            "first_seen": first_seen,
            "last_seen": last_seen,
            "rotation": "rotated" if rotation_count > 0 else ("static" if rotation_count == 0 else "unknown"),
            "rotation_count": rotation_count,
            "context": context,
            "values": values[:50],
            "sources": sources[:50],
            "value_history": {v: h[:20] for v, h in list(value_history.items())[:20]},
        }
    with _CRED_CACHE_LOCK:
        _CRED_SECTION_CACHE[key] = out
    return out


def build_evidence_bundle(out_dir, domain, results, extras, aggregated_secrets, sources):
    prov = {
        "domain": domain,
        "generated": datetime.now(timezone.utc).isoformat(),
        "secrets": {},
        "urls": {},
        "subdomains": {},
    }
    for name, data in aggregated_secrets.items():
        prov["secrets"][name] = {
            "severity": data.get("severity", "info"),
            "count": len(data.get("values", [])),
            "values": data.get("values", [])[:200],
            "sources": data.get("sources", [])[:200],
        }
    for r in results:
        u = r.get("original")
        if not u:
            continue
        prov["urls"][u] = {
            "last_captured": r.get("last_captured"),
            "first_captured": r.get("first_captured"),
            "snapshot_count": r.get("snapshot_count"),
            "live_status": r.get("live_status"),
            "likely_removed": r.get("likely_removed"),
        }
    for s, info in (extras.get("subdomain_stats") or {}).items():
        prov["subdomains"][s] = info
    p = Path(out_dir) / f"{re.sub(r'[^a-zA-Z0-9.-]', '_', domain)}_provenance.json"
    try:
        p.write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")
        T("RAW", f"provenance -> {p}")
    except Exception as e:
        T("WARN", f"provenance write failed: {e}")


def build_coverage_report(out_dir, domain, results, extras):
    cov = {
        "domain": domain,
        "generated": datetime.now(timezone.utc).isoformat(),
        "urls_total": len(results),
        "urls_removed": sum(1 for r in results if r.get("likely_removed")),
        "urls_live": sum(1 for r in results if r.get("likely_removed") is False),
        "snapshots_total": extras.get("total_snapshots", 0),
        "subdomains": len(extras.get("subdomains", [])),
        "documents": len(extras.get("documents", [])),
        "special_files_found": len(extras.get("special_files", {})),
        "js_bundles_scanned": len(extras.get("js_bundle_secrets", {})),
        "source_maps_scanned": len(extras.get("source_map_secrets", {})),
        "special_files_scanned": len(extras.get("special_file_scans", {})),
        "ports_open": len(extras.get("ports", {})),
        "frameworks_hit": sum(len(v) for v in (extras.get("framework_endpoints") or {}).values()),
        "cloud_buckets_hit": sum(len(v) for v in (extras.get("cloud_buckets") or {}).values()),
        "patterns_checked": len(COMPILED_SECRETS),
        "patterns_that_hit": [],
        "patterns_that_missed": [],
    }
    seen = set()
    for u, ts_map in (extras.get("page_intel") or {}).items():
        for ts, intel in ts_map.items():
            for k in (intel.get("secrets") or {}).keys():
                seen.add(k)
    for u, hits in (extras.get("js_bundle_secrets") or {}).items():
        for k in hits.keys():
            seen.add(k)
    for u, hits in (extras.get("source_map_secrets") or {}).items():
        for k in hits.keys():
            seen.add(k)
    for f, data in (extras.get("special_file_scans") or {}).items():
        for k in (data.get("secrets") or {}).keys():
            seen.add(k)
    cov["patterns_that_hit"] = sorted(seen)
    cov["patterns_that_missed"] = sorted(set(COMPILED_SECRETS.keys()) - seen)
    p = Path(out_dir) / f"{re.sub(r'[^a-zA-Z0-9.-]', '_', domain)}_coverage.json"
    try:
        p.write_text(json.dumps(cov, indent=2, default=str), encoding="utf-8")
        T("COVERAGE", f"coverage -> {p}")
    except Exception as e:
        T("WARN", f"coverage write failed: {e}")


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    T("REPORT", f"JSON -> {path}")


def write_csv(path, results):
    if not results:
        Path(path).write_text("", encoding="utf-8")
        return
    all_keys = set()
    for r in results:
        all_keys.update(r.keys())
    all_keys.discard("archive_url")
    fieldnames = sorted(all_keys) + ["archive_url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in results:
            row = {k: r.get(k, "") for k in fieldnames}
            row["archive_url"] = wayback_snapshot_url(r.get("timestamp", ""), r.get("original", ""))
            w.writerow(row)


def _fmt_ts(ts):
    try:
        return datetime.strptime(ts, "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def _section(txt_lines, title):
    txt_lines.append("")
    txt_lines.append("=" * 100)
    txt_lines.append(f" {title}")
    txt_lines.append("=" * 100)


def write_txt(path, domain, results, extras, aggregated_secrets, source_map):
    L = []
    L.append("=" * 100)
    L.append(f" STRATASCAN DETAILED REPORT - {domain}")
    L.append("=" * 100)
    L.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    L.append(f"UA mode: {UA_MODE}  |  Proxies: {PROXIES.status().get('enabled')} ({PROXIES.status().get('count')})")
    L.append(f"Total snapshots: {extras.get('total_snapshots', 0)}")
    L.append(f"Unique URLs: {len(results)}")
    L.append(f"Likely removed: {sum(1 for r in results if r.get('likely_removed'))}")
    L.append(f"Still live: {sum(1 for r in results if r.get('likely_removed') is False)}")

    _section(L, "SECTION 0 - CREDENTIALS (FOCUSED)")
    credentials = build_credential_section(aggregated_secrets, source_map, domain=domain)
    if credentials:
        for name, data in sorted(credentials.items(), key=lambda x: -len(x[1]["values"])):
            L.append("")
            L.append(f"  [{data['score']}] {name}")
            L.append(f"    count={data['count']}  context={data['context']}  rotation={data['rotation']}  rotations_seen={data['rotation_count']}")
            if data["first_seen"]:
                L.append(f"    first_seen={data['first_seen']}  last_seen={data['last_seen']}")
            for v in data["values"][:20]:
                L.append(f"      value: {v[:200]}")
            for s in data["sources"][:10]:
                L.append(f"      source: {s}")
    else:
        L.append("  (none)")

    _section(L, "SECTION 1 - LIKELY REMOVED PAGES")
    removed = [r for r in results if r.get("likely_removed")]
    if removed:
        for r in sorted(removed, key=lambda x: x["timestamp"], reverse=True)[:500]:
            L.append("")
            L.append(f"  URL: {r['original']}")
            L.append(f"    Last captured: {_fmt_ts(r['timestamp'])}")
            L.append(f"    HTTP: {r.get('statuscode')}  MIME: {r.get('mimetype')}")
            L.append(f"    Snaps: {r.get('snapshot_count')}  Deletion: {r.get('deletion_class')}")
            L.append(f"    Live: {r.get('live_status')}")
            L.append(f"    Archive: {wayback_snapshot_url(r['timestamp'], r['original'])}")
    else:
        L.append("  (none)")

    _section(L, "SECTION 2 - STILL LIVE PAGES")
    live = [r for r in results if r.get("likely_removed") is False]
    if live:
        for r in sorted(live, key=lambda x: x["timestamp"], reverse=True)[:500]:
            L.append("")
            L.append(f"  URL: {r['original']}")
            L.append(f"    Last captured: {_fmt_ts(r['timestamp'])}  HTTP: {r.get('live_status')}")
            L.append(f"    Archive: {wayback_snapshot_url(r['timestamp'], r['original'])}")
    else:
        L.append("  (none)")

    _section(L, "SECTION 3 - AGGREGATED SECRETS")
    if aggregated_secrets:
        for name, data in sorted(aggregated_secrets.items(), key=lambda x: -len(x[1].get("values", []))):
            L.append("")
            L.append(f"  [{data.get('severity','?').upper()}] {name} - {len(data.get('values',[]))} value(s)")
            for v in data.get("values", [])[:50]:
                L.append(f"      value: {v[:300]}")
            for s in data.get("sources", [])[:20]:
                L.append(f"      source: {s}")
    else:
        L.append("  (none)")

    _section(L, "SECTION 4 - SECRET PROVENANCE")
    for src, secs in source_map.items():
        if not secs:
            continue
        L.append("")
        L.append(f"  SOURCE: {src}")
        for name, data in secs.items():
            if name.startswith("_"):
                continue
            vals = data.get("values", []) if isinstance(data, dict) else data
            sev = data.get("severity", "info") if isinstance(data, dict) else "info"
            for v in list(vals)[:20]:
                L.append(f"    [{sev}] {name}: {v[:300]}")

    _section(L, "SECTION 5 - DELETION TIMELINES")
    for u, data in list(extras.get("deletion_timelines", {}).items())[:500]:
        L.append("")
        L.append(f"  URL: {u}")
        L.append(f"    Last OK: {_fmt_ts(data.get('last_ok',''))}  First Bad: {_fmt_ts(data.get('first_bad',''))}")
        L.append(f"    Type: {data.get('type')}  Snaps: {data.get('total_snapshots')}")

    _section(L, "SECTION 6 - MASS DELETION EVENTS")
    for c in extras.get("mass_deletion_clusters", []):
        L.append("")
        L.append(f"  Timestamp: {_fmt_ts(c['timestamp'])}  Count: {c['count']}")
        for u in c.get("sample", []):
            L.append(f"      {u}")

    _section(L, "SECTION 7 - SUBDOMAINS")
    for s in extras.get("subdomains", []):
        L.append(f"  {s}")
    for s, d in extras.get("subdomain_stats", {}).items():
        L.append(f"    {s}  first={_fmt_ts(d.get('first',''))}  last={_fmt_ts(d.get('last',''))}  count={d.get('count')}")

    _section(L, "SECTION 8 - SUBDOMAIN TAKEOVER CANDIDATES")
    for t in extras.get("subdomain_takeover_candidates", []):
        L.append(f"  {t['subdomain']}  reason={t.get('reason')}")

    _section(L, "SECTION 9 - SUBDOMAIN PERMUTATIONS")
    for p in extras.get("subdomain_permutations", []):
        L.append(f"  {p}")

    _section(L, "SECTION 10 - SUBDOMAIN BRUTE-FORCE")
    for r in extras.get("subdomain_brute", []):
        L.append(f"  {r['host']} -> {r.get('ips')}")

    _section(L, "SECTION 11 - CT LOG NAMES")
    for n in extras.get("ct_names", []):
        L.append(f"  {n}")

    _section(L, "SECTION 12 - COMMON CRAWL")
    cc = extras.get("common_crawl", {})
    if cc:
        L.append(f"  Latest crawl: {cc.get('latest_crawl')}")
        for r in cc.get("results", [])[:200]:
            L.append(f"    {r.get('url','')}  status={r.get('status')}  mime={r.get('mime')}")

    _section(L, "SECTION 13 - RDAP WHOIS")
    rdap = extras.get("rdap", {})
    if rdap:
        for k in ("handle", "ldhName", "status", "events", "nameservers"):
            L.append(f"  {k}: {rdap.get(k)}")
        for e in rdap.get("entities", []):
            L.append(f"    Entity roles={e.get('roles')} name={e.get('name')} email={e.get('email')}")

    _section(L, "SECTION 14 - LEGACY WHOIS")
    whois_data = extras.get("whois", {})
    if whois_data:
        L.append(f"  Referral: {whois_data.get('referral')}")
        for ln in whois_data.get("raw", "").splitlines()[:50]:
            L.append(f"    {ln}")
        for ln in whois_data.get("registrar_raw", "").splitlines()[:100]:
            L.append(f"    {ln}")

    _section(L, "SECTION 15 - DNS RECORDS")
    for rtype, records in extras.get("dns_full", {}).items():
        L.append(f"  {rtype}:")
        for r in records:
            L.append(f"    {r}")

    _section(L, "SECTION 16 - DNS SRV")
    for name, records in extras.get("dns_srv", {}).items():
        L.append(f"  {name}: {records}")

    _section(L, "SECTION 17 - DNS TLSA")
    for name, records in extras.get("dns_tlsa", {}).items():
        L.append(f"  {name}: {records}")

    _section(L, "SECTION 18 - DNS SMIMEA")
    for name, records in extras.get("dns_smimea", {}).items():
        L.append(f"  {name}: {records}")

    _section(L, "SECTION 19 - DKIM SELECTORS")
    for sel, records in extras.get("dkim_selectors", {}).items():
        L.append(f"  {sel}: {records[:2]}")

    _section(L, "SECTION 20 - BIMI")
    bimi = extras.get("bimi", {})
    if bimi:
        L.append(f"  {bimi.get('name')}: {bimi.get('records')}")

    _section(L, "SECTION 21 - DNSSEC")
    L.append(f"  Validated: {extras.get('dnssec')}")

    _section(L, "SECTION 22 - WILDCARD DNS")
    L.append(f"  Detected: {extras.get('wildcard_dns')}")

    _section(L, "SECTION 23 - AXFR")
    for r in extras.get("axfr", []):
        L.append(f"  {r}")

    _section(L, "SECTION 24 - REVERSE DNS")
    for ip, host in extras.get("ptr", {}).items():
        L.append(f"  {ip} -> {host}")

    _section(L, "SECTION 25 - ASN + GEO")
    for k, v in extras.get("asn", {}).items():
        L.append(f"  {k}: {v}")

    _section(L, "SECTION 26 - PORT SCAN")
    for port, info in extras.get("ports", {}).items():
        L.append(f"  {port}/{info.get('service','')}  banner={info.get('banner','')[:200]}")

    _section(L, "SECTION 27 - TLS CERTIFICATE")
    for k, v in extras.get("tls", {}).items():
        L.append(f"  {k}: {v}")

    _section(L, "SECTION 28 - TLS VERSIONS")
    for v, s in extras.get("tls_versions", {}).items():
        L.append(f"  {v}: {'SUPPORTED' if s else 'not supported'}")

    _section(L, "SECTION 29 - TLS CIPHERS")
    for c, info in extras.get("tls_ciphers", {}).items():
        L.append(f"  {c} [{info.get('strength')}]: {'SUPPORTED' if info.get('supported') else 'no'}")

    _section(L, "SECTION 30 - TLS CHAIN")
    L.append(f"  {extras.get('tls_chain', {})}")

    _section(L, "SECTION 31 - HSTS PRELOAD")
    L.append(f"  {extras.get('hsts_preload', {})}")

    _section(L, "SECTION 32 - OCSP/CRL")
    L.append(f"  {extras.get('ocsp', {})}")

    _section(L, "SECTION 33 - HTTP/2")
    L.append(f"  ALPN: {extras.get('http2_proto')}")

    _section(L, "SECTION 34 - WAF")
    for w in extras.get("waf", []):
        L.append(f"  {w}")

    _section(L, "SECTION 35 - CORS")
    L.append(f"  {extras.get('cors', {})}")

    _section(L, "SECTION 36 - RATE LIMIT")
    for k, v in extras.get("rate_limit_headers", {}).items():
        L.append(f"  {k}: {v}")

    _section(L, "SECTION 37 - HEADER SUMMARY")
    for k, v in extras.get("header_summary", {}).items():
        L.append(f"  {k}: {v}")

    _section(L, "SECTION 38 - ARCHIVED HEADERS")
    for u, headers in list(extras.get("archived_headers", {}).items())[:100]:
        L.append(f"  URL: {u}")
        for k, v in headers.items():
            L.append(f"    {k}: {v[:300]}")

    _section(L, "SECTION 39 - ARCHIVED HEADER DIFFS")
    for u, diffs in list(extras.get("archived_header_diffs", {}).items())[:100]:
        L.append(f"  URL: {u}")
        for k, d in diffs.items():
            L.append(f"    {k}: first={d.get('first','')[:200]} last={d.get('last','')[:200]}")

    _section(L, "SECTION 40 - ARCHIVE EXCLUSIONS")
    for e in extras.get("archive_exclusions", []):
        L.append(f"  {e['url']}  tag={e['x_robots_tag']}")

    _section(L, "SECTION 41 - X-ARCHIVE-SRC")
    for u, src in extras.get("archive_src", {}).items():
        L.append(f"  {u} -> {src}")

    _section(L, "SECTION 42 - ROBTEX")
    for k, v in (extras.get("robtex") or {}).items():
        L.append(f"  {k}: {str(v)[:300]}")

    _section(L, "SECTION 43 - MNEMONIC")
    for k, v in (extras.get("mnemonic_pdns") or {}).items():
        L.append(f"  {k}: {str(v)[:300]}")

    _section(L, "SECTION 44 - HACKERTARGET")
    for k, v in (extras.get("hackertarget") or {}).items():
        L.append(f"  {k}: {str(v)[:500]}")

    _section(L, "SECTION 45 - CLOUD BUCKETS")
    for provider, items in extras.get("cloud_buckets", {}).items():
        L.append(f"  {provider}:")
        for i in items:
            L.append(f"    {i['status']}  {i['url']}")

    _section(L, "SECTION 46 - FRAMEWORK ENDPOINTS")
    for fw, items in extras.get("framework_endpoints", {}).items():
        L.append(f"  {fw}:")
        for i in items:
            L.append(f"    {i['status']}  {i['url']}")

    _section(L, "SECTION 47 - SPECIAL FILES")
    for fname, snaps in extras.get("special_files", {}).items():
        L.append(f"  {fname}  ({len(snaps)})")
        for s in snaps[:5]:
            L.append(f"    {_fmt_ts(s['timestamp'])}  status={s.get('statuscode')}  {s['archive']}")

    _section(L, "SECTION 48 - SPECIAL FILE SCANS")
    for fname, data in extras.get("special_file_scans", {}).items():
        L.append(f"  {fname}:")
        for name, vals in (data.get("secrets") or {}).items():
            if isinstance(vals, dict):
                L.append(f"    [{vals.get('severity')}] {name}: {vals.get('values')[:5]}")
            else:
                L.append(f"    {name}: {str(vals)[:200]}")
        struct = data.get("structural") or {}
        for k, v in struct.items():
            L.append(f"    [STRUCT] {k}: {v}")

    _section(L, "SECTION 49 - DOCUMENTS")
    for d in extras.get("documents", []):
        L.append(f"  [{d['extension']}] {d['url']}")
        L.append(f"    last={_fmt_ts(d['last_captured'])}  {d['archive_link']}")

    _section(L, "SECTION 50 - DOCUMENT METADATA")
    for url, meta in extras.get("document_metadata", {}).items():
        L.append(f"  {url}")
        for k, v in meta.items():
            L.append(f"    {k}: {v}")

    _section(L, "SECTION 51 - REDIRECTS")
    for r in extras.get("redirects", []):
        L.append(f"  {_fmt_ts(r['timestamp'])} {r['statuscode']}  {r['url']} -> {r.get('redirect_target','')}")

    _section(L, "SECTION 52 - JS BUNDLE SECRETS")
    for u, hits in extras.get("js_bundle_secrets", {}).items():
        L.append(f"  {u}")
        for name, data in hits.items():
            vals = data.get("values", []) if isinstance(data, dict) else data
            L.append(f"    {name}: {vals[:5]}")

    _section(L, "SECTION 53 - SOURCE MAP SECRETS")
    for u, hits in extras.get("source_map_secrets", {}).items():
        L.append(f"  {u}")
        for name, data in hits.items():
            vals = data.get("values", []) if isinstance(data, dict) else data
            L.append(f"    {name}: {vals[:5]}")

    _section(L, "SECTION 54 - JS DEOBFUSCATION")
    for u, hits in extras.get("js_deobfuscation", {}).items():
        L.append(f"  {u}")
        for k, vals in hits.items():
            L.append(f"    {k}: {vals[:10]}")

    _section(L, "SECTION 55 - PAGE INTELLIGENCE")
    for u, ts_map in extras.get("page_intel", {}).items():
        for ts, intel in ts_map.items():
            if not intel:
                continue
            L.append("")
            L.append(f"  URL: {u} @ {_fmt_ts(ts)}")
            L.append(f"    Archive: {wayback_snapshot_url(ts, u)}")
            for key in ("title", "generator", "canonical", "lang", "copyright_year",
                        "emails", "phones", "social_links", "cms_signatures",
                        "html_comments", "css_comments", "js_line_comments", "js_block_comments",
                        "hidden_elements", "websocket_urls", "graphql_queries",
                        "environment_names", "version_numbers", "console_logs",
                        "analytics_events", "js_error_messages", "nonces",
                        "possible_api_endpoints", "graphql_endpoints",
                        "login_forms", "stack_traces", "basic_auth_urls",
                        "url_param_creds", "phpinfo_data", "cloud_metadata_leak",
                        "initial_state_secrets", "next_data_secrets"):
                val = intel.get(key)
                if val:
                    L.append(f"    {key}: {val}")

    _section(L, "SECTION 56 - HIDDEN CONTENT")
    for u, ts_map in extras.get("page_intel", {}).items():
        for ts, intel in ts_map.items():
            for h in (intel.get("hidden_elements") or []):
                L.append(f"  {u} -> {h.get('tag')} [{h.get('style','')[:80]}] : {h.get('text','')[:300]}")

    _section(L, "SECTION 57 - HTML COMMENTS")
    for u, ts_map in extras.get("page_intel", {}).items():
        for ts, intel in ts_map.items():
            for c in (intel.get("html_comments_ctx") or []):
                L.append(f"  {u} @ {ts}: <!-- {c['comment'][:300]} -->")

    _section(L, "SECTION 58 - CSP DIRECTIVES")
    for u, ts_map in extras.get("page_intel", {}).items():
        for ts, intel in ts_map.items():
            if intel.get("csp_meta"):
                L.append(f"  {u} @ {ts}:")
                for k, v in intel["csp_meta"].items():
                    L.append(f"    {k}: {v}")

    _section(L, "SECTION 59 - JSON-LD")
    for u, ts_map in extras.get("page_intel", {}).items():
        for ts, intel in ts_map.items():
            if intel.get("jsonld"):
                L.append(f"  {u} @ {ts}: {len(intel['jsonld'])} block(s)")

    _section(L, "SECTION 60 - EMAIL PERMUTATIONS")
    for e in extras.get("email_permutations", []):
        L.append(f"  {e}")

    _section(L, "SECTION 61 - EMAIL MX")
    for e, data in extras.get("email_mx_validation", {}).items():
        L.append(f"  {e}: valid_mx={data.get('valid_mx')} mx={data.get('mx_records')}")

    _section(L, "SECTION 62 - CATCH-ALL")
    L.append(f"  {str(extras.get('catchall'))[:500]}")

    _section(L, "SECTION 63 - DORKS")
    for d in extras.get("dorks", []):
        L.append(f"  {d}")

    _section(L, "SECTION 64 - ROBOTS.TXT")
    for k, v in extras.get("robots_parsed", {}).items():
        L.append(f"  {k}: {v}")

    _section(L, "SECTION 65 - SITEMAP.XML")
    sp = extras.get("sitemap_parsed", {})
    L.append(f"  URL count: {len(sp.get('urls', []))}")
    L.append(f"  Sub-sitemaps: {sp.get('sitemaps')}")
    L.append(f"  Lastmods: {sp.get('lastmods')}")

    _section(L, "SECTION 66 - ROBOTS/SITEMAP DIFF")
    for section, data in extras.get("robots_sitemap_diff", {}).items():
        L.append(f"  {section}:")
        for k, v in data.items():
            L.append(f"    {k}: {v}")

    _section(L, "SECTION 67 - DISALLOW CROSS-REFERENCE")
    for h in extras.get("disallow_hits", []):
        L.append(f"  {h['url']}  rule={h['rule']}  ts={h['timestamp']}")

    _section(L, "SECTION 68 - CONTENT/STATUS")
    for k, v in extras.get("content_types", {}).items():
        L.append(f"    {k}: {v}")
    for k, v in extras.get("status_codes", {}).items():
        L.append(f"    {k}: {v}")

    _section(L, "SECTION 69 - TIMELINE")
    for k, v in extras.get("timeline", {}).items():
        L.append(f"  {k}: {v}")

    _section(L, "SECTION 70 - GAPS")
    for g in extras.get("gaps", []):
        L.append(f"  {g['from']} -> {g['to']} ({g['months_gap']}m)")

    _section(L, "SECTION 71 - URL STRUCTURE")
    for k, v in extras.get("url_depths", {}).items():
        L.append(f"    depth {k}: {v}")
    for k, v in extras.get("query_params", {}).items():
        L.append(f"    q:{k}: {v}")
    for k, v in extras.get("file_extensions", {}).items():
        L.append(f"    ext {k}: {v}")

    _section(L, "SECTION 72 - DIGEST CLUSTERS")
    for digest, urls in extras.get("digest_clusters", {}).items():
        L.append(f"  {digest}: {urls}")

    _section(L, "SECTION 73 - URLKEY")
    for k, v in extras.get("urlkey", {}).items():
        L.append(f"  {k}: {v}")

    _section(L, "SECTION 74 - SNAPSHOT RANK")
    for u, c in extras.get("snapshot_ranking", []):
        L.append(f"  {c:5d}  {u}")

    _section(L, "SECTION 75 - CASE VARIANTS")
    for k, v in extras.get("case_variants", {}).items():
        L.append(f"  {k}: {v}")

    _section(L, "SECTION 76 - SLASH VARIANTS")
    for k, v in extras.get("slash_variants", {}).items():
        L.append(f"  {k}: {v}")

    _section(L, "SECTION 77 - SCHEME VARIANTS")
    for k, v in extras.get("scheme_variants", {}).items():
        L.append(f"  {k}: {v}")

    _section(L, "SECTION 78 - PORT VARIANTS")
    for k, v in extras.get("port_variants", {}).items():
        L.append(f"  {k}: {v}")

    _section(L, "SECTION 79 - RESURRECTION MAP")
    for entry in extras.get("resurrection_map", []):
        L.append(f"  {entry.get('url')}")
        L.append(f"    last_live={entry.get('last_live')}  restore={entry.get('restore_url')}")

    _section(L, "SECTION 80 - LINK ROT")
    lr = extras.get("link_rot", {})
    if lr:
        L.append(f"  total_links={lr.get('total_links')}")
        for h, count in list(lr.get("by_host", {}).items())[:200]:
            L.append(f"    {h}: {count}")

    _section(L, "SECTION 81 - QUERY PARAM EVOLUTION")
    for path, series in list(extras.get("query_param_evolution", {}).items())[:200]:
        L.append(f"  {path}")
        for entry in series[:20]:
            L.append(f"    {entry['timestamp']}: {entry['params']}")

    _section(L, "SECTION 82 - FORM ENDPOINT HISTORY")
    for action, entries in list(extras.get("form_endpoint_history", {}).items())[:200]:
        L.append(f"  {action}")
        for entry in entries[:20]:
            L.append(f"    {entry['timestamp']}: {entry['url']}")

    _section(L, "SECTION 83 - SUBDOMAIN CROSSREF")
    for sub, info in list(extras.get("subdomain_crossref", {}).items())[:200]:
        L.append(f"  {sub}: first={info.get('first')} last={info.get('last')} count={info.get('count')}")

    _section(L, "SECTION 84 - EXTERNAL DOMAIN GRAPH")
    for host, info in list(extras.get("external_domain_graph", {}).items())[:200]:
        L.append(f"  {host}: first={info.get('first')} last={info.get('last')} hits={info.get('hits')}")

    _section(L, "SECTION 85 - SECRET AGE")
    for name, entries in list(extras.get("secret_age_estimation", {}).items())[:100]:
        for e in entries[:20]:
            L.append(f"  {name} value={e['value'][:80]} first={e['first']} last={e['last']}")

    _section(L, "SECTION 86 - DUPLICATE SITE DETECTION")
    for digest, urls in list(extras.get("duplicate_site_detection", {}).items())[:200]:
        L.append(f"  {digest[:24]}: {urls}")

    _section(L, "SECTION 87 - PAGE TREE")
    L.append(f"  {str(extras.get('page_tree', {}))[:5000]}")

    _section(L, "SECTION 88 - REDIRECT CHAINS")
    for u, chain in list(extras.get("redirect_chains", {}).items())[:200]:
        L.append(f"  {u}")
        for step in chain[:10]:
            L.append(f"    {step['timestamp']} {step['status']} -> {step['target']}")

    _section(L, "SECTION 89 - PASSIVE CRAWL CORRELATION")
    pcc = extras.get("passive_crawl_correlation", {})
    if pcc:
        L.append(f"  CDX-only URLs: {len(pcc.get('only_in_cdx', []))}")
        for u in pcc.get("only_in_cdx", [])[:100]:
            L.append(f"    {u}")
        L.append(f"  CommonCrawl-only URLs: {len(pcc.get('only_in_cc', []))}")
        for u in pcc.get("only_in_cc", [])[:100]:
            L.append(f"    {u}")
        L.append(f"  In both: {len(pcc.get('in_both', []))}")

    _section(L, "SECTION 90 - REVISIT RECORDS")
    for r in extras.get("revisit_records", [])[:200]:
        L.append(f"  {r.get('timestamp')}  {r.get('original')}")

    _section(L, "SECTION 91 - DUPLICATE SECRET COLLAPSE")
    for name, data in list(extras.get("duplicate_secret_collapse", {}).items())[:200]:
        L.append(f"  {name}: {data}")

    _section(L, "SECTION 92 - PHASE DURATIONS")
    for name, dur in sorted(extras.get("phase_durations", {}).items(), key=lambda x: -x[1]):
        L.append(f"  {name}: {dur:.1f}s")

    _section(L, "SECTION 93 - BASELINE DIFF")
    bd = extras.get("baseline_diff", {})
    if bd:
        L.append(f"  baseline: {bd.get('baseline_path')}")
        L.append(f"  new URLs: {len(bd.get('new_urls', []))}")
        for u in bd.get("new_urls", [])[:100]:
            L.append(f"    + {u}")
        L.append(f"  removed URLs: {len(bd.get('removed_urls', []))}")
        for u in bd.get("removed_urls", [])[:100]:
            L.append(f"    - {u}")
        L.append(f"  new secrets: {len(bd.get('new_secrets', []))}")
        for s in bd.get("new_secrets", [])[:100]:
            L.append(f"    + {s}")
        L.append(f"  new subdomains: {len(bd.get('new_subdomains', []))}")
        for s in bd.get("new_subdomains", [])[:100]:
            L.append(f"    + {s}")

    Path(path).write_text("\n".join(L), encoding="utf-8")
    T("REPORT", f"TXT -> {path}")


def write_html_report(path, domain, results, extras):
    removed = [r for r in results if r.get("likely_removed")]
    live = [r for r in results if r.get("likely_removed") is False]

    def url_rows(items, cls, label):
        rows = []
        for r in sorted(items, key=lambda x: x["timestamp"], reverse=True)[:2000]:
            arc = wayback_snapshot_url(r["timestamp"], r["original"])
            rows.append(f"""<tr><td><span class="badge {cls}">{label}</span></td>
              <td class="url"><a href="{html_module.escape(r['original'])}" target="_blank">{html_module.escape(r['original'])}</a></td>
              <td>{_fmt_ts(r['timestamp'])}</td><td>{r.get('statuscode','')}</td>
              <td>{html_module.escape(str(r.get('mimetype','')))}</td><td>{r.get('snapshot_count','')}</td>
              <td>{html_module.escape(str(r.get('deletion_class','')))}</td>
              <td><a href="{arc}" target="_blank">archive</a></td></tr>""")
        return "".join(rows)

    def json_block(title, obj, limit=30000):
        if not obj:
            return f"<div class='section'><h2>{html_module.escape(title)} (0)</h2><p class='muted'>None.</p></div>"
        s = json.dumps(obj, indent=2, default=str)[:limit]
        return f"<div class='section'><h2>{html_module.escape(title)}</h2><pre>{html_module.escape(s)}</pre></div>"

    def secrets_block(title, secrets_dict):
        if not secrets_dict:
            return f"<div class='section'><h2>{html_module.escape(title)} (0)</h2><p class='muted'>None.</p></div>"
        rows = []
        for name, data in secrets_dict.items():
            sev = data.get("severity", "?")
            for v in data.get("values", [])[:20]:
                rows.append(f"<tr><td class='severity-{html_module.escape(sev)}'>{html_module.escape(sev)}</td><td class='secret-name'>{html_module.escape(name)}</td><td class='secret-val'>{html_module.escape(str(v))[:300]}</td></tr>")
        return f"""<div class='section'><h2>SECRETS: {html_module.escape(title)} ({len(secrets_dict)})</h2>
        <table><thead><tr><th>Sev</th><th>Type</th><th>Value</th></tr></thead><tbody>{''.join(rows[:3000])}</tbody></table></div>"""

    sources = {}
    for u, ts_map in (extras.get("page_intel") or {}).items():
        for ts, intel in ts_map.items():
            src = u + "@" + ts
            d = _flatten_secrets_for_report(intel.get("secrets") or {})
            d["_ts"] = ts
            sources[src] = d
    for fname, data in (extras.get("special_file_scans") or {}).items():
        src = "special:" + fname
        d = _flatten_secrets_for_report(data.get("secrets") or {})
        snap = (extras.get("special_files") or {}).get(fname)
        if snap:
            d["_ts"] = snap[-1]["timestamp"]
        sources[src] = d
    for u, hits in (extras.get("js_bundle_secrets") or {}).items():
        sources["js:" + u] = _flatten_secrets_for_report(hits)
    for u, hits in (extras.get("source_map_secrets") or {}).items():
        sources["map:" + u] = _flatten_secrets_for_report(hits)
    aggregated = _dedupe_secrets_across(sources)
    credentials = build_credential_section(aggregated, sources, domain=domain)

    docs = extras.get("documents", [])
    redirects = extras.get("redirects", [])
    special = extras.get("special_files", {})
    ports = extras.get("ports", {})
    timelines = extras.get("deletion_timelines", {})
    clusters = extras.get("mass_deletion_clusters", [])

    docs_html = "".join(
        f"<tr><td>{html_module.escape(d['extension'])}</td><td class='url'><a href='{html_module.escape(d['url'])}'>{html_module.escape(d['url'])}</a></td>"
        f"<td>{_fmt_ts(d['last_captured'])}</td><td><a href='{d['archive_link']}'>archive</a></td></tr>"
        for d in docs[:500]
    )
    redirects_html = "".join(
        f"<tr><td class='url'>{html_module.escape(r['url'])}</td><td>{_fmt_ts(r['timestamp'])}</td><td>{r['statuscode']}</td><td class='url'>{html_module.escape(r.get('redirect_target',''))}</td></tr>"
        for r in redirects[:500]
    )
    special_html = ""
    for fname, snaps in list(special.items())[:300]:
        rows = "".join(
            f"<tr><td>{_fmt_ts(s['timestamp'])}</td><td>{s.get('statuscode','')}</td><td><a href='{s['archive']}'>archive</a></td></tr>"
            for s in snaps[:5]
        )
        special_html += f"<div class='intel-card'><div class='intel-url'>{html_module.escape(fname)} ({len(snaps)} snaps)</div><table>{rows}</table></div>"

    ports_html = "".join(f"<tr><td>{p}</td><td>{html_module.escape(str(info.get('service','')))}</td><td>{html_module.escape(str(info.get('banner',''))[:200])}</td></tr>" for p, info in ports.items())
    tl_html = "".join(f"<tr><td class='url'>{html_module.escape(u[:200])}</td><td>{d.get('last_ok','')}</td><td>{d.get('first_bad','')}</td><td>{d.get('type','')}</td></tr>" for u, d in list(timelines.items())[:2000])
    cluster_html = "".join(f"<tr><td>{c['timestamp']}</td><td>{c['count']}</td><td class='url'>{', '.join(html_module.escape(x[:80]) for x in c.get('sample',[]))}</td></tr>" for c in clusters)

    qpe = extras.get("query_param_evolution", {})
    qpe_html = ""
    for path, series in list(qpe.items())[:200]:
        rows = "".join(f"<tr><td>{e['timestamp']}</td><td>{html_module.escape(', '.join(e['params']))}</td></tr>" for e in series[:20])
        qpe_html += f"<div class='intel-card'><div class='intel-url'>{html_module.escape(path)}</div><table>{rows}</table></div>"
    if not qpe_html:
        qpe_html = "<p class='muted'>None.</p>"

    feh = extras.get("form_endpoint_history", {})
    feh_html = ""
    for action, entries in list(feh.items())[:200]:
        rows = "".join(f"<tr><td>{e['timestamp']}</td><td class='url'>{html_module.escape(e['url'])}</td></tr>" for e in entries[:20])
        feh_html += f"<div class='intel-card'><div class='intel-url'>{html_module.escape(action)}</div><table>{rows}</table></div>"
    if not feh_html:
        feh_html = "<p class='muted'>None.</p>"

    rmap = extras.get("resurrection_map", [])
    rmap_html = ""
    for e in rmap[:500]:
        rmap_html += f"<tr><td class='url'>{html_module.escape(e.get('url',''))}</td><td>{e.get('last_live','')}</td><td><a href='{html_module.escape(e.get('restore_url',''))}'>restore</a></td></tr>"
    if not rmap_html:
        rmap_html = "<tr><td colspan=3 class='muted'>None.</td></tr>"

    lr = extras.get("link_rot", {})
    lr_html = "".join(f"<tr><td>{html_module.escape(h)}</td><td>{c}</td></tr>" for h, c in list(lr.get("by_host", {}).items())[:200])
    if not lr_html:
        lr_html = "<tr><td colspan=2 class='muted'>None.</td></tr>"

    edg = extras.get("external_domain_graph", {})
    edg_html = "".join(f"<tr><td>{html_module.escape(h)}</td><td>{i.get('first','')}</td><td>{i.get('last','')}</td><td>{i.get('hits','')}</td></tr>" for h, i in list(edg.items())[:500])
    if not edg_html:
        edg_html = "<tr><td colspan=4 class='muted'>None.</td></tr>"

    sae = extras.get("secret_age_estimation", {})
    sae_html = ""
    for name, entries in list(sae.items())[:100]:
        for e in entries[:20]:
            sae_html += f"<tr><td>{html_module.escape(name)}</td><td class='secret-val'>{html_module.escape(e['value'][:120])}</td><td>{e['first']}</td><td>{e['last']}</td></tr>"
    if not sae_html:
        sae_html = "<tr><td colspan=4 class='muted'>None.</td></tr>"

    ds = extras.get("duplicate_site_detection", {})
    ds_html = "".join(f"<tr><td class='secret-name'>{html_module.escape(digest[:24])}</td><td class='url'>{html_module.escape(', '.join(urls[:20]))}</td></tr>" for digest, urls in list(ds.items())[:200])
    if not ds_html:
        ds_html = "<tr><td colspan=2 class='muted'>None.</td></tr>"

    pcc = extras.get("passive_crawl_correlation", {})
    pcc_html = ""
    if pcc:
        pcc_html += f"<p>CDX-only: {len(pcc.get('only_in_cdx', []))} | CC-only: {len(pcc.get('only_in_cc', []))} | Both: {len(pcc.get('in_both', []))}</p>"
        pcc_html += "<table><thead><tr><th>Scope</th><th>URL</th></tr></thead><tbody>"
        for u in pcc.get("only_in_cdx", [])[:100]:
            pcc_html += f"<tr><td>CDX</td><td class='url'>{html_module.escape(u)}</td></tr>"
        for u in pcc.get("only_in_cc", [])[:100]:
            pcc_html += f"<tr><td>CC</td><td class='url'>{html_module.escape(u)}</td></tr>"
        pcc_html += "</tbody></table>"
    else:
        pcc_html = "<p class='muted'>None.</p>"

    bd = extras.get("baseline_diff", {})
    bd_html = "<p class='muted'>No baseline.</p>"
    if bd:
        bd_html = f"<p>baseline: {html_module.escape(bd.get('baseline_path',''))}</p>"
        for label, key in (("New URLs", "new_urls"), ("Removed URLs", "removed_urls"),
                           ("New secrets", "new_secrets"), ("New subdomains", "new_subdomains")):
            items = bd.get(key, [])
            bd_html += f"<h3>{label} ({len(items)})</h3><ul>"
            for it in items[:200]:
                bd_html += f"<li>{html_module.escape(str(it))}</li>"
            bd_html += "</ul>"

    cred_rows = ""
    for name, data in sorted(credentials.items(), key=lambda x: -len(x[1]["values"])):
        sev_class = "severity-" + html_module.escape(data.get("severity", "unknown"))
        for v in data["values"][:10]:
            cred_rows += f"<tr><td class='{sev_class}'>{html_module.escape(data.get('score','?'))}</td><td class='secret-name'>{html_module.escape(name)}</td><td class='secret-val'>{html_module.escape(str(v))[:200]}</td><td>{html_module.escape(data.get('context',''))}</td><td>{html_module.escape(data.get('rotation',''))}</td><td>{data.get('first_seen') or ''}</td><td>{data.get('last_seen') or ''}</td></tr>"
    cred_html = f"""<div class='section'><h2>CREDENTIALS (focused)</h2>
    <table><thead><tr><th>Score</th><th>Type</th><th>Value</th><th>Context</th><th>Rotation</th><th>First</th><th>Last</th></tr></thead>
    <tbody>{cred_rows or '<tr><td colspan=7 class="muted">None.</td></tr>'}</tbody></table></div>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>STRATASCAN - {html_module.escape(domain)}</title>
<style>
body {{ margin:0; padding:24px; background:#0f1115; color:#e6e9ef; font-family:-apple-system,sans-serif; }}
h1 {{ font-size:1.4rem; }} h2 {{ font-size:1rem; margin:0 0 10px; }} h3 {{ font-size:.9rem; color:#8b93a7; }}
.muted {{ color:#8b93a7; }}
table {{ width:100%; border-collapse:collapse; font-size:.83rem; }}
th,td {{ padding:7px 8px; border-bottom:1px solid #262b36; text-align:left; vertical-align:top; }}
td.url {{ max-width:420px; word-break:break-all; }}
a {{ color:#5b8cff; text-decoration:none; }}
.section {{ margin-bottom:32px; }}
.intel-card {{ background:#171a21; border:1px solid #262b36; border-radius:10px; padding:14px; margin-bottom:14px; }}
.intel-url {{ margin-bottom:8px; font-weight:600; word-break:break-all; }}
pre {{ background:#0a0d12; border:1px solid #262b36; border-radius:8px; padding:12px; overflow-x:auto; max-height:500px; white-space:pre-wrap; word-break:break-all; font-size:.75rem; }}
.stats {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:24px; }}
.stat {{ background:#171a21; border:1px solid #262b36; border-radius:10px; padding:14px 18px; min-width:120px; }}
.stat .n {{ font-size:1.6rem; font-weight:700; }} .stat .l {{ font-size:.72rem; color:#8b93a7; text-transform:uppercase; }}
.badge {{ padding:2px 8px; border-radius:999px; font-size:.7rem; }}
.badge.removed {{ background:rgba(255,91,110,.15); color:#ff5b6e; }}
.badge.live {{ background:rgba(52,211,153,.15); color:#34d399; }}
td.severity-critical {{ color:#ff5b6e; font-weight:700; }}
td.severity-high {{ color:#ff8a3d; }} td.severity-medium {{ color:#f0c040; }}
td.secret-name {{ font-family:monospace; color:#f0c040; }}
td.secret-val {{ font-family:monospace; color:#ff5b6e; word-break:break-all; }}
</style></head><body>
<h1>STRATASCAN</h1>
<div class="muted">Target: {html_module.escape(domain)} - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} - UA: {UA_MODE} - Proxies: {PROXIES.status().get('count')}</div>
<div class="stats">
<div class="stat"><div class="n">{len(results)}</div><div class="l">URLs</div></div>
<div class="stat"><div class="n" style="color:#ff5b6e">{len(removed)}</div><div class="l">Removed</div></div>
<div class="stat"><div class="n" style="color:#34d399">{len(live)}</div><div class="l">Live</div></div>
<div class="stat"><div class="n">{len(extras.get('subdomains', []))}</div><div class="l">Subdomains</div></div>
<div class="stat"><div class="n">{len(docs)}</div><div class="l">Docs</div></div>
<div class="stat"><div class="n">{len(ports)}</div><div class="l">Ports</div></div>
<div class="stat"><div class="n" style="color:#ff5b6e">{len(credentials)}</div><div class="l">Credential Types</div></div>
</div>
{cred_html}
{secrets_block("Aggregated Secrets (all)", aggregated)}
<div class='section'><h2>Removed ({len(removed)})</h2><table><thead><tr><th>Status</th><th>URL</th><th>Last</th><th>HTTP</th><th>Type</th><th>Snaps</th><th>Del</th><th>Archive</th></tr></thead><tbody>{url_rows(removed, 'removed', 'REMOVED')}</tbody></table></div>
<div class='section'><h2>Live ({len(live)})</h2><table><thead><tr><th>Status</th><th>URL</th><th>Last</th><th>HTTP</th><th>Type</th><th>Snaps</th><th>Del</th><th>Archive</th></tr></thead><tbody>{url_rows(live, 'live', 'LIVE')}</tbody></table></div>
{json_block("Subdomains", extras.get("subdomains", []))}
{json_block("Subdomain Stats", extras.get("subdomain_stats", {}))}
<div class='section'><h2>Resurrection Map ({len(rmap)})</h2><table><thead><tr><th>URL</th><th>Last Live</th><th>Restore</th></tr></thead><tbody>{rmap_html}</tbody></table></div>
<div class='section'><h2>Link Rot Hosts ({len(lr.get('by_host', {}))})</h2><table><thead><tr><th>Host</th><th>Hits</th></tr></thead><tbody>{lr_html}</tbody></table></div>
<div class='section'><h2>External Domain Graph ({len(edg)})</h2><table><thead><tr><th>Host</th><th>First</th><th>Last</th><th>Hits</th></tr></thead><tbody>{edg_html}</tbody></table></div>
<div class='section'><h2>Query Param Evolution ({len(qpe)})</h2>{qpe_html}</div>
<div class='section'><h2>Form Endpoint History ({len(feh)})</h2>{feh_html}</div>
<div class='section'><h2>Secret Age Estimation ({len(sae)})</h2><table><thead><tr><th>Type</th><th>Value</th><th>First</th><th>Last</th></tr></thead><tbody>{sae_html}</tbody></table></div>
<div class='section'><h2>Duplicate Site Detection ({len(ds)})</h2><table><thead><tr><th>Digest</th><th>URLs</th></tr></thead><tbody>{ds_html}</tbody></table></div>
<div class='section'><h2>Passive Crawl Correlation</h2>{pcc_html}</div>
<div class='section'><h2>Baseline Diff</h2>{bd_html}</div>
<div class='section'><h2>Documents ({len(docs)})</h2><table><tbody>{docs_html}</tbody></table></div>
<div class='section'><h2>Redirects ({len(redirects)})</h2><table><tbody>{redirects_html}</tbody></table></div>
<div class='section'><h2>Special Files ({len(special)})</h2>{special_html}</div>
<div class='section'><h2>Ports ({len(ports)})</h2><table><tbody>{ports_html}</tbody></table></div>
<div class='section'><h2>Deletion Timelines ({len(timelines)})</h2><table><tbody>{tl_html}</tbody></table></div>
<div class='section'><h2>Mass Deletion Events ({len(clusters)})</h2><table><tbody>{cluster_html}</tbody></table></div>
{json_block("DNS Full", extras.get("dns_full", {}))}
{json_block("DKIM", extras.get("dkim_selectors", {}))}
{json_block("TLS", extras.get("tls", {}))}
{json_block("Header Summary", extras.get("header_summary", {}))}
{json_block("WHOIS", extras.get("whois", {}))}
{json_block("RDAP", extras.get("rdap", {}))}
{json_block("Common Crawl", extras.get("common_crawl", {}))}
{json_block("Framework Endpoints", extras.get("framework_endpoints", {}))}
{json_block("Cloud Buckets", extras.get("cloud_buckets", {}))}
{json_block("Document Metadata", extras.get("document_metadata", {}))}
{json_block("JS Bundle Secrets", extras.get("js_bundle_secrets", {}))}
{json_block("Source Map Secrets", extras.get("source_map_secrets", {}))}
{json_block("JS Deobfuscation", extras.get("js_deobfuscation", {}))}
{json_block("Redirect Chains", extras.get("redirect_chains", {}))}
{json_block("Revisit Records", extras.get("revisit_records", [])[:200])}
{json_block("URLKey", dict(list(extras.get("urlkey", {}).items())[:500]))}
{json_block("Snapshot Ranking", extras.get("snapshot_ranking", [])[:500])}
{json_block("Page Tree", extras.get("page_tree", {}))}
{json_block("Duplicate Secret Collapse", extras.get("duplicate_secret_collapse", {}))}
{json_block("Disallow Hits", extras.get("disallow_hits", [])[:500])}
{json_block("Phase Durations", extras.get("phase_durations", {}))}
{json_block("Jitter Config", jitter_status())}
</body></html>"""
    Path(path).write_text(html, encoding="utf-8")
    T("REPORT", f"HTML -> {path}")


def query_robtex(domain):
    return http_get_json(f"{ROBTEX_URL}pdns/forward/{urllib.parse.quote(domain)}", timeout=15) or {}


def query_mnemonic_pdns(domain):
    return http_get_json(f"{MNEMONIC_PDNS_URL}?query={urllib.parse.quote(domain)}", timeout=20) or {}


def query_hackertarget(domain):
    body = http_get(f"{HACKERTARGET_URL}hostsearch/?q={urllib.parse.quote(domain)}", timeout=15)
    return {"raw": body[:5000]} if body else {}


def generate_email_permutations(names, domain, existing_emails=None):
    existing = set(e.lower() for e in (existing_emails or []))
    out = set()
    for name in names:
        parts = re.split(r'\s+', name.strip())
        if len(parts) < 2:
            continue
        first, last = parts[0].lower(), parts[-1].lower()
        fi, li = first[0], last[0]
        for pattern in (f"{first}@{domain}", f"{last}@{domain}",
                        f"{first}.{last}@{domain}", f"{first}_{last}@{domain}",
                        f"{fi}{last}@{domain}", f"{first}{li}@{domain}",
                        f"{fi}.{last}@{domain}", f"{first}.{li}@{domain}",
                        f"{last}.{first}@{domain}", f"{fi}{li}@{domain}",
                        f"{last}@{domain}", f"{first}{last}@{domain}",
                        f"{fi}-{last}@{domain}", f"{first}-{li}@{domain}",
                        f"{first}.{fi}{last}@{domain}", f"{fi}{last}.{first}@{domain}",
                        f"{first}_{li}@{domain}", f"{fi}_{last}@{domain}"):
            if pattern.lower() not in existing:
                out.add(pattern)
    return sorted(out)


def validate_email_mx(email):
    domain = email.split("@")[-1]
    data = http_get_json(f"{DOH_GOOGLE_URL}?name={urllib.parse.quote(domain)}&type=MX", timeout=10)
    if data and data.get("Answer"):
        return True, [a.get("data") for a in data["Answer"]]
    return False, []


def detect_catchall(domain):
    data = http_get_json(f"{DOH_GOOGLE_URL}?name={urllib.parse.quote(domain)}&type=MX", timeout=10)
    mx = [a.get("data") for a in (data or {}).get("Answer", [])]
    return {"mx_records": mx, "note": "Active catch-all requires SMTP RCPT test"}


def check_cloud_buckets(domain):
    base = domain.split(".")[0]
    names = [base, f"{base}-backup", f"{base}-dev", f"{base}-staging", f"{base}-prod",
             f"{base}-assets", f"{base}-static", f"{base}-media", f"{base}-files",
             f"{base}-uploads", f"{base}-data", f"{base}-logs", f"{base}-public",
             f"{base}-private", f"{base}-internal", f"{base}-external",
             f"{base}-test", f"{base}-demo", f"{base}-old", f"{base}-new",
             f"{base}-backups", f"{base}-archive", f"{base}-temp", f"{base}-tmp",
             f"{base}-cache", f"{base}-cdn", f"{base}-img", f"{base}-images",
             f"{base}-video", f"{base}-audio", f"{base}-docs", f"{base}-documents",
             f"{base}-pdf", f"{base}-excel", f"{base}-word", f"{base}-ppt",
             f"{base}-backup-2023", f"{base}-backup-2024", f"{base}-backup-2025"]
    findings = {}

    def work(item):
        name, provider, url = item
        status, _, _ = http_get_range(url, "0-1023", timeout=6)
        return name, provider, url, status

    tasks = []
    for name in names:
        for provider, url in [("s3", f"https://{name}.s3.amazonaws.com/"),
                              ("gcs", f"https://storage.googleapis.com/{name}/"),
                              ("azure", f"https://{name}.blob.core.windows.net/?comp=list"),
                              ("do", f"https://{name}.nyc3.digitaloceanspaces.com/"),
                              ("wasabi", f"https://{name}.s3.wasabisys.com/"),
                              ("backblaze", f"https://{name}.s3.us-west-002.backblazeb2.com/"),
                              ("linode", f"https://{name}.us-east-1.linodeobjects.com/"),
                              ("vultr", f"https://{name}.ewr1.vultrobjects.com/"),
                              ("scaleway", f"https://{name}.s3.fr-par.scw.cloud/"),
                              ("ovh", f"https://{name}.s3.gra.io.cloud.ovh.net/")]:
            tasks.append((name, provider, url))

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(work, t) for t in tasks]
        for fut in concurrent.futures.as_completed(futures):
            try:
                name, provider, url, status = fut.result()
            except Exception:
                continue
            if status and status < 400:
                findings.setdefault(provider, []).append({"name": name, "url": url, "status": status})
    return findings


def run_dorks(domain):
    return [
        f'site:{domain}', f'site:{domain} filetype:pdf',
        f'site:{domain} filetype:doc OR filetype:docx',
        f'site:{domain} filetype:xls OR filetype:xlsx',
        f'site:{domain} filetype:sql', f'site:{domain} filetype:env',
        f'site:{domain} filetype:log', f'site:{domain} filetype:bak',
        f'site:{domain} inurl:admin', f'site:{domain} inurl:login',
        f'site:{domain} inurl:api', f'site:{domain} inurl:config',
        f'site:{domain} inurl:backup', f'site:{domain} intitle:"index of"',
        f'site:{domain} intitle:"dashboard"', f'site:{domain} intitle:"phpMyAdmin"',
        f'site:{domain} intext:"api_key"', f'site:{domain} intext:"password"',
        f'site:{domain} ext:git OR ext:svn',
        f'"{domain}" site:pastebin.com', f'"{domain}" site:github.com',
        f'"{domain}" site:gitlab.com', f'"{domain}" site:bitbucket.org',
        f'"{domain}" site:stackoverflow.com', f'"{domain}" site:reddit.com',
        f'"{domain}" site:medium.com', f'"{domain}" site:dev.to',
        f'"{domain}" site:trello.com', f'"{domain}" site:notion.so',
        f'"{domain}" site:airtable.com', f'"{domain}" site:docs.google.com',
        f'"{domain}" site:drive.google.com', f'"{domain}" site:dropbox.com',
        f'"{domain}" site:onedrive.live.com', f'"{domain}" site:sharepoint.com',
        f'"{domain}" site:s3.amazonaws.com', f'"{domain}" site:blob.core.windows.net',
        f'"{domain}" site:storage.googleapis.com', f'"{domain}" site:digitaloceanspaces.com',
        f'"{domain}" intext:"BEGIN RSA PRIVATE KEY"', f'"{domain}" intext:"BEGIN OPENSSH PRIVATE KEY"',
        f'"{domain}" intext:"AKIA"', f'"{domain}" intext:"AIza"',
        f'"{domain}" intext:"sk_live_"', f'"{domain}" intext:"xoxb-"',
        f'"{domain}" intext:"ghp_"', f'"{domain}" intext:"glpat-"',
    ]


def _default_out_dir():
    script_dir = Path(__file__).resolve().parent
    out_path = script_dir / "wayback_reports"
    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        out_path = Path.home() / "wayback_reports"
        out_path.mkdir(parents=True, exist_ok=True)
    return out_path


def load_baseline(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        T("DIFF", f"baseline read failed: {e}")
        return None
    return data


def diff_against_baseline(baseline, results, extras, aggregated_secrets):
    if not baseline:
        return {}
    old_urls = set()
    old_subs = set()
    old_secrets = set()
    for r in baseline.get("results", []) or []:
        u = r.get("original")
        if u:
            old_urls.add(u)
    for s in (baseline.get("extras", {}) or {}).get("subdomains", []) or []:
        old_subs.add(s)
    for name, data in (baseline.get("aggregated_secrets", {}) or {}).items():
        for v in data.get("values", []):
            old_secrets.add(f"{name}:{v}")
    new_urls = sorted({r.get("original") for r in results if r.get("original")} - old_urls)
    removed_urls = sorted(old_urls - {r.get("original") for r in results if r.get("original")})
    new_subs = sorted(set(extras.get("subdomains", [])) - old_subs)
    new_secrets = []
    for name, data in (aggregated_secrets or {}).items():
        for v in data.get("values", []):
            key = f"{name}:{v}"
            if key not in old_secrets:
                new_secrets.append(key)
    return {
        "baseline_path": baseline.get("_path", "?"),
        "new_urls": new_urls,
        "removed_urls": removed_urls,
        "new_subdomains": new_subs,
        "new_secrets": sorted(new_secrets),
    }


def flush_partial_report(domain, results, extras, aggregated_secrets, sources):
    if not domain:
        return
    prefix = re.sub(r"[^a-zA-Z0-9.-]", "_", domain) + "_partial"
    out_path = _default_out_dir()
    try:
        write_json(out_path / f"{prefix}.json",
                   {"partial": True, "results": results, "extras": extras,
                    "secrets": aggregated_secrets, "sources": sources})
    except Exception as e:
        T("WARN", f"partial JSON failed: {e}")
    try:
        write_csv(out_path / f"{prefix}.csv", results)
    except Exception as e:
        T("WARN", f"partial CSV failed: {e}")
    try:
        write_html_report(out_path / f"{prefix}.html", domain, results, extras)
    except Exception as e:
        T("WARN", f"partial HTML failed: {e}")
    try:
        write_txt(out_path / f"{prefix}.txt", domain, results, extras, aggregated_secrets, sources)
    except Exception as e:
        T("WARN", f"partial TXT failed: {e}")
    T("SAVE", f"partial report -> {out_path}/{prefix}.*")


PHASE_IDS = [
    "FETCHING CDX INDEX",
    "PROBING LIVE STATUS",
    "MAPPING TOPOLOGY",
    "HARVESTING HTTP HEADERS",
    "TLS / DNS RECON",
    "WAYBACK / ARCHIVE ENDPOINTS",
    "CERTIFICATE TRANSPARENCY",
    "WHOIS / RDAP",
    "DNS FULL RECORDS",
    "PASSIVE DNS SOURCES",
    "SPECIAL FILES",
    "SCANNING SPECIAL FILE CONTENTS",
    "PARSING ROBOTS / SITEMAP",
    "CONTENT INTEL",
    "JS BUNDLE HARVESTING",
    "SOURCE MAP HARVESTING",
    "JS DEOBFUSCATION",
    "DELETION FORENSICS",
    "SUBDOMAIN TAKEOVER PROBE",
    "ADJACENT SNAPSHOT DIFFS",
    "WAYBACK VS LIVE DIFF",
    "ARCHIVED HEADERS",
    "DOCUMENT METADATA",
    "FRAMEWORK ENDPOINTS",
    "CLOUD BUCKET ENUMERATION",
    "DORK GENERATION",
    "ROBOTS/SITEMAP HISTORICAL DIFF",
    "SUBDOMAIN PERMUTATION + BRUTE",
    "EMAIL PERMUTATIONS + MX",
    "VARIANT ENUMERATION",
    "RESURRECTION MAP",
    "LINK ROT QUANTIFICATION",
    "QUERY PARAM EVOLUTION",
    "SECRET AGE ESTIMATION",
    "FORM ENDPOINT HISTORY",
    "EXTERNAL DOMAIN GRAPH",
    "DUPLICATE SITE DETECTION",
    "REVISIT RECORD ANALYSIS",
    "URLKEY / SURT ANALYTICS",
    "SNAPSHOT DENSITY RANKING",
    "REDIRECT CHAIN RECONSTRUCTION",
    "PASSIVE CRAWL CORRELATION",
    "PAGE TREE RECONSTRUCTION",
    "DUPLICATE SECRET COLLAPSE",
    "CREDENTIAL CORRELATION",
    "RAW EVIDENCE EXPORT",
    "COVERAGE REPORT",
    "CACHE WARMUP",
]
PHASE_INDEX = {name: i + 1 for i, name in enumerate(PHASE_IDS)}
PHASE_COUNT = len(PHASE_IDS)

ACTIVE_PHASES = None
_PHASE_LOCK = threading.Lock()
_PHASE_START = {}
_PHASE_DURATION = {}
_PHASE_TIME_LOCK = threading.Lock()

SCAN_RUNNING = threading.Event()
SIGINT_HARD_LOCK = threading.Lock()
SIGINT_COUNT = {"n": 0}

CAP_TO_PHASES = {
    "cdx": ["FETCHING CDX INDEX"],
    "cdx_full": ["FETCHING CDX INDEX"],
    "cdx_filter": ["FETCHING CDX INDEX"],
    "cdx_prefix": ["FETCHING CDX INDEX"],
    "timeline": ["DELETION FORENSICS"],
    "calendar": ["WAYBACK / ARCHIVE ENDPOINTS"],
    "anchor": ["WAYBACK / ARCHIVE ENDPOINTS"],
    "availability": ["WAYBACK / ARCHIVE ENDPOINTS"],
    "sparkline": ["WAYBACK / ARCHIVE ENDPOINTS"],
    "timemap": ["WAYBACK / ARCHIVE ENDPOINTS"],
    "timemap_json": ["WAYBACK / ARCHIVE ENDPOINTS"],
    "memento_agg": ["WAYBACK / ARCHIVE ENDPOINTS"],
    "archive_today": ["WAYBACK / ARCHIVE ENDPOINTS"],
    "common_crawl": ["WAYBACK / ARCHIVE ENDPOINTS", "PASSIVE CRAWL CORRELATION"],
    "crt": ["CERTIFICATE TRANSPARENCY"],
    "rdap": ["WHOIS / RDAP"],
    "whois": ["WHOIS / RDAP"],
    "live_status": ["PROBING LIVE STATUS"],
    "deletion_class": ["PROBING LIVE STATUS", "DELETION FORENSICS"],
    "deletion_window": ["DELETION FORENSICS"],
    "mass_deletion": ["DELETION FORENSICS"],
    "first_last_diff": ["DELETION FORENSICS"],
    "adjacent_diff": ["ADJACENT SNAPSHOT DIFFS"],
    "wayback_live_diff": ["WAYBACK VS LIVE DIFF"],
    "headers": ["HARVESTING HTTP HEADERS"],
    "header_summary": ["HARVESTING HTTP HEADERS"],
    "archived_headers": ["ARCHIVED HEADERS"],
    "archived_header_diff": ["ARCHIVED HEADERS"],
    "cookie_flags": ["HARVESTING HTTP HEADERS"],
    "exclusions": ["HARVESTING HTTP HEADERS"],
    "archive_src": ["HARVESTING HTTP HEADERS"],
    "revisit": ["REVISIT RECORD ANALYSIS"],
    "tls": ["TLS / DNS RECON"],
    "tls_versions": ["TLS / DNS RECON"],
    "tls_ciphers": ["TLS / DNS RECON"],
    "tls_chain": ["TLS / DNS RECON"],
    "ocsp": ["TLS / DNS RECON"],
    "hsts_preload": ["TLS / DNS RECON"],
    "dns": ["TLS / DNS RECON"],
    "dns_full": ["DNS FULL RECORDS"],
    "srv": ["DNS FULL RECORDS"],
    "tlsa": ["DNS FULL RECORDS"],
    "smimea": ["DNS FULL RECORDS"],
    "dkim": ["DNS FULL RECORDS"],
    "bimi": ["DNS FULL RECORDS"],
    "dnssec": ["DNS FULL RECORDS"],
    "axfr": ["DNS FULL RECORDS"],
    "ptr": ["DNS FULL RECORDS"],
    "wildcard": ["DNS FULL RECORDS"],
    "asn": ["TLS / DNS RECON"],
    "ports": ["TLS / DNS RECON"],
    "http2": ["TLS / DNS RECON"],
    "waf": ["TLS / DNS RECON"],
    "cors": ["HARVESTING HTTP HEADERS"],
    "ratelimit": ["HARVESTING HTTP HEADERS"],
    "robtex": ["PASSIVE DNS SOURCES"],
    "mnemonic_pdns": ["PASSIVE DNS SOURCES"],
    "hackertarget": ["PASSIVE DNS SOURCES"],
    "subdomains": ["MAPPING TOPOLOGY"],
    "subdomain_stats": ["MAPPING TOPOLOGY"],
    "subdomain_crossref": ["MAPPING TOPOLOGY"],
    "takeover": ["SUBDOMAIN TAKEOVER PROBE"],
    "subdomain_perm": ["SUBDOMAIN PERMUTATION + BRUTE"],
    "subdomain_brute": ["SUBDOMAIN PERMUTATION + BRUTE"],
    "case_variant": ["VARIANT ENUMERATION"],
    "slash_variant": ["VARIANT ENUMERATION"],
    "scheme_variant": ["VARIANT ENUMERATION"],
    "port_variant": ["VARIANT ENUMERATION"],
    "documents": ["DOCUMENT METADATA"],
    "redirects": ["MAPPING TOPOLOGY"],
    "content_types": ["MAPPING TOPOLOGY"],
    "status_codes": ["MAPPING TOPOLOGY"],
    "timeline_monthly": ["MAPPING TOPOLOGY"],
    "gaps": ["MAPPING TOPOLOGY"],
    "url_depths": ["MAPPING TOPOLOGY"],
    "query_params": ["MAPPING TOPOLOGY"],
    "file_extensions": ["MAPPING TOPOLOGY"],
    "first_last_seen": ["MAPPING TOPOLOGY"],
    "churn": ["MAPPING TOPOLOGY"],
    "digest_cluster": ["DUPLICATE SITE DETECTION"],
    "urlkey": ["URLKEY / SURT ANALYTICS"],
    "snapshot_rank": ["SNAPSHOT DENSITY RANKING"],
    "robots_parsed": ["PARSING ROBOTS / SITEMAP"],
    "robots_diff": ["ROBOTS/SITEMAP HISTORICAL DIFF"],
    "sitemap_parsed": ["PARSING ROBOTS / SITEMAP"],
    "sitemap_diff": ["ROBOTS/SITEMAP HISTORICAL DIFF"],
    "special_files": ["SPECIAL FILES"],
    "special_scan": ["SCANNING SPECIAL FILE CONTENTS"],
    "framework_endpoints": ["FRAMEWORK ENDPOINTS"],
    "page_intel": ["CONTENT INTEL"],
    "hidden": ["CONTENT INTEL"],
    "comments": ["CONTENT INTEL"],
    "css_comments": ["CONTENT INTEL"],
    "js_comments": ["CONTENT INTEL"],
    "data_attrs": ["CONTENT INTEL"],
    "aria": ["CONTENT INTEL"],
    "initial_state": ["CONTENT INTEL"],
    "next_data": ["CONTENT INTEL"],
    "nuxt_data": ["CONTENT INTEL"],
    "jsonld": ["CONTENT INTEL"],
    "secrets": ["CONTENT INTEL", "SCANNING SPECIAL FILE CONTENTS", "JS BUNDLE HARVESTING", "SOURCE MAP HARVESTING"],
    "b64": ["CONTENT INTEL", "SCANNING SPECIAL FILE CONTENTS", "JS BUNDLE HARVESTING", "SOURCE MAP HARVESTING"],
    "hex": ["CONTENT INTEL", "SCANNING SPECIAL FILE CONTENTS", "JS BUNDLE HARVESTING", "SOURCE MAP HARVESTING"],
    "js_bundles": ["JS BUNDLE HARVESTING"],
    "source_maps": ["SOURCE MAP HARVESTING"],
    "sourcemaps": ["CONTENT INTEL"],
    "js_deobfuscate": ["JS DEOBFUSCATION"],
    "email_perm": ["EMAIL PERMUTATIONS + MX"],
    "email_mx": ["EMAIL PERMUTATIONS + MX"],
    "catchall": ["EMAIL PERMUTATIONS + MX"],
    "dorks": ["DORK GENERATION"],
    "cloud_buckets": ["CLOUD BUCKET ENUMERATION"],
    "resurrection": ["RESURRECTION MAP"],
    "link_rot": ["LINK ROT QUANTIFICATION"],
    "query_param_evolution": ["QUERY PARAM EVOLUTION"],
    "form_endpoint_history": ["FORM ENDPOINT HISTORY"],
    "external_domain_graph": ["EXTERNAL DOMAIN GRAPH"],
    "secret_age": ["SECRET AGE ESTIMATION"],
    "duplicate_site": ["DUPLICATE SITE DETECTION"],
    "resurrection_map": ["RESURRECTION MAP"],
    "cred_provenance": ["CREDENTIAL CORRELATION"],
    "cred_score": ["CREDENTIAL CORRELATION"],
    "jsonl": ["RAW EVIDENCE EXPORT"],
    "baseline_diff": ["COVERAGE REPORT"],
    "ignore_file": ["CREDENTIAL CORRELATION"],
    "env_parser": ["SCANNING SPECIAL FILE CONTENTS", "CONTENT INTEL"],
    "wp_parser": ["SCANNING SPECIAL FILE CONTENTS"],
    "django_parser": ["SCANNING SPECIAL FILE CONTENTS"],
    "docker_parser": ["SCANNING SPECIAL FILE CONTENTS"],
    "json_walker": ["SCANNING SPECIAL FILE CONTENTS", "CONTENT INTEL"],
    "source_content": ["SOURCE MAP HARVESTING"],
    "atob": ["CONTENT INTEL", "JS BUNDLE HARVESTING", "SOURCE MAP HARVESTING"],
    "jwt_claims": ["CONTENT INTEL", "HARVESTING HTTP HEADERS"],
    "url_param_creds": ["CONTENT INTEL"],
    "cookie_jwt": ["HARVESTING HTTP HEADERS"],
    "header_secrets": ["HARVESTING HTTP HEADERS", "ARCHIVED HEADERS"],
    "basic_auth_url": ["CONTENT INTEL"],
    "stack_trace": ["CONTENT INTEL"],
    "phpinfo_parse": ["SCANNING SPECIAL FILE CONTENTS"],
    "cloud_meta": ["CONTENT INTEL"],
    "disallow_xref": ["PARSING ROBOTS / SITEMAP"],
    "entropy": [],
    "hashes": ["CONTENT INTEL", "SCANNING SPECIAL FILE CONTENTS", "JS BUNDLE HARVESTING", "SOURCE MAP HARVESTING"],
    "cache": [],
    "raw_evidence": ["RAW EVIDENCE EXPORT"],
    "proxy": [],
    "ua": [],
    "rate_limit": [],
    "jitter": [],
    "cli": [], "tui": [],
    "report_json": [], "report_csv": [], "report_html": [], "report_txt": [],
}

PHASE_DEPENDENCIES = {
    "HARVESTING HTTP HEADERS": ["FETCHING CDX INDEX"],
    "DELETION FORENSICS": ["FETCHING CDX INDEX"],
    "WAYBACK VS LIVE DIFF": ["FETCHING CDX INDEX"],
    "MAPPING TOPOLOGY": ["FETCHING CDX INDEX"],
    "TLS / DNS RECON": [],
    "WAYBACK / ARCHIVE ENDPOINTS": [],
    "CERTIFICATE TRANSPARENCY": [],
    "WHOIS / RDAP": [],
    "DNS FULL RECORDS": [],
    "PASSIVE DNS SOURCES": [],
    "SPECIAL FILES": [],
    "SCANNING SPECIAL FILE CONTENTS": ["SPECIAL FILES"],
    "PARSING ROBOTS / SITEMAP": [],
    "CONTENT INTEL": ["FETCHING CDX INDEX"],
    "JS BUNDLE HARVESTING": ["FETCHING CDX INDEX"],
    "SOURCE MAP HARVESTING": ["CONTENT INTEL"],
    "JS DEOBFUSCATION": ["FETCHING CDX INDEX"],
    "SUBDOMAIN TAKEOVER PROBE": ["MAPPING TOPOLOGY"],
    "ADJACENT SNAPSHOT DIFFS": ["FETCHING CDX INDEX"],
    "ARCHIVED HEADERS": ["FETCHING CDX INDEX"],
    "DOCUMENT METADATA": ["MAPPING TOPOLOGY"],
    "FRAMEWORK ENDPOINTS": [],
    "CLOUD BUCKET ENUMERATION": [],
    "DORK GENERATION": [],
    "ROBOTS/SITEMAP HISTORICAL DIFF": [],
    "SUBDOMAIN PERMUTATION + BRUTE": [],
    "EMAIL PERMUTATIONS + MX": ["CONTENT INTEL"],
    "VARIANT ENUMERATION": ["FETCHING CDX INDEX"],
    "RESURRECTION MAP": ["DELETION FORENSICS"],
    "LINK ROT QUANTIFICATION": ["CONTENT INTEL"],
    "QUERY PARAM EVOLUTION": ["FETCHING CDX INDEX"],
    "SECRET AGE ESTIMATION": ["CONTENT INTEL"],
    "FORM ENDPOINT HISTORY": ["CONTENT INTEL"],
    "EXTERNAL DOMAIN GRAPH": ["CONTENT INTEL"],
    "DUPLICATE SITE DETECTION": ["FETCHING CDX INDEX"],
    "REVISIT RECORD ANALYSIS": ["FETCHING CDX INDEX"],
    "URLKEY / SURT ANALYTICS": ["FETCHING CDX INDEX"],
    "SNAPSHOT DENSITY RANKING": ["FETCHING CDX INDEX"],
    "REDIRECT CHAIN RECONSTRUCTION": ["FETCHING CDX INDEX"],
    "PASSIVE CRAWL CORRELATION": ["WAYBACK / ARCHIVE ENDPOINTS"],
    "PAGE TREE RECONSTRUCTION": ["FETCHING CDX INDEX"],
    "DUPLICATE SECRET COLLAPSE": ["CONTENT INTEL"],
    "CREDENTIAL CORRELATION": ["CONTENT INTEL"],
    "RAW EVIDENCE EXPORT": [],
    "COVERAGE REPORT": [],
    "CACHE WARMUP": [],
    "PROBING LIVE STATUS": ["FETCHING CDX INDEX"],
}


def _phase_names_for_ids(ids):
    return {PHASE_IDS[i - 1] for i in ids if 1 <= i <= PHASE_COUNT}


def _expand_phase_dependencies(ids):
    expanded = set(ids)
    changed = True
    while changed:
        changed = False
        for idx in list(expanded):
            if not (1 <= idx <= PHASE_COUNT):
                continue
            name = PHASE_IDS[idx - 1]
            for dep_name in PHASE_DEPENDENCIES.get(name, []):
                dep_idx = PHASE_INDEX.get(dep_name)
                if dep_idx and dep_idx not in expanded:
                    expanded.add(dep_idx)
                    changed = True
    return expanded


def _phase_ids_from_selection():
    ids = set()
    if not get_selection_active():
        return ids
    for serial, _ in SELECTION.snapshot():
        if 1 <= serial <= len(CAPABILITY_CATALOG):
            key = CAPABILITY_CATALOG[serial - 1][2]
            for name in CAP_TO_PHASES.get(key, []):
                idx = PHASE_INDEX.get(name)
                if idx:
                    ids.add(idx)
    return ids


def effective_phases():
    with _PHASE_LOCK:
        explicit = None if ACTIVE_PHASES is None else set(ACTIVE_PHASES)
    sel = _phase_ids_from_selection()
    if explicit is None and not sel:
        return None
    if explicit is None:
        base = sel if sel else set()
    elif not sel:
        base = set(explicit)
    else:
        base = set(explicit) | set(sel)
    if not base:
        return None
    return _expand_phase_dependencies(base)


def set_active_phases(ids):
    global ACTIVE_PHASES
    with _PHASE_LOCK:
        ACTIVE_PHASES = None if not ids else set(ids)


def get_active_phases():
    with _PHASE_LOCK:
        return None if ACTIVE_PHASES is None else set(ACTIVE_PHASES)


def phase_enabled(name):
    eff = effective_phases()
    if eff is None:
        return True
    idx = PHASE_INDEX.get(name)
    if idx is None:
        return True
    return idx in eff


def show_phases():
    active = get_active_phases()
    eff = effective_phases()
    T("PHASES", f"phase catalog - {PHASE_COUNT} entries")
    for i, name in enumerate(PHASE_IDS, start=1):
        explicit = "[ON] " if (active is None or i in active) else "[OFF]"
        effective = "[EFF]" if (eff is None or i in eff) else "     "
        dur = _PHASE_DURATION.get(name)
        extra = f"  ({dur:.1f}s)" if dur else ""
        T("PHASES", f"  p{i:02d} {explicit} {effective} {name}{extra}")
    if eff is not None:
        T("PHASES", f"effective: {sorted(eff)}")
    else:
        T("PHASES", "effective: ALL")


class Selection:
    def __init__(self):
        self.selected = OrderedDict()
        self.lock = threading.Lock()

    def clear(self):
        with self.lock:
            self.selected.clear()

    def add(self, serial, name, desc):
        with self.lock:
            self.selected[serial] = {"name": name, "desc": desc}

    def snapshot(self):
        with self.lock:
            return list(self.selected.items())

    def keys(self):
        with self.lock:
            return set(self.selected.keys())


SELECTION = Selection()
_SELECTION_ACTIVE_LOCK = threading.Lock()
_SELECTION_ACTIVE = {"v": False}


def get_selection_active():
    with _SELECTION_ACTIVE_LOCK:
        return _SELECTION_ACTIVE["v"]


def set_selection_active(v):
    with _SELECTION_ACTIVE_LOCK:
        _SELECTION_ACTIVE["v"] = bool(v)


CAPABILITY_CATALOG = []
_CAP_CACHE = {}
_CAP_CACHE_LOCK = threading.Lock()


def _register_capabilities():
    catalog = [
        ("CDX index fetch", "Pull every snapshot record for the target domain", "cdx"),
        ("CDX full-field query", "urlkey, offset, filename, redirect fields", "cdx_full"),
        ("CDX filter language", "statuscode/mimetype/regex filters", "cdx_filter"),
        ("CDX prefix query", "matchType=prefix path enumeration", "cdx_prefix"),
        ("CDX timeline per URL", "Full status history per URL", "timeline"),
        ("Calendar captures API", "Per-day snapshot density", "calendar"),
        ("Anchor text search", "Which URLs referenced a term", "anchor"),
        ("Availability API", "Nearest-snapshot lookup", "availability"),
        ("Snapshot sparkline", "Per-year snapshot density", "sparkline"),
        ("Memento TimeMap (link)", "Machine-readable snapshot list", "timemap"),
        ("Memento TimeMap (JSON)", "JSON-format TimeMap", "timemap_json"),
        ("Memento aggregator", "Multi-archive TimeMap", "memento_agg"),
        ("Archive.today lookup", "Independent snapshot lookup", "archive_today"),
        ("Common Crawl query", "Independent crawl history", "common_crawl"),
        ("Certificate Transparency (crt.sh)", "Subdomain lookup", "crt"),
        ("RDAP WHOIS", "Modern JSON WHOIS", "rdap"),
        ("WHOIS via port 43", "Legacy WHOIS with referral", "whois"),
        ("Live status probing", "HEAD every archived URL", "live_status"),
        ("Deletion classification", "removed/gone/legal/blocked/redirected/offline", "deletion_class"),
        ("Deletion window detection", "Bracket when each URL disappeared", "deletion_window"),
        ("Mass deletion clustering", "Group URLs deleted in same window", "mass_deletion"),
        ("First vs last diff", "Diff earliest and latest snapshot body", "first_last_diff"),
        ("Adjacent snapshot diffs", "Diff every adjacent snapshot pair", "adjacent_diff"),
        ("Wayback vs live diff", "Compare last archive with live", "wayback_live_diff"),
        ("Live header harvest", "Full HTTP response headers", "headers"),
        ("Header summary", "Aggregate servers, security, CDN, cookies", "header_summary"),
        ("Archived header extraction", "X-Archive-Orig-* headers per snapshot", "archived_headers"),
        ("Archived header diff", "Historical Server/CSP/cookie changes", "archived_header_diff"),
        ("Cookie flag analysis", "Secure, HttpOnly, SameSite", "cookie_flags"),
        ("Archive exclusion detection", "X-Robots-Tag noarchive/noindex", "exclusions"),
        ("X-Archive-Src extraction", "WARC collection identifier", "archive_src"),
        ("Revisit detection", "warc/revisit records", "revisit"),
        ("TLS certificate info", "Subject, issuer, SANs, validity", "tls"),
        ("TLS version enumeration", "TLS 1.0/1.1/1.2/1.3 support", "tls_versions"),
        ("TLS cipher enumeration", "Weak/strong cipher support", "tls_ciphers"),
        ("Certificate chain validation", "Broken/incomplete chains", "tls_chain"),
        ("OCSP/CRL check", "Revocation support", "ocsp"),
        ("HSTS preload check", "Preload list membership", "hsts_preload"),
        ("DNS resolution", "Live IPv4 + IPv6", "dns"),
        ("DNS full record lookup", "A/AAAA/CNAME/MX/NS/SOA/TXT/CAA", "dns_full"),
        ("DNS SRV enumeration", "Service location records", "srv"),
        ("DNS TLSA lookup", "DANE cert fingerprints", "tlsa"),
        ("DNS SMIMEA lookup", "S/MIME cert fingerprints", "smimea"),
        ("DKIM selector enumeration", "Reveals mail provider", "dkim"),
        ("BIMI records", "Brand Indicators for Message Identification", "bimi"),
        ("DNSSEC validation", "Signing status", "dnssec"),
        ("Zone transfer attempt", "AXFR test", "axfr"),
        ("Reverse DNS lookup", "PTR from IP", "ptr"),
        ("Wildcard DNS detection", "Random subdomain probe", "wildcard"),
        ("ASN lookup", "Network ownership", "asn"),
        ("TCP port scan", "Open ports on resolved IPs", "ports"),
        ("HTTP/2 detection", "Protocol version", "http2"),
        ("WAF fingerprinting", "Cloudflare, Akamai, Sucuri", "waf"),
        ("CORS misconfiguration", "Access-Control-Allow-Origin: *", "cors"),
        ("Rate limit header parsing", "API quota hints", "ratelimit"),
        ("Robtex passive DNS", "Free passive DNS history", "robtex"),
        ("Mnemonic Passive DNS", "Free passive DNS", "mnemonic_pdns"),
        ("HackerTarget API", "Reverse IP, DNS lookup", "hackertarget"),
        ("Subdomain enumeration", "Every subdomain in CDX", "subdomains"),
        ("Subdomain first/last seen", "Timeline stats per subdomain", "subdomain_stats"),
        ("Subdomain takeover probe", "Dead subdomains claimable", "takeover"),
        ("Subdomain permutation", "dev-, staging-, api- patterns", "subdomain_perm"),
        ("Subdomain brute-force", "Wordlist-based DNS enumeration", "subdomain_brute"),
        ("Case variant enumeration", "/About vs /about vs /ABOUT", "case_variant"),
        ("Slash variant enumeration", "/page vs /page/", "slash_variant"),
        ("Scheme variant enumeration", "http vs https", "scheme_variant"),
        ("Port variant enumeration", ":80 vs :8080", "port_variant"),
        ("Document harvesting", "Every archived document", "documents"),
        ("PDF metadata extraction", "Author, XMP, producer", "pdf_meta"),
        ("Office metadata extraction", "Author, company", "office_meta"),
        ("Office macro detection", "VBA macro presence", "office_macros"),
        ("Image EXIF extraction", "GPS, camera, software", "exif"),
        ("PNG chunk extraction", "Text chunks", "png_chunks"),
        ("SVG embedded JS detection", "XSS vectors", "svg_js"),
        ("ZIP internal listing", "Contained files", "zip_listing"),
        ("TAR internal listing", "Contained files", "tar_listing"),
        ("SQL dump parsing", "Tables, columns, sample rows", "sql_dump"),
        ("Log file parsing", "Usernames, IPs, paths", "log_parse"),
        ("PEM/CRT/KEY parsing", "Cert/key material", "pem_parse"),
        ("PGP key parsing", "UID, email, fingerprint", "pgp"),
        ("SSH key fingerprinting", "SHA-256 fingerprint", "ssh_key"),
        ("Torrent file parsing", "Trackers, file list", "torrent"),
        ("ICS calendar parsing", "Events, attendees", "ics"),
        ("RSS/Atom feed parsing", "Content feed extraction", "rss"),
        ("Redirect history", "301/302/303/307/308 events", "redirects"),
        ("Content-type breakdown", "Mimetype frequency", "content_types"),
        ("Status code breakdown", "HTTP status frequency", "status_codes"),
        ("Capture timeline", "Snapshots by month", "timeline_monthly"),
        ("Capture gap detection", "Periods with no snapshots", "gaps"),
        ("URL depth distribution", "Path segments per URL", "url_depths"),
        ("Query parameter frequency", "Query params across URLs", "query_params"),
        ("File extension frequency", "File extensions across URLs", "file_extensions"),
        ("First/last seen", "Earliest and latest snapshot", "first_last_seen"),
        ("Digest change rate", "Content churn ratio", "churn"),
        ("Digest clustering", "Duplicate content graph", "digest_cluster"),
        ("URLKey analysis", "SURT-form dedup", "urlkey"),
        ("Snapshot count ranking", "Importance proxy", "snapshot_rank"),
        ("robots.txt parsing", "User-agents, disallow, allow, sitemaps", "robots_parsed"),
        ("robots.txt historical diff", "New disallow rules over time", "robots_diff"),
        ("sitemap.xml parsing", "URLs, nested sitemaps, lastmods", "sitemap_parsed"),
        ("sitemap.xml historical diff", "New/removed URLs over time", "sitemap_diff"),
        ("Special file probing", "well-known sensitive paths", "special_files"),
        ("Special file content scan", "Fetch + scan every hit for secrets", "special_scan"),
        ("Framework endpoint enumeration", "framework-specific paths", "framework_endpoints"),
        ("Page intelligence", "Title, generator, canonical, meta, headings", "page_intel"),
        ("Email extraction", "Every email found", "emails"),
        ("Phone extraction", "Context-anchored phones", "phones"),
        ("Social link extraction", "Every social profile", "social_links"),
        ("Internal/external links", "Link graph per page", "links"),
        ("JS file discovery", "Every script src", "js_files"),
        ("CSS file discovery", "Every stylesheet", "css_files"),
        ("Image discovery", "Every img src", "images"),
        ("Iframe discovery", "Every iframe src", "iframes"),
        ("Form + input extraction", "Every form + input", "forms"),
        ("API endpoint discovery", "Every /api/... string", "api_endpoints"),
        ("GraphQL endpoint discovery", "/graphql, /gql, /query", "graphql_endpoints"),
        ("CMS fingerprinting", "CMS signatures", "cms"),
        ("Analytics ID extraction", "GA, GA4, GTM, FB Pixel", "analytics"),
        ("Hidden element extraction", "display:none, aria-hidden, hidden inputs", "hidden"),
        ("HTML comment extraction", "Every comment with context", "comments"),
        ("CSS comment extraction", "Every CSS comment", "css_comments"),
        ("JS comment extraction", "Every JS comment", "js_comments"),
        ("Data attribute extraction", "data-* attributes", "data_attrs"),
        ("ARIA label extraction", "aria-label, aria-description", "aria"),
        ("Title attribute extraction", "title= tooltips", "title_attr"),
        ("Image alt text extraction", "alt= attributes", "alt_text"),
        ("Placeholder text extraction", "placeholder= attributes", "placeholder"),
        ("window.__INITIAL_STATE__ parsing", "App state from JS", "initial_state"),
        ("__NEXT_DATA__ parsing", "Next.js SSR state", "next_data"),
        ("__NUXT__ parsing", "Nuxt SSR state", "nuxt_data"),
        ("Base64 data URI decoding", "Decode base64 data URIs", "data_uri"),
        ("Nonce/CSRF extraction", "Nonces and CSRF tokens", "nonce"),
        ("Pingback/webmention links", "Pingback, webmention endpoints", "pingback"),
        ("Preconnect/prefetch domains", "Third-party domains", "preconnect"),
        ("Analytics event extraction", "Track/send/log calls", "analytics_events"),
        ("JS error message extraction", "throw new Error strings", "js_errors"),
        ("WebSocket URL extraction", "wss:// endpoints", "ws_urls"),
        ("GraphQL query extraction", "query/mutation strings", "gql_queries"),
        ("Environment name extraction", "production/staging/dev", "env_names"),
        ("Version number extraction", "Semantic versions", "versions"),
        ("Console log extraction", "console.log strings", "console_logs"),
        ("JSON-LD extraction", "Structured data blocks", "jsonld"),
        ("Feed link discovery", "RSS/Atom feeds", "feeds"),
        ("Manifest discovery", "PWA manifest", "manifest"),
        ("Hreflang extraction", "i18n alternates", "hreflang"),
        ("SRI hash extraction", "Subresource Integrity", "sri"),
        ("CSP parsing", "Directive-by-directive", "csp_parse"),
        ("Source-map reference extraction", "sourceMappingURL refs", "sourcemaps"),
        ("Source map fetching", "Fetch .js.map and scan", "source_maps"),
        ("JS bundle harvesting", "Fetch every .js and scan", "js_bundles"),
        ("JS deobfuscation", "Basic walk on minified JS", "js_deobfuscate"),
        ("Secret scanning", "secret patterns", "secrets"),
        ("Base64 auto-decode", "Decode + rescan base64", "b64"),
        ("Hex auto-decode", "Decode + rescan hex", "hex"),
        ("Email permutation generation", "Corporate email guesses", "email_perm"),
        ("Email MX validation", "Mail server check", "email_mx"),
        ("Catch-all email detection", "Wildcard mail behavior", "catchall"),
        ("Google/Bing dork generation", "Search engine dorks", "dorks"),
        ("User-agent rotation", "real UAs", "ua"),
        ("Proxy rotation", "Rotate outbound requests through proxies", "proxy"),
        ("Rate limiting", "Token bucket per host", "rate_limit"),
        ("Adaptive jitter", "Randomized 5-8s throttle for archive.org", "jitter"),
        ("CLI mode", "Scriptable batch scan", "cli"),
        ("TUI mode", "Interactive console", "tui"),
        ("JSON report", "Machine-readable dump", "report_json"),
        ("CSV report", "One row per URL", "report_csv"),
        ("HTML report", "Dark-themed with severity", "report_html"),
        ("TXT report", "Full detailed text report", "report_txt"),
        ("Resurrection map", "Removed URL -> last live snapshot", "resurrection"),
        ("Link rot quantification", "Ratio of dead outbound links", "link_rot"),
        ("Query param evolution", "Query params over time per path", "query_param_evolution"),
        ("Form endpoint history", "Forms aggregated per action", "form_endpoint_history"),
        ("Subdomain cross-reference", "First/last seen per subdomain", "subdomain_crossref"),
        ("External domain graph", "External hosts seen", "external_domain_graph"),
        ("Secret age estimation", "First/last seen per secret", "secret_age"),
        ("Duplicate site detection", "Digest clusters", "duplicate_site"),
        ("JSONL checkpoint", "Append-only record log per scan", "jsonl"),
        ("Cross-scan baseline diff", "Compare current vs previous report", "baseline_diff"),
        ("Entropy gate", "Filter low-entropy secret matches", "entropy"),
        ("Structural env parser", ".env KEY=VALUE extraction", "env_parser"),
        ("WP config parser", "wp-config.php constants", "wp_parser"),
        ("Django settings parser", "PASSWORD fields", "django_parser"),
        ("Docker env block parser", "docker-compose environment", "docker_parser"),
        ("JSON tree walker", "Recursive JSON secret extraction", "json_walker"),
        ("Source map sourcesContent", "Extract per-file source", "source_content"),
        ("atob/Buffer.from decoder", "Decode JS-embedded base64", "atob"),
        ("JWT claim extractor", "iss/aud/sub/role/exp", "jwt_claims"),
        ("URL param credential scan", "token=, key=, password=, pwd=", "url_param_creds"),
        ("Cookie JWT detection", "Session cookies carrying JWTs", "cookie_jwt"),
        ("Header secret extraction", "X-Api-Key, Authorization echoes", "header_secrets"),
        ("Basic auth URL extraction", "user:pass@host", "basic_auth_url"),
        ("Stack trace parser", "Error pages leaking config", "stack_trace"),
        ("phpinfo parser", "Table-structured phpinfo output", "phpinfo_parse"),
        ("Cloud metadata leak", "169.254.169.254 references", "cloud_meta"),
        ("Disallow cross-reference", "robots.txt paths that were archived", "disallow_xref"),
        ("Credential provenance", "First/last seen, context, rotation", "cred_provenance"),
        ("Credential severity scoring", "severity x context x rotation", "cred_score"),
        ("Ignore allowlist", ".stratascan_ignore file", "ignore_file"),
        ("Hashed password detection", "bcrypt/argon2/scrypt/pbkdf2/md5crypt", "hashes"),
        ("Local cache", "SQLite store for CDX, bodies, findings", "cache"),
        ("Raw evidence export", "findings.jsonl + raw_snapshots + provenance + coverage", "raw_evidence"),
    ]
    CAPABILITY_CATALOG.clear()
    CAPABILITY_CATALOG.extend(catalog)


_register_capabilities()


def _invalidate_cap_cache():
    with _CAP_CACHE_LOCK:
        _CAP_CACHE.clear()


def show_capability_catalog():
    T("SHOW", f"capability catalog - {len(CAPABILITY_CATALOG)} entries")
    eff = effective_phases()
    for i, (name, desc, key) in enumerate(CAPABILITY_CATALOG, start=1):
        marker = ""
        if get_selection_active() and i in SELECTION.keys():
            marker = " [SELECTED]"
        note = ""
        phases = CAP_TO_PHASES.get(key, [])
        if eff is not None and phases:
            active_here = any(PHASE_INDEX.get(p) in eff for p in phases)
            note = " [RUN]" if active_here else " [SKIP]"
        T("SHOW", f"  {i:03d}. {name}  [{key}]  - {desc}{marker}{note}")


def show_selection():
    items = SELECTION.snapshot()
    if not items:
        T("SELECT", "no items selected - all capabilities run (subject to phase filter)")
        return
    T("SELECT", f"{len(items)} selected")
    for serial, data in items:
        T("SELECT", f"  #{serial}  {data['name']} - {data['desc']}")
    ids = _phase_ids_from_selection()
    if ids:
        T("SELECT", f"implied phases (raw): {sorted(ids)}")
        expanded = _expand_phase_dependencies(ids)
        added = sorted(expanded - ids)
        if added:
            T("SELECT", f"auto-included dependency phases: {added}")


def handle_select(arg):
    arg = (arg or "").strip()
    if not arg:
        show_selection()
        return
    if arg.lower() in ("clear", "reset", "none"):
        SELECTION.clear()
        set_selection_active(False)
        _invalidate_cap_cache()
        T("SELECT", "selection cleared")
        return
    if arg.lower() in ("all", "*"):
        SELECTION.clear()
        set_selection_active(False)
        _invalidate_cap_cache()
        T("SELECT", f"all {len(CAPABILITY_CATALOG)} capabilities enabled")
        return
    added = 0
    bad = []
    for p in re.split(r"[,\s]+", arg):
        if not p:
            continue
        try:
            n = int(p)
        except ValueError:
            bad.append(p)
            continue
        if 1 <= n <= len(CAPABILITY_CATALOG):
            name, desc, key = CAPABILITY_CATALOG[n - 1]
            SELECTION.add(n, name, desc)
            added += 1
        else:
            bad.append(p)
    if added:
        set_selection_active(True)
        _invalidate_cap_cache()
    T("SELECT", f"added {added} item(s) (total {len(SELECTION.snapshot())})")
    if bad:
        T("SELECT", f"invalid: {', '.join(bad)}")
    show_selection()


def _cap(key):
    if not get_selection_active():
        return True
    with _CAP_CACHE_LOCK:
        cached = _CAP_CACHE.get(key)
    if cached is not None:
        return cached
    keys = SELECTION.keys()
    result = False
    for i, (name, desc, k) in enumerate(CAPABILITY_CATALOG, start=1):
        if k == key and i in keys:
            result = True
            break
    with _CAP_CACHE_LOCK:
        _CAP_CACHE[key] = result
    return result


def _phase_begin(name):
    with _PHASE_TIME_LOCK:
        _PHASE_START[name] = time.time()
    idx = PHASE_INDEX.get(name, 0)
    T("PHASE", f"[p{idx:02d}/{PHASE_COUNT}] {name}")


def _phase_end(name):
    with _PHASE_TIME_LOCK:
        t0 = _PHASE_START.pop(name, None)
        if t0:
            _PHASE_DURATION[name] = time.time() - t0


def run_deep_scan(domain, date_from=None, date_to=None, workers=8,
                  extract_content=True, only_removed=False, content_limit=200,
                  no_live_check=False, path_contains=None, mimetype=None,
                  out_dir=None, max_snapshots=None, full_special=True,
                  harvest_headers=True, scan_js=True, scan_maps=True, scan_special=True,
                  deletion_forensics=True, network_depth=True, document_meta=True,
                  archived_headers=True, framework_scan=True, cloud_scan=True,
                  dork_gen=True, wayback_extras=True, baseline_path=None, raw=False,
                  state=None, partial_sink=None, stop_flag=None):
    domain = normalize_domain(domain)
    prefix = re.sub(r"[^a-zA-Z0-9.-]", "_", domain)
    if out_dir:
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
    else:
        out_path = _default_out_dir()

    _bind_jsonl(out_path / f"{prefix}_checkpoint.jsonl")
    _bind_cache(out_path / f"{prefix}_cache.sqlite")
    _bind_raw(out_path, raw)
    if raw:
        _bind_findings(out_path / f"{prefix}_findings.jsonl", True)
    _load_ignore(out_path)

    js = jitter_status()
    T("JITTER", f"enabled={js['enabled']} range={js['min']:.1f}-{js['max']:.1f}s hosts={js['hosts']}")

    def update_stat(key, value):
        if state is not None:
            state.stats[key] = value

    def set_phase(phase):
        if state is not None:
            state.stats["phase"] = phase

    snapshots = []
    if phase_enabled("FETCHING CDX INDEX"):
        _phase_begin("FETCHING CDX INDEX")
        set_phase("FETCHING CDX INDEX")
        snapshots = fetch_all_snapshots(domain, date_from, date_to, max_snapshots)
        T("PHASE", f"{len(snapshots)} raw snapshot records")
        update_stat("snapshots", len(snapshots))
        if partial_sink is not None:
            partial_sink.setdefault("extras", {})["total_snapshots"] = len(snapshots)
        _phase_end("FETCHING CDX INDEX")

    by_url = group_by_url(snapshots)
    update_stat("urls", len(by_url))

    status_map = None
    if phase_enabled("PROBING LIVE STATUS") and not no_live_check:
        _phase_begin("PROBING LIVE STATUS")
        set_phase("PROBING LIVE STATUS")
        status_map = check_live_status(by_url, workers=workers, limit=1000)
        _phase_end("PROBING LIVE STATUS")
    deletion_classes = classify_deletion(status_map) if status_map else {}
    results = build_url_results(by_url, status_map, deletion_classes)
    results = filter_results(results, path_contains, mimetype, only_removed)
    result_urls = {r["original"] for r in results}
    update_stat("removed", sum(1 for r in results if r.get("likely_removed")))
    update_stat("live", sum(1 for r in results if r.get("likely_removed") is False))
    if partial_sink is not None:
        partial_sink["results"] = results

    subdomains, subdomain_stats, documents, redirects = [], {}, [], []
    ctypes, status_codes, timeline, gaps = Counter(), Counter(), {}, []
    url_depths, query_params, file_extensions = {}, {}, {}
    fl_seen, digest_rate, page_tree = {}, 0.0, {}
    if phase_enabled("MAPPING TOPOLOGY"):
        _phase_begin("MAPPING TOPOLOGY")
        set_phase("MAPPING TOPOLOGY")
        subdomains = extract_subdomains(snapshots, domain)
        subdomain_stats = subdomain_first_last_seen(snapshots, domain)
        documents = harvest_documents(by_url)
        redirects = find_redirect_history(by_url)
        ctypes = content_type_breakdown(snapshots)
        status_codes = status_code_breakdown(snapshots)
        timeline = capture_timeline(snapshots)
        gaps = find_capture_gaps(timeline)
        url_depths = url_depth_distribution(by_url.keys())
        query_params = extract_query_params(by_url.keys())
        file_extensions = extract_file_extensions(by_url.keys())
        fl_seen = first_last_seen(snapshots)
        digest_rate = digest_change_rate(snapshots)
        update_stat("subdomains", len(subdomains))
        update_stat("documents", len(documents))
        update_stat("redirects", len(redirects))
        if partial_sink is not None:
            partial_sink.setdefault("extras", {})["subdomains"] = subdomains
            partial_sink.setdefault("extras", {})["documents"] = documents
        _phase_end("MAPPING TOPOLOGY")

    if phase_enabled("PAGE TREE RECONSTRUCTION"):
        _phase_begin("PAGE TREE RECONSTRUCTION")
        page_tree = build_path_tree(by_url.keys())
        _phase_end("PAGE TREE RECONSTRUCTION")

    header_summary, header_map, archive_exclusions, archive_src = {}, {}, [], {}
    if phase_enabled("HARVESTING HTTP HEADERS") and harvest_headers and not no_live_check:
        _phase_begin("HARVESTING HTTP HEADERS")
        set_phase("HARVESTING HTTP HEADERS")
        header_map = harvest_live_headers(by_url, workers=workers, limit=500)
        header_summary = summarize_headers(header_map)
        archive_exclusions = detect_archive_exclusions(header_map)
        archive_src = extract_archive_src(header_map)
        cookie_secrets = _scan_cookie_values(header_map)
        header_secrets = _scan_headers_for_secrets(header_map)
        if partial_sink is not None:
            partial_sink.setdefault("extras", {})["header_summary"] = header_summary
            if cookie_secrets:
                partial_sink.setdefault("extras", {})["cookie_secrets"] = cookie_secrets
            if header_secrets:
                partial_sink.setdefault("extras", {})["header_secrets"] = header_secrets
        _phase_end("HARVESTING HTTP HEADERS")

    root_host = urllib.parse.urlparse(domain if "://" in domain else "http://" + domain).netloc or domain
    tls_info, dns_info = {}, {}
    if phase_enabled("TLS / DNS RECON"):
        _phase_begin("TLS / DNS RECON")
        set_phase("TLS / DNS RECON")
        tls_info = fetch_cert_info(root_host)
        dns_info = resolve_dns(root_host)
        if partial_sink is not None:
            partial_sink.setdefault("extras", {})["tls"] = tls_info
            partial_sink.setdefault("extras", {})["dns"] = dns_info
        _phase_end("TLS / DNS RECON")

    availability, sparkline, timemap = {}, {}, []
    timemap_json, memento_agg, archive_today = {}, [], {}
    common_crawl, calendar_data, anchor_data = {}, {}, []
    cdx_full_fields, cdx_filtered_example, cdx_prefix_example = [], [], []
    if phase_enabled("WAYBACK / ARCHIVE ENDPOINTS"):
        _phase_begin("WAYBACK / ARCHIVE ENDPOINTS")
        set_phase("WAYBACK / ARCHIVE ENDPOINTS")
        availability = fetch_availability(domain)
        sparkline = fetch_sparkline(domain)
        timemap = fetch_timemap(domain)
        timemap_json = fetch_timemap_json(domain)
        memento_agg = fetch_memento_aggregator(domain)
        archive_today = fetch_archive_today(domain)
        common_crawl = fetch_common_crawl(domain)
        calendar_data = fetch_calendar_captures(domain)
        anchor_data = fetch_anchor_search(domain.split(".")[0])
        cdx_full_fields = fetch_cdx_full_fields(domain, date_from, date_to, limit=100)
        cdx_filtered_example = fetch_cdx_filtered(domain, ["statuscode:404"], date_from, date_to, limit=100)
        cdx_prefix_example = fetch_cdx_prefix(domain + "/admin", date_from, date_to, limit=50)
        _phase_end("WAYBACK / ARCHIVE ENDPOINTS")

    ct_names = []
    if phase_enabled("CERTIFICATE TRANSPARENCY") and not no_live_check:
        _phase_begin("CERTIFICATE TRANSPARENCY")
        set_phase("CERTIFICATE TRANSPARENCY")
        ct_names = fetch_crt_sh(domain)
        if partial_sink is not None:
            partial_sink.setdefault("extras", {})["ct_names"] = ct_names
        _phase_end("CERTIFICATE TRANSPARENCY")

    rdap_data, whois_data = {}, {}
    if phase_enabled("WHOIS / RDAP"):
        _phase_begin("WHOIS / RDAP")
        set_phase("WHOIS / RDAP")
        rdap_data = fetch_rdap(domain)
        whois_data = fetch_whois(domain)
        if partial_sink is not None:
            partial_sink.setdefault("extras", {})["whois"] = whois_data
            partial_sink.setdefault("extras", {})["rdap"] = rdap_data
        _phase_end("WHOIS / RDAP")

    dns_full, dns_srv, dns_tlsa, dns_smimea = {}, {}, {}, {}
    dkim_selectors, bimi = {}, {}
    dnssec_ok, wildcard_dns, axfr_results, ptr_records = False, False, [], {}
    if phase_enabled("DNS FULL RECORDS"):
        _phase_begin("DNS FULL RECORDS")
        set_phase("DNS FULL RECORDS")
        dns_full = fetch_dns_records(domain)
        dns_srv = fetch_dns_srv(domain)
        dns_tlsa = fetch_dns_tlsa(domain)
        dns_smimea = fetch_dns_smimea(domain)
        dkim_selectors = fetch_dkim_selectors(domain)
        bimi = fetch_bimi(domain)
        dnssec_ok = fetch_dnssec_status(domain)
        wildcard_dns = check_wildcard_dns(domain)
        axfr_results = attempt_zone_transfer(domain)
        for ip in (dns_info.get("ipv4") or [])[:5]:
            ptr = reverse_dns_lookup(ip)
            if ptr:
                ptr_records[ip] = ptr
        if partial_sink is not None:
            partial_sink.setdefault("extras", {})["dns_full"] = dns_full
            partial_sink.setdefault("extras", {})["dkim_selectors"] = dkim_selectors
        _phase_end("DNS FULL RECORDS")

    ports, tls_versions, tls_ciphers, tls_chain = {}, {}, {}, {}
    hsts_preload, ocsp_info, waf_hits = {}, {}, []
    http2_proto, cors_info, ratelimit_info, asn_info = None, {}, {}, {}
    if network_depth and not no_live_check:
        resolved_ips = dns_info.get("ipv4") or []
        if resolved_ips:
            ports = scan_ports(resolved_ips[0], workers=20)
            update_stat("ports", len(ports))
            if partial_sink is not None:
                partial_sink.setdefault("extras", {})["ports"] = ports
            asn_info = fetch_asn_geoip(resolved_ips[0])
        tls_versions = check_tls_versions(root_host)
        tls_ciphers = check_tls_ciphers(root_host)
        tls_chain = fetch_cert_chain(root_host)
        hsts_preload = check_hsts_preload(root_host)
        ocsp_info = check_ocsp(root_host)
        http2_proto = check_http2(root_host)
        status, headers = http_head_full(f"https://{root_host}")
        waf_hits = fingerprint_waf(headers)
        cors_info = check_cors(headers)
        ratelimit_info = check_rate_limit_headers(headers)

    robtex_data, mnemonic_data, hackertarget_data = {}, {}, {}
    if phase_enabled("PASSIVE DNS SOURCES"):
        _phase_begin("PASSIVE DNS SOURCES")
        set_phase("PASSIVE DNS SOURCES")
        robtex_data = query_robtex(domain)
        mnemonic_data = query_mnemonic_pdns(domain)
        hackertarget_data = query_hackertarget(domain)
        _phase_end("PASSIVE DNS SOURCES")

    special_files, special_file_scans = {}, {}
    if phase_enabled("SPECIAL FILES") and full_special:
        _phase_begin("SPECIAL FILES")
        set_phase("SPECIAL FILES")
        special_files = fetch_all_special_files(domain, date_from, date_to, workers=workers)
        update_stat("special_files", len(special_files))
        if partial_sink is not None:
            partial_sink.setdefault("extras", {})["special_files"] = special_files
        _phase_end("SPECIAL FILES")

    if phase_enabled("SCANNING SPECIAL FILE CONTENTS") and scan_special and special_files:
        _phase_begin("SCANNING SPECIAL FILE CONTENTS")
        set_phase("SCANNING SPECIAL FILE CONTENTS")
        special_file_scans = scan_special_file_contents(special_files, workers=workers, limit=200)
        if partial_sink is not None:
            partial_sink.setdefault("extras", {})["special_file_scans"] = special_file_scans
        _phase_end("SCANNING SPECIAL FILE CONTENTS")

    robots_parsed, sitemap_parsed = {}, {}
    if phase_enabled("PARSING ROBOTS / SITEMAP"):
        _phase_begin("PARSING ROBOTS / SITEMAP")
        set_phase("PARSING ROBOTS / SITEMAP")
        try:
            rh = fetch_special_file_history(domain, "robots.txt", date_from, date_to)
            if rh:
                robots_parsed = parse_robots_txt(rh[-1]["content_preview"])
            sh = fetch_special_file_history(domain, "sitemap.xml", date_from, date_to)
            if sh:
                sitemap_parsed = parse_sitemap_xml(sh[-1]["content_preview"])
        except Exception as e:
            T("WARN", f"robots/sitemap error: {e}")
        _phase_end("PARSING ROBOTS / SITEMAP")

    disallow_hits = []
    if robots_parsed and snapshots:
        disallow_hits = cross_reference_disallow(robots_parsed, snapshots)

    page_intel = {}
    if phase_enabled("CONTENT INTEL") and extract_content:
        _phase_begin("CONTENT INTEL")
        set_phase("CONTENT INTEL")
        limited_urls = set(list(result_urls)[: content_limit])
        page_intel = enrich_with_content(by_url, workers=workers, only_urls=limited_urls)
        if partial_sink is not None:
            partial_sink.setdefault("extras", {})["page_intel"] = page_intel
        _phase_end("CONTENT INTEL")

    js_bundle_secrets = {}
    if phase_enabled("JS BUNDLE HARVESTING") and scan_js:
        _phase_begin("JS BUNDLE HARVESTING")
        set_phase("JS BUNDLE HARVESTING")
        js_bundle_secrets = harvest_js_bundles(by_url, workers=workers, limit=200)
        _phase_end("JS BUNDLE HARVESTING")

    source_map_secrets = {}
    if phase_enabled("SOURCE MAP HARVESTING") and scan_maps and page_intel:
        _phase_begin("SOURCE MAP HARVESTING")
        set_phase("SOURCE MAP HARVESTING")
        source_map_secrets = harvest_source_maps(page_intel, workers=workers, limit=50)
        _phase_end("SOURCE MAP HARVESTING")

    js_deobfuscation = {}
    if phase_enabled("JS DEOBFUSCATION") and scan_js:
        _phase_begin("JS DEOBFUSCATION")
        set_phase("JS DEOBFUSCATION")
        js_deobfuscation = harvest_js_deobfuscation(by_url, workers=workers, limit=100)
        _phase_end("JS DEOBFUSCATION")

    deletion_timelines, mass_deletion_clusters, first_last_diffs = {}, [], {}
    takeover_candidates, adjacent_diff, wayback_live_diff = [], {}, {}
    if phase_enabled("DELETION FORENSICS") and deletion_forensics:
        _phase_begin("DELETION FORENSICS")
        set_phase("DELETION FORENSICS")
        timelines = build_url_timelines(by_url, workers=workers, limit=200)
        deletion_timelines, mass_deletion_clusters = detect_deletion_windows(timelines)
        update_stat("timelines", len(deletion_timelines))
        update_stat("clusters", len(mass_deletion_clusters))
        first_last_diffs = diff_first_last(by_url, timelines, workers=workers, limit=100)
        if partial_sink is not None:
            partial_sink.setdefault("extras", {})["deletion_timelines"] = deletion_timelines
            partial_sink.setdefault("extras", {})["mass_deletion_clusters"] = mass_deletion_clusters
        _phase_end("DELETION FORENSICS")

    if phase_enabled("SUBDOMAIN TAKEOVER PROBE") and subdomains:
        _phase_begin("SUBDOMAIN TAKEOVER PROBE")
        set_phase("SUBDOMAIN TAKEOVER PROBE")
        takeover_candidates = detect_subdomain_takeover(subdomains, workers=workers)
        _phase_end("SUBDOMAIN TAKEOVER PROBE")

    if phase_enabled("ADJACENT SNAPSHOT DIFFS") and wayback_extras:
        _phase_begin("ADJACENT SNAPSHOT DIFFS")
        set_phase("ADJACENT SNAPSHOT DIFFS")
        adjacent_diff = diff_adjacent_snapshots(by_url, workers=workers, limit=30)
        _phase_end("ADJACENT SNAPSHOT DIFFS")

    if phase_enabled("WAYBACK VS LIVE DIFF") and wayback_extras:
        _phase_begin("WAYBACK VS LIVE DIFF")
        set_phase("WAYBACK VS LIVE DIFF")
        wayback_live_diff = diff_wayback_live(by_url, workers=workers, limit=20)
        _phase_end("WAYBACK VS LIVE DIFF")

    archived_headers_map, archived_header_diffs = {}, {}
    if phase_enabled("ARCHIVED HEADERS") and archived_headers:
        _phase_begin("ARCHIVED HEADERS")
        set_phase("ARCHIVED HEADERS")
        try:
            for u in list(by_url.keys())[:20]:
                caps = by_url[u]
                if caps:
                    archived_headers_map[u] = fetch_archived_headers(caps[-1]["timestamp"], u)
            archived_header_diffs = diff_archived_headers(by_url, workers=workers, limit=30)
        except Exception as e:
            T("WARN", f"archived header error: {e}")
        _phase_end("ARCHIVED HEADERS")

    document_metadata = {}
    if phase_enabled("DOCUMENT METADATA") and document_meta and documents:
        _phase_begin("DOCUMENT METADATA")
        set_phase("DOCUMENT METADATA")
        try:
            document_metadata = analyze_documents(documents, workers=workers, limit=100)
        except Exception as e:
            T("WARN", f"document metadata error: {e}")
        _phase_end("DOCUMENT METADATA")

    framework_endpoints = {}
    if phase_enabled("FRAMEWORK ENDPOINTS") and framework_scan and not no_live_check:
        _phase_begin("FRAMEWORK ENDPOINTS")
        set_phase("FRAMEWORK ENDPOINTS")
        try:
            framework_endpoints = probe_framework_endpoints(root_host, workers=workers)
            update_stat("frameworks", sum(len(v) for v in framework_endpoints.values()))
        except Exception as e:
            T("WARN", f"framework scan error: {e}")
        _phase_end("FRAMEWORK ENDPOINTS")

    cloud_buckets = {}
    if phase_enabled("CLOUD BUCKET ENUMERATION") and cloud_scan and not no_live_check:
        _phase_begin("CLOUD BUCKET ENUMERATION")
        set_phase("CLOUD BUCKET ENUMERATION")
        try:
            cloud_buckets = check_cloud_buckets(domain)
        except Exception as e:
            T("WARN", f"cloud bucket error: {e}")
        _phase_end("CLOUD BUCKET ENUMERATION")

    dorks = []
    if phase_enabled("DORK GENERATION") and dork_gen:
        _phase_begin("DORK GENERATION")
        set_phase("DORK GENERATION")
        try:
            dorks = run_dorks(domain)
        except Exception as e:
            T("WARN", f"dork gen error: {e}")
        _phase_end("DORK GENERATION")

    robots_sitemap_diff = {}
    if phase_enabled("ROBOTS/SITEMAP HISTORICAL DIFF"):
        _phase_begin("ROBOTS/SITEMAP HISTORICAL DIFF")
        set_phase("ROBOTS/SITEMAP HISTORICAL DIFF")
        try:
            robots_sitemap_diff = diff_robots_sitemaps(domain, date_from, date_to)
        except Exception as e:
            T("WARN", f"robots/sitemap diff error: {e}")
        _phase_end("ROBOTS/SITEMAP HISTORICAL DIFF")

    subdomain_perms, subdomain_brute = [], []
    if phase_enabled("SUBDOMAIN PERMUTATION + BRUTE"):
        _phase_begin("SUBDOMAIN PERMUTATION + BRUTE")
        set_phase("SUBDOMAIN PERMUTATION + BRUTE")
        subdomain_perms = permute_subdomains(domain)
        if not no_live_check:
            subdomain_brute = brute_subdomains(domain, workers=12)
        _phase_end("SUBDOMAIN PERMUTATION + BRUTE")

    email_perm, email_mx_validation, catchall = [], {}, {}
    if phase_enabled("EMAIL PERMUTATIONS + MX"):
        _phase_begin("EMAIL PERMUTATIONS + MX")
        set_phase("EMAIL PERMUTATIONS + MX")
        names = set()
        existing_emails = set()
        for u, ts_map in page_intel.items():
            for ts, intel in ts_map.items():
                existing_emails.update(intel.get("emails") or [])
                for h in (intel.get("headings") or []):
                    m = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})', h.get("text", ""))
                    if m:
                        names.add(m.group(1))
        email_perm = generate_email_permutations(names, domain, existing_emails) if names else []
        for e in list(existing_emails)[:20]:
            valid, mx = validate_email_mx(e)
            email_mx_validation[e] = {"valid_mx": valid, "mx_records": mx}
        catchall = detect_catchall(domain)
        _phase_end("EMAIL PERMUTATIONS + MX")

    case_variants, slash_variants, scheme_variants, port_variants = {}, {}, {}, {}
    if phase_enabled("VARIANT ENUMERATION") and wayback_extras:
        _phase_begin("VARIANT ENUMERATION")
        set_phase("VARIANT ENUMERATION")
        case_variants = enumerate_case_variants(snapshots)
        slash_variants = enumerate_slash_variants(snapshots)
        scheme_variants = enumerate_scheme_variants(snapshots)
        port_variants = enumerate_port_variants(snapshots)
        _phase_end("VARIANT ENUMERATION")

    resurrection_map = []
    if phase_enabled("RESURRECTION MAP"):
        _phase_begin("RESURRECTION MAP")
        set_phase("RESURRECTION MAP")
        for u, data in deletion_timelines.items():
            resurrection_map.append({
                "url": u,
                "last_live": data.get("last_ok"),
                "restore_url": wayback_snapshot_url(data.get("last_ok", ""), u),
            })
        resurrection_map = resurrection_map[:2000]
        _phase_end("RESURRECTION MAP")

    link_rot = {}
    if phase_enabled("LINK ROT QUANTIFICATION"):
        _phase_begin("LINK ROT QUANTIFICATION")
        set_phase("LINK ROT QUANTIFICATION")
        linked_hosts = Counter()
        total_links = 0
        for u, ts_map in page_intel.items():
            for ts, intel in ts_map.items():
                for l in (intel.get("external_links") or []):
                    host = urllib.parse.urlparse(l).netloc
                    if host:
                        linked_hosts[host] += 1
                        total_links += 1
        link_rot = {"total_links": total_links, "by_host": dict(linked_hosts.most_common(500))}
        _phase_end("LINK ROT QUANTIFICATION")

    query_param_evolution = {}
    if phase_enabled("QUERY PARAM EVOLUTION"):
        _phase_begin("QUERY PARAM EVOLUTION")
        set_phase("QUERY PARAM EVOLUTION")
        query_param_evolution = build_query_param_evolution(by_url)
        _phase_end("QUERY PARAM EVOLUTION")

    form_endpoint_history = {}
    if phase_enabled("FORM ENDPOINT HISTORY"):
        _phase_begin("FORM ENDPOINT HISTORY")
        set_phase("FORM ENDPOINT HISTORY")
        form_endpoint_history = build_form_endpoint_history(page_intel)
        _phase_end("FORM ENDPOINT HISTORY")

    external_domain_graph = {}
    if phase_enabled("EXTERNAL DOMAIN GRAPH"):
        _phase_begin("EXTERNAL DOMAIN GRAPH")
        set_phase("EXTERNAL DOMAIN GRAPH")
        external_domain_graph = build_external_domain_graph(page_intel)
        _phase_end("EXTERNAL DOMAIN GRAPH")

    secret_age_estimation = {}
    if phase_enabled("SECRET AGE ESTIMATION"):
        _phase_begin("SECRET AGE ESTIMATION")
        set_phase("SECRET AGE ESTIMATION")
        secret_age_estimation = build_secret_age_estimation(page_intel)
        _phase_end("SECRET AGE ESTIMATION")

    duplicate_site_detection = {}
    if phase_enabled("DUPLICATE SITE DETECTION"):
        _phase_begin("DUPLICATE SITE DETECTION")
        set_phase("DUPLICATE SITE DETECTION")
        duplicate_site_detection = digest_clustering(by_url)
        _phase_end("DUPLICATE SITE DETECTION")

    revisit_records = []
    if phase_enabled("REVISIT RECORD ANALYSIS"):
        _phase_begin("REVISIT RECORD ANALYSIS")
        set_phase("REVISIT RECORD ANALYSIS")
        revisit_records = detect_revisit_records(snapshots)
        _phase_end("REVISIT RECORD ANALYSIS")

    urlkey_data = {}
    if phase_enabled("URLKEY / SURT ANALYTICS"):
        _phase_begin("URLKEY / SURT ANALYTICS")
        set_phase("URLKEY / SURT ANALYTICS")
        urlkey_data = urlkey_analysis(snapshots)
        _phase_end("URLKEY / SURT ANALYTICS")

    snapshot_rank = []
    if phase_enabled("SNAPSHOT DENSITY RANKING"):
        _phase_begin("SNAPSHOT DENSITY RANKING")
        set_phase("SNAPSHOT DENSITY RANKING")
        snapshot_rank = snapshot_count_ranking(by_url)
        _phase_end("SNAPSHOT DENSITY RANKING")

    redirect_chains = {}
    if phase_enabled("REDIRECT CHAIN RECONSTRUCTION"):
        _phase_begin("REDIRECT CHAIN RECONSTRUCTION")
        set_phase("REDIRECT CHAIN RECONSTRUCTION")
        redirect_chains = build_redirect_chains(by_url)
        _phase_end("REDIRECT CHAIN RECONSTRUCTION")

    passive_crawl_correlation = {}
    if phase_enabled("PASSIVE CRAWL CORRELATION") and common_crawl:
        _phase_begin("PASSIVE CRAWL CORRELATION")
        set_phase("PASSIVE CRAWL CORRELATION")
        passive_crawl_correlation = correlate_passive_crawl(snapshots, common_crawl)
        _phase_end("PASSIVE CRAWL CORRELATION")

    sources = {}
    for u, ts_map in page_intel.items():
        for ts, intel in ts_map.items():
            src = u + "@" + ts
            d = _flatten_secrets_for_report(intel.get("secrets") or {})
            d["_ts"] = ts
            sources[src] = d
    for fname, data in special_file_scans.items():
        src = "special:" + fname
        d = _flatten_secrets_for_report(data.get("secrets") or {})
        snap = special_files.get(fname)
        if snap:
            d["_ts"] = snap[-1]["timestamp"]
        sources[src] = d
    for u, hits in js_bundle_secrets.items():
        sources["js:" + u] = _flatten_secrets_for_report(hits)
    for u, hits in source_map_secrets.items():
        sources["map:" + u] = _flatten_secrets_for_report(hits)
    aggregated_secrets = _dedupe_secrets_across(sources)

    duplicate_secret_collapse = {}
    if phase_enabled("DUPLICATE SECRET COLLAPSE"):
        _phase_begin("DUPLICATE SECRET COLLAPSE")
        set_phase("DUPLICATE SECRET COLLAPSE")
        for name, data in aggregated_secrets.items():
            duplicate_secret_collapse[name] = {
                "count": len(data.get("values", [])),
                "sources": len(data.get("sources", [])),
                "severity": data.get("severity"),
            }
        _phase_end("DUPLICATE SECRET COLLAPSE")

    total_secrets = sum(len(v.get("values", [])) for v in aggregated_secrets.values())
    update_stat("secrets", total_secrets)

    extras = {
        "total_snapshots": len(snapshots),
        "subdomains": subdomains,
        "subdomain_stats": subdomain_stats,
        "subdomain_permutations": subdomain_perms,
        "subdomain_brute": subdomain_brute,
        "subdomain_takeover_candidates": takeover_candidates,
        "subdomain_crossref": subdomain_stats,
        "ct_names": ct_names,
        "documents": documents,
        "document_metadata": document_metadata,
        "redirects": redirects,
        "redirect_chains": redirect_chains,
        "content_types": dict(ctypes.most_common()),
        "status_codes": dict(status_codes.most_common()),
        "timeline": timeline,
        "gaps": gaps,
        "url_depths": url_depths,
        "query_params": query_params,
        "file_extensions": file_extensions,
        "first_last_seen": fl_seen,
        "digest_change_rate": digest_rate,
        "header_summary": header_summary,
        "archived_headers": archived_headers_map,
        "archived_header_diffs": archived_header_diffs,
        "archive_exclusions": archive_exclusions,
        "archive_src": archive_src,
        "tls": tls_info,
        "tls_versions": tls_versions,
        "tls_ciphers": tls_ciphers,
        "tls_chain": tls_chain,
        "hsts_preload": hsts_preload,
        "ocsp": ocsp_info,
        "http2_proto": http2_proto,
        "dns": dns_info,
        "dns_full": dns_full,
        "dns_srv": dns_srv,
        "dns_tlsa": dns_tlsa,
        "dns_smimea": dns_smimea,
        "dkim_selectors": dkim_selectors,
        "bimi": bimi,
        "dnssec": dnssec_ok,
        "wildcard_dns": wildcard_dns,
        "axfr": axfr_results,
        "ptr": ptr_records,
        "asn": asn_info,
        "whois": whois_data,
        "rdap": rdap_data,
        "ports": ports,
        "waf": waf_hits,
        "cors": cors_info,
        "rate_limit_headers": ratelimit_info,
        "jitter": jitter_status(),
        "availability": availability,
        "sparkline": sparkline,
        "timemap": timemap,
        "timemap_json": timemap_json,
        "calendar": calendar_data,
        "anchor": anchor_data,
        "memento_aggregator": memento_agg,
        "archive_today": archive_today,
        "common_crawl": common_crawl,
        "passive_crawl_correlation": passive_crawl_correlation,
        "cdx_full_fields_sample": cdx_full_fields[:50],
        "cdx_filtered_sample": cdx_filtered_example[:50],
        "cdx_prefix_sample": cdx_prefix_example[:50],
        "revisit_records": revisit_records[:500],
        "digest_clusters": duplicate_site_detection,
        "duplicate_site_detection": duplicate_site_detection,
        "urlkey": urlkey_data,
        "snapshot_ranking": snapshot_rank,
        "case_variants": case_variants,
        "slash_variants": slash_variants,
        "scheme_variants": scheme_variants,
        "port_variants": port_variants,
        "adjacent_diffs": {k: v[:50] for k, v in list(adjacent_diff.items())[:50]},
        "wayback_live_diff": {k: v[:100] for k, v in list(wayback_live_diff.items())[:30]},
        "special_files": special_files,
        "special_file_scans": special_file_scans,
        "framework_endpoints": framework_endpoints,
        "robots_parsed": robots_parsed,
        "sitemap_parsed": sitemap_parsed,
        "robots_sitemap_diff": robots_sitemap_diff,
        "disallow_hits": disallow_hits,
        "page_intel": page_intel,
        "page_tree": page_tree,
        "js_bundle_secrets": js_bundle_secrets,
        "js_deobfuscation": js_deobfuscation,
        "source_map_secrets": source_map_secrets,
        "email_permutations": email_perm,
        "email_mx_validation": email_mx_validation,
        "catchall": catchall,
        "deletion_timelines": deletion_timelines,
        "mass_deletion_clusters": mass_deletion_clusters,
        "first_last_diffs": first_last_diffs,
        "cloud_buckets": cloud_buckets,
        "robtex": robtex_data,
        "mnemonic_pdns": mnemonic_data,
        "hackertarget": hackertarget_data,
        "dorks": dorks,
        "ua_mode": UA_MODE,
        "proxy_status": PROXIES.status(),
        "resurrection_map": resurrection_map,
        "link_rot": link_rot,
        "query_param_evolution": query_param_evolution,
        "form_endpoint_history": form_endpoint_history,
        "external_domain_graph": external_domain_graph,
        "secret_age_estimation": secret_age_estimation,
        "duplicate_secret_collapse": duplicate_secret_collapse,
        "phase_durations": dict(_PHASE_DURATION),
        "effective_phases": (sorted(effective_phases()) if effective_phases() is not None else "ALL"),
    }

    if baseline_path:
        baseline = load_baseline(baseline_path)
        if baseline:
            baseline["_path"] = baseline_path
            extras["baseline_diff"] = diff_against_baseline(baseline, results, extras, aggregated_secrets)
            T("DIFF", f"baseline diff computed against {baseline_path}")

    if partial_sink is not None:
        partial_sink["results"] = results
        partial_sink["extras"] = extras
        partial_sink["aggregated_secrets"] = aggregated_secrets
        partial_sink["sources"] = sources

    set_phase("WRITING REPORTS")
    write_json(out_path / f"{prefix}_wayback_report.json",
               {"results": results, "extras": extras,
                "aggregated_secrets": aggregated_secrets, "sources": sources})
    write_csv(out_path / f"{prefix}_wayback_report.csv", results)
    write_html_report(out_path / f"{prefix}_wayback_report.html", domain, results, extras)
    txt_path = out_path / f"{prefix}_wayback_report.txt"
    write_txt(txt_path, domain, results, extras, aggregated_secrets, sources)
    T("SAVE", f"Detailed TXT report -> {txt_path}")

    if raw:
        build_evidence_bundle(out_path, domain, results, extras, aggregated_secrets, sources)
        build_coverage_report(out_path, domain, results, extras)

    removed_count = sum(1 for r in results if r.get("likely_removed"))
    T("PHASE", f"DONE - {len(results)} urls, {removed_count} removed, "
                f"{len(subdomains)} subdomains, {len(documents)} docs, {len(special_files)} special files, "
                f"{len(deletion_timelines)} timelines, {len(ports)} ports")
    set_phase("COMPLETE")
    _unbind_jsonl()
    _unbind_raw()
    return {"results": results, "extras": extras, "out_dir": str(out_path)}


def _install_sigint(handler):
    try:
        signal.signal(signal.SIGINT, handler)
    except ValueError:
        pass


def _default_sigint_handler(state):
    def _handler(signum, frame):
        with SIGINT_HARD_LOCK:
            SIGINT_COUNT["n"] += 1
            n = SIGINT_COUNT["n"]
        if n >= 2 or not SCAN_RUNNING.is_set():
            T("WARN", "hard exit")
            try:
                os._exit(130)
            except Exception:
                pass
        T("WARN", "Ctrl+C - flushing partial report")
        if state is not None and hasattr(state, "stop_flag"):
            try:
                state.stop_flag.set()
            except Exception:
                pass
        try:
            flush_partial_report(
                normalize_domain(getattr(state, "target", "") or ""),
                getattr(state, "partial", {}).get("results") or [],
                getattr(state, "partial", {}).get("extras") or {},
                getattr(state, "partial", {}).get("aggregated_secrets") or {},
                getattr(state, "partial", {}).get("sources") or {},
            )
        except Exception as e:
            T("ERROR", f"partial flush failed: {e}")
    return _handler


def run_cli():
    ap = argparse.ArgumentParser(description="Deep Wayback Machine OSINT tool")
    ap.add_argument("domain")
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--path-contains")
    ap.add_argument("--mimetype")
    ap.add_argument("--max-snapshots", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-live-check", action="store_true")
    ap.add_argument("--only-removed", action="store_true")
    ap.add_argument("--content-limit", type=int, default=200)
    ap.add_argument("--no-js-scan", action="store_true")
    ap.add_argument("--no-map-scan", action="store_true")
    ap.add_argument("--no-special-scan", action="store_true")
    ap.add_argument("--no-deletion-forensics", action="store_true")
    ap.add_argument("--no-network-depth", action="store_true")
    ap.add_argument("--no-document-meta", action="store_true")
    ap.add_argument("--no-archived-headers", action="store_true")
    ap.add_argument("--no-framework-scan", action="store_true")
    ap.add_argument("--no-cloud-scan", action="store_true")
    ap.add_argument("--no-dork-gen", action="store_true")
    ap.add_argument("--no-wayback-extras", action="store_true")
    ap.add_argument("--ua-mode", choices=["rotate", "random", "fixed"], default="rotate")
    ap.add_argument("--ua-index", type=int, default=0)
    ap.add_argument("--quiet-telemetry", action="store_true")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--phases", default=None)
    ap.add_argument("--select", default=None)
    ap.add_argument("--proxy", action="append", default=[])
    ap.add_argument("--proxy-file", default=None)
    ap.add_argument("--proxy-mode", choices=["rotate", "random", "fixed"], default="rotate")
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--raw", action="store_true")
    ap.add_argument("--no-jitter", action="store_true")
    ap.add_argument("--jitter-min", type=float, default=None)
    ap.add_argument("--jitter-max", type=float, default=None)
    args = ap.parse_args()

    set_ua_mode(args.ua_mode, args.ua_index)
    TELEMETRY.verbose = not args.quiet_telemetry

    if args.no_jitter:
        set_jitter(enabled=False)
    else:
        set_jitter(enabled=True)
    if args.jitter_min is not None or args.jitter_max is not None:
        set_jitter(jmin=args.jitter_min, jmax=args.jitter_max)
    js = jitter_status()
    T("JITTER", f"enabled={js['enabled']} range={js['min']:.1f}-{js['max']:.1f}s hosts={js['hosts']}")

    if args.proxy_file:
        added, skipped = PROXIES.load_file(args.proxy_file)
        if added < 0:
            T("PROXY", skipped)
        else:
            T("PROXY", f"loaded {added} from {args.proxy_file} ({skipped} dupes)")
            PROXIES.mode = args.proxy_mode
            PROXIES.enabled = True
    if args.proxy:
        for p in args.proxy:
            PROXIES.add(p)
        PROXIES.mode = args.proxy_mode
        PROXIES.enabled = True
        T("PROXY", f"enabled with {len(PROXIES.list)} proxies, mode={PROXIES.mode}")

    if args.phases:
        ids = set()
        for tok in args.phases.split(","):
            tok = tok.strip().lstrip("p")
            if tok.isdigit() and 1 <= int(tok) <= PHASE_COUNT:
                ids.add(int(tok))
        set_active_phases(ids)

    if args.select:
        handle_select(args.select)

    eff = effective_phases()
    if eff is None:
        T("PHASES", "effective phases: ALL")
    else:
        T("PHASES", f"effective phases: {sorted(eff)}")
        for i in sorted(eff):
            T("PHASES", f"  p{i:02d}  {PHASE_IDS[i-1]}")

    partial = {"results": [], "extras": {}, "aggregated_secrets": {}, "sources": {}}
    stop_flag = threading.Event()
    state_obj = type("S", (), {})()
    state_obj.target = args.domain
    state_obj.stop_flag = stop_flag
    state_obj.partial = partial

    SCAN_RUNNING.set()
    with SIGINT_HARD_LOCK:
        SIGINT_COUNT["n"] = 0
    _install_sigint(_default_sigint_handler(state_obj))
    try:
        run_deep_scan(
            args.domain, args.date_from, args.date_to, args.workers,
            extract_content=True,
            only_removed=args.only_removed,
            content_limit=max(args.content_limit, 1),
            no_live_check=args.no_live_check, path_contains=args.path_contains,
            mimetype=args.mimetype, out_dir=args.out_dir, max_snapshots=args.max_snapshots,
            full_special=True,
            harvest_headers=not args.no_live_check,
            scan_js=not args.no_js_scan,
            scan_maps=not args.no_map_scan,
            scan_special=not args.no_special_scan,
            deletion_forensics=not args.no_deletion_forensics,
            network_depth=not args.no_network_depth,
            document_meta=not args.no_document_meta,
            archived_headers=not args.no_archived_headers,
            framework_scan=not args.no_framework_scan,
            cloud_scan=not args.no_cloud_scan,
            dork_gen=not args.no_dork_gen,
            wayback_extras=not args.no_wayback_extras,
            baseline_path=args.baseline,
            raw=args.raw,
            partial_sink=partial,
            stop_flag=stop_flag,
        )
    except KeyboardInterrupt:
        T("WARN", "scan interrupted by user")
    finally:
        SCAN_RUNNING.clear()
        _install_sigint(signal.SIG_DFL)


class State:
    def __init__(self):
        self.target = None
        self.date_from = None
        self.date_to = None
        self.path_contains = None
        self.baseline_path = None
        self.workers = 8
        self.raw = False
        self.only_removed = False
        self.running = False
        self.log = []
        self.log_max = 100000
        self.stats = {
            "snapshots": 0, "urls": 0, "removed": 0, "live": 0,
            "subdomains": 0, "documents": 0, "redirects": 0,
            "special_files": 0, "secrets": 0, "timelines": 0,
            "clusters": 0, "ports": 0, "frameworks": 0, "phase": "IDLE",
        }
        self.log_lock = threading.Lock()
        self.scroll_offset = 0
        self.auto_follow = True
        self.partial = {"results": [], "extras": {}, "aggregated_secrets": {}, "sources": {}}
        self.stop_flag = threading.Event()
        self.launch_lock = threading.Lock()

    def push_log(self, line):
        with self.log_lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self.log.append(f"[{ts}] {line}")
            if len(self.log) > self.log_max:
                self.log = self.log[self.log_max // 10:]


STATE = State()


class LogPrinter:
    def __init__(self, state):
        self.state = state
        self.buf = ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf or "\r" in self.buf:
            for sep in ("\n", "\r"):
                if sep in self.buf:
                    line, self.buf = self.buf.split(sep, 1)
                    if line.strip():
                        self.state.push_log(line.rstrip())

    def flush(self):
        pass


def run_pipeline(state: State):
    import sys as _sys
    old_stdout = _sys.stdout
    _sys.stdout = LogPrinter(state)
    TELEMETRY.bind(state.push_log)
    SCAN_RUNNING.set()
    with SIGINT_HARD_LOCK:
        SIGINT_COUNT["n"] = 0
    state.partial = {"results": [], "extras": {}, "aggregated_secrets": {}, "sources": {}}
    state.stop_flag = threading.Event()
    _install_sigint(_default_sigint_handler(state))
    try:
        run_deep_scan(
            state.target, state.date_from, state.date_to, state.workers,
            extract_content=True,
            only_removed=state.only_removed,
            content_limit=200,
            no_live_check=False,
            path_contains=state.path_contains,
            mimetype=None,
            out_dir=None,
            max_snapshots=None,
            full_special=True,
            harvest_headers=True,
            scan_js=True,
            scan_maps=True,
            scan_special=True,
            deletion_forensics=True,
            network_depth=True,
            document_meta=True,
            archived_headers=True,
            framework_scan=True,
            cloud_scan=True,
            dork_gen=True,
            wayback_extras=True,
            baseline_path=state.baseline_path,
            raw=state.raw,
            state=state,
            partial_sink=state.partial,
            stop_flag=state.stop_flag,
        )
    except KeyboardInterrupt:
        T("WARN", "scan aborted")
        state.stats["phase"] = "ABORTED"
    except Exception as e:
        T("ERROR", f"{e}")
        for line in traceback.format_exc().splitlines()[-12:]:
            T("ERROR", line)
        state.stats["phase"] = "ERROR"
    finally:
        SCAN_RUNNING.clear()
        _sys.stdout = old_stdout
        state.running = False
        TELEMETRY.unbind()


FRAME_TL, FRAME_TR, FRAME_BL, FRAME_BR = "╔", "╗", "╚", "╝"
FRAME_H, FRAME_V = "═", "║"
C_FRAME = 1
C_TITLE = 2
C_ACCENT = 3
C_LOG = 4
C_STAT_OK = 5
C_STAT_WARN = 6
C_CMD = 7
C_DIM = 8
C_SCROLL = 9
C_STRATA = 10
C_SCAN = 11
C_AUTHOR = 12


def init_colors():
    try:
        curses.start_color()
        curses.use_default_colors()
    except curses.error:
        return
    curses.init_pair(C_FRAME, curses.COLOR_CYAN, -1)
    curses.init_pair(C_TITLE, curses.COLOR_CYAN, -1)
    curses.init_pair(C_ACCENT, curses.COLOR_MAGENTA, -1)
    curses.init_pair(C_LOG, curses.COLOR_GREEN, -1)
    curses.init_pair(C_STAT_OK, curses.COLOR_GREEN, -1)
    curses.init_pair(C_STAT_WARN, curses.COLOR_RED, -1)
    curses.init_pair(C_CMD, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_DIM, curses.COLOR_BLUE, -1)
    curses.init_pair(C_SCROLL, curses.COLOR_YELLOW, -1)
    if curses.COLORS >= 256:
        try:
            curses.init_pair(C_STRATA, 124, -1)
        except curses.error:
            curses.init_pair(C_STRATA, curses.COLOR_RED, -1)
        try:
            curses.init_pair(C_SCAN, 250, -1)
        except curses.error:
            curses.init_pair(C_SCAN, curses.COLOR_WHITE, -1)
        try:
            curses.init_pair(C_AUTHOR, 202, -1)
        except curses.error:
            curses.init_pair(C_AUTHOR, curses.COLOR_RED, -1)
    else:
        curses.init_pair(C_STRATA, curses.COLOR_RED, -1)
        curses.init_pair(C_SCAN, curses.COLOR_WHITE, -1)
        curses.init_pair(C_AUTHOR, curses.COLOR_RED, -1)


def draw_box(win, y, x, h, w, title=None, title_extra=None):
    if h < 2 or w < 2:
        return
    try:
        win.attron(curses.color_pair(C_FRAME))
        win.addstr(y, x, FRAME_TL + FRAME_H * (w - 2) + FRAME_TR)
        for i in range(1, h - 1):
            win.addstr(y + i, x, FRAME_V)
            win.addstr(y + i, x + w - 1, FRAME_V)
        win.addstr(y + h - 1, x, FRAME_BL + FRAME_H * (w - 2) + FRAME_BR)
        win.attroff(curses.color_pair(C_FRAME))
        if title:
            win.attron(curses.color_pair(C_TITLE) | curses.A_BOLD)
            win.addstr(y, x + 2, f" {title} ")
            win.attroff(curses.color_pair(C_TITLE) | curses.A_BOLD)
        if title_extra:
            win.attron(curses.color_pair(C_SCROLL) | curses.A_BOLD)
            xx = x + w - len(title_extra) - 3
            if xx > x + 2:
                win.addstr(y, xx, title_extra)
            win.attroff(curses.color_pair(C_SCROLL) | curses.A_BOLD)
    except curses.error:
        pass


def safe_addstr(win, y, x, s, attr=0):
    try:
        win.addstr(y, x, s, attr)
    except curses.error:
        pass


BANNER = [
    " ███████╗████████╗██████╗  █████╗ ████████╗ █████╗ ███████╗ ██████╗ █████╗ ███╗   ██╗",
    " ██╔════╝╚══██╔══╝██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗██╔════╝██╔════╝██╔══██╗████╗  ██║",
    " ███████╗   ██║   ██████╔╝███████║   ██║   ███████║███████╗██║     ███████║██╔██╗ ██║",
    " ╚════██║   ██║   ██╔══██╗██╔══██║   ██║   ██╔══██║╚════██║██║     ██╔══██║██║╚██╗██║",
    " ███████║   ██║   ██║  ██║██║  ██║   ██║   ██║  ██║███████║╚██████╗██║  ██║██║ ╚████║",
    " ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝",
]

BANNER_SPLIT = 51


def draw_header(win, w):
    strata_attr = curses.color_pair(C_STRATA) | curses.A_BOLD
    scan_attr = curses.color_pair(C_SCAN) | curses.A_BOLD
    for i, line in enumerate(BANNER):
        x0 = max(0, (w - len(line)) // 2)
        left = line[:BANNER_SPLIT]
        right = line[BANNER_SPLIT:]
        safe_addstr(win, i, x0, left[:w], strata_attr)
        if x0 + len(left) < w:
            safe_addstr(win, i, x0 + len(left), right[: w - x0 - len(left)], scan_attr)
    sub = "// DEEP ARCHIVE RECONNAISSANCE CONSOLE // WAYBACK OSINT ENGINE"
    js = jitter_status()
    author = "made by: SYLHETYHACKVENGER (THE-ERROR808)"
    meta = f"// UA: {UA_MODE} ({len(USER_AGENTS)})  |  Phases: {PHASE_COUNT}  |  Caps: {len(CAPABILITY_CATALOG)}  |  Proxies: {PROXIES.status().get('count')}  |  Raw: {'ON' if STATE.raw else 'off'}  |  Jitter: {js['min']:.1f}-{js['max']:.1f}s"
    safe_addstr(win, len(BANNER), max(0, (w - len(sub)) // 2), sub[:w], curses.color_pair(C_DIM))
    safe_addstr(win, len(BANNER) + 1, max(0, (w - len(author)) // 2), author[:w], curses.color_pair(C_AUTHOR) | curses.A_BOLD)
    safe_addstr(win, len(BANNER) + 2, max(0, (w - len(meta)) // 2), meta[:w], curses.color_pair(C_DIM) | curses.A_DIM)


def draw_stats_panel(win, y, x, h, w, state: State):
    draw_box(win, y, x, h, w, "SYSTEM STATUS")
    active = get_active_phases()
    eff = effective_phases()
    active_str = "ALL" if active is None else f"{len(active)}/{PHASE_COUNT}"
    eff_str = "ALL" if eff is None else f"{len(eff)}/{PHASE_COUNT}"
    js = jitter_status()
    rows = [
        ("TARGET", state.target or "-"),
        ("PHASE", state.stats["phase"]),
        ("SNAPSHOTS", str(state.stats["snapshots"])),
        ("UNIQUE URLS", str(state.stats["urls"])),
        ("LIKELY REMOVED", str(state.stats["removed"])),
        ("STILL LIVE", str(state.stats["live"])),
        ("SUBDOMAINS", str(state.stats["subdomains"])),
        ("DOCUMENTS", str(state.stats["documents"])),
        ("REDIRECTS", str(state.stats["redirects"])),
        ("SPECIAL FILES", str(state.stats["special_files"])),
        ("SECRETS FOUND", str(state.stats["secrets"])),
        ("TIMELINES", str(state.stats["timelines"])),
        ("MASS DELETIONS", str(state.stats["clusters"])),
        ("OPEN PORTS", str(state.stats["ports"])),
        ("FRAMEWORK HITS", str(state.stats["frameworks"])),
        ("", ""),
        ("PHASES EXPLICIT", active_str),
        ("PHASES EFFECTIVE", eff_str),
        ("WORKERS", str(state.workers)),
        ("UA MODE", f"{UA_MODE} ({len(USER_AGENTS)})"),
        ("PROXIES", f"{'ON' if PROXIES.status().get('enabled') else 'OFF'} ({PROXIES.status().get('count')})"),
        ("CAPABILITIES", "ALL" if not get_selection_active() else f"{len(SELECTION.snapshot())}"),
        ("RAW MODE", "ON" if state.raw else "off"),
        ("JITTER", f"{'ON' if js['enabled'] else 'off'} {js['min']:.1f}-{js['max']:.1f}s x{js['adaptive_backoff']:.2f}"),
    ]
    for i, (label, val) in enumerate(rows):
        yy = y + 2 + i
        if yy >= y + h - 1:
            break
        if not label:
            continue
        safe_addstr(win, yy, x + 2, f"{label:<16}", curses.color_pair(C_DIM) | curses.A_BOLD)
        color = C_STAT_OK
        if label == "PHASE" and state.stats["phase"] in ("ERROR", "NO DATA", "ABORTED"):
            color = C_STAT_WARN
        elif label in ("LIKELY REMOVED", "SECRETS FOUND", "OPEN PORTS") and val != "0":
            color = C_STAT_WARN
        elif label == "PROXIES" and PROXIES.status().get("enabled"):
            color = C_CMD
        elif label == "CAPABILITIES" and get_selection_active():
            color = C_CMD
        elif label == "PHASES EFFECTIVE" and eff is not None and len(eff) < PHASE_COUNT:
            color = C_CMD
        elif label == "RAW MODE" and state.raw:
            color = C_CMD
        elif label == "JITTER" and js["enabled"]:
            color = C_CMD
        safe_addstr(win, yy, x + 19, val[: w - 21], curses.color_pair(color))
    if state.running:
        spin = "◐◓◑◒"[int(time.time() * 4) % 4]
        safe_addstr(win, y + h - 2, x + 2, f"{spin} scanning...", curses.color_pair(C_ACCENT) | curses.A_BOLD)


SCAN_GLYPHS = "▁▂▃▄▅▆▇█▇▆▅▄▃▂"


def draw_log_panel(win, y, x, h, w, state: State):
    inner_h = h - 2
    title_extra = "[ LIVE ]" if state.auto_follow else f"[ SCROLL +{state.scroll_offset} ]"
    draw_box(win, y, x, h, w, "LIVE TELEMETRY", title_extra=title_extra)
    with state.log_lock:
        total = len(state.log)
        if total == 0:
            lines = []
        else:
            if state.auto_follow:
                start = max(0, total - inner_h)
                end = total
            else:
                end = max(0, total - state.scroll_offset)
                start = max(0, end - inner_h)
            lines = state.log[start:end]
    for i, line in enumerate(lines):
        if i >= inner_h:
            break
        attr = curses.color_pair(C_LOG)
        if "[PHASE]" in line or "[PHASES]" in line:
            attr = curses.color_pair(C_ACCENT) | curses.A_BOLD
        elif "[ERROR]" in line or "[WARN]" in line or "[SECRET]" in line:
            attr = curses.color_pair(C_STAT_WARN) | curses.A_BOLD
        elif "[SAVE]" in line or "[REPORT]" in line:
            attr = curses.color_pair(C_CMD) | curses.A_BOLD
        elif "[PROXY]" in line:
            attr = curses.color_pair(C_CMD) | curses.A_BOLD
        elif "[JITTER]" in line or "[RATE]" in line:
            attr = curses.color_pair(C_SCROLL) | curses.A_BOLD
        elif "[CKPT]" in line or "[DIFF]" in line or "[CRED]" in line or "[CACHE]" in line or "[RAW]" in line or "[COVERAGE]" in line:
            attr = curses.color_pair(C_SCROLL) | curses.A_BOLD
        safe_addstr(win, y + 1 + i, x + 2, line[: w - 4], attr)
    if total > inner_h:
        try:
            track_h = inner_h
            bar_pos = track_h - 1 if state.auto_follow else max(0, min(track_h - 1, track_h - 1 - int(state.scroll_offset * track_h / max(1, total))))
            for i in range(track_h):
                ch = "█" if i == bar_pos else "│"
                attr = curses.color_pair(C_SCROLL) if i == bar_pos else curses.color_pair(C_DIM) | curses.A_DIM
                safe_addstr(win, y + 1 + i, x + w - 2, ch, attr)
        except curses.error:
            pass
    if state.running and state.auto_follow:
        t = time.time()
        bar_row = y + 1 + len(lines)
        if bar_row < y + h - 1:
            inner_w = w - 4
            pos = int(t * 14) % max(1, inner_w)
            bar = ["-"] * inner_w
            for k in range(6):
                idx = (pos + k) % inner_w
                bar[idx] = SCAN_GLYPHS[(k * 2) % len(SCAN_GLYPHS)]
            safe_addstr(win, bar_row, x + 2, "".join(bar), curses.color_pair(C_ACCENT) | curses.A_BOLD)
        spinner = "|/-\\"[int(t * 10) % 4]
        label = f" {spinner} SCAN IN PROGRESS {spinner} "
        safe_addstr(win, y + h - 1, max(x + 2, x + (w - len(label)) // 2), label, curses.color_pair(C_ACCENT) | curses.A_BOLD)
    elif not state.auto_follow:
        hint = " SCROLLED - PgUp/PgDn . Up/Down . Home/End . Ctrl+E resume live "
        safe_addstr(win, y + h - 1, max(x + 2, x + (w - len(hint)) // 2), hint[: w - 4], curses.color_pair(C_SCROLL) | curses.A_BOLD)


def draw_help_panel(win, y, x, h, w):
    draw_box(win, y, x, h, w, "COMMAND REFERENCE")
    cmds = [
        ("show", "list capabilities"),
        ("select <n>", "select capability (auto-adds deps)"),
        ("select 1,5,15", "bulk select"),
        ("select all", "enable all"),
        ("select clear", "reset all"),
        ("selected", "show selection"),
        ("phases", "list phases"),
        ("phase p1,p5,p9", "explicit phase filter"),
        ("phase all", "clear phase filter"),
        ("target <domain>", "set target"),
        ("url/www/site/domain/host", "target aliases"),
        ("run / all / scan", "start scan"),
        ("raw on|off", "raw evidence mode"),
        ("jitter on|off", "adaptive jitter 5-8s"),
        ("jitter min <s>", "set jitter lower bound"),
        ("jitter max <s>", "set jitter upper bound"),
        ("jitter show", "show jitter status"),
        ("from <YYYYMMDD>", "date-from filter"),
        ("to <YYYYMMDD>", "date-to filter"),
        ("path <substr>", "path filter"),
        ("removed on|off", "only removed"),
        ("baseline <file>", "diff against previous JSON"),
        ("workers <n>", "concurrency"),
        ("ua rotate|random|fixed", "user agent"),
        ("ua fixed <n>", "pin UA"),
        ("ua list", "list UAs"),
        ("proxy load <file>", "load proxies from file"),
        ("proxy add <url>", "add single proxy"),
        ("proxy list", "show proxies"),
        ("proxy on|off", "toggle proxies"),
        ("proxy mode rotate|random|fixed", "rotation"),
        ("proxy clear", "remove all"),
        ("telemetry on|off", "raw verbosity"),
        ("clear", "clear log"),
        ("quit / q", "exit"),
        ("", ""),
        ("Up / Down", "scroll 1 line"),
        ("PgUp / PgDn", "scroll 1 page"),
        ("Home / End", "top / bottom"),
        ("Ctrl+E", "resume live tail"),
        ("Ctrl+C", "flush partial + abort"),
    ]
    for i, (c, d) in enumerate(cmds):
        yy = y + 2 + i
        if yy >= y + h - 1:
            break
        if not c:
            continue
        safe_addstr(win, yy, x + 2, c, curses.color_pair(C_CMD) | curses.A_BOLD)
        safe_addstr(win, yy, x + 32, d[: w - 34], curses.color_pair(C_DIM))


def draw_cmd_bar(win, y, w, cmd_buf, state):
    win.attron(curses.color_pair(C_FRAME))
    safe_addstr(win, y, 0, FRAME_H * w)
    win.attroff(curses.color_pair(C_FRAME))
    prompt = "CMD > "
    safe_addstr(win, y + 1, 1, prompt, curses.color_pair(C_ACCENT) | curses.A_BOLD)
    safe_addstr(win, y + 1, 1 + len(prompt), cmd_buf[: w - len(prompt) - 3], curses.color_pair(C_CMD))
    active = get_active_phases()
    eff = effective_phases()
    js = jitter_status()
    ph = "ALL" if active is None else f"{len(active)}"
    ef = "ALL" if eff is None else f"{len(eff)}"
    px = "on" if PROXIES.status().get("enabled") else "off"
    cap = "ALL" if not get_selection_active() else str(len(SELECTION.snapshot()))
    rw = "on" if state.raw else "off"
    jt = f"{js['min']:.0f}-{js['max']:.0f}" if js["enabled"] else "off"
    hint = f"UA:{UA_MODE}  TEL:{'on' if TELEMETRY.verbose else 'off'}  PH:{ph} EFF:{ef}/{PHASE_COUNT}  PX:{px}  CAP:{cap}  RAW:{rw}  JT:{jt}"
    hx = w - len(hint) - 2
    if hx > 1 + len(prompt) + len(cmd_buf) + 1:
        safe_addstr(win, y + 1, hx, hint, curses.color_pair(C_DIM) | curses.A_DIM)
    try:
        win.move(y + 1, 1 + len(prompt) + min(len(cmd_buf), w - len(prompt) - 3))
    except curses.error:
        pass


def _launch_scan(state):
    with state.launch_lock:
        if state.running:
            state.push_log("!! scan already in progress")
            return
        if not state.target:
            state.push_log("!! set a target first (target <domain>)")
            return
        state.running = True
    state.auto_follow = True
    state.scroll_offset = 0
    state.partial = {"results": [], "extras": {}, "aggregated_secrets": {}, "sources": {}}
    state.stop_flag = threading.Event()

    js = jitter_status()
    if js["enabled"]:
        state.push_log(f"[JITTER] adaptive jitter ACTIVE  range={js['min']:.1f}-{js['max']:.1f}s  hosts={js['hosts']}")
    else:
        state.push_log("[JITTER] adaptive jitter DISABLED")

    eff = effective_phases()
    if eff is None:
        state.push_log("[PHASES] effective: ALL")
    else:
        state.push_log(f"[PHASES] effective: {sorted(eff)}")
        for i in sorted(eff):
            if 1 <= i <= PHASE_COUNT:
                state.push_log(f"[PHASES]   p{i:02d}  {PHASE_IDS[i-1]}")
        skipped = [i for i in range(1, PHASE_COUNT + 1) if i not in eff]
        if skipped:
            state.push_log(f"[PHASES] skipped: {skipped}")
    sel_ids = _phase_ids_from_selection()
    if get_selection_active() and sel_ids:
        expanded = _expand_phase_dependencies(sel_ids)
        added = sorted(expanded - sel_ids)
        state.push_log(f"[SELECT] selection implies phases: {sorted(sel_ids)}")
        if added:
            state.push_log(f"[SELECT] auto-added dependency phases: {added}")
    if state.raw:
        state.push_log("[RAW] raw evidence mode is ON - will write findings.jsonl, raw_snapshots/, provenance.json, coverage.json")

    state.push_log(f"launching scan on {state.target}...")
    threading.Thread(target=run_pipeline, args=(state,), daemon=True).start()


TARGET_ALIASES = {"target", "url", "www", "site", "domain", "host", "scan-url"}


def handle_phase(arg):
    arg = (arg or "").strip().lower()
    if not arg:
        show_phases()
        return
    if arg in ("all", "*"):
        set_active_phases(None)
        T("PHASES", "phase filter cleared")
        return
    ids = set()
    bad = []
    for tok in re.split(r"[,\s]+", arg):
        tok = tok.strip().lstrip("p")
        if not tok.isdigit():
            bad.append(tok)
            continue
        n = int(tok)
        if 1 <= n <= PHASE_COUNT:
            ids.add(n)
        else:
            bad.append(tok)
    if ids:
        set_active_phases(ids)
        T("PHASES", f"explicit phases: {sorted(ids)}")
    if bad:
        T("PHASES", f"invalid: {bad}")
    show_phases()


def handle_jitter(arg, state):
    bits = (arg or "").strip().split()
    if not bits:
        js = jitter_status()
        state.push_log(f"jitter: enabled={js['enabled']} range={js['min']:.1f}-{js['max']:.1f}s hosts={js['hosts']} backoff={js['adaptive_backoff']:.2f}")
        return
    sub = bits[0].lower()
    if sub in ("on", "true", "1", "yes", "enable", "enabled"):
        set_jitter(enabled=True)
        state.push_log("jitter -> ON")
    elif sub in ("off", "false", "0", "no", "disable", "disabled"):
        set_jitter(enabled=False)
        state.push_log("jitter -> OFF")
    elif sub == "min":
        if len(bits) < 2:
            state.push_log("!! usage: jitter min <seconds>")
            return
        try:
            set_jitter(jmin=float(bits[1]))
            js = jitter_status()
            state.push_log(f"jitter min -> {js['min']:.1f}s (range {js['min']:.1f}-{js['max']:.1f}s)")
        except ValueError:
            state.push_log("!! min requires numeric seconds")
    elif sub == "max":
        if len(bits) < 2:
            state.push_log("!! usage: jitter max <seconds>")
            return
        try:
            set_jitter(jmax=float(bits[1]))
            js = jitter_status()
            state.push_log(f"jitter max -> {js['max']:.1f}s (range {js['min']:.1f}-{js['max']:.1f}s)")
        except ValueError:
            state.push_log("!! max requires numeric seconds")
    elif sub in ("show", "status"):
        js = jitter_status()
        state.push_log(f"jitter: enabled={js['enabled']} range={js['min']:.1f}-{js['max']:.1f}s hosts={js['hosts']} backoff={js['adaptive_backoff']:.2f}")
    else:
        state.push_log("usage: jitter on|off | jitter min <s> | jitter max <s> | jitter show")


def handle_proxy(arg, state):
    parts = (arg or "").strip().split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    val = parts[1].strip() if len(parts) > 1 else ""
    if not sub or sub == "status":
        s = PROXIES.status()
        state.push_log(f"proxies: enabled={s['enabled']} mode={s['mode']} count={s['count']} failed={s['failed']} source={s.get('source_file')}")
        for p in s["list"][:50]:
            state.push_log(f"  {p}")
        if s["count"] > 50:
            state.push_log(f"  ... and {s['count'] - 50} more")
        return
    if sub == "load":
        if not val:
            state.push_log("proxy file path> ")
            state.push_log("!! usage: proxy load <file>")
            return
        added, skipped = PROXIES.load_file(val)
        if added < 0:
            state.push_log(f"!! {skipped}")
            return
        state.push_log(f"loaded {added} proxies from {val} ({skipped} duplicates skipped)")
        if added > 0:
            PROXIES.enabled = True
            state.push_log(f"proxies ON ({PROXIES.status()['count']} total)")
        return
    if sub == "add":
        if not val:
            state.push_log("!! usage: proxy add <url>")
            return
        if PROXIES.add(val):
            state.push_log(f"proxy added -> {val}")
        else:
            state.push_log(f"!! proxy already exists or invalid: {val}")
        return
    if sub == "clear":
        PROXIES.clear()
        state.push_log("proxies cleared")
        return
    if sub == "list":
        s = PROXIES.status()
        state.push_log(f"proxy list ({s['count']}) mode={s['mode']} enabled={s['enabled']} source={s.get('source_file')}")
        for p in s["list"][:200]:
            state.push_log(f"  {p}")
        if s["count"] > 200:
            state.push_log(f"  ... and {s['count'] - 200} more")
        return
    if sub == "on":
        if not PROXIES.list:
            state.push_log("proxy file path> ")
            state.push_log("!! no proxies configured. use 'proxy load <file>'")
            return
        PROXIES.enabled = True
        state.push_log(f"proxies ON ({PROXIES.status()['count']})")
        return
    if sub == "off":
        PROXIES.enabled = False
        state.push_log("proxies OFF")
        return
    if sub == "mode":
        if val not in ("rotate", "random", "fixed"):
            state.push_log("!! mode: rotate | random | fixed")
            return
        PROXIES.mode = val
        state.push_log(f"proxy mode -> {val}")
        return
    state.push_log("usage: proxy load <file> | proxy add <url> | proxy list | proxy clear | proxy on | proxy off | proxy mode | proxy status")


def parse_and_apply(cmd, state: State):
    cmd = cmd.strip()
    if not cmd:
        return None
    parts = cmd.split(maxsplit=1)
    verb = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if verb in ("quit", "q", "exit"):
        return "QUIT"
    if verb == "show":
        show_capability_catalog()
        return None
    if verb in ("select", "sel"):
        handle_select(arg)
        return None
    if verb == "selected":
        show_selection()
        return None
    if verb in ("phases", "phase", "p"):
        handle_phase(arg)
        return None
    if verb in ("proxy", "proxies"):
        handle_proxy(arg, state)
        return None
    if verb in ("jitter", "delay", "throttle"):
        handle_jitter(arg, state)
        return None
    if verb == "raw":
        on = arg.lower() in ("on", "true", "1", "yes", "enable", "enabled")
        off = arg.lower() in ("off", "false", "0", "no", "disable", "disabled")
        if on:
            state.raw = True
            state.push_log("raw mode -> ON")
        elif off:
            state.raw = False
            state.push_log("raw mode -> OFF")
        else:
            state.push_log(f"raw mode is {'ON' if state.raw else 'OFF'}")
        return None

    if verb in TARGET_ALIASES:
        if not arg:
            state.push_log(f"!! usage: {verb} <domain>")
            return None
        state.target = normalize_domain(arg)
        state.push_log(f"target set -> {state.target}")
        state.push_log("ready. type 'run' to start the scan.")
        return None

    if verb not in {
        "from", "to", "path", "removed", "workers",
        "run", "all", "deep", "clear", "help", "scan",
        "ua", "useragent", "user-agent", "telemetry", "verbose", "baseline",
    }:
        if ("://" in verb) or re.match(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$", verb, re.IGNORECASE):
            state.target = normalize_domain(cmd)
            state.push_log(f"target set -> {state.target}")
            state.push_log("ready. type 'run' to start the scan.")
            return None
        state.push_log(f"!! unknown command: {verb}  (type 'help')")
        return None

    if verb == "from":
        state.date_from = arg or None
        state.push_log(f"date-from -> {state.date_from}")
    elif verb == "to":
        state.date_to = arg or None
        state.push_log(f"date-to -> {state.date_to}")
    elif verb == "path":
        state.path_contains = arg or None
        state.push_log(f"path filter -> {state.path_contains}")
    elif verb == "removed":
        state.only_removed = arg.lower() in ("on", "true", "1", "yes")
        state.push_log(f"only-removed -> {'ON' if state.only_removed else 'OFF'}")
    elif verb == "baseline":
        state.baseline_path = arg or None
        state.push_log(f"baseline -> {state.baseline_path}")
    elif verb == "workers":
        try:
            state.workers = max(1, min(32, int(arg)))
            state.push_log(f"workers -> {state.workers}")
        except ValueError:
            state.push_log("!! workers requires integer")
    elif verb in ("ua", "useragent", "user-agent"):
        bits = arg.split()
        if not bits:
            state.push_log(f"UA pool: {len(USER_AGENTS)} agents; mode: {UA_MODE}")
        elif bits[0] in ("rotate", "random"):
            set_ua_mode(bits[0])
            state.push_log(f"UA mode -> {UA_MODE}")
        elif bits[0] == "fixed":
            idx = 0
            if len(bits) >= 2:
                try:
                    idx = int(bits[1])
                except ValueError:
                    state.push_log("!! requires integer")
                    return None
            set_ua_mode("fixed", idx)
            state.push_log(f"UA mode -> fixed[{UA_FIXED_INDEX}]")
        elif bits[0] in ("list", "ls"):
            for i, ua in enumerate(USER_AGENTS):
                state.push_log(f"  [{i:02d}] {ua[:110]}")
        else:
            state.push_log("usage: ua rotate | ua random | ua fixed <n> | ua list")
    elif verb in ("telemetry", "verbose"):
        on = arg.lower() in ("on", "true", "1", "yes", "verbose")
        off = arg.lower() in ("off", "false", "0", "no", "quiet")
        if on:
            TELEMETRY.verbose = True
            state.push_log("telemetry -> ON")
        elif off:
            TELEMETRY.verbose = False
            state.push_log("telemetry -> OFF")
        else:
            state.push_log(f"telemetry is {'ON' if TELEMETRY.verbose else 'OFF'}")
    elif verb in ("all", "deep", "run", "scan"):
        if arg:
            state.target = normalize_domain(arg)
        _launch_scan(state)
    elif verb == "clear":
        with state.log_lock:
            state.log.clear()
        state.scroll_offset = 0
        state.auto_follow = True
    elif verb == "help":
        state.push_log("see COMMAND REFERENCE panel")
    return None


def run_tui(stdscr):
    try:
        curses.curs_set(1)
    except curses.error:
        pass
    curses.noecho()
    stdscr.nodelay(True)
    stdscr.timeout(150)
    init_colors()
    TELEMETRY.bind(STATE.push_log)
    _install_sigint(_default_sigint_handler(STATE))
    STATE.push_log("console initialized.")
    STATE.push_log("made by: SYLHETYHACKVENGER (THE-ERROR808)")
    STATE.push_log(f"UA rotation: {UA_MODE} ({len(USER_AGENTS)} agents)")
    STATE.push_log(f"capability catalog: {len(CAPABILITY_CATALOG)} entries")
    STATE.push_log(f"phase catalog: {PHASE_COUNT} phases (type 'phases')")
    STATE.push_log(f"proxy pool: {PROXIES.status().get('count')} configured")
    js = jitter_status()
    STATE.push_log(f"adaptive jitter: {'ON' if js['enabled'] else 'off'}  range {js['min']:.1f}-{js['max']:.1f}s  hosts {js['hosts']}")
    STATE.push_log("set a target then type 'run' to start the scan.")
    STATE.push_log("'phase p1,p5,p9' filters phases; 'select 1,2,15' filters capabilities.")
    STATE.push_log("'select' now auto-includes dependency phases (e.g. picking #24 pulls in #1).")
    STATE.push_log("'jitter min 6' / 'jitter max 9' tune the randomized archive.org throttle.")
    STATE.push_log("'proxy load all.txt' loads a proxy list (e.g. from monosans/proxy-list).")
    STATE.push_log("'raw on' enables raw evidence mode (findings.jsonl + raw_snapshots).")
    STATE.push_log("'baseline <file.json>' diffs against a previous report.")
    STATE.push_log("Ctrl+C flushes partial report; second Ctrl+C forces exit.")

    cmd_buf = ""
    try:
        while True:
            h, w = stdscr.getmaxyx()
            if h < 10 or w < 40:
                try:
                    stdscr.erase()
                    stdscr.addstr(0, 0, "terminal too small")
                    stdscr.refresh()
                except curses.error:
                    pass
                ch = stdscr.getch()
                if ch in (ord("q"), 3):
                    break
                continue
            stdscr.erase()
            header_h = len(BANNER) + 4
            cmdbar_h = 3
            body_y = header_h
            body_h = max(6, h - header_h - cmdbar_h)
            draw_header(stdscr, w)
            left_w = max(20, w * 2 // 3)
            right_w = w - left_w
            draw_log_panel(stdscr, body_y, 0, body_h, left_w, STATE)
            stats_h = min(27, body_h)
            draw_stats_panel(stdscr, body_y, left_w, stats_h, right_w, STATE)
            if body_h > stats_h:
                draw_help_panel(stdscr, body_y + stats_h, left_w, body_h - stats_h, right_w)
            draw_cmd_bar(stdscr, h - cmdbar_h, w, cmd_buf, STATE)
            stdscr.refresh()

            try:
                ch = stdscr.getch()
            except curses.error:
                ch = -1
            if ch == -1:
                continue

            inner_h = max(1, body_h - 2)
            if ch == curses.KEY_UP:
                with STATE.log_lock:
                    total = len(STATE.log)
                if total > 0:
                    if STATE.auto_follow:
                        STATE.auto_follow = False
                        STATE.scroll_offset = 1
                    else:
                        STATE.scroll_offset = min(total - 1, STATE.scroll_offset + 1)
                continue
            elif ch == curses.KEY_DOWN:
                if not STATE.auto_follow:
                    if STATE.scroll_offset <= 1:
                        STATE.scroll_offset = 0
                        STATE.auto_follow = True
                    else:
                        STATE.scroll_offset -= 1
                continue
            elif ch == curses.KEY_PPAGE:
                with STATE.log_lock:
                    total = len(STATE.log)
                if total > 0:
                    if STATE.auto_follow:
                        STATE.auto_follow = False
                        STATE.scroll_offset = min(total - 1, inner_h)
                    else:
                        STATE.scroll_offset = min(total - 1, STATE.scroll_offset + inner_h)
                continue
            elif ch == curses.KEY_NPAGE:
                if not STATE.auto_follow:
                    if STATE.scroll_offset <= inner_h:
                        STATE.scroll_offset = 0
                        STATE.auto_follow = True
                    else:
                        STATE.scroll_offset -= inner_h
                continue
            elif ch == curses.KEY_HOME:
                with STATE.log_lock:
                    total = len(STATE.log)
                if total > 0:
                    STATE.auto_follow = False
                    STATE.scroll_offset = max(0, total - 1)
                continue
            elif ch == curses.KEY_END:
                STATE.auto_follow = True
                STATE.scroll_offset = 0
                continue
            elif ch == 5:
                STATE.auto_follow = True
                STATE.scroll_offset = 0
                continue

            if ch in (curses.KEY_ENTER, 10, 13):
                result = parse_and_apply(cmd_buf, STATE)
                cmd_buf = ""
                if result == "QUIT":
                    break
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                cmd_buf = cmd_buf[:-1]
            elif ch == 3:
                break
            elif 32 <= ch <= 126:
                cmd_buf += chr(ch)
    finally:
        TELEMETRY.unbind()
        try:
            curses.curs_set(1)
        except curses.error:
            pass


def main():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        run_cli()
    else:
        try:
            curses.wrapper(run_tui)
        except KeyboardInterrupt:
            pass
        finally:
            TELEMETRY.unbind()
            try:
                _unbind_jsonl()
            except Exception:
                pass
            try:
                _unbind_raw()
            except Exception:
                pass
        print("console closed.")


if __name__ == "__main__":
    main()
