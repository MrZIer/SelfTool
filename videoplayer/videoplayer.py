#!/usr/bin/env python3
"""
Simple Video Player — 一个轻量级本地视频播放器
支持: 加载视频、宽屏切换、全屏、音量调节
"""

import os
import sys
import json
import mimetypes
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器，支持并发请求"""
    daemon_threads = True
from urllib.parse import urlparse, unquote, parse_qs

# ── 配置 ──────────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 18080
VIDEO_PATH = ""

VIDEO_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".ogv", ".ts", ".mts",
}


def is_video_file(name):
    _, ext = os.path.splitext(name.lower())
    return ext in VIDEO_EXTS


def format_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} TB"


# ── HTTP 处理器 ────────────────────────────────────────────
class PlayerHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        req_path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        if req_path == "/":
            self._serve_html()
        elif req_path == "/config":
            self._serve_config()
        elif req_path == "/video":
            self._serve_video()
        elif req_path == "/browse":
            self._serve_browse(query)
        elif req_path == "/load":
            self._serve_load(query)
        elif req_path == "/drives":
            self._serve_drives()
        else:
            self.send_error(404)

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode("utf-8"))

    def _serve_config(self):
        global VIDEO_PATH
        if VIDEO_PATH and os.path.isfile(VIDEO_PATH):
            data = {"name": os.path.basename(VIDEO_PATH), "path": VIDEO_PATH,
                    "size": os.path.getsize(VIDEO_PATH)}
        else:
            data = {"name": "", "path": "", "size": 0}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _serve_drives(self):
        """返回可用的磁盘根目录列表"""
        drives = []
        try:
            import string
            for letter in string.ascii_uppercase:
                path = f"{letter}:\\"
                if os.path.exists(path):
                    drives.append(path)
        except:
            pass
        if not drives:
            drives = ["/"]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(drives).encode("utf-8"))

    def _serve_browse(self, query):
        dir_path = query.get("path", [None])[0]
        if dir_path:
            dir_path = unquote(dir_path)
        else:
            dir_path = os.path.abspath(".")

        try:
            dir_path = os.path.abspath(dir_path)
            if not os.path.isdir(dir_path):
                dir_path = os.path.dirname(dir_path)
        except:
            dir_path = os.path.abspath(".")

        result = {"current": dir_path, "parent": None, "files": [], "folders": []}
        parent = os.path.dirname(dir_path)
        if parent and parent != dir_path:
            result["parent"] = parent

        try:
            entries = sorted(os.listdir(dir_path), key=lambda x: (not os.path.isdir(os.path.join(dir_path, x)), x.lower()))
            for name in entries:
                full = os.path.join(dir_path, name)
                try:
                    if os.path.isdir(full):
                        result["folders"].append(name)
                    elif os.path.isfile(full) and is_video_file(name):
                        stat = os.stat(full)
                        result["files"].append({
                            "name": name, "size": format_size(stat.st_size),
                            "size_bytes": stat.st_size,
                        })
                except PermissionError:
                    continue
        except PermissionError:
            pass

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))

    def _serve_load(self, query):
        global VIDEO_PATH
        file_path = query.get("path", [None])[0]
        if file_path:
            file_path = unquote(file_path)
            if os.path.isfile(file_path):
                VIDEO_PATH = file_path
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True, "name": os.path.basename(file_path),
                    "path": file_path,
                }).encode("utf-8"))
                return
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"success": False}).encode("utf-8"))

    def _serve_video(self):
        global VIDEO_PATH
        if not VIDEO_PATH or not os.path.isfile(VIDEO_PATH):
            self.send_error(404, "Video not found")
            return

        file_size = os.path.getsize(VIDEO_PATH)
        mime_type, _ = mimetypes.guess_type(VIDEO_PATH)
        if mime_type is None:
            mime_type = "video/mp4"

        range_header = self.headers.get("Range")
        start, end = 0, file_size - 1

        if range_header:
            try:
                range_val = range_header.strip().removeprefix("bytes=")
                parts = range_val.split("-")
                start = int(parts[0])
                if parts[1]:
                    end = int(parts[1])
            except (ValueError, IndexError):
                pass
            content_length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(content_length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            with open(VIDEO_PATH, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk: break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            with open(VIDEO_PATH, "rb") as f:
                remaining = file_size
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk: break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    def log_message(self, format, *args):
        pass


# ── HTML 播放器页面 ────────────────────────────────────────
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Simple Video Player</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{
    background:#0d0d1a;color:#ddd;
    font-family:'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;
    height:100vh;overflow:hidden;user-select:none;
  }
  .layout{display:flex;height:100vh;overflow:hidden}

  /* 左侧栏 */
  .sidebar{
    width:300px;min-width:140px;max-width:500px;background:#111827;
    border-right:none;display:flex;flex-direction:column;
    flex-shrink:0;overflow:hidden;
  }
  .sidebar.hidden{width:0!important;min-width:0!important;padding:0;overflow:hidden;border-right:none}
  .sidebar.hidden+.splitter{width:0!important;pointer-events:none}

  /* 拖拽分割线 */
  .splitter{
    width:6px;cursor:col-resize;background:#1e293b;
    flex-shrink:0;position:relative;z-index:10;
    transition:background .15s;
  }
  .splitter:hover,.splitter.active{background:#3b82f6}

  .sidebar-title{
    display:flex;align-items:center;gap:8px;
    padding:12px 14px;border-bottom:1px solid #1e293b;
    font-size:14px;font-weight:600;color:#e2e8f0;flex-shrink:0;
  }
  .sidebar-title .icon{font-size:18px}

  .sidebar-actions{
    display:flex;gap:6px;padding:10px 14px;border-bottom:1px solid #1e293b;flex-shrink:0;
  }
  .sidebar-actions button{
    flex:1;padding:8px 12px;border:none;border-radius:6px;
    cursor:pointer;font-size:13px;font-weight:500;
    display:flex;align-items:center;justify-content:center;gap:6px;
    transition:all .2s;
  }
  .btn-open-folder{
    background:#2563eb;color:#fff;
  }
  .btn-open-folder:hover{background:#1d4ed8}
  .btn-open-folder:active{transform:scale(.98)}
  .btn-drives{
    background:#374151;color:#d1d5db;
  }
  .btn-drives:hover{background:#4b5563}

  .path-bar{
    display:flex;align-items:center;gap:4px;
    padding:8px 14px;border-bottom:1px solid #1e293b;flex-shrink:0;
  }
  .path-bar input{
    flex:1;background:#1f2937;border:1px solid #374151;color:#e5e7eb;
    padding:6px 10px;border-radius:5px;font-size:12px;outline:none;
    font-family:'Consolas','Cascadia Code',monospace;
  }
  .path-bar input:focus{border-color:#2563eb}
  .path-bar input::placeholder{color:#6b7280}
  .path-bar button{
    background:#374151;border:none;color:#d1d5db;
    width:28px;height:28px;border-radius:5px;cursor:pointer;
    font-size:14px;display:flex;align-items:center;justify-content:center;
  }
  .path-bar button:hover{background:#2563eb;color:#fff}

  .dir-list{
    flex:1;overflow-y:auto;padding:4px 0;
  }
  .dir-list::-webkit-scrollbar{width:4px}
  .dir-list::-webkit-scrollbar-thumb{background:#374151;border-radius:2px}

  .dir-item{
    display:flex;align-items:center;padding:7px 14px;cursor:pointer;
    gap:8px;font-size:13px;transition:background .12s;
    border-left:3px solid transparent;
  }
  .dir-item:hover{background:rgba(255,255,255,.04)}
  .dir-item.active{background:rgba(37,99,235,.2);border-left-color:#2563eb}
  .dir-item.folder{color:#93c5fd}
  .dir-item.folder:hover{color:#60a5fa}
  .dir-item.parent{color:#9ca3af;font-style:italic}
  .dir-item .ico{flex-shrink:0;font-size:15px;width:20px;text-align:center}
  .dir-item .name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .dir-item .size{color:#6b7280;font-size:11px;flex-shrink:0;margin-left:8px}
  .empty-msg{padding:30px 20px;text-align:center;color:#6b7280;font-size:13px}

  /* 主区域 */
  .main{flex:1;display:flex;flex-direction:column;min-width:0}

  .topbar{
    display:flex;align-items:center;padding:10px 16px;
    background:#111827;border-bottom:1px solid #1e293b;flex-shrink:0;gap:10px;
  }
  .topbar .toggle-sidebar{
    background:none;border:none;color:#9ca3af;font-size:20px;
    cursor:pointer;padding:2px 6px;border-radius:4px;
  }
  .topbar .toggle-sidebar:hover{color:#fff;background:rgba(255,255,255,.06)}
  .topbar .brand{
    font-size:15px;font-weight:700;
    background:linear-gradient(135deg,#3b82f6,#8b5cf6);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  }
  .topbar .cur-file{font-size:12px;color:#9ca3af;margin-left:auto;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:35%}

  .progress-wrap{
    width:100%;height:4px;background:#1f2937;cursor:pointer;
    position:relative;flex-shrink:0;
  }
  .progress-wrap .buf{
    height:100%;background:rgba(255,255,255,.08);width:0;
    position:absolute;top:0;left:0;
  }
  .progress-wrap .fil{
    height:100%;background:linear-gradient(90deg,#3b82f6,#8b5cf6);width:0;
    border-radius:0 2px 2px 0;position:relative;z-index:1;
  }

  .video-container{
    flex:1;display:flex;align-items:center;justify-content:center;
    background:#000;position:relative;overflow:hidden;
  }
  .video-container.widescreen video{
    width:100%;height:100%;object-fit:contain;
  }
  .video-container:not(.widescreen) video{
    aspect-ratio:auto;max-width:100%;max-height:100%;object-fit:contain;
  }
  .video-container video{display:none;width:100%;height:100%}
  .drop-hint{
    position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
    background:rgba(0,0,0,.85);color:#3b82f6;font-size:20px;font-weight:600;
    border:3px dashed #3b82f6;border-radius:16px;margin:30px;
    opacity:0;pointer-events:none;transition:opacity .2s;z-index:10;
  }
  .drop-hint.show{opacity:1}

  .start-hint{
    text-align:center;color:#4b5563;
  }
  .start-hint .big{font-size:52px;display:block;margin-bottom:12px}
  .start-hint p{font-size:15px;line-height:2}

  /* 控制栏 */
  .ctrl-bar{
    display:flex;align-items:center;gap:16px;
    padding:12px 20px;background:#111827;border-top:1px solid #1e293b;
    flex-shrink:0;flex-wrap:wrap;
  }
  .ctrl-bar button{
    background:#1f2937;border:none;color:#d1d5db;
    height:38px;border-radius:8px;cursor:pointer;
    font-size:15px;display:flex;align-items:center;justify-content:center;
    transition:all .2s;gap:6px;padding:0 14px;
  }
  .ctrl-bar button:hover{background:#2563eb;color:#fff;transform:translateY(-1px)}
  .ctrl-bar button:active{transform:scale(.96)}
  .ctrl-bar button.active{background:#2563eb;color:#fff}

  .ctrl-bar .icon-btn{width:38px;padding:0}
  .ctrl-bar .spacer{flex:1}

  .ctrl-bar label{font-size:13px;color:#9ca3af;display:flex;align-items:center;gap:6px}
  .ctrl-bar input[type=range]{
    -webkit-appearance:none;appearance:none;height:4px;
    border-radius:2px;background:#374151;outline:none;cursor:pointer;width:100px;
  }
  .ctrl-bar input[type=range]::-webkit-slider-thumb{
    -webkit-appearance:none;width:14px;height:14px;border-radius:50%;
    background:#3b82f6;cursor:pointer;
  }
  .ctrl-bar input[type=range]::-moz-range-thumb{
    width:14px;height:14px;border-radius:50%;background:#3b82f6;border:none;
  }
  .vol-num{font-size:13px;color:#d1d5db;min-width:28px;text-align:center}
  .time{font-size:13px;color:#9ca3af;font-variant-numeric:tabular-nums}

  @media(max-width:768px){
    .sidebar{width:220px;min-width:180px}
    .ctrl-bar{gap:8px;padding:10px 12px}
    .ctrl-bar input[type=range]{width:70px}
    .ctrl-bar button{padding:0 10px;font-size:13px}
  }

  /* 文件夹选择弹窗 */
  .modal-overlay{
    display:none;position:fixed;inset:0;z-index:9999;
    background:rgba(0,0,0,.7);align-items:center;justify-content:center;
  }
  .modal-overlay.show{display:flex}
  .modal-box{
    width:600px;max-width:90vw;max-height:80vh;
    background:#111827;border-radius:12px;border:1px solid #1e293b;
    display:flex;flex-direction:column;overflow:hidden;
    box-shadow:0 20px 60px rgba(0,0,0,.6);
  }
  .modal-header{
    display:flex;align-items:center;justify-content:space-between;
    padding:14px 18px;border-bottom:1px solid #1e293b;
    font-size:16px;font-weight:600;color:#e2e8f0;
  }
  .modal-header button{
    background:none;border:none;color:#9ca3af;font-size:20px;
    cursor:pointer;padding:4px 8px;border-radius:4px;
  }
  .modal-header button:hover{background:rgba(255,255,255,.06);color:#fff}
  .modal-path-bar{
    padding:10px 14px;border-bottom:1px solid #1e293b;
    display:flex;flex-direction:column;gap:6px;
  }
  .modal-path-bar input{
    background:#1f2937;border:1px solid #374151;color:#e5e7eb;
    padding:8px 12px;border-radius:6px;font-size:13px;outline:none;
    font-family:'Consolas','Cascadia Code',monospace;
  }
  .modal-path-bar input:focus{border-color:#2563eb}
  .modal-path-bar input::placeholder{color:#6b7280}
  .modal-cur-path{font-size:11px;color:#6b7280;font-family:'Consolas',monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .modal-dir-list{
    flex:1;overflow-y:auto;min-height:200px;max-height:50vh;padding:4px 0;
  }
  .modal-dir-list::-webkit-scrollbar{width:4px}
  .modal-dir-list::-webkit-scrollbar-thumb{background:#374151;border-radius:2px}
  .modal-footer{
    padding:10px 14px;border-top:1px solid #1e293b;
    font-size:11px;color:#6b7280;
  }

  /* 全屏悬浮覆盖层 */
  .fs-overlay{
    position:fixed;inset:0;z-index:9998;pointer-events:none;
    display:flex;flex-direction:column;opacity:0;
    transition:opacity .3s;
  }
  .fs-overlay.visible{opacity:1}
  .fs-overlay.visible>*{pointer-events:auto}
  .fs-top{
    display:flex;align-items:center;justify-content:space-between;
    padding:12px 20px;background:linear-gradient(180deg,rgba(0,0,0,.7),transparent);
  }
  .fs-title{font-size:14px;color:#e5e7eb;font-weight:500}
  .fs-exit{
    background:rgba(255,255,255,.1);border:none;color:#fff;
    width:32px;height:32px;border-radius:8px;cursor:pointer;font-size:18px;
  }
  .fs-exit:hover{background:rgba(255,255,255,.2)}
  .fs-center{
    flex:1;display:flex;align-items:center;justify-content:center;gap:24px;
  }
  .fs-center button{
    background:rgba(255,255,255,.1);border:none;color:#fff;
    width:48px;height:48px;border-radius:50%;cursor:pointer;
    font-size:20px;transition:background .2s,transform .15s;
  }
  .fs-center button:hover{background:rgba(255,255,255,.2);transform:scale(1.1)}
  .fs-center .fs-play{width:56px;height:56px;font-size:24px}
  .fs-bottom{
    display:flex;align-items:center;gap:12px;
    padding:16px 20px;padding-top:30px;
    background:linear-gradient(0deg,rgba(0,0,0,.7),transparent);
    flex-wrap:wrap;
  }
  .fs-time{font-size:13px;color:#d1d5db;font-variant-numeric:tabular-nums;flex-shrink:0}
  .fs-progress{
    flex:1;height:4px;background:rgba(255,255,255,.15);cursor:pointer;
    position:relative;border-radius:2px;min-width:80px;
  }
  .fs-progress .fs-buf{
    height:100%;background:rgba(255,255,255,.15);width:0;
    position:absolute;top:0;left:0;border-radius:2px;
  }
  .fs-progress .fs-fil{
    height:100%;background:#3b82f6;width:0;
    position:relative;z-index:1;border-radius:2px;
  }
  .fs-progress:hover{height:6px;margin-top:-2px}
  .fs-spacer{flex:1}
  .fs-wide{
    background:rgba(255,255,255,.1);border:none;color:#fff;
    padding:6px 12px;border-radius:6px;cursor:pointer;font-size:15px;
  }
  .fs-wide:hover{background:rgba(255,255,255,.2)}
  .fs-wide.active{background:#2563eb}
  .fs-vol-label{cursor:pointer;font-size:14px}
  .fs-vol{
    -webkit-appearance:none;appearance:none;height:4px;width:80px;
    border-radius:2px;background:rgba(255,255,255,.15);outline:none;cursor:pointer;
  }
  .fs-vol::-webkit-slider-thumb{
    -webkit-appearance:none;width:14px;height:14px;border-radius:50%;
    background:#fff;cursor:pointer;
  }
  .fs-vol::-moz-range-thumb{width:14px;height:14px;border-radius:50%;background:#fff;border:none}
</style>
</head>
<body>

<div class="layout">

  <!-- ========== 左侧文件夹面板 ========== -->
  <div class="sidebar" id="sidebar">
    <div class="sidebar-title">
      <span class="icon">📁</span> 文件浏览器
    </div>
    <div class="sidebar-actions">
      <button class="btn-open-folder" id="btnOpenFolder">
        📂 打开文件夹
      </button>
      <button class="btn-drives" id="btnDrives" title="磁盘列表">💿</button>
    </div>
    <div class="path-bar">
      <input id="pathInput" type="text" placeholder="输入路径后回车..." spellcheck="false">
      <button id="btnGo" title="跳转">↵</button>
    </div>
    <div class="dir-list" id="dirList">
      <div class="empty-msg">点击上方按钮选择文件夹</div>
    </div>
  </div>

  <!-- ========== 拖拽分割线 ========== -->
  <div class="splitter" id="splitter"></div>

  <!-- ========== 主区域 ========== -->
  <div class="main" id="mainArea">
    <div class="topbar">
      <button class="toggle-sidebar" id="toggleSidebar" title="显示/隐藏侧栏">☰</button>
      <span class="brand">Simple Player</span>
      <span class="cur-file" id="curFile">-- 未加载视频 --</span>
    </div>

    <div class="progress-wrap" id="progressWrap">
      <div class="buf" id="bufBar"></div>
      <div class="fil" id="filBar"></div>
    </div>

    <div class="video-container" id="videoContainer">
      <div class="start-hint" id="startHint">
        <span class="big">🎬</span>
        <p>点击左侧 <b>📂 打开文件夹</b> 选择视频目录<br>或把视频文件拖放到这里</p>
      </div>
      <video id="video" preload="metadata" playsinline></video>
      <div class="drop-hint" id="dropHint">📁 释放文件以播放</div>
    </div>

    <div class="ctrl-bar" id="ctrlBar">
      <button class="icon-btn" id="btnRew" title="后退5秒 (←)">⏪</button>
      <button class="icon-btn" id="btnPlay" title="播放/暂停 (Space)">▶</button>
      <button class="icon-btn" id="btnFwd" title="快进5秒 (→)">⏩</button>
      <span class="time" id="timeDisplay">00:00 / 00:00</span>
      <div class="spacer"></div>
      <button id="btnWide" title="宽屏 16:9 (W)">
        📐 宽屏
      </button>
      <button id="btnFull" title="全屏 (F)">
        <span id="fullIcon">⛶</span> <span id="fullLabel">全屏</span>
      </button>
      <label id="volIcon" title="静音 (M)" style="cursor:pointer">🔊</label>
      <input type=range id="volSlider" min=0 max=100 value=80>
      <span class="vol-num" id="volNum">80</span>
    </div>
  </div>

</div>

<!-- ========== 文件夹选择弹出窗口 ========== -->
<div class="modal-overlay" id="folderModal">
  <div class="modal-box">
    <div class="modal-header">
      <span>📁 选择文件夹</span>
      <button id="modalClose" title="关闭">✕</button>
    </div>
    <div class="modal-path-bar">
      <input id="modalPathInput" type="text" placeholder="输入路径后回车..." spellcheck="false">
      <span class="modal-cur-path" id="modalCurrentPath"></span>
    </div>
    <div class="modal-dir-list" id="modalDirList">
      <div class="empty-msg">加载中...</div>
    </div>
    <div class="modal-footer">
      <span class="modal-hint">💡 单击视频文件播放 | 双击文件夹进入</span>
    </div>
  </div>
</div>

<!-- ========== 全屏悬浮控制栏 ========== -->
<div class="fs-overlay" id="fsOverlay">
  <div class="fs-top">
    <span class="fs-title" id="fsTitle">未加载视频</span>
    <button class="fs-exit" id="fsExit" title="退出全屏">✕</button>
  </div>
  <div class="fs-center" id="fsCenter">
    <button class="fs-rew" id="fsRew" title="后退5秒">⏪</button>
    <button class="fs-play" id="fsPlay" title="播放/暂停">▶</button>
    <button class="fs-fwd" id="fsFwd" title="快进5秒">⏩</button>
  </div>
  <div class="fs-bottom">
    <span class="fs-time" id="fsTime">00:00 / 00:00</span>
    <div class="fs-progress" id="fsProgressWrap">
      <div class="fs-buf" id="fsBufBar"></div>
      <div class="fs-fil" id="fsFilBar"></div>
    </div>
    <span class="fs-spacer"></span>
    <button class="fs-wide" id="fsWide" title="宽屏">📐</button>
    <label class="fs-vol-label">🔊</label>
    <input type=range class="fs-vol" id="fsVolSlider" min=0 max=100 value=80>
  </div>
</div>

<script>
(function(){
  const video=document.getElementById('video');
  const container=document.getElementById('videoContainer');
  const startHint=document.getElementById('startHint');
  const curFile=document.getElementById('curFile');
  const filBar=document.getElementById('filBar');
  const bufBar=document.getElementById('bufBar');
  const progressWrap=document.getElementById('progressWrap');
  const timeDisplay=document.getElementById('timeDisplay');
  const dropHint=document.getElementById('dropHint');
  const sidebar=document.getElementById('sidebar');
  const toggleSidebar=document.getElementById('toggleSidebar');
  const dirList=document.getElementById('dirList');
  const pathInput=document.getElementById('pathInput');
  const btnGo=document.getElementById('btnGo');
  const btnOpenFolder=document.getElementById('btnOpenFolder');
  const btnDrives=document.getElementById('btnDrives');

  const btnPlay=document.getElementById('btnPlay');
  const btnRew=document.getElementById('btnRew');
  const btnFwd=document.getElementById('btnFwd');
  const btnWide=document.getElementById('btnWide');
  const btnFull=document.getElementById('btnFull');
  const fullIcon=document.getElementById('fullIcon');
  const fullLabel=document.getElementById('fullLabel');
  const volSlider=document.getElementById('volSlider');
  const volNum=document.getElementById('volNum');
  const volIcon=document.getElementById('volIcon');

  let currentDir='';

  function fmtTime(t){
    if(!t||isNaN(t))return'00:00';
    return String(Math.floor(t/60)).padStart(2,'0')+':'+String(Math.floor(t%60)).padStart(2,'0');
  }

  function fmtPath(p){return p.replace(/\\/g,'/')}

  // ── 加载服务端视频 ──
  function loadServerVideo(filePath){
    fetch('/load?path='+encodeURIComponent(filePath))
    .then(r=>r.json())
    .then(d=>{
      if(d.success){
        video.src='/video?t='+Date.now();
        video.load();
        curFile.textContent=d.name;
        startHint.style.display='none';
        video.style.display='block';
        document.querySelectorAll('.dir-item').forEach(e=>e.classList.remove('active'));
        document.querySelectorAll('.dir-item.file').forEach(e=>{
          if(e.dataset.path===filePath)e.classList.add('active');
        });
      }
    });
  }

  // ── 目录浏览 ──
  function browseDir(dirPath){
    const params=dirPath?'?path='+encodeURIComponent(dirPath):'';
    fetch('/browse'+params)
    .then(r=>r.json())
    .then(d=>{
      currentDir=d.current;
      renderDirList(d);
      pathInput.value=fmtPath(d.current);
    })
    .catch(()=>{dirList.innerHTML='<div class="empty-msg">无法访问该路径</div>'});
  }

  function renderDirList(d){
    let h='';
    if(d.parent){
      h+=`<div class="dir-item parent" data-path="${d.parent}">
        <span class=ico>📂</span><span class=name>.. (上级目录)</span></div>`;
    }
    for(const f of d.folders){
      const full=fmtPath(d.current)+'/'+f;
      h+=`<div class="dir-item folder" data-path="${full}">
        <span class=ico>📁</span><span class=name>${f}</span></div>`;
    }
    if(d.files.length===0&&d.folders.length===0&&!d.parent){
      h+='<div class="empty-msg">此目录没有视频文件</div>';
    }else{
      for(const f of d.files){
        const full=fmtPath(d.current)+'/'+f.name;
        h+=`<div class="dir-item file" data-path="${full}">
          <span class=ico>🎬</span><span class=name>${f.name}</span><span class=size>${f.size}</span></div>`;
      }
    }
    dirList.innerHTML=h;
    bindSidebarClicks();
  }

  // ── 原生文件夹选择 → 填充侧栏 ──
  let fsDirHandle=null;
  const fsHandleMap=new Map(); // virtual-path -> FileSystemDirectoryHandle

  async function openFolderPrompt(){
    try{
      const handle=await window.showDirectoryPicker();
      fsDirHandle=handle;
      fsHandleMap.clear();
      fsHandleMap.set(handle.name,handle);
      currentDir=handle.name;
      pathInput.value=handle.name;
      await browseHandleSidebar(handle,handle.name);
    }catch(err){
      if(err.name==='AbortError')return;
      // 回退：聚焦路径输入框让用户手动输入
      pathInput.focus();
      pathInput.placeholder='浏览器不支持，请在此输入路径后回车（如 G:\\Anime）';
    }
  }

  async function browseHandleSidebar(handle,displayPath){
    const dirs=[],files=[];
    const pending=[];
    try{
      for await(const[name,entry]of handle.entries()){
        if(entry.kind==='directory'){
          dirs.push(name);
          fsHandleMap.set(displayPath+'/'+name,entry);
          pending.push(collectSidebarVideos(entry,displayPath+'/'+name,files));
        }else{
          const ext='.'+name.split('.').pop().toLowerCase();
          if(['.mp4','.mkv','.avi','.mov','.wmv','.flv','.webm','.m4v','.mpg','.mpeg','.ogv','.ts'].includes(ext)){
            files.push({name,entry,relPath:displayPath+'/'+name});
          }
        }
      }
      await Promise.all(pending);
    }catch(e){}

    dirs.sort((a,b)=>a.toLowerCase().localeCompare(b.toLowerCase()));
    files.sort((a,b)=>a.name.toLowerCase().localeCompare(b.name.toLowerCase()));

    currentDir=displayPath;
    pathInput.value=displayPath;

    let h='';
    // 返回上级（如果不在根）
    if(displayPath!==fsDirHandle.name){
      const pp=displayPath.substring(0,displayPath.lastIndexOf('/'));
      h+=`<div class="dir-item parent" data-path="${pp}" data-handle="1">
        <span class=ico>📂</span><span class=name>.. (上级目录)</span></div>`;
    }
    for(const d of dirs){
      const full=displayPath+'/'+d;
      h+=`<div class="dir-item folder" data-path="${full}" data-handle="1">
        <span class=ico>📁</span><span class=name>${d}</span></div>`;
    }
    if(files.length===0&&dirs.length===0&&displayPath===fsDirHandle.name){
      h+='<div class="empty-msg">此目录及子目录中没有视频文件</div>';
    }
    for(const f of files){
      const prefix=f.subDir?`[${f.subDir}] `:'';
      h+=`<div class="dir-item file" data-path="${f.relPath}" data-handle="1">
        <span class=ico>🎬</span><span class=name>${prefix}${f.name}</span></div>`;
    }
    dirList.innerHTML=h;
    bindSidebarClicks();
  }

  async function collectSidebarVideos(handle,relPath,allFiles,depth=0){
    if(depth>1)return;
    try{
      for await(const[name,entry]of handle.entries()){
        if(entry.kind==='directory'&&depth<1){
          fsHandleMap.set(relPath+'/'+name,entry);
          await collectSidebarVideos(entry,relPath+'/'+name,allFiles,depth+1);
        }else if(entry.kind==='file'){
          const ext='.'+name.split('.').pop().toLowerCase();
          if(['.mp4','.mkv','.avi','.mov','.wmv','.flv','.webm','.m4v','.mpg','.mpeg','.ogv','.ts'].includes(ext)){
            const subDir=relPath.split('/').slice(1).join('/');
            allFiles.push({name,entry,subDir:subDir||null,relPath:relPath+'/'+name});
          }
        }
      }
    }catch(e){}
  }

  async function playHandleFile(fullPath){
    const parts=fullPath.split('/');
    const fileName=parts.pop();
    const dirPath=parts.join('/');
    let dh=dirPath?fsHandleMap.get(dirPath):fsDirHandle;
    if(dh){
      try{
        const fh=await dh.getFileHandle(fileName);
        const file=await fh.getFile();
        video.src=URL.createObjectURL(file);
        video.load();
        curFile.textContent=fileName;
        startHint.style.display='none';
        video.style.display='block';
      }catch(e){
        alert('无法读取文件: '+e.message);
      }
    }
  }

  // ── 统一侧栏点击处理 ──
  function bindSidebarClicks(){
    dirList.querySelectorAll('.dir-item').forEach(el=>{
      el.addEventListener('click',async()=>{
        if(el.dataset.handle==='1'){
          // Handle-based 导航
          if(el.classList.contains('folder')){
            const hh=fsHandleMap.get(el.dataset.path);
            if(hh)await browseHandleSidebar(hh,el.dataset.path);
          }else if(el.classList.contains('parent')){
            const hh=fsHandleMap.get(el.dataset.path);
            if(hh)await browseHandleSidebar(hh,el.dataset.path);
          }else{
            await playHandleFile(el.dataset.path);
          }
        }else{
          // 服务端路径导航
          if(el.classList.contains('folder')||el.classList.contains('parent')){
            browseDir(el.dataset.path);
          }else{
            loadServerVideo(el.dataset.path);
          }
        }
      });
    });
  }

  // ── 显示磁盘列表 ──
  function showDrives(){
    fetch('/drives')
    .then(r=>r.json())
    .then(drives=>{
      let h='<div class="empty-msg" style="text-align:left;padding:10px 14px">📀 磁盘列表：</div>';
      for(const d of drives){
        h+=`<div class="dir-item folder" data-path="${d}">
          <span class=ico>💿</span><span class=name>${d}</span></div>`;
      }
      dirList.innerHTML=h;
      bindSidebarClicks();
    });
  }

  // ── 侧栏开关 ──
  toggleSidebar.addEventListener('click',()=>{
    sidebar.classList.toggle('hidden');
  });

  // ── 分割线拖拽调整侧栏宽度 ──
  const splitter=document.getElementById('splitter');
  let isDraggingSplitter=false;
  splitter.addEventListener('mousedown',e=>{
    isDraggingSplitter=true;
    splitter.classList.add('active');
    document.body.style.cursor='col-resize';
    document.body.style.userSelect='none';
    e.preventDefault();
  });
  document.addEventListener('mousemove',e=>{
    if(!isDraggingSplitter)return;
    const w=e.clientX;
    if(w>=140&&w<=500)sidebar.style.width=w+'px';
  });
  document.addEventListener('mouseup',()=>{
    if(!isDraggingSplitter)return;
    isDraggingSplitter=false;
    splitter.classList.remove('active');
    document.body.style.cursor='';
    document.body.style.userSelect='';
  });

  // ── 路径跳转 ──
  function goToPath(){
    const v=pathInput.value.trim();
    if(v)browseDir(v);
  }
  pathInput.addEventListener('keydown',e=>{if(e.key==='Enter')goToPath()});
  btnGo.addEventListener('click',goToPath);
  btnOpenFolder.addEventListener('click',openFolderPrompt);
  btnDrives.addEventListener('click',showDrives);

  // ── 视频点击播放/暂停 + 双击全屏 ──
  let clickTimer=null;
  video.addEventListener('click',e=>{
    // 防止拖拽进度条时误触发
    if(e.target===video||e.target===container){
      if(clickTimer){
        clearTimeout(clickTimer);clickTimer=null;
        toggleFullscreen();
      }else{
        clickTimer=setTimeout(()=>{togglePlay();clickTimer=null},250);
      }
    }
  });
  container.addEventListener('click',e=>{
    if(e.target===container){
      if(clickTimer){
        clearTimeout(clickTimer);clickTimer=null;
        toggleFullscreen();
      }else{
        clickTimer=setTimeout(()=>{togglePlay();clickTimer=null},250);
      }
    }
  });

  // ── 跳过按钮 ──
  btnRew.addEventListener('click',()=>{video.currentTime=Math.max(0,(video.currentTime||0)-5)});
  btnFwd.addEventListener('click',()=>{video.currentTime=Math.min(video.duration||0,(video.currentTime||0)+5)});

  // ── 播放/暂停 ──
  function togglePlay(){
    if(video.paused)video.play().catch(()=>{});else video.pause();
  }

  // ── 进度条 hover 时间预览 ──
  const hoverTip=document.createElement('div');
  hoverTip.style.cssText='position:absolute;top:-28px;background:rgba(0,0,0,.85);color:#fff;font-size:11px;padding:3px 8px;border-radius:4px;pointer-events:none;display:none;white-space:nowrap;z-index:5;font-variant-numeric:tabular-nums';
  progressWrap.style.position='relative';
  progressWrap.appendChild(hoverTip);
  progressWrap.addEventListener('mousemove',e=>{
    if(!video.duration)return;
    const r=progressWrap.getBoundingClientRect();
    const pct=(e.clientX-r.left)/r.width;
    const t=pct*video.duration;
    hoverTip.textContent=fmtTime(t);
    hoverTip.style.display='block';
    hoverTip.style.left=(e.clientX-r.left-hoverTip.offsetWidth/2)+'px';
  });
  progressWrap.addEventListener('mouseleave',()=>{hoverTip.style.display='none'});

  // ── 音量静音切换 ──
  let lastVol=80;
  let muted=false;
  volIcon.addEventListener('click',()=>{
    if(muted){
      setVolume(lastVol);
      muted=false;
    }else{
      lastVol=parseInt(volSlider.value,10);
      setVolume(0);
      muted=true;
    }
  });

  // ── 进度更新 ──
  function updateProgress(){
    if(video.duration){
      filBar.style.width=(video.currentTime/video.duration*100)+'%';
      timeDisplay.textContent=fmtTime(video.currentTime)+' / '+fmtTime(video.duration);
    }
  }

  function seekTo(e){
    const r=progressWrap.getBoundingClientRect();
    const pct=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));
    if(video.duration)video.currentTime=pct*video.duration;
  }

  // ── 宽屏 ──
  function toggleWidescreen(){
    const wide=container.classList.toggle('widescreen');
    btnWide.classList.toggle('active',wide);
    fsWide.classList.toggle('active',wide);
    sidebar.classList.toggle('hidden',wide);
  }

  // ══════ 全屏 Bilibili 风格覆层 ══════
  const fsOverlay=document.getElementById('fsOverlay');
  const fsTitle=document.getElementById('fsTitle');
  const fsPlay=document.getElementById('fsPlay');
  const fsRew=document.getElementById('fsRew');
  const fsFwd=document.getElementById('fsFwd');
  const fsTime=document.getElementById('fsTime');
  const fsProgressWrap=document.getElementById('fsProgressWrap');
  const fsFilBar=document.getElementById('fsFilBar');
  const fsBufBar=document.getElementById('fsBufBar');
  const fsWide=document.getElementById('fsWide');
  const fsVolSlider=document.getElementById('fsVolSlider');
  const fsExit=document.getElementById('fsExit');

  let fsHideTimer=null;

  function toggleFullscreen(){
    if(!document.fullscreenElement){
      document.querySelector('.topbar').style.display='none';
      document.getElementById('progressWrap').style.display='none';
      document.getElementById('ctrlBar').style.display='none';
      sidebar.classList.add('hidden');
      document.documentElement.requestFullscreen().catch(()=>{
        document.querySelector('.topbar').style.display='';
        document.getElementById('progressWrap').style.display='';
        document.getElementById('ctrlBar').style.display='';
        sidebar.classList.remove('hidden');
      });
    }else{
      document.exitFullscreen().catch(()=>{});
    }
  }

  function onFullscreenChange(){
    if(document.fullscreenElement){
      fullLabel.textContent='退出全屏';
      btnFull.classList.add('active');
      document.querySelector('.topbar').style.display='none';
      document.getElementById('progressWrap').style.display='none';
      document.getElementById('ctrlBar').style.display='none';
      sidebar.classList.add('hidden');
      fsTitle.textContent=curFile.textContent;
      fsOverlay.classList.add('visible');
      fsVolSlider.value=volSlider.value;
      resetFsTimer();
      document.addEventListener('mousemove',onFsMouseMove);
      document.addEventListener('mousedown',onFsMouseMove);
    }else{
      fullLabel.textContent='全屏';
      btnFull.classList.remove('active');
      document.querySelector('.topbar').style.display='';
      document.getElementById('progressWrap').style.display='';
      document.getElementById('ctrlBar').style.display='';
      sidebar.classList.remove('hidden');
      fsOverlay.classList.remove('visible');
      clearTimeout(fsHideTimer);
      document.removeEventListener('mousemove',onFsMouseMove);
      document.removeEventListener('mousedown',onFsMouseMove);
    }
  }

  function onFsMouseMove(){
    resetFsTimer();
  }

  function resetFsTimer(){
    clearTimeout(fsHideTimer);
    fsOverlay.classList.add('visible');
    fsHideTimer=setTimeout(()=>{
      fsOverlay.classList.remove('visible');
    },3500);
  }

  // 全屏覆层按钮事件
  fsExit.addEventListener('click',()=>document.exitFullscreen());
  fsPlay.addEventListener('click',togglePlay);
  fsRew.addEventListener('click',()=>{video.currentTime=Math.max(0,(video.currentTime||0)-5);resetFsTimer()});
  fsFwd.addEventListener('click',()=>{video.currentTime=Math.min(video.duration||0,(video.currentTime||0)+5);resetFsTimer()});
  fsWide.addEventListener('click',()=>{toggleWidescreen();resetFsTimer()});
  fsVolSlider.addEventListener('input',()=>{setVolume(fsVolSlider.value);resetFsTimer()});

  // 全屏进度条
  function updateFsProgress(){
    if(video.duration){
      fsFilBar.style.width=(video.currentTime/video.duration*100)+'%';
      fsTime.textContent=fmtTime(video.currentTime)+' / '+fmtTime(video.duration);
    }
  }
  function fsSeekTo(e){
    const r=fsProgressWrap.getBoundingClientRect();
    const pct=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));
    if(video.duration)video.currentTime=pct*video.duration;
    resetFsTimer();
  }
  fsProgressWrap.addEventListener('click',fsSeekTo);
  fsProgressWrap.addEventListener('mousedown',e=>{
    fsSeekTo(e);
    function m(ev){fsSeekTo(ev)}
    function u(){document.removeEventListener('mousemove',m);document.removeEventListener('mouseup',u)}
    document.addEventListener('mousemove',m);
    document.addEventListener('mouseup',u);
  });

  // ── 音量 ──
  function setVolume(v){
    const val=parseInt(v,10)/100;
    video.volume=Math.max(0,Math.min(1,val));
    volNum.textContent=parseInt(v,10);
    volSlider.value=v;
    fsVolSlider.value=v;
    updateVolIcon(parseInt(v,10));
  }
  function updateVolIcon(v){
    if(v==0){volIcon.textContent='🔇';}
    else if(v<34){volIcon.textContent='🔉';}
    else{volIcon.textContent='🔊';}
  }

  // ── 键盘快捷键 ──
  document.addEventListener('keydown',e=>{
    if(e.target.tagName==='INPUT')return;
    switch(e.key){
      case' ':e.preventDefault();togglePlay();break;
      case'f':case'F':e.preventDefault();toggleFullscreen();break;
      case'w':case'W':e.preventDefault();toggleWidescreen();break;
      case'ArrowUp':e.preventDefault();setVolume(Math.min(100,parseInt(volSlider.value,10)+5));break;
      case'ArrowDown':e.preventDefault();setVolume(Math.max(0,parseInt(volSlider.value,10)-5));break;
      case'ArrowLeft':e.preventDefault();video.currentTime=Math.max(0,(video.currentTime||0)-5);break;
      case'ArrowRight':e.preventDefault();video.currentTime=Math.min(video.duration||0,(video.currentTime||0)+5);break;
    }
  });

  // ── 事件绑定 ──
  btnPlay.addEventListener('click',togglePlay);
  btnWide.addEventListener('click',toggleWidescreen);
  btnFull.addEventListener('click',toggleFullscreen);
  volSlider.addEventListener('input',()=>setVolume(volSlider.value));

  video.addEventListener('play',()=>{btnPlay.textContent='⏸';fsPlay.textContent='⏸'});
  video.addEventListener('pause',()=>{btnPlay.textContent='▶';fsPlay.textContent='▶'});
  video.addEventListener('timeupdate',()=>{updateProgress();updateFsProgress()});
  video.addEventListener('loadedmetadata',()=>{updateProgress();updateFsProgress()});
  video.addEventListener('progress',()=>{
    if(video.buffered.length>0&&video.duration){
      const pct=(video.buffered.end(video.buffered.length-1)/video.duration*100)+'%';
      bufBar.style.width=pct;
      fsBufBar.style.width=pct;
    }
  });

  progressWrap.addEventListener('click',seekTo);
  progressWrap.addEventListener('mousedown',e=>{
    seekTo(e);
    function m(ev){seekTo(ev)}
    function u(){document.removeEventListener('mousemove',m);document.removeEventListener('mouseup',u)}
    document.addEventListener('mousemove',m);
    document.addEventListener('mouseup',u);
  });

  document.addEventListener('fullscreenchange',onFullscreenChange);

  // 拖放
  document.addEventListener('dragover',e=>{e.preventDefault();dropHint.classList.add('show')});
  document.addEventListener('dragleave',e=>{dropHint.classList.remove('show')});
  document.addEventListener('drop',e=>{
    e.preventDefault();dropHint.classList.remove('show');
    const f=e.dataTransfer.files[0];
    if(f){
      video.src=URL.createObjectURL(f);video.load();
      curFile.textContent=f.name;
      startHint.style.display='none';video.style.display='block';
    }
  });

  // ── 初始化 ──
  setVolume(80);
  fetch('/config').then(r=>r.json()).then(d=>{
    if(d.path&&d.size>0){
      video.src='/video?t='+Date.now();video.load();
      curFile.textContent=d.name;
      startHint.style.display='none';video.style.display='block';
      const sep=d.path.lastIndexOf('/')>d.path.lastIndexOf('\\')?'/':'\\';
      const p=d.path.substring(0,d.path.lastIndexOf(sep));
      browseDir(p||'/');
    }else{
      browseDir('');
    }
  }).catch(()=>browseDir(''));
})();
</script>
</body>
</html>
"""


