"""
P2P Tunnel Industrial Web Administration & Telemetry Console.
Built with pure-Python asyncio HTTP/1.1 server (Zero external dependencies).
Features:
- Monochrome + Subtle Accent Industrial Design (inspired by Vercel, Linear, Cloudflare Zero Trust).
- Smooth Dark / Light Theme Toggle persisted in localStorage (#09090b / #121215 Dark & #f4f4f5 / #ffffff Light).
- Pure inline SVG vector iconography (strictly zero emojis).
- Real-time KPI summary strip: Normalized Server Key (XXXX-YYYY) with copy & regenerate, Active Peers & TCP Streams, Target Service & Address, and Live Traffic Speed + CPU/RAM Telemetry.
- Unified Command Center layout + dedicated section views (Overview, Live Peers, HWID Firewall & History, Live Console Logs, Configuration).
- Custom animated confirmation modals, HWID ban modal, manual HWID ban bar, and stacked toast notifications.
"""

import asyncio
import json
import os
import sys
import time
import hmac
import hashlib
import secrets
import urllib.parse
from typing import Dict, List, Optional, Any, Tuple


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="tr" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>P2P Tunnel — Sunucu Kontrol Konsolu</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root, [data-theme="dark"] {
      --bg-base: #09090b;
      --bg-surface: #121215;
      --bg-elevated: #18181c;
      --bg-muted: #1f1f24;
      --bg-hover: rgba(255, 255, 255, 0.035);
      --bg-glass: rgba(18, 18, 21, 0.85);
      --border-subtle: #27272a;
      --border-strong: #3f3f46;
      --text-primary: #fafafa;
      --text-secondary: #a1a1aa;
      --text-tertiary: #71717a;
      --accent-primary: #fafafa;
      --accent-primary-fg: #09090b;
      --accent-primary-hover: #e4e4e7;
      --status-online: #10b981;
      --status-online-bg: rgba(16, 185, 129, 0.1);
      --status-online-border: rgba(16, 185, 129, 0.25);
      --status-warn: #f59e0b;
      --status-warn-bg: rgba(245, 158, 11, 0.1);
      --status-warn-border: rgba(245, 158, 11, 0.25);
      --status-danger: #f43f5e;
      --status-danger-bg: rgba(244, 63, 94, 0.1);
      --status-danger-border: rgba(244, 63, 94, 0.25);
      --status-info: #6366f1;
      --status-info-bg: rgba(99, 102, 241, 0.1);
      --status-info-border: rgba(99, 102, 241, 0.25);
      --terminal-bg: #070709;
      --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.4);
      --shadow-modal: 0 24px 48px -12px rgba(0, 0, 0, 0.85);
      --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-mono: 'JetBrains Mono', 'Cascadia Mono', 'Consolas', monospace;
      --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
    }

    [data-theme="light"] {
      --bg-base: #f4f4f5;
      --bg-surface: #ffffff;
      --bg-elevated: #fafafa;
      --bg-muted: #f4f4f5;
      --bg-hover: rgba(9, 9, 11, 0.03);
      --bg-glass: rgba(255, 255, 255, 0.88);
      --border-subtle: #e4e4e7;
      --border-strong: #d4d4d8;
      --text-primary: #09090b;
      --text-secondary: #52525b;
      --text-tertiary: #71717a;
      --accent-primary: #09090b;
      --accent-primary-fg: #fafafa;
      --accent-primary-hover: #27272a;
      --status-online: #059669;
      --status-online-bg: rgba(5, 150, 105, 0.08);
      --status-online-border: rgba(5, 150, 105, 0.22);
      --status-warn: #d97706;
      --status-warn-bg: rgba(217, 119, 6, 0.08);
      --status-warn-border: rgba(217, 119, 6, 0.22);
      --status-danger: #e11d48;
      --status-danger-bg: rgba(225, 29, 72, 0.08);
      --status-danger-border: rgba(225, 29, 72, 0.22);
      --status-info: #4f46e5;
      --status-info-bg: rgba(79, 70, 229, 0.08);
      --status-info-border: rgba(79, 70, 229, 0.22);
      --terminal-bg: #111114;
      --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.04);
      --shadow-modal: 0 20px 40px -15px rgba(0, 0, 0, 0.18);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    html, body {
      background-color: var(--bg-base);
      color: var(--text-primary);
      font-family: var(--font-sans);
      font-size: 13px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      min-height: 100vh;
      transition: background-color 0.2s ease, color 0.2s ease;
    }

    /* Custom Scrollbar */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border-subtle); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--border-strong); }

    /* Animations */
    @keyframes pulseDot {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.45; transform: scale(1.25); }
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes modalIn {
      from { opacity: 0; transform: scale(0.96) translateY(8px); }
      to { opacity: 1; transform: scale(1) translateY(0); }
    }
    @keyframes toastIn {
      from { opacity: 0; transform: translateY(16px) scale(0.96); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes toastOut {
      from { opacity: 1; transform: translateY(0) scale(1); }
      to { opacity: 0; transform: translateY(8px) scale(0.96); }
    }
    @keyframes shakeError {
      0%, 100% { transform: translateX(0); }
      20%, 60% { transform: translateX(-6px); }
      40%, 80% { transform: translateX(6px); }
    }

    .tabular { font-variant-numeric: tabular-nums; }
    .mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

    /* Top Header Bar */
    .topbar {
      position: sticky;
      top: 0;
      z-index: 100;
      height: 56px;
      background: var(--bg-glass);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      gap: 16px;
    }

    .topbar-left {
      display: flex;
      align-items: center;
      gap: 20px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      user-select: none;
    }

    .brand-mark {
      width: 28px;
      height: 28px;
      border-radius: 6px;
      background: var(--text-primary);
      color: var(--bg-base);
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .brand-text {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .brand-name {
      font-weight: 700;
      font-size: 14px;
      letter-spacing: -0.02em;
      color: var(--text-primary);
    }

    .brand-tag {
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 600;
      padding: 2px 6px;
      border-radius: 4px;
      background: var(--bg-muted);
      color: var(--text-secondary);
      border: 1px solid var(--border-subtle);
      letter-spacing: 0.04em;
    }

    .nav-tabs {
      display: flex;
      align-items: center;
      gap: 4px;
      padding-left: 12px;
      border-left: 1px solid var(--border-subtle);
    }

    .nav-tab {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 11px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-secondary);
      background: transparent;
      border: 1px solid transparent;
      cursor: pointer;
      transition: all 0.15s ease;
    }

    .nav-tab:hover {
      color: var(--text-primary);
      background: var(--bg-hover);
    }

    .nav-tab.active {
      color: var(--text-primary);
      background: var(--bg-elevated);
      border-color: var(--border-subtle);
      font-weight: 600;
    }

    .topbar-right {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .telemetry-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      height: 30px;
      padding: 0 10px;
      border-radius: 6px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      font-size: 11.5px;
      font-weight: 500;
      color: var(--text-secondary);
    }

    .telemetry-pill.status-live {
      background: var(--status-online-bg);
      border-color: var(--status-online-border);
      color: var(--status-online);
      font-weight: 600;
    }

    .dot-live {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--status-online);
      animation: pulseDot 2s infinite;
    }

    .dot-offline {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--status-danger);
    }

    .icon-btn {
      width: 30px;
      height: 30px;
      border-radius: 6px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      color: var(--text-secondary);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.15s ease;
    }

    .icon-btn:hover {
      color: var(--text-primary);
      border-color: var(--border-strong);
      background: var(--bg-elevated);
    }

    /* Main Container */
    .container {
      max-width: 1440px;
      margin: 0 auto;
      padding: 20px 24px 40px;
    }

    /* KPI Summary Strip (4 Cards) */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 18px;
    }

    .kpi-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 16px 18px;
      box-shadow: var(--shadow-card);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 118px;
      transition: border-color 0.15s ease;
    }

    .kpi-card:hover {
      border-color: var(--border-strong);
    }

    .kpi-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: var(--text-secondary);
      font-size: 11.5px;
      font-weight: 500;
      margin-bottom: 10px;
    }

    .kpi-header-icon {
      color: var(--text-tertiary);
      display: flex;
      align-items: center;
    }

    .kpi-main {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 10px;
    }

    .kpi-value {
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -0.03em;
      color: var(--text-primary);
      line-height: 1.1;
    }

    .kpi-value.key-code {
      font-family: var(--font-mono);
      font-size: 20px;
      letter-spacing: 0.04em;
    }

    .kpi-actions {
      display: flex;
      align-items: center;
      gap: 5px;
    }

    .kpi-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      color: var(--text-tertiary);
      padding-top: 8px;
      border-top: 1px solid var(--border-subtle);
    }

    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      height: 30px;
      padding: 0 12px;
      border-radius: 6px;
      font-family: var(--font-sans);
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.15s ease;
      user-select: none;
      white-space: nowrap;
    }

    .btn:active { transform: scale(0.98); }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }

    .btn-xs {
      height: 24px;
      padding: 0 8px;
      font-size: 11px;
      border-radius: 5px;
      gap: 4px;
    }

    .btn-primary {
      background: var(--accent-primary);
      color: var(--accent-primary-fg);
      font-weight: 600;
    }

    .btn-primary:hover:not(:disabled) {
      background: var(--accent-primary-hover);
    }

    .btn-secondary {
      background: var(--bg-elevated);
      color: var(--text-primary);
      border-color: var(--border-subtle);
    }

    .btn-secondary:hover:not(:disabled) {
      border-color: var(--border-strong);
      background: var(--bg-muted);
    }

    .btn-ghost {
      background: transparent;
      color: var(--text-secondary);
      border-color: transparent;
    }

    .btn-ghost:hover:not(:disabled) {
      color: var(--text-primary);
      background: var(--bg-hover);
    }

    .btn-danger {
      background: var(--status-danger-bg);
      color: var(--status-danger);
      border-color: var(--status-danger-border);
    }

    .btn-danger:hover:not(:disabled) {
      background: var(--status-danger);
      color: #ffffff;
    }

    .btn-success {
      background: var(--status-online-bg);
      color: var(--status-online);
      border-color: var(--status-online-border);
    }

    .btn-success:hover:not(:disabled) {
      background: var(--status-online);
      color: #ffffff;
    }

    /* Section Grid Layout */
    .main-grid {
      display: grid;
      grid-template-columns: 1fr 380px;
      gap: 16px;
      margin-bottom: 16px;
      align-items: start;
    }

    .bottom-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 16px;
      align-items: start;
    }

    /* Panel Card */
    .panel {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      box-shadow: var(--shadow-card);
      overflow: hidden;
    }

    .panel-header {
      padding: 13px 18px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: var(--bg-elevated);
    }

    .panel-title-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .panel-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-primary);
      letter-spacing: -0.01em;
    }

    .panel-subtitle {
      font-size: 11.5px;
      color: var(--text-tertiary);
    }

    .panel-body {
      padding: 18px;
    }

    /* Badges & Pills */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      line-height: 1.4;
      border: 1px solid transparent;
    }

    .badge-neutral {
      background: var(--bg-muted);
      color: var(--text-secondary);
      border-color: var(--border-subtle);
    }

    .badge-online {
      background: var(--status-online-bg);
      color: var(--status-online);
      border-color: var(--status-online-border);
    }

    .badge-warn {
      background: var(--status-warn-bg);
      color: var(--status-warn);
      border-color: var(--status-warn-border);
    }

    .badge-danger {
      background: var(--status-danger-bg);
      color: var(--status-danger);
      border-color: var(--status-danger-border);
    }

    .badge-info {
      background: var(--status-info-bg);
      color: var(--status-info);
      border-color: var(--status-info-border);
    }

    .code-chip {
      font-family: var(--font-mono);
      font-size: 11.5px;
      padding: 2px 7px;
      border-radius: 4px;
      background: var(--bg-muted);
      color: var(--text-primary);
      border: 1px solid var(--border-subtle);
      display: inline-flex;
      align-items: center;
      gap: 5px;
      cursor: pointer;
      transition: border-color 0.15s ease, background 0.15s ease;
    }

    .code-chip:hover {
      border-color: var(--border-strong);
    }

    /* Tables */
    .table-wrap {
      width: 100%;
      overflow-x: auto;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }

    th {
      padding: 9px 14px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-tertiary);
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      white-space: nowrap;
    }

    td {
      padding: 11px 14px;
      border-bottom: 1px solid var(--border-subtle);
      font-size: 12.5px;
      color: var(--text-primary);
      vertical-align: middle;
    }

    tr:last-child td {
      border-bottom: none;
    }

    tbody tr:hover td {
      background: var(--bg-hover);
    }

    .empty-state {
      padding: 36px 20px;
      text-align: center;
      color: var(--text-tertiary);
      font-size: 12.5px;
    }

    /* Forms & Inputs */
    .form-group {
      margin-bottom: 14px;
    }

    .form-label {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11.5px;
      font-weight: 500;
      color: var(--text-secondary);
      margin-bottom: 5px;
    }

    .form-hint {
      font-size: 11px;
      color: var(--text-tertiary);
      margin-top: 4px;
      line-height: 1.4;
    }

    .input-field {
      width: 100%;
      height: 34px;
      padding: 0 11px;
      border-radius: 6px;
      background: var(--bg-base);
      border: 1px solid var(--border-subtle);
      color: var(--text-primary);
      font-family: var(--font-sans);
      font-size: 12.5px;
      outline: none;
      transition: border-color 0.15s ease;
    }

    .input-field.mono {
      font-family: var(--font-mono);
    }

    .input-field:focus {
      border-color: var(--text-secondary);
    }

    .input-row {
      display: flex;
      gap: 6px;
      align-items: center;
    }

    .divider {
      height: 1px;
      background: var(--border-subtle);
      margin: 16px 0;
    }

    /* Manual Ban Bar */
    .manual-ban-bar {
      padding: 12px 14px;
      background: var(--bg-base);
      border-bottom: 1px solid var(--border-subtle);
      display: grid;
      grid-template-columns: 120px 1fr 1fr auto;
      gap: 8px;
      align-items: center;
    }

    /* Progress Bar */
    .meter-bar {
      width: 64px;
      height: 5px;
      background: var(--bg-muted);
      border-radius: 3px;
      overflow: hidden;
      display: inline-block;
      vertical-align: middle;
      margin-left: 6px;
    }

    .meter-fill {
      height: 100%;
      background: var(--text-primary);
      border-radius: 3px;
      transition: width 0.3s ease;
    }

    /* Live Log Console */
    .terminal-box {
      background: var(--terminal-bg);
      color: #d4d4d8;
      font-family: var(--font-mono);
      font-size: 11.5px;
      line-height: 1.65;
      padding: 14px 16px;
      height: 290px;
      overflow-y: auto;
    }

    .log-entry {
      padding: 1px 0;
      word-break: break-all;
      border-bottom: 1px solid rgba(255, 255, 255, 0.02);
    }

    .log-ts { color: #71717a; margin-right: 6px; }
    .log-warn { color: #fbbf24; }
    .log-err { color: #fb7185; }
    .log-ok { color: #34d399; }

    /* Modals & Overlays */
    .overlay {
      position: fixed;
      inset: 0;
      background: rgba(9, 9, 11, 0.78);
      backdrop-filter: blur(6px);
      -webkit-backdrop-filter: blur(6px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 9000;
      padding: 16px;
    }

    .modal-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      width: 100%;
      max-width: 420px;
      padding: 24px;
      box-shadow: var(--shadow-modal);
      animation: modalIn 0.2s var(--ease-out) forwards;
    }

    .modal-card.shake {
      animation: shakeError 0.35s ease;
    }

    .modal-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;
    }

    .modal-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--text-primary);
    }

    .modal-desc {
      font-size: 12.5px;
      color: var(--text-secondary);
      margin-bottom: 18px;
      line-height: 1.5;
    }

    .modal-footer {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 20px;
    }

    /* Toasts */
    #toast-container {
      position: fixed;
      bottom: 20px;
      right: 20px;
      z-index: 9999;
      display: flex;
      flex-direction: column;
      gap: 8px;
      pointer-events: none;
    }

    .toast {
      pointer-events: auto;
      background: var(--bg-surface);
      border: 1px solid var(--border-strong);
      border-radius: 8px;
      padding: 10px 14px;
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--text-primary);
      font-size: 12.5px;
      font-weight: 500;
      box-shadow: var(--shadow-modal);
      animation: toastIn 0.22s var(--ease-out) forwards;
    }

    .toast.hide {
      animation: toastOut 0.2s ease forwards;
    }

    /* Responsive adjustments */
    @media (max-width: 1180px) {
      .kpi-grid { grid-template-columns: repeat(2, 1fr); }
      .main-grid { grid-template-columns: 1fr; }
      .bottom-grid { grid-template-columns: 1fr; }
    }

    @media (max-width: 720px) {
      .topbar { padding: 0 14px; height: auto; py: 10px; flex-wrap: wrap; padding-top: 10px; padding-bottom: 10px; }
      .nav-tabs { display: none; }
      .kpi-grid { grid-template-columns: 1fr; }
      .manual-ban-bar { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>

  <!-- Toast Container -->
  <div id="toast-container"></div>

  <!-- Login Overlay -->
  <div id="login-overlay" class="overlay" style="display: __LOGIN_DISPLAY__; z-index: 9500;">
    <div class="modal-card" id="login-box-el">
      <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 14px;">
        <div class="brand-mark">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <div>
          <div class="modal-title">P2P Tunnel Sunucu Konsolu</div>
          <div style="font-size: 11px; color: var(--text-tertiary);">Yönetici Kimlik Doğrulaması</div>
        </div>
      </div>
      <p class="modal-desc">
        Sunucu yapılandırmasına, canlı tünel oturumlarına ve donanım güvenlik duvarına erişmek için yönetici anahtarını (Admin Secret) girin.
      </p>
      <form id="login-form" onsubmit="handleLogin(event)">
        <div class="form-group">
          <label class="form-label">Yönetici Anahtarı (Admin Secret)</label>
          <input type="password" id="login-password" class="input-field mono" placeholder="••••••••••••••••" required autofocus>
        </div>
        <div id="login-error" style="color: var(--status-danger); font-size: 12px; margin-bottom: 12px; display: none;"></div>
        <button type="submit" class="btn btn-primary" id="btn-login-submit" style="width: 100%; height: 36px;">
          Konsola Bağlan
        </button>
      </form>
    </div>
  </div>

  <!-- Custom Confirmation Modal -->
  <div id="confirm-modal" class="overlay">
    <div class="modal-card">
      <div class="modal-top">
        <span class="modal-title" id="confirm-modal-title">İşlem Onayı</span>
        <button class="icon-btn" onclick="closeConfirmModal(false)" style="width: 24px; height: 24px; border: none;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
      <p class="modal-desc" id="confirm-modal-message"></p>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeConfirmModal(false)">Vazgeç</button>
        <button class="btn btn-danger" id="confirm-modal-btn" onclick="closeConfirmModal(true)">Onayla</button>
      </div>
    </div>
  </div>

  <!-- HWID Ban Modal -->
  <div id="ban-modal" class="overlay">
    <div class="modal-card">
      <div class="modal-top">
        <span class="modal-title">Donanım Kimliğini Yasakla (HWID Ban)</span>
        <button class="icon-btn" onclick="closeBanModal()" style="width: 24px; height: 24px; border: none;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
      <p class="modal-desc">
        Bu işlem cihazın Anakart UUID, MachineGuid ve HWID parmak izini kara listeye ekler ve aktif bağlantısını anında sonlandırır.
      </p>
      <div class="form-group">
        <label class="form-label">Hedef Kullanıcı</label>
        <input type="text" id="ban-user-display" class="input-field" readonly style="opacity: 0.75;">
      </div>
      <div class="form-group">
        <label class="form-label">Donanım Kimliği (HWID)</label>
        <input type="text" id="ban-hwid-display" class="input-field mono" readonly style="opacity: 0.75;">
      </div>
      <div class="form-group">
        <label class="form-label">Yasaklama Sebebi</label>
        <input type="text" id="ban-reason-input" class="input-field" placeholder="Örn: Kural İhlali / Yetkisiz Erişim" value="Yönetici tarafından yasaklandı">
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeBanModal()">Vazgeç</button>
        <button class="btn btn-danger" onclick="confirmBan()">Cihazı Kalıcı Yasakla</button>
      </div>
    </div>
  </div>

  <!-- Top Header Bar -->
  <header class="topbar">
    <div class="topbar-left">
      <div class="brand">
        <div class="brand-mark">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
        </div>
        <div class="brand-text">
          <span class="brand-name" id="header-server-name">P2P Tunnel</span>
          <span class="brand-tag">CONSOLE</span>
        </div>
      </div>

      <nav class="nav-tabs">
        <button class="nav-tab active" onclick="setViewMode('all', this)">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>
          <span>Genel Konsol</span>
        </button>
        <button class="nav-tab" onclick="setViewMode('peers', this)">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          <span>Aktif Bağlantılar</span>
        </button>
        <button class="nav-tab" onclick="setViewMode('security', this)">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/></svg>
          <span>Kara Liste & Geçmiş</span>
        </button>
        <button class="nav-tab" onclick="setViewMode('logs', this)">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>
          <span>Canlı Loglar</span>
        </button>
      </nav>
    </div>

    <div class="topbar-right">
      <div class="telemetry-pill status-live" id="header-status-pill">
        <span class="dot-live"></span>
        <span>Çevrimiçi</span>
      </div>
      <div class="telemetry-pill mono" title="Sunucu Çalışma Süresi (Uptime)">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        <span id="header-uptime">00:00:00</span>
      </div>
      <div class="telemetry-pill mono" title="Yerel UDP Dinleme Portu">
        <span>UDP</span>
        <strong id="header-udp-port" style="color: var(--text-primary);">:25566</strong>
      </div>
      <button class="icon-btn" onclick="toggleTheme()" id="theme-toggle-btn" title="Tema Değiştir (Koyu / Açık)">
        <svg id="theme-icon-sun" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display: none;"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>
        <svg id="theme-icon-moon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>
      </button>
      <button class="icon-btn" onclick="refreshAll()" title="Verileri Şimdi Yenile">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>
      </button>
      <button class="icon-btn" onclick="handleLogout()" title="Oturumu Kapat">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/></svg>
      </button>
    </div>
  </header>

  <main class="container">
    <!-- KPI Summary Strip (4 Cards) -->
    <section class="kpi-grid">
      <!-- KPI 1: Sunucu Bağlantı Kodu -->
      <div class="kpi-card">
        <div class="kpi-header">
          <span>Sunucu Bağlantı Kodu</span>
          <span class="kpi-header-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/></svg>
          </span>
        </div>
        <div class="kpi-main">
          <div class="kpi-value key-code" id="kpi-server-key">----</div>
          <div class="kpi-actions">
            <button class="btn btn-secondary btn-xs" id="btn-copy-key" onclick="copyServerKey()">
              <span id="copy-key-icon">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
              </span>
              <span id="copy-key-text">Kopyala</span>
            </button>
            <button class="btn btn-ghost btn-xs" onclick="regenerateServerKey()" title="Yeni Bağlantı Kodu Üret">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg>
              <span>Yenile</span>
            </button>
          </div>
        </div>
        <div class="kpi-footer">
          <span>STUN Dış Uç Nokta</span>
          <span class="mono" id="kpi-public-endpoint">Çözümleniyor...</span>
        </div>
      </div>

      <!-- KPI 2: Aktif Tünel & Oyuncu -->
      <div class="kpi-card">
        <div class="kpi-header">
          <span>Aktif Tünel & Oyuncu</span>
          <span class="kpi-header-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </span>
        </div>
        <div class="kpi-main">
          <div class="kpi-value tabular" id="stat-clients-count">0</div>
          <span class="badge badge-neutral mono" id="stat-streams-badge">0 TCP Akışı</span>
        </div>
        <div class="kpi-footer">
          <span>İstemci Sürüm Koruması</span>
          <span class="mono" id="kpi-client-version">v2.6</span>
        </div>
      </div>

      <!-- KPI 3: Hedef Servis & Adres -->
      <div class="kpi-card">
        <div class="kpi-header">
          <span>Hedef Servis & Adres</span>
          <span class="kpi-header-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="8" x="2" y="2" rx="2"/><rect width="20" height="8" x="2" y="14" rx="2"/><line x1="6" x2="6.01" y1="6" y2="6"/><line x1="6" x2="6.01" y1="18" y2="18"/></svg>
          </span>
        </div>
        <div class="kpi-main">
          <div class="kpi-value mono" id="kpi-game-port">:25565</div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <span class="badge badge-online" id="stat-mc-status">
              <span class="dot-live"></span> Dinleniyor
            </span>
            <button class="btn btn-ghost btn-xs" onclick="focusSettingsInput()" title="Servis Portu ve Adresi Düzenle">
              Düzenle
            </button>
          </div>
        </div>
        <div class="kpi-footer">
          <span>İstemci Bağlantı Adresi</span>
          <span class="mono" id="kpi-conn-address" style="color: var(--text-primary);">baglanti.localhost</span>
        </div>
      </div>

      <!-- KPI 4: Anlık Trafik & Hız -->
      <div class="kpi-card">
        <div class="kpi-header">
          <span>Anlık Trafik & Sistem Yükü</span>
          <span class="kpi-header-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
          </span>
        </div>
        <div class="kpi-main">
          <div class="mono" style="font-size: 14px; font-weight: 600;">
            <span style="color: var(--status-online);">↓ <span id="kpi-rx-speed">0 KB/s</span></span>
            <span style="color: var(--text-tertiary); margin: 0 4px;">/</span>
            <span style="color: var(--status-info);">↑ <span id="kpi-tx-speed">0 KB/s</span></span>
          </div>
          <span class="badge badge-neutral mono" id="kpi-total-traffic">0 MB</span>
        </div>
        <div class="kpi-footer">
          <span>
            CPU: <strong class="mono" id="stat-cpu" style="color: var(--text-primary);">0%</strong>
            <span class="meter-bar"><span class="meter-fill" id="cpu-meter-fill" style="width: 0%;"></span></span>
          </span>
          <span>
            RAM: <strong class="mono" id="stat-ram" style="color: var(--text-primary);">0%</strong>
            <span class="mono" id="stat-ram-sub" style="display: none;"></span>
          </span>
        </div>
      </div>
    </section>

    <!-- Main Grid: Live Peers + Settings Card -->
    <div class="main-grid" id="section-main-grid">
      <!-- Live Peers Table -->
      <section class="panel" id="panel-live-peers">
        <div class="panel-header">
          <div class="panel-title-wrap">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            <h2 class="panel-title">Aktif Bağlantılar (Canlı Tünel Oturumları)</h2>
            <span class="badge badge-neutral mono" id="clients-table-count">0 bağlı</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <input type="text" id="peer-search-input" class="input-field" placeholder="Kullanıcı, IP veya HWID filtrele..." oninput="renderClientsTable()" style="height: 28px; width: 210px; font-size: 11.5px;">
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Kullanıcı / Rol</th>
                <th>Cihaz</th>
                <th>Dış IP:Port</th>
                <th>Donanım Kimliği (HWID)</th>
                <th>Ping / Akış</th>
                <th>Trafik / Süre</th>
                <th style="text-align: right;">İşlem</th>
              </tr>
            </thead>
            <tbody id="clients-tbody">
              <tr><td colspan="7" class="empty-state">Şu anda aktif tünel bağlantısı bulunmuyor.</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Tunnel & Service Configuration Card -->
      <section class="panel" id="panel-settings">
        <div class="panel-header">
          <div class="panel-title-wrap">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            <h2 class="panel-title">Tünel & Servis Yapılandırması</h2>
          </div>
        </div>
        <div class="panel-body">
          <form onsubmit="handleSaveSettings(event)">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
              <div class="form-group">
                <label class="form-label">Sunucu Adı</label>
                <input type="text" id="setting-server-name" class="input-field" placeholder="P2P Oyun Sunucusu" required>
              </div>
              <div class="form-group">
                <label class="form-label">Bağlantı Kodu</label>
                <input type="text" id="setting-server-key" class="input-field mono" placeholder="XXXX-YYYY" required>
              </div>
            </div>

            <div style="display: grid; grid-template-columns: 120px 1fr; gap: 10px;">
              <div class="form-group">
                <label class="form-label">Servis Portu</label>
                <input type="number" id="setting-game-port" class="input-field mono" value="25565" min="1" max="65535" required>
              </div>
              <div class="form-group">
                <label class="form-label">İstemci Bağlantı Adresi</label>
                <input type="text" id="setting-connection-address" class="input-field mono" value="baglanti.localhost" placeholder="baglanti.localhost" required>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">
                <span>Yönetici Şifresi (Admin Secret)</span>
                <span style="font-size: 10.5px; color: var(--text-tertiary);">Panel & Admin Tüneli</span>
              </label>
              <div class="input-row">
                <input type="password" id="setting-admin-secret" class="input-field mono" placeholder="Değiştirmek için yeni şifre girin">
                <button type="button" class="btn btn-secondary" onclick="togglePasswordVisibility('setting-admin-secret')" title="Göster / Gizle" style="height: 34px; padding: 0 10px;">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                </button>
              </div>
            </div>

            <div class="form-group" style="margin-bottom: 16px;">
              <label class="form-label">İstemci Sürüm Koruması (Cloudflare R2)</label>
              <div class="input-row">
                <input type="text" id="setting-client-version" class="input-field mono" value="Yükleniyor..." readonly style="opacity: 0.8;">
                <button type="button" class="btn btn-secondary" onclick="refreshVersionFromR2()" style="height: 34px;">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg>
                  <span>R2 Senkronize</span>
                </button>
              </div>
            </div>

            <button type="submit" class="btn btn-primary" id="btn-save-settings" style="width: 100%; height: 34px;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="20 6 9 17 4 12"/></svg>
              <span>Yapılandırmayı Kaydet</span>
            </button>
          </form>
        </div>
      </section>
    </div>

    <!-- Bottom Grid (2 Columns: HWID Blacklist & Connection History) -->
    <div class="bottom-grid" id="section-security-grid">
      <!-- Column 1: Yasaklı Cihazlar (HWID Kara Listesi) -->
      <section class="panel" id="panel-bans">
        <div class="panel-header">
          <div class="panel-title-wrap">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/></svg>
            <h2 class="panel-title">Yasaklı Cihazlar (HWID Kara Listesi)</h2>
            <span class="badge badge-danger mono" id="bans-table-count">0 kayıt</span>
          </div>
        </div>
        <!-- Manual HWID Ban Quick Row -->
        <form class="manual-ban-bar" onsubmit="handleManualBan(event)">
          <input type="text" id="manual-ban-user" class="input-field" placeholder="Kullanıcı (İsteğe bağlı)" style="height: 28px; font-size: 11.5px;">
          <input type="text" id="manual-ban-hwid" class="input-field mono" placeholder="HWID veya Anakart UUID girin..." required style="height: 28px; font-size: 11.5px;">
          <input type="text" id="manual-ban-reason" class="input-field" placeholder="Yasaklama sebebi..." style="height: 28px; font-size: 11.5px;">
          <button type="submit" class="btn btn-danger btn-xs" style="height: 28px; padding: 0 10px;">
            Yasakla
          </button>
        </form>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Kullanıcı</th>
                <th>Donanım Kimliği (HWID)</th>
                <th>Sebep</th>
                <th>Tarih</th>
                <th style="text-align: right;">İşlem</th>
              </tr>
            </thead>
            <tbody id="bans-tbody">
              <tr><td colspan="5" class="empty-state">Kara listede yasaklı cihaz bulunmuyor.</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Column 2: Bağlantı Geçmişi (Son Oturumlar) -->
      <section class="panel" id="panel-history">
        <div class="panel-header">
          <div class="panel-title-wrap">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/></svg>
            <h2 class="panel-title">Bağlantı Geçmişi (Son Oturumlar)</h2>
            <span class="badge badge-neutral mono" id="history-table-count">0 kayıt</span>
          </div>
          <button class="btn btn-secondary btn-xs" onclick="clearConnectionHistory()">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            <span>Geçmişi Temizle</span>
          </button>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Kullanıcı & Durum</th>
                <th>HWID / Cihaz</th>
                <th>Son IP</th>
                <th>Son Görülme</th>
                <th style="text-align: right;">İşlem</th>
              </tr>
            </thead>
            <tbody id="history-tbody">
              <tr><td colspan="5" class="empty-state">Geçmiş bağlantı kaydı bulunmuyor.</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <!-- Live Server Console Logs -->
    <section class="panel" id="panel-logs">
      <div class="panel-header">
        <div class="panel-title-wrap">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>
          <h2 class="panel-title">Canlı Sunucu Log Akışı</h2>
          <span class="panel-subtitle">Gerçek zamanlı KCP / UDP / Kimlik doğrulama olayları</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <input type="text" id="log-filter-input" class="input-field" placeholder="Loglarda ara..." oninput="renderLogsView()" style="height: 26px; width: 180px; font-size: 11px;">
          <button class="btn btn-secondary btn-xs" onclick="clearConsoleView()">Görünümü Temizle</button>
        </div>
      </div>
      <div class="terminal-box" id="console-stream">
        <div class="log-entry">Sunucu telemetri akışı başlatılıyor...</div>
      </div>
    </section>

    <!-- Hidden compatibility input for legacy copyServerKey -->
    <input type="hidden" id="dash-server-key" value="">
  </main>

  <script>
    let cachedClients = [];
    let cachedHistory = [];
    let cachedLogs = [];
    let targetBanClient = null;
    let confirmResolver = null;
    let serverUptimeSec = 0;

    // 1. Theme Initialization & Toggle (Saved in localStorage)
    function initTheme() {
      const saved = localStorage.getItem('p2p_console_theme') || 'dark';
      applyTheme(saved);
    }

    function applyTheme(theme) {
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('p2p_console_theme', theme);
      const sun = document.getElementById('theme-icon-sun');
      const moon = document.getElementById('theme-icon-moon');
      if (sun && moon) {
        if (theme === 'dark') {
          sun.style.display = 'block';
          moon.style.display = 'none';
        } else {
          sun.style.display = 'none';
          moon.style.display = 'block';
        }
      }
    }

    function toggleTheme() {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      applyTheme(current === 'dark' ? 'light' : 'dark');
    }

    initTheme();

    // 2. View Mode Filter (All / Peers / Security / Logs)
    function setViewMode(mode, btnEl) {
      document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
      if (btnEl) btnEl.classList.add('active');

      const mainGrid = document.getElementById('section-main-grid');
      const secGrid = document.getElementById('section-security-grid');
      const logsPanel = document.getElementById('panel-logs');

      if (mode === 'all') {
        mainGrid.style.display = 'grid';
        secGrid.style.display = 'grid';
        logsPanel.style.display = 'block';
      } else if (mode === 'peers') {
        mainGrid.style.display = 'grid';
        secGrid.style.display = 'none';
        logsPanel.style.display = 'none';
      } else if (mode === 'security') {
        mainGrid.style.display = 'none';
        secGrid.style.display = 'grid';
        logsPanel.style.display = 'none';
      } else if (mode === 'logs') {
        mainGrid.style.display = 'none';
        secGrid.style.display = 'none';
        logsPanel.style.display = 'block';
      }
    }

    // 3. Formatting Helpers
    function escapeHtml(str) {
      return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function formatBytes(bytes) {
      const b = Number(bytes) || 0;
      if (b < 1024) return b + ' B';
      if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB';
      if (b < 1024 * 1024 * 1024) return (b / (1024 * 1024)).toFixed(2) + ' MB';
      return (b / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
    }

    function formatRate(bytesPerSec) {
      const bps = Number(bytesPerSec) || 0;
      if (bps < 1024) return bps.toFixed(0) + ' B/s';
      if (bps < 1024 * 1024) return (bps / 1024).toFixed(1) + ' KB/s';
      return (bps / (1024 * 1024)).toFixed(2) + ' MB/s';
    }

    function formatDuration(sec) {
      const s = Math.max(0, Math.floor(Number(sec) || 0));
      const hrs = Math.floor(s / 3600);
      const mins = Math.floor((s % 3600) / 60);
      const rem = s % 60;
      if (hrs > 0) return `${hrs}sa ${mins}dk`;
      if (mins > 0) return `${mins}dk ${rem}sn`;
      return `${rem}sn`;
    }

    function formatUptimeClock(sec) {
      const s = Math.max(0, Math.floor(Number(sec) || 0));
      const hrs = String(Math.floor(s / 3600)).padStart(2, '0');
      const mins = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
      const rem = String(s % 60).padStart(2, '0');
      return `${hrs}:${mins}:${rem}`;
    }

    function normalizeKeyDisplay(key) {
      let clean = String(key || '').trim().toUpperCase();
      if (clean.startsWith('MC-')) clean = clean.slice(3);
      return clean || '----';
    }

    // 4. Toast Notification System
    function showToast(message, type = 'success') {
      const container = document.getElementById('toast-container');
      const toast = document.createElement('div');
      toast.className = 'toast';

      let color = 'var(--status-online)';
      let icon = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="20 6 9 17 4 12"/></svg>';
      if (type === 'error') {
        color = 'var(--status-danger)';
        icon = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
      } else if (type === 'info') {
        color = 'var(--text-secondary)';
        icon = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>';
      }

      toast.innerHTML = `<span style="color:${color};display:flex;">${icon}</span><span>${escapeHtml(message)}</span>`;
      container.appendChild(toast);

      setTimeout(() => {
        toast.classList.add('hide');
        setTimeout(() => toast.remove(), 220);
      }, 3000);
    }

    function copyText(text, label = 'Değer') {
      if (!text || text === 'N/A' || text === '-') return;
      navigator.clipboard.writeText(text);
      showToast(`${label} panoya kopyalandı: ${text}`, 'success');
    }

    // 5. Custom Confirm Modal
    function showConfirmModal(title, message, confirmBtnText = 'Onayla', isDanger = true) {
      return new Promise((resolve) => {
        confirmResolver = resolve;
        document.getElementById('confirm-modal-title').innerText = title;
        document.getElementById('confirm-modal-message').innerHTML = message;
        const btn = document.getElementById('confirm-modal-btn');
        btn.innerText = confirmBtnText;
        btn.className = isDanger ? 'btn btn-danger' : 'btn btn-primary';
        document.getElementById('confirm-modal').style.display = 'flex';
      });
    }

    function closeConfirmModal(result) {
      document.getElementById('confirm-modal').style.display = 'none';
      if (confirmResolver) {
        confirmResolver(result);
        confirmResolver = null;
      }
    }

    // 6. Auth Login & Logout
    async function handleLogin(e) {
      e.preventDefault();
      const pwd = document.getElementById('login-password').value;
      const errEl = document.getElementById('login-error');
      const box = document.getElementById('login-box-el');
      errEl.style.display = 'none';

      try {
        const res = await fetch('/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: pwd })
        });
        const data = await res.json();
        if (data.success) {
          document.getElementById('login-overlay').style.display = 'none';
          showToast('Yönetici oturumu açıldı.', 'success');
          refreshAll(true);
        } else {
          box.classList.remove('shake');
          void box.offsetWidth;
          box.classList.add('shake');
          errEl.innerText = data.message || 'Yönetici anahtarı hatalı.';
          errEl.style.display = 'block';
        }
      } catch (err) {
        errEl.innerText = 'Sunucu ile iletişim kurulamadı.';
        errEl.style.display = 'block';
      }
    }

    async function handleLogout() {
      const ok = await showConfirmModal(
        'Oturumu Kapat',
        'Yönetici konsolu oturumunu sonlandırmak istediğinize emin misiniz?',
        'Çıkış Yap',
        false
      );
      if (ok) {
        await fetch('/api/logout', { method: 'POST' });
        location.reload();
      }
    }

    // 7. Data Loaders
    async function loadStatus() {
      try {
        const res = await fetch('/api/status');
        if (res.status === 401) {
          document.getElementById('login-overlay').style.display = 'flex';
          return;
        }
        const data = await res.json();

        const normKey = normalizeKeyDisplay(data.server_key);
        document.getElementById('kpi-server-key').innerText = normKey;
        document.getElementById('dash-server-key').value = normKey;
        document.getElementById('header-server-name').innerText = data.server_name || 'P2P Tunnel';
        document.getElementById('header-udp-port').innerText = ':' + (data.udp_port || 25566);

        serverUptimeSec = Number(data.server_uptime) || 0;
        document.getElementById('header-uptime').innerText = formatUptimeClock(serverUptimeSec);

        const pubEp = Array.isArray(data.public_endpoint)
          ? `${data.public_endpoint[0]}:${data.public_endpoint[1]}`
          : (data.public_endpoint || 'Yerel Ağ');
        document.getElementById('kpi-public-endpoint').innerText = pubEp;

        document.getElementById('stat-clients-count').innerText = data.connected_clients ?? 0;
        document.getElementById('stat-streams-badge').innerText = `${data.active_streams ?? 0} TCP Akışı`;
        document.getElementById('kpi-client-version').innerText = 'v' + (data.required_client_version || '2.6');

        const gPort = data.game_port || 25565;
        document.getElementById('kpi-game-port').innerText = ':' + gPort;
        document.getElementById('kpi-conn-address').innerText = data.connection_address || 'baglanti.localhost';

        const mcStatusEl = document.getElementById('stat-mc-status');
        if (data.game_port_active) {
          mcStatusEl.className = 'badge badge-online';
          mcStatusEl.innerHTML = `<span class="dot-live"></span> Aktif (${gPort})`;
        } else {
          mcStatusEl.className = 'badge badge-danger';
          mcStatusEl.innerHTML = `<span class="dot-offline"></span> Kapalı (${gPort})`;
        }

        document.getElementById('kpi-rx-speed').innerText = formatRate(data.rx_speed_bps || 0);
        document.getElementById('kpi-tx-speed').innerText = formatRate(data.tx_speed_bps || 0);
        const totalBytes = (Number(data.total_rx_bytes) || 0) + (Number(data.total_tx_bytes) || 0);
        document.getElementById('kpi-total-traffic').innerText = formatBytes(totalBytes);

        const cpuPct = Math.round(Number(data.cpu_percent) || 0);
        const ramPct = Math.round(Number(data.ram_percent) || 0);
        document.getElementById('stat-cpu').innerText = cpuPct + '%';
        document.getElementById('cpu-meter-fill').style.width = Math.min(100, cpuPct) + '%';
        document.getElementById('stat-ram').innerText = `${ramPct}% (${data.ram_used_mb || 0}MB)`;
        document.getElementById('stat-ram-sub').innerText = `${data.ram_used_mb || 0} MB / ${data.ram_total_mb || 0} MB`;
      } catch (e) {}
    }

    async function loadClients() {
      try {
        const res = await fetch('/api/clients');
        if (res.status === 401) return;
        const data = await res.json();
        cachedClients = data.clients || [];
        cachedHistory = data.history || [];
        renderClientsTable();
        renderHistoryTable();
      } catch (e) {}
    }

    function renderClientsTable() {
      const tbody = document.getElementById('clients-tbody');
      const countEl = document.getElementById('clients-table-count');
      const filter = (document.getElementById('peer-search-input')?.value || '').trim().toLowerCase();

      const filtered = cachedClients.filter(c => {
        if (!filter) return true;
        return (
          (c.username || '').toLowerCase().includes(filter) ||
          (c.peer_addr || '').toLowerCase().includes(filter) ||
          (c.hwid || '').toLowerCase().includes(filter) ||
          (c.computer_name || '').toLowerCase().includes(filter)
        );
      });

      countEl.innerText = `${cachedClients.length} bağlı`;

      if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Aktif tünel bağlantısı bulunmuyor.</td></tr>';
        return;
      }

      tbody.innerHTML = filtered.map(c => {
        const isAdmin = c.role === 'ADMIN';
        const roleBadge = isAdmin
          ? '<span class="badge badge-info">YÖNETİCİ</span>'
          : '<span class="badge badge-neutral">OYUNCU</span>';
        const verStr = c.version && !c.version.includes('Eski') ? `v${escapeHtml(c.version)}` : 'Eski';
        const hwidFull = c.hwid || 'N/A';
        const hwidShort = hwidFull.length > 18 ? hwidFull.slice(0, 16) + '…' : hwidFull;

        const pingVal = Number(c.ping_ms) || 0;
        const pingClass = pingVal < 65 ? 'badge-online' : (pingVal < 140 ? 'badge-warn' : 'badge-danger');
        const streamsCount = Number(c.active_streams) || 0;
        const trafficStr = `↓${formatBytes(c.bytes_received || 0)} ↑${formatBytes(c.bytes_sent || 0)}`;

        const detailsSafe = escapeHtml(JSON.stringify(c.hwid_details || {}));
        const userSafe = escapeHtml(c.username || 'Bilinmeyen');
        const addrSafe = escapeHtml(c.peer_addr || '');
        const hwidSafe = escapeHtml(hwidFull);

        return `<tr>
          <td>
            <div style="display:flex;align-items:center;gap:6px;">
              <strong style="font-weight:600;">${userSafe}</strong>
              ${roleBadge}
              <span class="mono" style="font-size:10.5px;color:var(--text-tertiary);">${verStr}</span>
            </div>
          </td>
          <td>
            <div style="font-size:12px;">${escapeHtml(c.computer_name || '-')}</div>
            <div style="font-size:10.5px;color:var(--text-tertiary);">${escapeHtml(c.os || '')}</div>
          </td>
          <td>
            <span class="code-chip" onclick="copyText('${addrSafe}', 'IP Adresi')" title="Kopyalamak için tıklayın">
              ${addrSafe}
            </span>
          </td>
          <td>
            <span class="code-chip" onclick="copyText('${hwidSafe}', 'HWID')" title="${hwidSafe} (Kopyalamak için tıklayın)">
              ${escapeHtml(hwidShort)}
            </span>
          </td>
          <td>
            <span class="badge ${pingClass} mono">${pingVal.toFixed(1)} ms</span>
            <span class="mono" style="font-size:11px;color:var(--text-secondary);margin-left:5px;">${streamsCount} akış</span>
          </td>
          <td>
            <div class="mono" style="font-size:11.5px;">${trafficStr}</div>
            <div class="mono" style="font-size:10.5px;color:var(--text-tertiary);">${formatDuration(c.duration_seconds)}</div>
          </td>
          <td style="text-align:right;">
            <div style="display:inline-flex;gap:5px;">
              <button class="btn btn-secondary btn-xs" onclick="kickClient('${addrSafe}', '${userSafe}')">At</button>
              <button class="btn btn-danger btn-xs" onclick="openBanModal('${userSafe}', '${hwidSafe}', '${addrSafe}', ${detailsSafe})">Yasakla</button>
            </div>
          </td>
        </tr>`;
      }).join('');
    }

    function renderHistoryTable() {
      const tbody = document.getElementById('history-tbody');
      const countEl = document.getElementById('history-table-count');
      countEl.innerText = `${cachedHistory.length} kayıt`;

      if (cachedHistory.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Geçmiş bağlantı kaydı bulunmuyor.</td></tr>';
        return;
      }

      tbody.innerHTML = cachedHistory.map(h => {
        const isOnline = Boolean(h.is_online);
        const statusBadge = isOnline
          ? '<span class="badge badge-online"><span class="dot-live"></span> Aktif</span>'
          : '<span class="badge badge-neutral">Ayrıldı</span>';

        const hwidFull = h.hwid || 'N/A';
        const hwidShort = hwidFull.length > 16 ? hwidFull.slice(0, 14) + '…' : hwidFull;
        const userSafe = escapeHtml(h.username || 'Bilinmeyen');
        const hwidSafe = escapeHtml(hwidFull);
        const addrSafe = escapeHtml(h.peer_addr || '');
        const detailsSafe = escapeHtml(JSON.stringify(h.hwid_details || {}));

        const actionHtml = h.is_banned
          ? '<span class="badge badge-danger">YASAKLI</span>'
          : `<button class="btn btn-danger btn-xs" onclick="openBanModal('${userSafe}', '${hwidSafe}', '${addrSafe}', ${detailsSafe})">Yasakla</button>`;

        return `<tr>
          <td>
            <div style="display:flex;align-items:center;gap:6px;">
              <strong style="font-weight:600;">${userSafe}</strong>
              ${statusBadge}
            </div>
            <div style="font-size:10.5px;color:var(--text-tertiary);">${escapeHtml(h.computer_name || '-')} • ${h.login_count || 1} giriş</div>
          </td>
          <td>
            <span class="code-chip" onclick="copyText('${hwidSafe}', 'HWID')" title="${hwidSafe}">
              ${escapeHtml(hwidShort)}
            </span>
          </td>
          <td class="mono" style="font-size:11.5px;color:var(--text-secondary);">${escapeHtml(h.ip || '-')}</td>
          <td class="mono" style="font-size:11px;color:var(--text-tertiary);">${escapeHtml(h.last_seen || '-')}</td>
          <td style="text-align:right;">${actionHtml}</td>
        </tr>`;
      }).join('');
    }

    async function loadBans() {
      try {
        const res = await fetch('/api/bans');
        if (res.status === 401) return;
        const data = await res.json();
        const bans = data.bans || [];
        const tbody = document.getElementById('bans-tbody');
        document.getElementById('bans-table-count').innerText = `${bans.length} kayıt`;

        if (bans.length === 0) {
          tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Kara listede yasaklı cihaz bulunmuyor.</td></tr>';
          return;
        }

        tbody.innerHTML = bans.map(b => {
          const hwidFull = b.hwid || '-';
          const hwidShort = hwidFull.length > 16 ? hwidFull.slice(0, 14) + '…' : hwidFull;
          const userSafe = escapeHtml(b.username || 'Bilinmeyen');
          const hwidSafe = escapeHtml(hwidFull);
          const idSafe = escapeHtml(b.id || hwidFull);

          return `<tr>
            <td><strong>${userSafe}</strong></td>
            <td>
              <span class="code-chip" onclick="copyText('${hwidSafe}', 'HWID')" title="${hwidSafe}">
                ${escapeHtml(hwidShort)}
              </span>
            </td>
            <td style="color:var(--text-secondary);font-size:12px;">${escapeHtml(b.reason || '-')}</td>
            <td class="mono" style="color:var(--text-tertiary);font-size:11px;">${escapeHtml(b.banned_at || '-')}</td>
            <td style="text-align:right;">
              <button class="btn btn-success btn-xs" onclick="unbanClient('${idSafe}', '${userSafe}')">Yasağı Kaldır</button>
            </td>
          </tr>`;
        }).join('');
      } catch (e) {}
    }

    async function loadLogs() {
      try {
        const res = await fetch('/api/logs');
        if (res.status === 401) return;
        const data = await res.json();
        cachedLogs = data.logs || [];
        renderLogsView();
      } catch (e) {}
    }

    function renderLogsView() {
      const box = document.getElementById('console-stream');
      const filter = (document.getElementById('log-filter-input')?.value || '').trim().toLowerCase();
      const isAtBottom = (box.scrollHeight - box.scrollTop - box.clientHeight) < 60;

      const list = cachedLogs.filter(l => !filter || l.toLowerCase().includes(filter));
      if (list.length === 0) {
        box.innerHTML = '<div class="log-entry" style="color:#71717a;">Kayıtlı konsol logu bulunamadı.</div>';
        return;
      }

      box.innerHTML = list.map(line => {
        const safe = escapeHtml(line);
        let cls = '';
        if (line.includes('hatası') || line.includes('reddedildi') || line.includes('CRASH') || line.includes('FAIL')) {
          cls = 'log-err';
        } else if (line.includes('atıldı') || line.includes('yasaklandı') || line.includes('uyarı') || line.includes('zaman aşımı')) {
          cls = 'log-warn';
        } else if (line.includes('bağlandı') || line.includes('hazır') || line.includes('güncellendi')) {
          cls = 'log-ok';
        }
        return `<div class="log-entry ${cls}">${safe}</div>`;
      }).join('');

      if (isAtBottom) {
        box.scrollTop = box.scrollHeight;
      }
    }

    function clearConsoleView() {
      cachedLogs = [];
      document.getElementById('console-stream').innerHTML = '<div class="log-entry" style="color:#71717a;">Konsol görünümü temizlendi.</div>';
      showToast('Konsol ekranı temizlendi.', 'info');
    }

    async function loadSettings() {
      try {
        const res = await fetch('/api/settings');
        if (res.status === 401) return;
        const data = await res.json();
        if (data.server_name) document.getElementById('setting-server-name').value = data.server_name;
        if (data.server_key) document.getElementById('setting-server-key').value = normalizeKeyDisplay(data.server_key);
        if (data.game_port) document.getElementById('setting-game-port').value = data.game_port;
        if (data.connection_address) document.getElementById('setting-connection-address').value = data.connection_address;
        if (data.admin_secret) document.getElementById('setting-admin-secret').value = data.admin_secret;
        if (data.required_client_version) {
          document.getElementById('setting-client-version').value = `v${data.required_client_version} (R2 Aktif)`;
        }
      } catch (e) {}
    }

    // 8. Interactive Actions
    function copyServerKey() {
      const key = document.getElementById('kpi-server-key').innerText.trim();
      if (!key || key === '----') return;
      navigator.clipboard.writeText(key);
      const txtEl = document.getElementById('copy-key-text');
      txtEl.innerText = 'Kopyalandı';
      showToast(`Sunucu bağlantı kodu kopyalandı: ${key}`, 'success');
      setTimeout(() => { txtEl.innerText = 'Kopyala'; }, 1800);
    }

    async function regenerateServerKey() {
      const ok = await showConfirmModal(
        'Sunucu Bağlantı Kodunu Yenile',
        'Yeni bir <b>XXXX-YYYY</b> sunucu anahtarı üretilecek ve oda şifreleme anahtarları yenilenecektir. Onaylıyor musunuz?',
        'Anahtarı Yenile',
        true
      );
      if (!ok) return;

      try {
        const res = await fetch('/api/regenerate_key', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          const clean = normalizeKeyDisplay(data.server_key);
          document.getElementById('kpi-server-key').innerText = clean;
          document.getElementById('setting-server-key').value = clean;
          showToast(data.message || 'Sunucu anahtarı yenilendi.', 'success');
          loadStatus();
        } else {
          showToast(data.message || 'Anahtar yenilenemedi.', 'error');
        }
      } catch (e) {
        showToast('İstek sırasında hata oluştu.', 'error');
      }
    }

    function focusSettingsInput() {
      const el = document.getElementById('setting-game-port');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.focus();
        el.select();
      }
    }

    async function handleSaveSettings(e) {
      e.preventDefault();
      const sName = document.getElementById('setting-server-name').value.trim();
      const sKey = normalizeKeyDisplay(document.getElementById('setting-server-key').value);
      const sPort = parseInt(document.getElementById('setting-game-port').value, 10) || 25565;
      const sAddr = document.getElementById('setting-connection-address').value.trim();
      const sAdmin = document.getElementById('setting-admin-secret').value.trim();

      const btn = document.getElementById('btn-save-settings');
      btn.disabled = true;

      try {
        const res = await fetch('/api/update_settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            server_name: sName,
            server_key: sKey,
            game_port: sPort,
            connection_address: sAddr,
            admin_secret: sAdmin
          })
        });
        const data = await res.json();
        if (data.success) {
          showToast(data.message || 'Yapılandırma kaydedildi.', 'success');
          await loadStatus();
          await loadSettings();
        } else {
          showToast(data.message || 'Ayarlar kaydedilemedi.', 'error');
        }
      } catch (err) {
        showToast('Sunucu bağlantı hatası.', 'error');
      } finally {
        btn.disabled = false;
      }
    }

    async function refreshVersionFromR2() {
      const field = document.getElementById('setting-client-version');
      field.value = 'R2 sorgulanıyor...';
      try {
        const res = await fetch('/api/version/refresh', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          field.value = `v${data.version} (R2 Senkronize)`;
          document.getElementById('kpi-client-version').innerText = `v${data.version}`;
          showToast(`İstemci sürüm koruması güncellendi: v${data.version}`, 'success');
        } else {
          showToast(data.message || 'Sürüm sorgulanamadı.', 'error');
        }
      } catch (e) {
        showToast('Bağlantı hatası.', 'error');
      }
    }

    function togglePasswordVisibility(id) {
      const el = document.getElementById(id);
      if (el) el.type = el.type === 'password' ? 'text' : 'password';
    }

    async function kickClient(peerAddr, username) {
      const ok = await showConfirmModal(
        'Bağlantıyı Sonlandır (Kick)',
        `<b>${escapeHtml(username)}</b> (<code class="mono">${escapeHtml(peerAddr)}</code>) adlı istemcinin tünel bağlantısını kesmek istiyor musunuz?`,
        'Bağlantıyı Kes',
        true
      );
      if (!ok) return;

      try {
        const res = await fetch('/api/kick', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ peer_addr: peerAddr })
        });
        const data = await res.json();
        if (data.success) {
          showToast(data.message || 'İstemci bağlantısı kesildi.', 'success');
          loadClients();
          loadStatus();
        } else {
          showToast(data.message || 'İstemci bulunamadı.', 'error');
        }
      } catch (e) {
        showToast('İşlem başarısız.', 'error');
      }
    }

    function openBanModal(username, hwid, peerAddr, details) {
      targetBanClient = { username, hwid, peerAddr, details: details || {} };
      document.getElementById('ban-user-display').value = username || 'Bilinmeyen';
      document.getElementById('ban-hwid-display').value = hwid || 'N/A';
      document.getElementById('ban-reason-input').value = 'Yönetici tarafından yasaklandı';
      document.getElementById('ban-modal').style.display = 'flex';
    }

    function closeBanModal() {
      document.getElementById('ban-modal').style.display = 'none';
      targetBanClient = null;
    }

    async function confirmBan() {
      if (!targetBanClient) return;
      const reason = document.getElementById('ban-reason-input').value.trim() || 'Yönetici tarafından yasaklandı';
      try {
        const res = await fetch('/api/ban', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: targetBanClient.username,
            hwid: targetBanClient.hwid,
            peer_addr: targetBanClient.peerAddr,
            hwid_details: targetBanClient.details,
            reason: reason
          })
        });
        const data = await res.json();
        closeBanModal();
        if (data.success) {
          showToast(data.message || 'Cihaz kalıcı olarak yasaklandı.', 'success');
          loadClients();
          loadBans();
          loadStatus();
        } else {
          showToast(data.message || 'Yasaklama işlemi başarısız.', 'error');
        }
      } catch (e) {
        showToast('Bağlantı hatası.', 'error');
      }
    }

    async function handleManualBan(e) {
      e.preventDefault();
      const user = document.getElementById('manual-ban-user').value.trim() || 'Manuel Kayıt';
      const hwid = document.getElementById('manual-ban-hwid').value.trim().toUpperCase();
      const reason = document.getElementById('manual-ban-reason').value.trim() || 'Manuel HWID Yasağı';
      if (!hwid) return;

      try {
        const res = await fetch('/api/ban', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: user, hwid: hwid, reason: reason })
        });
        const data = await res.json();
        if (data.success) {
          document.getElementById('manual-ban-user').value = '';
          document.getElementById('manual-ban-hwid').value = '';
          document.getElementById('manual-ban-reason').value = '';
          showToast(`${hwid} kara listeye eklendi.`, 'success');
          loadBans();
          loadClients();
        } else {
          showToast(data.message || 'Yasaklanamadı.', 'error');
        }
      } catch (err) {
        showToast('İstek başarısız.', 'error');
      }
    }

    async function unbanClient(banId, label) {
      const ok = await showConfirmModal(
        'Donanım Yasağını Kaldır',
        `<b>${escapeHtml(label)}</b> için uygulanan HWID yasağını kaldırmak istiyor musunuz?`,
        'Yasağı Kaldır',
        false
      );
      if (!ok) return;

      try {
        const res = await fetch('/api/unban', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: banId })
        });
        const data = await res.json();
        if (data.success) {
          showToast(data.message || 'Yasak kaldırıldı.', 'success');
          loadBans();
          loadClients();
        } else {
          showToast(data.message || 'Yasak kaldırılamadı.', 'error');
        }
      } catch (e) {
        showToast('İşlem başarısız.', 'error');
      }
    }

    async function clearConnectionHistory() {
      const ok = await showConfirmModal(
        'Bağlantı Geçmişini Temizle',
        'Tüm geçmiş oturum kayıtlarını kalıcı olarak temizlemek istiyor musunuz? (Aktif yasaklar etkilenmez)',
        'Geçmişi Temizle',
        true
      );
      if (!ok) return;

      try {
        const res = await fetch('/api/clear_history', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          showToast(data.message || 'Bağlantı geçmişi temizlendi.', 'success');
          loadClients();
        } else {
          showToast(data.message || 'Geçmiş temizlenemedi.', 'error');
        }
      } catch (e) {
        showToast('İstek başarısız.', 'error');
      }
    }

    async function refreshAll(includeSettings = false) {
      await Promise.all([
        loadStatus(),
        loadClients(),
        loadBans(),
        loadLogs()
      ]);
      if (includeSettings) {
        await loadSettings();
      }
    }

    // Live 1s Uptime Ticker + 2.5s Telemetry Polling
    setInterval(() => {
      if (serverUptimeSec > 0) {
        serverUptimeSec += 1;
        const el = document.getElementById('header-uptime');
        if (el) el.innerText = formatUptimeClock(serverUptimeSec);
      }
    }, 1000);

    setInterval(() => {
      refreshAll(false);
    }, 2500);

    refreshAll(true);
  </script>