# ── 主程序 ──────────────────────────────────────────────────
def open_browser():
    import time
    time.sleep(0.5)
    try:
        webbrowser.open(f"http://{HOST}:{PORT}")
    except Exception:
        pass


def main():
    global VIDEO_PATH, PORT

    import argparse
    parser = argparse.ArgumentParser(
        description="Simple Video Player",
        epilog="示例: %(prog)s video.mp4  或  %(prog)s --port 8080",
    )
    parser.add_argument("video", nargs="?", help="视频文件路径")
    parser.add_argument("--port", "-p", type=int, default=PORT, help=f"端口 (默认 {PORT})")
    args = parser.parse_args()
    PORT = args.port

    if args.video:
        VIDEO_PATH = os.path.abspath(args.video)
        if not os.path.isfile(VIDEO_PATH):
            print(f"❌ 文件不存在: {VIDEO_PATH}")
            sys.exit(1)
        print(f"📁 视频: {VIDEO_PATH}")

    server = ThreadingHTTPServer((HOST, PORT), PlayerHandler)
    print(f"🌐 http://{HOST}:{PORT}")
    print("⌨️ Space=播放  F=全屏  W=宽屏  ←→=快进/退  ↑↓=音量  Esc=退出全屏")
    print("—" * 45)
    print("按 Ctrl+C 退出")

    threading.Thread(target=open_browser, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 退出")
        server.shutdown()


if __name__ == "__main__":
    main()