</body>
</html>"""


MAZIPANEL_MANAGED_HTML = """<!DOCTYPE html>
<html lang="tr" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>P2P Tunnel — maziPanel Tarafından Yönetiliyor</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #09090b;
      --bg-surface: #121215;
      --bg-elevated: #18181c;
      --border-subtle: #27272a;
      --border-strong: #3f3f46;
      --text-primary: #fafafa;
      --text-secondary: #a1a1aa;
      --text-tertiary: #71717a;
      --status-online: #10b981;
      --status-online-bg: rgba(16, 185, 129, 0.1);
      --status-online-border: rgba(16, 185, 129, 0.25);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      background-color: var(--bg-base);
      color: var(--text-primary);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      -webkit-font-smoothing: antialiased;
    }
    .card {
      width: 100%;
      max-width: 460px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 32px 28px;
      box-shadow: 0 24px 48px -12px rgba(0, 0, 0, 0.85);
      text-align: center;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 4px 10px;
      border-radius: 999px;
      background: var(--status-online-bg);
      border: 1px solid var(--status-online-border);
      color: var(--status-online);
      font-size: 11.5px;
      font-weight: 600;
      margin-bottom: 18px;
    }
    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--status-online);
    }
    h1 {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--text-primary);
      margin-bottom: 10px;
    }
    p {
      font-size: 13px;
      line-height: 1.6;
      color: var(--text-secondary);
      margin-bottom: 24px;
    }
    .mono {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11.5px;
      color: var(--text-primary);
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      padding: 2px 6px;
      border-radius: 4px;
    }
    .btn-primary {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      height: 40px;
      border-radius: 8px;
      background: var(--text-primary);
      color: var(--bg-base);
      font-size: 13px;
      font-weight: 600;
      text-decoration: none;
      transition: opacity 0.15s ease;
    }
    .btn-primary:hover {
      opacity: 0.9;
    }
    .divider {
      height: 1px;
      background: var(--border-subtle);
      margin: 20px 0 16px;
    }
    .subtle-link {
      display: inline-block;
      font-size: 11.5px;
      color: var(--text-tertiary);
      text-decoration: none;
      transition: color 0.15s ease;
    }
    .subtle-link:hover {
      color: var(--text-secondary);
      text-decoration: underline;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">
      <span class="dot"></span>
      <span>Yerel API Köprüsü Aktif</span>
    </div>
    <h1>P2P Tunnel — maziPanel Tarafından Yönetiliyor</h1>
    <p>
      Bu P2P Tunnel sunucusu <span class="mono">maziPanel</span> entegrasyon modunda çalışmaktadır.
      İstemci yönetimi, HWID güvenlik duvarı ve sunucu ayarları maziPanel arayüzü üzerinden kontrol edilmektedir.
    </p>
    <a class="btn-primary" href="http://localhost:8080/p2p">
      <span>maziPanel Yönetim Ekranını Aç</span>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17l9.2-9.2M17 17V7H7"/></svg>
    </a>
    <div class="divider"></div>
    <a class="subtle-link" href="/?standalone=1">Yerel tanılama konsolunu doğrudan görüntüle (?standalone=1)</a>
  </div>
</body>
</html>"""


class WebAdminPanel:
    """Integrated Async HTTP Web Dashboard for P2PMCServer."""

    def __init__(self, server, port: int = 9090, panel_mode: Optional[str] = None):
        self.server = server
        self.port = port
        resolved_mode = (
            panel_mode
            or getattr(server, "panel_mode", None)
            or (server.config.get("panel_mode") if hasattr(server, "config") and isinstance(server.config, dict) else None)
            or "standalone"
        )
        self.panel_mode: str = str(resolved_mode).strip().lower()
        if self.panel_mode not in ("standalone", "mazipanel"):
            self.panel_mode = "standalone"

        self.server_task: Optional[asyncio.Server] = None
        self.session_token: str = secrets.token_hex(24)
        self.session_expiry: float = time.time() + 86400 * 7
        self.log_buffer: List[str] = []
        self.max_logs = 400

        # Traffic rate tracking state
        self._last_net_ts: float = time.time()
        self._last_tx_bytes: int = 0
        self._last_rx_bytes: int = 0
        self._base_tx_bytes: Optional[int] = None
        self._base_rx_bytes: Optional[int] = None
        self._tx_speed_bps: float = 0.0
        self._rx_speed_bps: float = 0.0

        self._preload_logs_from_disk()

    def _get_effective_panel_mode(self) -> str:
        mode = (
            getattr(self.server, "panel_mode", None)
            or (self.server.config.get("panel_mode") if hasattr(self.server, "config") and isinstance(self.server.config, dict) else None)
            or self.panel_mode
            or "standalone"
        )
        mode_str = str(mode).strip().lower()
        return mode_str if mode_str in ("standalone", "mazipanel") else "standalone"

    def _preload_logs_from_disk(self):
        """Preloads recent lines from server.log so web logs are never cleared on restart."""
        try:
            from core.paths import get_app_data_dir, get_server_config_path
            possible_paths = [
                os.path.join(get_app_data_dir(), "server.log"),
                os.path.join(os.path.dirname(get_server_config_path()), "server.log"),
                os.path.expanduser("~/.config/p2ptunnel/server.log"),
                os.path.expanduser("~/.p2ptunnel/server.log"),
                r"C:\ProgramData\P2PTunnel\server.log",
            ]
            log_file = None
            for p in possible_paths:
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    log_file = p
                    break

            if not log_file:
                return

            chunk_size = 256 * 1024
            with open(log_file, "rb") as f:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                read_size = min(file_size, chunk_size)
                f.seek(file_size - read_size)
                tail_data = f.read(read_size).decode("utf-8", errors="replace")
                lines = tail_data.splitlines()

            clean_lines = []
            for l in lines[-self.max_logs:]:
                l = l.strip()
                if not l:
                    continue
                if l.startswith("[") and len(l) > 20 and l[11:19].replace(":", "").isdigit():
                    time_part = l[12:20]
                    msg_body = l[24:].strip()
                    if msg_body.startswith("[INFO]") or msg_body.startswith("[WARN]") or msg_body.startswith("[ERROR]"):
                        msg_body = msg_body[6:].strip()
                    clean_lines.append(f"[{time_part}] {msg_body}")
                elif l.startswith("[") and "]" in l:
                    clean_lines.append(l)
                else:
                    clean_lines.append(f"[{time.strftime('%H:%M:%S')}] {l}")

            if clean_lines:
                self.log_buffer = clean_lines[-self.max_logs:]
        except Exception:
            pass

    def append_log(self, msg: str):
        """Buffers server log lines for web console viewer."""
        ts = time.strftime("%H:%M:%S")
        clean_msg = str(msg).strip()
        self.log_buffer.append(f"[{ts}] {clean_msg}")
        if len(self.log_buffer) > self.max_logs:
            self.log_buffer.pop(0)

    def _instrument_tunnel_metrics(self, tunnel):
        """Attaches lightweight byte counters to a P2PTunnel instance if not already present."""
        if getattr(tunnel, "_web_metrics_attached", False):
            return
        try:
            tunnel._web_metrics_attached = True
            if not hasattr(tunnel, "bytes_sent"):
                tunnel.bytes_sent = 0
            if not hasattr(tunnel, "bytes_received"):
                tunnel.bytes_received = 0

            orig_send = tunnel._send_udp_encrypted
            def _tracked_send(kcp_packet: bytes):
                tunnel.bytes_sent = getattr(tunnel, "bytes_sent", 0) + len(kcp_packet)
                return orig_send(kcp_packet)

            orig_feed = tunnel.feed_datagram
            def _tracked_feed(decrypted: bytes, addr: Tuple[str, int]):
                tunnel.bytes_received = getattr(tunnel, "bytes_received", 0) + len(decrypted)
                return orig_feed(decrypted, addr)

            tunnel._send_udp_encrypted = _tracked_send
            if hasattr(tunnel, "kcp") and hasattr(tunnel.kcp, "outbound_callback"):
                tunnel.kcp.outbound_callback = _tracked_send
            tunnel.feed_datagram = _tracked_feed
        except Exception:
            pass

    def _sample_network_traffic(self) -> Tuple[float, float, int, int]:
        """Samples system/tunnel network counters to compute live RX/TX speeds and cumulative totals."""
        now = time.time()
        dt = max(0.05, now - self._last_net_ts)

        # Sum active tunnel counters and attach hooks
        clients_dict = getattr(self.server, "clients", {})
        tunnel_tx = 0
        tunnel_rx = 0
        for tunnel in list(clients_dict.values()):
            self._instrument_tunnel_metrics(tunnel)
            tunnel_tx += getattr(tunnel, "bytes_sent", 0)
            tunnel_rx += getattr(tunnel, "bytes_received", 0)

        sys_tx = 0
        sys_rx = 0
        try:
            import psutil
            net = psutil.net_io_counters()
            if net:
                sys_tx = int(net.bytes_sent)
                sys_rx = int(net.bytes_recv)
        except Exception:
            try:
                if os.path.exists("/proc/net/dev"):
                    with open("/proc/net/dev", "r") as f:
                        for line in f.readlines()[2:]:
                            if ":" in line:
                                iface, data = line.split(":", 1)
                                if iface.strip() == "lo":
                                    continue
                                fields = data.split()
                                if len(fields) >= 9:
                                    sys_rx += int(fields[0])
                                    sys_tx += int(fields[8])
            except Exception:
                pass

        cur_tx = tunnel_tx if tunnel_tx > 0 else sys_tx
        cur_rx = tunnel_rx if tunnel_rx > 0 else sys_rx

        if self._base_tx_bytes is None:
            self._base_tx_bytes = cur_tx
            self._base_rx_bytes = cur_rx
            self._last_tx_bytes = cur_tx
            self._last_rx_bytes = cur_rx
            self._last_net_ts = now
            return 0.0, 0.0, 0, 0

        if dt >= 0.4:
            self._tx_speed_bps = max(0.0, (cur_tx - self._last_tx_bytes) / dt)
            self._rx_speed_bps = max(0.0, (cur_rx - self._last_rx_bytes) / dt)
            self._last_tx_bytes = cur_tx
            self._last_rx_bytes = cur_rx
            self._last_net_ts = now

        total_tx = max(0, cur_tx - (self._base_tx_bytes or 0))
        total_rx = max(0, cur_rx - (self._base_rx_bytes or 0))
        return self._tx_speed_bps, self._rx_speed_bps, total_tx, total_rx

    async def start(self):
        """Starts the HTTP server on 127.0.0.1:port."""
        try:
            self.server_task = await asyncio.start_server(
                self._handle_client,
                "127.0.0.1",
                self.port,
            )
            if hasattr(self.server, "logger"):
                self.server.logger.debug(
                    f"Web Yönetim Paneli dinleniyor: http://127.0.0.1:{self.port} (mod: {self._get_effective_panel_mode()})"
                )
        except Exception as e:
            if hasattr(self.server, "logger"):
                self.server.logger.error(f"Web Paneli başlatılamadı ({self.port}): {e}")

    async def stop(self):
        """Gracefully shuts down the HTTP server."""
        if self.server_task:
            self.server_task.close()
            await self.server_task.wait_closed()
            self.server_task = None

    def _check_auth(self, headers: Dict[str, str], cookies: Optional[Dict[str, str]] = None) -> bool:
        """
        Verifies request authentication via:
        1. Stateless X-P2P-Admin-Secret header (for maziPanel local bridge)
        2. Authorization: Bearer <session_token_or_admin_secret>
        3. Cookie: p2p_session=<session_token>
        """
        if hasattr(self.server, "sync_config_from_disk"):
            try:
                self.server.sync_config_from_disk()
            except Exception:
                pass

        norm_headers = {str(k).lower(): str(v).strip() for k, v in (headers or {}).items()}

        expected_admin = (
            getattr(getattr(self.server, "acl", None), "admin_secret", None)
            or (self.server.config.get("admin_secret") if hasattr(self.server, "config") and isinstance(self.server.config, dict) else None)
            or getattr(self.server, "admin_secret", None)
            or ""
        )
        expected_admin = str(expected_admin).strip()

        # If admin_secret is empty on the server, allow local access
        if not expected_admin:
            return True

        # 1. Stateless X-P2P-Admin-Secret header
        admin_secret_hdr = norm_headers.get("x-p2p-admin-secret", "")
        if admin_secret_hdr and hmac.compare_digest(admin_secret_hdr, expected_admin):
            return True

        # 2. Authorization header (Bearer session token or admin_secret)
        auth_header = norm_headers.get("authorization", "")
        if auth_header:
            bearer_val = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else auth_header.strip()
            if bearer_val:
                if self._verify_session(bearer_val) or hmac.compare_digest(bearer_val, expected_admin):
                    return True

        # 3. Session Cookie (p2p_session)
        parsed_cookies = dict(cookies) if cookies else {}
        if not parsed_cookies and "cookie" in norm_headers:
            for part in norm_headers["cookie"].split(";"):
                if "=" in part:
                    ck, cv = part.strip().split("=", 1)
                    parsed_cookies[ck.strip()] = cv.strip()

        cookie_token = parsed_cookies.get("p2p_session", "")
        if cookie_token and self._verify_session(cookie_token):
            return True

        return False

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handles an incoming HTTP request."""
        try:
            header_data = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)
            lines = header_data.decode("utf-8", errors="ignore").split("\r\n")
            if not lines or not lines[0]:
                writer.close()
                return

            req_line = lines[0].split(" ")
            if len(req_line) < 2:
                writer.close()
                return

            method = req_line[0].upper()
            full_path = req_line[1]

            headers = {}
            for line in lines[1:]:
                if ": " in line:
                    k, v = line.split(": ", 1)
                    headers[k.lower()] = v.strip()

            content_length = int(headers.get("content-length", 0))
            body_bytes = b""
            if 0 < content_length < 1024 * 1024:
                body_bytes = await asyncio.wait_for(reader.readexactly(content_length), timeout=5.0)

            cookies = {}
            if "cookie" in headers:
                for part in headers["cookie"].split(";"):
                    if "=" in part:
                        ck, cv = part.strip().split("=", 1)
                        cookies[ck] = cv

            has_valid_session = self._check_auth(headers, cookies)

            parsed_url = urllib.parse.urlparse(full_path)
            path = parsed_url.path
            query_params = urllib.parse.parse_qs(parsed_url.query)

            # Route Dispatcher
            if path in ("/", "/index.html"):
                force_standalone = query_params.get("standalone", ["0"])[0] in ("1", "true", "yes")
                if self._get_effective_panel_mode() == "mazipanel" and not force_standalone:
                    self._send_response(
                        writer,
                        MAZIPANEL_MANAGED_HTML.encode("utf-8"),
                        content_type="text/html; charset=utf-8",
                    )
                else:
                    await self._serve_dashboard(writer, has_valid_session)
            elif path == "/api/login" and method == "POST":
                await self._handle_api_login(writer, body_bytes)
            elif path == "/api/logout" and method == "POST":
                await self._handle_api_logout(writer)
            elif not has_valid_session:
                self._send_json(writer, {"error": "Unauthorized"}, status=401)
            elif path == "/api/status" and method == "GET":
                await self._handle_api_status(writer)
            elif path == "/api/clients" and method == "GET":
                self._handle_api_clients(writer)
            elif path == "/api/history" and method == "GET":
                self._handle_api_history(writer)
            elif path == "/api/bans" and method == "GET":
                self._handle_api_bans(writer)
            elif path == "/api/kick" and method == "POST":
                await self._handle_api_kick(writer, body_bytes)
            elif path == "/api/ban" and method == "POST":
                await self._handle_api_ban(writer, body_bytes)
            elif path == "/api/unban" and method == "POST":
                self._handle_api_unban(writer, body_bytes)
            elif path in ("/api/clear_history", "/api/history/clear") and method in ("POST", "DELETE"):
                self._handle_api_clear_history(writer)
            elif path == "/api/regenerate_key" and method == "POST":
                await self._handle_api_regenerate_key(writer)
            elif path == "/api/settings" and method == "GET":
                self._handle_api_get_settings(writer)
            elif path in ("/api/settings", "/api/update_settings") and method == "POST":
                await self._handle_api_save_settings(writer, body_bytes)
            elif path == "/api/version/refresh" and method == "POST":
                await self._handle_api_refresh_version(writer)
            elif path == "/api/logs" and method == "GET":
                self._send_json(writer, {"logs": self.log_buffer})
            else:
                self._send_response(writer, b"404 Not Found", status=404, content_type="text/plain")

        except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            try:
                self._send_response(writer, f"500 Internal Error: {e}".encode(), status=500, content_type="text/plain")
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def _verify_session(self, token: str) -> bool:
        if not token:
            return False
        if time.time() > self.session_expiry:
            return False
        return hmac.compare_digest(token, self.session_token)

    def _send_response(
        self,
        writer,
        body: bytes,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
        extra_headers: Optional[List[str]] = None,
    ):
        status_text = {
            200: "OK",
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            500: "Internal Server Error",
        }.get(status, "OK")

        headers = [
            f"HTTP/1.1 {status} {status_text}",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(body)}",
            "Connection: close",
            "Cache-Control: no-cache, no-store, must-revalidate",
        ]
        if extra_headers:
            headers.extend(extra_headers)

        header_bytes = ("\r\n".join(headers) + "\r\n\r\n").encode("utf-8")
        writer.write(header_bytes + body)

    def _send_json(self, writer, data: Any, status: int = 200, extra_headers: Optional[List[str]] = None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_response(
            writer,
            body,
            status=status,
            content_type="application/json; charset=utf-8",
            extra_headers=extra_headers,
        )

    async def _handle_api_login(self, writer, body_bytes: bytes):
        if hasattr(self.server, "sync_config_from_disk"):
            try:
                self.server.sync_config_from_disk()
            except Exception:
                pass

        try:
            req = json.loads(body_bytes.decode("utf-8"))
            password = req.get("password", "").strip()
        except Exception:
            self._send_json(writer, {"success": False, "message": "Geçersiz istek"}, status=400)
            return

        expected_admin = getattr(self.server.acl, "admin_secret", "")
        if expected_admin and hmac.compare_digest(password, expected_admin):
            self.session_token = secrets.token_hex(24)
            self.session_expiry = time.time() + 86400 * 7
            cookie_hdr = f"Set-Cookie: p2p_session={self.session_token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800"
            self._send_json(writer, {"success": True, "token": self.session_token}, extra_headers=[cookie_hdr])
        else:
            self._send_json(writer, {"success": False, "message": "Yönetici şifresi hatalı!"}, status=401)

    async def _handle_api_logout(self, writer):
        self.session_token = secrets.token_hex(24)
        cookie_hdr = "Set-Cookie: p2p_session=; Path=/; HttpOnly; Max-Age=0"
        self._send_json(writer, {"success": True}, extra_headers=[cookie_hdr])

    async def _handle_api_status(self, writer):
        if hasattr(self.server, "sync_config_from_disk"):
            try:
                self.server.sync_config_from_disk()
            except Exception:
                pass

        cpu_pct = 0.0
        ram_pct = 0.0
        ram_used_mb = 0
        ram_total_mb = 0

        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            ram_pct = vm.percent
            ram_used_mb = int(vm.used / (1024 * 1024))
            ram_total_mb = int(vm.total / (1024 * 1024))
        except Exception:
            try:
                if os.path.exists("/proc/meminfo"):
                    with open("/proc/meminfo", "r") as f:
                        lines = f.readlines()
                    mem = {}
                    for l in lines:
                        parts = l.split(":")
                        if len(parts) == 2:
                            mem[parts[0].strip()] = int(parts[1].split()[0])
                    total_kb = mem.get("MemTotal", 1)
                    avail_kb = mem.get("MemAvailable", 0)
                    ram_total_mb = int(total_kb / 1024)
                    ram_used_mb = int((total_kb - avail_kb) / 1024)
                    ram_pct = round((ram_used_mb / ram_total_mb) * 100.0, 1)
            except Exception:
                pass

        target_service_port = int(getattr(self.server.acl, "allowed_game_port", 25565))
        mc_port_open = False
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.25)
            mc_port_open = (sock.connect_ex(("127.0.0.1", target_service_port)) == 0)
            sock.close()
        except Exception:
            mc_port_open = False

        vm = getattr(self.server, "version_manager", None)
        req_client_ver = vm.get_required_version() if vm else "3.0"

        active_tunnels = [
            t for t in getattr(self.server, "clients", {}).values()
            if getattr(t, "authenticated", False) and getattr(t, "running", False)
        ]
        active_streams = sum(len(getattr(t, "streams", {})) for t in active_tunnels)
        tx_speed_bps, rx_speed_bps, total_tx_bytes, total_rx_bytes = self._sample_network_traffic()

        udp_port = getattr(self.server, "local_udp_port", 25566)
        if getattr(self.server, "sock", None):
            try:
                udp_port = self.server.sock.getsockname()[1]
            except Exception:
                pass

        from core.invite import normalize_server_key
        raw_key = getattr(self.server, "server_key", "")
        raw_pub_ep = getattr(self.server, "public_endpoint", None)
        if isinstance(raw_pub_ep, (tuple, list)) and len(raw_pub_ep) >= 2:
            formatted_pub_ep = f"{raw_pub_ep[0]}:{raw_pub_ep[1]}"
        elif isinstance(raw_pub_ep, str):
            formatted_pub_ep = raw_pub_ep.strip()
        else:
            formatted_pub_ep = None

        status_data = {
            "server_name": getattr(self.server, "server_name", "P2P Sunucusu"),
            "server_key": normalize_server_key(raw_key),
            "game_port": target_service_port,
            "connection_address": getattr(self.server.acl, "connection_address", "baglanti.localhost"),
            "game_port_active": mc_port_open,
            "web_port": self.port,
            "udp_port": udp_port,
            "panel_mode": self._get_effective_panel_mode(),
            "connected_clients": len(active_tunnels),
            "active_streams": active_streams,
            "cpu_percent": cpu_pct,
            "ram_percent": ram_pct,
            "ram_used_mb": ram_used_mb,
            "ram_total_mb": ram_total_mb,
            "tx_speed_bps": round(tx_speed_bps, 1),
            "rx_speed_bps": round(rx_speed_bps, 1),
            "total_tx_bytes": total_tx_bytes,
            "total_rx_bytes": total_rx_bytes,
            "public_endpoint": formatted_pub_ep,
            "server_uptime": int(time.time() - getattr(self.server, "start_time", time.time())),
            "required_client_version": req_client_ver,
        }
        self._send_json(writer, status_data)

    def _handle_api_clients(self, writer):
        clients_data = []
        clients_dict = getattr(self.server, "clients", {})
        now = time.time()

        for addr, tunnel in list(clients_dict.items()):
            if not getattr(tunnel, "authenticated", False) or not getattr(tunnel, "running", False):
                continue
            self._instrument_tunnel_metrics(tunnel)
            info = getattr(tunnel, "client_info", {})
            conn_at = info.get("connected_at", now)
            duration_sec = int(now - conn_at)

            stream_local_ports = []
            for _sid, stream_pair in list(getattr(tunnel, "streams", {}).items()):
                try:
                    _r, _w = stream_pair
                    sockname = _w.get_extra_info("sockname") if _w else None
                    if sockname and len(sockname) >= 2 and sockname[1]:
                        stream_local_ports.append(int(sockname[1]))
                except Exception:
                    pass

            clients_data.append({
                "peer_addr": f"{addr[0]}:{addr[1]}",
                "ip": addr[0],
                "port": addr[1],
                "username": info.get("username") or "Bilinmeyen",
                "version": info.get("version") or "Eski (Sürümsüz)",
                "computer_name": info.get("computer_name") or "-",
                "hwid": info.get("hwid") or "N/A",
                "hwid_details": info.get("hwid_details") or {},
                "os": info.get("os") or "Bilinmiyor",
                "role": getattr(tunnel.peer_role, "name", "PLAYER") if tunnel.peer_role else "PLAYER",
                "ping_ms": round(getattr(tunnel, "current_rtt_ms", 0.0), 1),
                "active_streams": len(getattr(tunnel, "streams", {})),
                "local_ports": stream_local_ports,
                "bytes_sent": getattr(tunnel, "bytes_sent", 0),
                "bytes_received": getattr(tunnel, "bytes_received", 0),
                "duration_seconds": duration_sec,
                "authenticated": getattr(tunnel, "authenticated", False),
            })

        hist_mgr = getattr(self.server, "history_manager", None)
        ban_mgr = getattr(self.server.acl, "ban_manager", None)
        history_data = hist_mgr.get_history(ban_manager=ban_mgr) if hist_mgr else []

        self._send_json(writer, {"clients": clients_data, "history": history_data})

    def _handle_api_history(self, writer):
        hist_mgr = getattr(self.server, "history_manager", None)
        ban_mgr = getattr(self.server.acl, "ban_manager", None)
        history_data = hist_mgr.get_history(ban_manager=ban_mgr) if hist_mgr else []
        self._send_json(writer, {"history": history_data})

    def _handle_api_clear_history(self, writer):
        hist_mgr = getattr(self.server, "history_manager", None)
        if hist_mgr:
            hist_mgr._history.clear()
            hist_mgr._save_history()
            self.append_log("Bağlantı geçmişi yönetici tarafından temizlendi.")
            self._send_json(writer, {"success": True, "message": "Bağlantı geçmişi başarıyla temizlendi."})
        else:
            self._send_json(writer, {"success": False, "message": "Geçmiş yöneticisi bulunamadı."})

    async def _handle_api_regenerate_key(self, writer):
        try:
            from core.invite import generate_server_key, derive_credentials_from_key, normalize_server_key
            from core.crypto import PacketCipher, derive_key

            new_key = normalize_server_key(generate_server_key())
            cfg = getattr(self.server, "config", {})
            self.server.server_key = new_key
            self.server.short_code = new_key
            cfg["server_key"] = new_key

            _, derived_room_sec, derived_player_tok = derive_credentials_from_key(new_key)
            self.server.room_secret = derived_room_sec
            self.server.player_token = derived_player_tok
            self.server.acl.player_token = derived_player_tok
            if hasattr(self.server.acl, "add_player_token"):
                self.server.acl.add_player_token(derived_player_tok)
            cfg["room_secret"] = derived_room_sec
            cfg["player_token"] = derived_player_tok
            self.server.cipher = PacketCipher(derive_key(derived_room_sec))
            if hasattr(self.server, "restart_signaling"):
                self.server.restart_signaling()

            cfg_path = getattr(self.server, "config_path", None)
            if cfg_path:
                try:
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=2, ensure_ascii=False)
                    self.server._config_mtime = os.path.getmtime(cfg_path)
                except Exception as e:
                    self.append_log(f"Ayar dosyasına yazılamadı: {e}")

            self.append_log(f"Sunucu bağlantı kodu yenilendi: {new_key}")
            self._send_json(writer, {
                "success": True,
                "server_key": new_key,
                "message": f"Yeni sunucu bağlantı kodu oluşturuldu: {new_key}",
            })
        except Exception as e:
            self._send_json(writer, {"success": False, "message": f"Anahtar üretilemedi: {e}"}, status=500)

    def _handle_api_bans(self, writer):
        ban_mgr = getattr(self.server.acl, "ban_manager", None)
        bans = ban_mgr.get_bans() if ban_mgr else []
        self._send_json(writer, {"bans": bans})

    async def _handle_api_kick(self, writer, body_bytes: bytes):
        try:
            req = json.loads(body_bytes.decode("utf-8"))
            target_addr = req.get("peer_addr", "").strip()
            target_hwid = req.get("hwid", "").strip().upper()
        except Exception:
            self._send_json(writer, {"success": False, "message": "Geçersiz veri"}, status=400)
            return

        kicked = False
        target_name = ""
        clients_dict = getattr(self.server, "clients", {})
        for addr, tunnel in list(clients_dict.items()):
            addr_str = f"{addr[0]}:{addr[1]}"
            hwid = str(tunnel.client_info.get("hwid", "")).strip().upper()
            if (target_addr and addr_str == target_addr) or (target_hwid and hwid == target_hwid):
                target_name = tunnel.client_info.get("username", "Kullanıcı")
                tunnel.send_disconnect()
                await tunnel.stop()
                clients_dict.pop(addr, None)
                kicked = True
                self.append_log(f"İstemci atıldı (Kick): {target_name} ({addr_str})")
                break

        if kicked:
            self._send_json(writer, {"success": True, "message": f"{target_name} bağlantısı sonlandırıldı."})
        else:
            self._send_json(writer, {"success": False, "message": "Hedef istemci bulunamadı."})

    async def _handle_api_ban(self, writer, body_bytes: bytes):
        try:
            req = json.loads(body_bytes.decode("utf-8"))
            hwid = req.get("hwid", "").strip().upper()
            hwid_details = req.get("hwid_details", {})
            username = req.get("username", "Bilinmeyen")
            reason = req.get("reason", "Yönetici tarafından yasaklandı").strip()
            peer_addr = req.get("peer_addr", "").strip()
        except Exception:
            self._send_json(writer, {"success": False, "message": "Geçersiz veri"}, status=400)
            return

        if not hwid:
            self._send_json(writer, {"success": False, "message": "HWID boş olamaz!"}, status=400)
            return

        ban_mgr = getattr(self.server.acl, "ban_manager", None)
        if ban_mgr:
            ban_mgr.ban(
                hwid=hwid,
                hwid_details=hwid_details,
                username=username,
                reason=reason or "Yönetici tarafından yasaklandı",
            )
            self.append_log(f"HWID Ban uygulandı: {username} ({hwid}) - Sebep: {reason}")

        clients_dict = getattr(self.server, "clients", {})
        for addr, tunnel in list(clients_dict.items()):
            addr_str = f"{addr[0]}:{addr[1]}"
            t_hwid = str(tunnel.client_info.get("hwid", "")).strip().upper()
            t_details = tunnel.client_info.get("hwid_details", {})
            t_mb = str(t_details.get("motherboard_uuid", "")).strip().upper()
            req_mb = str(hwid_details.get("motherboard_uuid", "")).strip().upper()

            if (t_hwid == hwid) or (peer_addr and addr_str == peer_addr) or (t_mb and t_mb == req_mb):
                tunnel.send_disconnect()
                await tunnel.stop()
                clients_dict.pop(addr, None)

        self._send_json(writer, {"success": True, "message": f"{username} başarıyla yasaklandı."})

    def _handle_api_unban(self, writer, body_bytes: bytes):
        try:
            req = json.loads(body_bytes.decode("utf-8"))
            identifier = req.get("id") or req.get("hwid") or ""
        except Exception:
            self._send_json(writer, {"success": False, "message": "Geçersiz veri"}, status=400)
            return

        ban_mgr = getattr(self.server.acl, "ban_manager", None)
        if ban_mgr and ban_mgr.unban(identifier):
            self.append_log(f"Yasak kaldırıldı (Unban): {identifier}")
            self._send_json(writer, {"success": True, "message": "Yasak başarıyla kaldırıldı."})
        else:
            self._send_json(writer, {"success": False, "message": "Yasak kaydı bulunamadı."})

    def _handle_api_get_settings(self, writer):
        from core.invite import normalize_server_key
        cfg = getattr(self.server, "config", {})
        vm = getattr(self.server, "version_manager", None)
        req_ver = vm.get_required_version() if vm else "3.0"
        self._send_json(writer, {
            "server_name": getattr(self.server, "server_name", "P2P Sunucusu"),
            "server_key": normalize_server_key(getattr(self.server, "server_key", "")),
            "game_port": getattr(self.server.acl, "allowed_game_port", cfg.get("game_port", 25565)),
            "connection_address": getattr(self.server.acl, "connection_address", cfg.get("connection_address", "baglanti.localhost")),
            "web_port": self.port,
            "panel_mode": self._get_effective_panel_mode(),
            "admin_secret": getattr(self.server.acl, "admin_secret", ""),
            "required_client_version": req_ver,
        })

    async def _handle_api_refresh_version(self, writer):
        vm = getattr(self.server, "version_manager", None)
        if vm:
            refreshed = await asyncio.to_thread(vm.refresh_sync)
            current = vm.get_required_version()
            self._send_json(writer, {"success": True, "version": current, "refreshed": bool(refreshed)})
        else:
            self._send_json(writer, {"success": False, "message": "Sürüm yöneticisi aktif değil."})

    async def _handle_api_save_settings(self, writer, body_bytes: bytes):
        try:
            req = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            self._send_json(writer, {"success": False, "message": "Geçersiz ayar verisi"}, status=400)
            return

        cfg = getattr(self.server, "config", {})
        changed = False
        key_changed = False

        new_name = req.get("server_name")
        if new_name is not None and str(new_name).strip():
            self.server.server_name = str(new_name).strip()
            cfg["server_name"] = self.server.server_name
            changed = True

        new_key = req.get("server_key")
        if new_key is not None and str(new_key).strip():
            from core.invite import derive_credentials_from_key, normalize_server_key
            from core.crypto import PacketCipher, derive_key
            norm_k = normalize_server_key(str(new_key))
            if norm_k != self.server.server_key:
                key_changed = True
            self.server.server_key = norm_k
            self.server.short_code = norm_k
            cfg["server_key"] = self.server.server_key
            try:
                _, derived_room_sec, derived_player_tok = derive_credentials_from_key(self.server.server_key)
                self.server.room_secret = derived_room_sec
                self.server.player_token = derived_player_tok
                self.server.acl.player_token = derived_player_tok
                if hasattr(self.server.acl, "add_player_token"):
                    self.server.acl.add_player_token(derived_player_tok)
                cfg["room_secret"] = derived_room_sec
                cfg["player_token"] = derived_player_tok
                self.server.cipher = PacketCipher(derive_key(derived_room_sec))
                if key_changed and hasattr(self.server, "restart_signaling"):
                    self.server.restart_signaling()
            except Exception as e:
                self.append_log(f"Server anahtarı türetme hatası: {e}")
            changed = True

        new_port = req.get("game_port")
        if new_port is not None:
            try:
                p_val = int(new_port)
                if 1 <= p_val <= 65535:
                    self.server.acl.allowed_game_port = p_val
                    cfg["game_port"] = p_val
                    changed = True
            except ValueError:
                pass

        new_addr = req.get("connection_address")
        if new_addr is not None and str(new_addr).strip():
            addr_val = str(new_addr).strip().lower()
            if addr_val not in ("127.0.0.1", "localhost") and not addr_val.endswith(".localhost"):
                addr_val = f"{addr_val}.localhost"
            self.server.acl.connection_address = addr_val
            cfg["connection_address"] = addr_val
            changed = True

        new_admin = req.get("admin_secret")
        if new_admin is not None and str(new_admin).strip():
            cleaned_admin = str(new_admin).strip()
            self.server.admin_secret = cleaned_admin
            self.server.acl.admin_secret = cleaned_admin
            cfg["admin_secret"] = cleaned_admin
            changed = True

        new_panel_mode = req.get("panel_mode")
        if new_panel_mode is not None and str(new_panel_mode).strip().lower() in ("standalone", "mazipanel"):
            cleaned_mode = str(new_panel_mode).strip().lower()
            self.panel_mode = cleaned_mode
            self.server.panel_mode = cleaned_mode
            cfg["panel_mode"] = cleaned_mode
            changed = True

        if changed:
            cfg_path = getattr(self.server, "config_path", None)
            if cfg_path:
                try:
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=2, ensure_ascii=False)
                    self.server._config_mtime = os.path.getmtime(cfg_path)
                except Exception as e:
                    self.append_log(f"Ayar dosyasına yazılamadı: {e}")
            self.append_log("Sunucu ayarları web paneli üzerinden güncellendi.")
            self._send_json(writer, {"success": True, "message": "Yapılandırma kalıcı olarak kaydedildi."})
        else:
            self._send_json(writer, {"success": False, "message": "Değiştirilen ayar bulunamadı."})

    async def _serve_dashboard(self, writer, is_authenticated: bool):
        html = self._generate_html(is_authenticated)
        self._send_response(writer, html.encode("utf-8"), content_type="text/html; charset=utf-8")

    def _generate_html(self, is_authenticated: bool) -> str:
        login_display = "none" if is_authenticated else "flex"
        return DASHBOARD_HTML.replace("__LOGIN_DISPLAY__", login_display)


WebManagementPanel = WebAdminPanel
