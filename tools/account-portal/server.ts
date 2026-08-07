import { crypto } from "https://deno.land/std@0.200.0/crypto/mod.ts";
import { parse as parseYaml } from "https://deno.land/std@0.200.0/yaml/mod.ts";
import { isAbsolute, join, fromFileUrl, dirname } from "https://deno.land/std@0.200.0/path/mod.ts";

interface PortalConfig {
  server?: {
    port?: number;
    use_ssl?: boolean;
    cert_path?: string;
    key_path?: string;
    redirect_http?: boolean;
    http_redirect_port?: number;
  };
  database?: {
    container_name?: string;
    user?: string;
    password?: string;
    auth_db?: string;
  };
}

const currentDir = dirname(fromFileUrl(import.meta.url));

let config: PortalConfig = {};
try {
  const configText = await Deno.readTextFile(join(currentDir, "config.yml"));
  config = parseYaml(configText) as PortalConfig;
  console.log("[Portal] Loaded configuration from config.yml");
} catch {
  console.log("[Portal] config.yml not found, using default settings (port: 3000, HTTP).");
}

const serverPort = config.server?.port ?? 3000;
const useSsl = config.server?.use_ssl ?? false;
const certPath = config.server?.cert_path ?? "./cert.pem";
const keyPath = config.server?.key_path ?? "./key.pem";
const redirectHttp = config.server?.redirect_http ?? false;
const httpRedirectPort = config.server?.http_redirect_port ?? 80;

const dbContainer = config.database?.container_name ?? "ac-database";
const dbUser = config.database?.user ?? "root";
const dbPass = config.database?.password ?? "password";
const dbAuthName = config.database?.auth_db ?? "acore_auth";

// SRP6 constants for WotLK / AzerothCore authentication
const N = BigInt("0x894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7");
const g = 7n;

async function sha1(data: Uint8Array): Promise<Uint8Array> {
  const hashBuffer = await crypto.subtle.digest("SHA-1", data as any);
  return new Uint8Array(hashBuffer);
}

function bytesToBigIntLE(bytes: Uint8Array): bigint {
  let value = 0n;
  for (let i = 0; i < bytes.length; i++) {
    value += BigInt(bytes[i]) << BigInt(i * 8);
  }
  return value;
}

function bigIntToBytesLE(value: bigint, length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  for (let i = 0; i < length; i++) {
    bytes[i] = Number((value >> BigInt(i * 8)) & 0xFFn);
  }
  return bytes;
}

function modPow(base: bigint, exponent: bigint, modulus: bigint): bigint {
  if (modulus === 1n) return 0n;
  let result = 1n;
  base = base % modulus;
  while (exponent > 0n) {
    if (exponent % 2n === 1n) {
      result = (result * base) % modulus;
    }
    exponent = exponent / 2n;
    base = (base * base) % modulus;
  }
  return result;
}

async function calculateVerifier(username: string, password: string, salt: Uint8Array): Promise<Uint8Array> {
  const encoder = new TextEncoder();
  const identity = username.toUpperCase() + ":" + password.toUpperCase();
  const h1 = await sha1(encoder.encode(identity));

  const combined = new Uint8Array(salt.length + h1.length);
  combined.set(salt, 0);
  combined.set(h1, salt.length);
  const h2 = await sha1(combined);

  const x = bytesToBigIntLE(h2);
  const v = modPow(g, x, N);
  return bigIntToBytesLE(v, 32);
}

// Execute command on docker database
async function runQuery(sql: string): Promise<string> {
  const command = new Deno.Command("docker", {
    args: [
      "exec",
      dbContainer,
      "mysql",
      `-u${dbUser}`,
      `-p${dbPass}`,
      "-sN",
      "-e",
      sql,
    ],
    cwd: "/home/bdodroid/wow-server-playerbots",
  });
  const { code, stdout, stderr } = await command.output();
  if (code !== 0) {
    const errorText = new TextDecoder().decode(stderr).trim();
    throw new Error(errorText || `Docker DB command failed with exit code ${code}`);
  }
  return new TextDecoder().decode(stdout).trim();
}

const HTML_CONTENT = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SpellDraft WoW - Account Portal & Installation Guide</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700;800;900&family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    :root {
      /* Color Palette matched exactly to SpellDraft main website */
      --color-bg-darkest: #050811;   /* Deep void black-blue */
      --color-bg-dark: #0b1120;      /* Dark navy blue */
      --color-bg-medium: #111a2e;    /* Slate blue-grey */
      --color-bg-light: #1c273e;     /* Accent blue-grey */
      
      --color-purple: #9d52ff;       /* Mystical purple */
      --color-purple-hover: #b47dff;
      --color-purple-glow: rgba(157, 82, 255, 0.35);
      --color-purple-border: rgba(157, 82, 255, 0.15);

      --color-orange: #f97316;       /* Spell-fire orange */
      --color-orange-hover: #fb923c;
      --color-orange-glow: rgba(249, 115, 22, 0.35);
      --color-orange-border: rgba(249, 115, 22, 0.15);

      --color-gold: #d4af37;         /* Antique gold accents */
      --color-gold-glow: rgba(212, 175, 55, 0.25);
      
      --color-text: #f3f4f6;         /* Bright text */
      --color-text-muted: #9ca3af;   /* Muted text */
      --color-text-dark: #6b7280;    /* Dark helper text */
      --color-text-emerald: #10b981; /* Success green */
      --color-text-rose: #f43f5e;    /* Error red */
      
      --font-title: 'Cinzel', serif;
      --font-body: 'Inter', sans-serif;
      --transition-smooth: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    html {
      scroll-behavior: smooth;
    }

    body {
      background: radial-gradient(circle at 50% 50%, var(--color-bg-dark) 0%, var(--color-bg-darkest) 100%);
      color: var(--color-text);
      min-height: 100vh;
      font-family: var(--font-body);
      overflow-x: hidden;
      position: relative;
    }

    /* Ambient background glows matching website */
    body::before {
      content: "";
      position: fixed;
      width: 500px;
      height: 500px;
      background: radial-gradient(circle, rgba(157, 82, 255, 0.08) 0%, transparent 70%);
      top: -150px;
      left: -150px;
      z-index: 0;
      pointer-events: none;
    }

    body::after {
      content: "";
      position: fixed;
      width: 500px;
      height: 500px;
      background: radial-gradient(circle, rgba(249, 115, 22, 0.06) 0%, transparent 70%);
      bottom: -150px;
      right: -150px;
      z-index: 0;
      pointer-events: none;
    }

    /* Hero Full-Screen Layout */
    .hero-section {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      position: relative;
      padding: 40px 20px;
      z-index: 10;
    }

    .container {
      width: 100%;
      max-width: 450px;
      z-index: 10;
    }

    .card {
      background: rgba(5, 8, 17, 0.85);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid var(--color-purple-border);
      border-radius: 20px;
      padding: 40px 32px;
      box-shadow: 0 15px 35px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.05);
      position: relative;
    }

    /* Logo & Header */
    .logo {
      font-family: var(--font-title);
      font-size: 28px;
      font-weight: 900;
      letter-spacing: 1px;
      text-align: center;
      margin-bottom: 8px;
    }

    .logo-purple {
      color: var(--color-purple);
      text-shadow: 0 0 10px rgba(157, 82, 255, 0.3);
    }

    .logo-orange {
      color: var(--color-orange);
      text-shadow: 0 0 10px rgba(249, 115, 22, 0.3);
    }

    .header p {
      color: var(--color-text-muted);
      font-size: 11px;
      text-align: center;
      letter-spacing: 2px;
      text-transform: uppercase;
      margin-bottom: 32px;
      font-weight: 500;
    }

    /* Tabs styling matching website buttons */
    .tabs {
      display: flex;
      background: rgba(5, 8, 17, 0.9);
      padding: 4px;
      border-radius: 12px;
      border: 1px solid var(--color-purple-border);
      margin-bottom: 32px;
    }

    .tab-btn {
      flex: 1;
      border: none;
      background: transparent;
      color: var(--color-text-muted);
      padding: 10px 0;
      font-size: 13px;
      font-weight: 600;
      font-family: var(--font-body);
      cursor: pointer;
      border-radius: 8px;
      transition: var(--transition-smooth);
    }

    .tab-btn.active {
      color: #ffffff;
      background: rgba(157, 82, 255, 0.15);
      border: 1px solid rgba(157, 82, 255, 0.25);
      box-shadow: 0 0 12px rgba(157, 82, 255, 0.1);
    }

    /* Forms */
    .form-group {
      margin-bottom: 24px;
    }

    .form-group label {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      font-weight: 600;
      color: var(--color-text-muted);
      margin-bottom: 10px;
      text-transform: uppercase;
      letter-spacing: 1px;
    }

    .form-group label i {
      color: var(--color-purple);
      font-size: 14px;
    }

    .input-wrapper input {
      width: 100%;
      background: rgba(11, 17, 32, 0.8);
      border: 1px solid var(--color-bg-light);
      border-radius: 10px;
      padding: 12px 16px;
      color: var(--color-text);
      font-size: 14px;
      font-family: var(--font-body);
      outline: none;
      transition: var(--transition-smooth);
    }

    .input-wrapper input:focus {
      border-color: var(--color-purple);
      box-shadow: 0 0 15px var(--color-purple-glow);
      background: rgba(17, 26, 46, 0.8);
    }

    /* Submit Button with Magic Gradient */
    .submit-btn {
      width: 100%;
      background: linear-gradient(90deg, var(--color-purple) 0%, var(--color-orange) 100%);
      color: #ffffff;
      border: none;
      border-radius: 10px;
      padding: 14px;
      font-size: 13px;
      font-weight: 700;
      font-family: var(--font-body);
      text-transform: uppercase;
      letter-spacing: 1px;
      cursor: pointer;
      transition: var(--transition-smooth);
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 8px;
    }

    .submit-btn:hover {
      box-shadow: 0 0 20px var(--color-purple-glow), 0 0 20px var(--color-orange-glow);
      transform: translateY(-1px);
    }

    .submit-btn:active {
      transform: translateY(1px);
    }

    .spinner {
      width: 16px;
      height: 16px;
      border: 2px solid rgba(255, 255, 255, 0.3);
      border-top-color: white;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      display: none;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    /* Status Notifications */
    .status-msg {
      margin-top: 24px;
      padding: 14px 18px;
      border-radius: 10px;
      font-size: 13px;
      font-weight: 500;
      display: none;
      animation: fadeIn 0.3s ease;
      line-height: 1.5;
    }

    .status-msg.success {
      background: rgba(16, 185, 129, 0.08);
      border: 1px solid rgba(16, 185, 129, 0.2);
      color: var(--color-text-emerald);
      box-shadow: 0 0 10px rgba(16, 185, 129, 0.05);
    }

    .status-msg.error {
      background: rgba(244, 63, 94, 0.08);
      border: 1px solid rgba(244, 63, 94, 0.2);
      color: var(--color-text-rose);
      box-shadow: 0 0 10px rgba(244, 63, 94, 0.05);
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(5px); }
      to { opacity: 1; transform: translateY(0); }
    }

    /* Bouncing Scroll Down Indicator */
    .scroll-indicator {
      position: absolute;
      bottom: 24px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      color: var(--color-text-muted);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 2px;
      text-transform: uppercase;
      cursor: pointer;
      transition: var(--transition-smooth);
      z-index: 10;
    }

    .scroll-indicator:hover {
      color: var(--color-orange);
      text-shadow: 0 0 10px var(--color-orange-glow);
    }

    .bounce {
      animation: bounce 2s infinite;
      font-size: 18px;
      color: var(--color-purple);
    }

    @keyframes bounce {
      0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
      40% { transform: translateY(8px); }
      60% { transform: translateY(4px); }
    }

    /* Installation Guide Section */
    .guide-section {
      width: 100%;
      max-width: 1050px;
      margin: 0 auto;
      padding: 80px 20px 80px 20px;
      position: relative;
      z-index: 10;
    }

    .guide-header {
      text-align: center;
      margin-bottom: 48px;
    }

    .guide-title {
      font-family: var(--font-title);
      font-size: 32px;
      font-weight: 900;
      letter-spacing: 2px;
      margin-bottom: 12px;
    }

    .guide-subtitle {
      color: var(--color-text-muted);
      font-size: 14px;
      max-width: 600px;
      margin: 0 auto;
      line-height: 1.6;
    }

    .guide-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 24px;
      margin-bottom: 60px;
    }

    .guide-card {
      background: rgba(5, 8, 17, 0.85);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid var(--color-purple-border);
      border-radius: 18px;
      padding: 32px 26px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.05);
      display: flex;
      flex-direction: column;
      position: relative;
      transition: var(--transition-smooth);
    }

    .guide-card:hover {
      border-color: rgba(157, 82, 255, 0.4);
      transform: translateY(-4px);
      box-shadow: 0 15px 35px rgba(0, 0, 0, 0.8), 0 0 20px var(--color-purple-glow);
    }

    .step-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(157, 82, 255, 0.15);
      border: 1px solid rgba(157, 82, 255, 0.3);
      color: var(--color-purple-hover);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      padding: 5px 12px;
      border-radius: 20px;
      width: fit-content;
      margin-bottom: 20px;
    }

    .card-title {
      font-family: var(--font-title);
      font-size: 18px;
      font-weight: 800;
      margin-bottom: 12px;
      color: #ffffff;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .card-title i {
      color: var(--color-orange);
    }

    .card-desc {
      color: var(--color-text-muted);
      font-size: 13px;
      line-height: 1.6;
      margin-bottom: 24px;
      flex-grow: 1;
    }

    .card-desc code {
      background: rgba(17, 26, 46, 0.9);
      border: 1px solid var(--color-bg-light);
      color: var(--color-gold);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 12px;
      font-family: monospace;
    }

    .guide-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      background: linear-gradient(90deg, var(--color-orange) 0%, #ea580c 100%);
      color: #ffffff;
      text-decoration: none;
      border: none;
      border-radius: 10px;
      padding: 13px 18px;
      font-size: 12px;
      font-weight: 700;
      font-family: var(--font-body);
      text-transform: uppercase;
      letter-spacing: 1px;
      transition: var(--transition-smooth);
      box-shadow: 0 4px 12px rgba(249, 115, 22, 0.3);
      margin-top: auto;
    }

    .guide-btn:hover {
      box-shadow: 0 0 18px var(--color-orange-glow);
      transform: translateY(-2px);
    }

    .guide-btn-purple {
      background: linear-gradient(90deg, var(--color-purple) 0%, #7c3aed 100%);
      box-shadow: 0 4px 12px rgba(157, 82, 255, 0.3);
    }

    .guide-btn-purple:hover {
      box-shadow: 0 0 18px var(--color-purple-glow);
    }

    .tip-box {
      background: rgba(17, 26, 46, 0.7);
      border: 1px solid var(--color-bg-light);
      border-left: 3px solid var(--color-gold);
      border-radius: 8px;
      padding: 12px 14px;
      font-size: 12px;
      color: var(--color-text-muted);
      margin-top: 16px;
      line-height: 1.5;
      display: flex;
      gap: 10px;
      align-items: flex-start;
    }

    .tip-box i {
      color: var(--color-gold);
      font-size: 14px;
      margin-top: 2px;
    }

    .code-box {
      background: rgba(11, 17, 32, 0.95);
      border: 1px solid var(--color-bg-light);
      border-radius: 10px;
      padding: 12px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-top: auto;
    }

    .code-box code {
      font-family: monospace;
      font-size: 12px;
      color: var(--color-gold);
      word-break: break-all;
    }

    .copy-btn {
      background: rgba(157, 82, 255, 0.15);
      border: 1px solid rgba(157, 82, 255, 0.3);
      color: #ffffff;
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 11px;
      font-weight: 700;
      font-family: var(--font-body);
      cursor: pointer;
      transition: var(--transition-smooth);
      display: flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }

    .copy-btn:hover {
      background: var(--color-purple);
      box-shadow: 0 0 12px var(--color-purple-glow);
    }

    .copy-btn.copied {
      background: rgba(16, 185, 129, 0.2);
      border-color: rgba(16, 185, 129, 0.4);
      color: var(--color-text-emerald);
    }

    .footer {
      text-align: center;
      margin-top: 40px;
      font-size: 11px;
      color: var(--color-text-dark);
      letter-spacing: 1px;
      text-transform: uppercase;
    }

    .footer-link {
      text-decoration: none;
      color: var(--color-purple);
      font-weight: 700;
      transition: var(--transition-smooth);
    }

    .footer-link:hover {
      color: var(--color-orange);
      text-shadow: 0 0 10px rgba(249, 115, 22, 0.4);
    }

    .hidden {
      display: none;
    }
  </style>
</head>
<body>

  <!-- Hero Section: Full Screen Account Portal -->
  <section class="hero-section">
    <div class="container">
      <div class="card">
        <div class="header">
          <div class="logo">
            <span class="logo-purple">SPELL</span><span class="logo-orange">DRAFT</span>
          </div>
          <p>Account Portal</p>
        </div>

        <div class="tabs">
          <button class="tab-btn active" onclick="switchTab('create')">Create Account</button>
          <button class="tab-btn" onclick="switchTab('reset')">Reset Password</button>
        </div>

        <!-- Create Account Form -->
        <form id="createForm" onsubmit="handleSubmit(event, 'create')">
          <div class="form-group">
            <label for="createUsername"><i class="fa-solid fa-user"></i> Username</label>
            <div class="input-wrapper">
              <input type="text" id="createUsername" required placeholder="3-16 alphanumeric characters">
            </div>
          </div>
          <div class="form-group">
            <label for="createPassword"><i class="fa-solid fa-lock"></i> Password</label>
            <div class="input-wrapper">
              <input type="password" id="createPassword" required placeholder="4-16 characters">
            </div>
          </div>
          <div class="form-group">
            <label for="createConfirm"><i class="fa-solid fa-shield-halved"></i> Confirm Password</label>
            <div class="input-wrapper">
              <input type="password" id="createConfirm" required placeholder="Confirm your password">
            </div>
          </div>
          <button type="submit" class="submit-btn" id="createBtn">
            <div class="spinner" id="createSpinner"></div>
            <span id="createBtnText">Create Account</span>
          </button>
        </form>

        <!-- Reset Password Form -->
        <form id="resetForm" class="hidden" onsubmit="handleSubmit(event, 'reset')">
          <div class="form-group">
            <label for="resetUsername"><i class="fa-solid fa-user"></i> Username</label>
            <div class="input-wrapper">
              <input type="text" id="resetUsername" required placeholder="Your username">
            </div>
          </div>
          <div class="form-group">
            <label for="resetCurrentPassword"><i class="fa-solid fa-key"></i> Current Password</label>
            <div class="input-wrapper">
              <input type="password" id="resetCurrentPassword" required placeholder="Enter current password">
            </div>
          </div>
          <div class="form-group">
            <label for="resetNewPassword"><i class="fa-solid fa-lock"></i> New Password</label>
            <div class="input-wrapper">
              <input type="password" id="resetNewPassword" required placeholder="4-16 characters">
            </div>
          </div>
          <div class="form-group">
            <label for="resetConfirm"><i class="fa-solid fa-shield-halved"></i> Confirm New Password</label>
            <div class="input-wrapper">
              <input type="password" id="resetConfirm" required placeholder="Confirm new password">
            </div>
          </div>
          <button type="submit" class="submit-btn" id="resetBtn">
            <div class="spinner" id="resetSpinner"></div>
            <span id="resetBtnText">Reset Password</span>
          </button>
        </form>

        <div class="status-msg" id="statusBox"></div>
      </div>
    </div>

    <!-- Bouncing Scroll Indicator -->
    <div class="scroll-indicator" onclick="scrollToGuide()">
      <span>Setup & How To Play</span>
      <i class="fa-solid fa-chevron-down bounce"></i>
    </div>
  </section>

  <!-- Installation Guide Section -->
  <section class="guide-section" id="install-guide">
    <div class="guide-header">
      <h2 class="guide-title"><span class="logo-purple">HOW TO</span> <span class="logo-orange">PLAY</span></h2>
      <p class="guide-subtitle">Follow these 3 quick steps to setup your client and enter the SpellDraft realm</p>
    </div>

    <div class="guide-grid">
      <!-- Step 1 -->
      <div class="guide-card">
        <div class="step-badge"><i class="fa-solid fa-1"></i> Step One</div>
        <h3 class="card-title"><i class="fa-solid fa-gamepad"></i> 1. WoW Client (3.3.5a)</h3>
        <p class="card-desc">If you do not have a clean World of Warcraft: Wrath of the Lich King (3.3.5a) client, download a compatible version from ChromieCraft.</p>
        <a href="https://www.chromiecraft.com/downloads/" target="_blank" rel="noopener" class="guide-btn">
          <i class="fa-solid fa-download"></i> Get 3.3.5a Client
        </a>
      </div>

      <!-- Step 2 -->
      <div class="guide-card">
        <div class="step-badge"><i class="fa-solid fa-2"></i> Step Two</div>
        <h3 class="card-title"><i class="fa-solid fa-file-zipper"></i> 2. SpellDraft Patch</h3>
        <p class="card-desc">Download <code>wow-client.zip</code> from our official releases. Extract the zip directly into your WoW 3.3.5a client root folder (copying <code>Interface/</code> and <code>Data/patch-P.mpq</code>).</p>
        <a href="https://github.com/bdodroid/mod-spelldraft/releases" target="_blank" rel="noopener" class="guide-btn guide-btn-purple">
          <i class="fa-solid fa-cloud-arrow-down"></i> Download wow-client.zip
        </a>
        <div class="tip-box">
          <i class="fa-solid fa-circle-info"></i>
          <span>Fully close and relaunch your game client after copying the patch files.</span>
        </div>
      </div>

      <!-- Step 3 -->
      <div class="guide-card">
        <div class="step-badge"><i class="fa-solid fa-3"></i> Step Three</div>
        <h3 class="card-title"><i class="fa-solid fa-network-wired"></i> 3. Set Realmlist</h3>
        <p class="card-desc">Open <code>Data/enUS/realmlist.wtf</code> (or <code>enGB</code>) in any text editor and set its contents to our server address:</p>
        <div class="code-box">
          <code id="realmlistCode">set realmlist realm.spelldraft.com</code>
          <button class="copy-btn" onclick="copyRealmlist(this)">
            <i class="fa-solid fa-copy"></i> <span>Copy</span>
          </button>
        </div>
      </div>
    </div>

    <div class="footer">
      <a href="https://spelldraft.com" target="_blank" class="footer-link">SpellDraft</a> &copy; 2026
    </div>
  </section>

  <script>
    function scrollToGuide() {
      document.getElementById('install-guide').scrollIntoView({ behavior: 'smooth' });
    }

    function copyRealmlist(btn) {
      const text = document.getElementById('realmlistCode').innerText;
      navigator.clipboard.writeText(text).then(() => {
        const span = btn.querySelector('span');
        const originalText = span.innerText;
        span.innerText = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => {
          span.innerText = originalText;
          btn.classList.remove('copied');
        }, 2000);
      });
    }

    function switchTab(type) {
      const tabBtns = document.querySelectorAll('.tab-btn');
      const createForm = document.getElementById('createForm');
      const resetForm = document.getElementById('resetForm');
      const statusBox = document.getElementById('statusBox');

      statusBox.style.display = 'none';

      if (type === 'create') {
        tabBtns[0].classList.add('active');
        tabBtns[1].classList.remove('active');
        createForm.classList.remove('hidden');
        resetForm.classList.add('hidden');
      } else {
        tabBtns[0].classList.remove('active');
        tabBtns[1].classList.add('active');
        createForm.classList.add('hidden');
        resetForm.classList.remove('hidden');
      }
    }

    async function handleSubmit(event, type) {
      event.preventDefault();
      
      const statusBox = document.getElementById('statusBox');
      const spinner = document.getElementById(type + 'Spinner');
      const btnText = document.getElementById(type + 'BtnText');
      const btn = document.getElementById(type + 'Btn');

      statusBox.style.display = 'none';

      let payload = {};
      
      if (type === 'create') {
        const username = document.getElementById('createUsername').value;
        const password = document.getElementById('createPassword').value;
        const confirm = document.getElementById('createConfirm').value;

        if (password !== confirm) {
          showStatus("Passwords do not match.", "error");
          return;
        }

        payload = { username, password };
      } else {
        const username = document.getElementById('resetUsername').value;
        const currentPassword = document.getElementById('resetCurrentPassword').value;
        const newPassword = document.getElementById('resetNewPassword').value;
        const confirm = document.getElementById('resetConfirm').value;

        if (newPassword !== confirm) {
          showStatus("New passwords do not match.", "error");
          return;
        }

        payload = { username, currentPassword, newPassword };
      }

      // Start Loading UI
      spinner.style.display = 'block';
      btnText.style.opacity = '0.5';
      btn.disabled = true;

      try {
        const endpoint = type === 'create' ? '/api/create-account' : '/api/reset-password';
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (response.ok && data.success) {
          showStatus(type === 'create' ? "Account created successfully! You can now log in." : "Password reset successfully!", "success");
          event.target.reset();
        } else {
          showStatus(data.error || "An error occurred.", "error");
        }
      } catch (err) {
        showStatus("Connection error. Is the server running?", "error");
      } finally {
        // Stop Loading UI
        spinner.style.display = 'none';
        btnText.style.opacity = '1';
        btn.disabled = false;
      }
    }

    function showStatus(msg, type) {
      const statusBox = document.getElementById('statusBox');
      statusBox.textContent = msg;
      statusBox.className = 'status-msg ' + type;
      statusBox.style.display = 'block';
    }
  </script>
</body>
</html>
`;

function resolvePath(filePath: string): string {
  if (isAbsolute(filePath)) return filePath;
  return join(currentDir, filePath);
}

let sslCert = "";
let sslKey = "";

if (useSsl) {
  try {
    sslCert = await Deno.readTextFile(resolvePath(certPath));
    sslKey = await Deno.readTextFile(resolvePath(keyPath));
    console.log(`[Portal] Loaded SSL cert (${certPath}) and key (${keyPath}).`);
  } catch (err: any) {
    console.error(`[Portal] Failed to load SSL files: ${err.message}`);
    console.error("[Portal] Check cert_path and key_path in config.yml.");
    Deno.exit(1);
  }
}

if (useSsl && redirectHttp) {
  console.log(`[Portal] Starting HTTP redirect server on port ${httpRedirectPort} -> HTTPS (port ${serverPort})`);
  Deno.serve({ port: httpRedirectPort }, (req: Request) => {
    const url = new URL(req.url);
    url.protocol = "https:";
    const hostHeader = req.headers.get("host")?.split(":")[0] || url.hostname;
    url.hostname = hostHeader;
    url.port = serverPort === 443 ? "" : serverPort.toString();
    return Response.redirect(url.toString(), 301);
  });
}

const serveOptions = useSsl
  ? { port: serverPort, cert: sslCert, key: sslKey }
  : { port: serverPort };

console.log(`[Portal] Starting ${useSsl ? "HTTPS" : "HTTP"} server on port ${serverPort}...`);

Deno.serve(serveOptions, async (req: Request) => {
  const url = new URL(req.url);

  // Serve Single Page Application
  if (req.method === "GET" && url.pathname === "/") {
    return new Response(HTML_CONTENT, {
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  }

  // API Endpoint: Create Account
  if (req.method === "POST" && url.pathname === "/api/create-account") {
    try {
      const body = await req.json();
      const { username, password } = body;

      if (!username || !password) {
        return Response.json({ error: "Username and password are required." }, { status: 400 });
      }

      const cleanUser = username.trim();
      const cleanPass = password.trim();

      if (!/^[a-zA-Z0-9]{3,16}$/.test(cleanUser)) {
        return Response.json({ error: "Username must be alphanumeric and between 3 and 16 characters." }, { status: 400 });
      }

      if (cleanPass.length < 4 || cleanPass.length > 16) {
        return Response.json({ error: "Password must be between 4 and 16 characters." }, { status: 400 });
      }

      // Check if user already exists
      const checkSql = `SELECT COUNT(*) FROM ${dbAuthName}.account WHERE username = '${cleanUser.toUpperCase()}';`;
      const count = await runQuery(checkSql);
      if (parseInt(count, 10) > 0) {
        return Response.json({ error: "Username already exists." }, { status: 400 });
      }

      // Generate Salt and Verifier
      const salt = new Uint8Array(32);
      crypto.getRandomValues(salt);
      const verifier = await calculateVerifier(cleanUser, cleanPass, salt);

      const saltHex = Array.from(salt).map(b => b.toString(16).padStart(2, "0")).join("");
      const verifierHex = Array.from(verifier).map(b => b.toString(16).padStart(2, "0")).join("");

      // Insert Account (Security level is 0/non-GM by default)
      const insertSql = `INSERT INTO ${dbAuthName}.account (username, salt, verifier, email, reg_mail) VALUES ('${cleanUser.toUpperCase()}', X'${saltHex}', X'${verifierHex}', '${cleanUser.toLowerCase()}@local.lan', '${cleanUser.toLowerCase()}@local.lan');`;
      await runQuery(insertSql);

      console.log(`[Portal] Account created: ${cleanUser.toUpperCase()}`);
      return Response.json({ success: true });
    } catch (e) {
      console.error(e);
      const err = e as any;
      return Response.json({ error: err.message || "Failed to create account." }, { status: 500 });
    }
  }

  // API Endpoint: Reset Password
  if (req.method === "POST" && url.pathname === "/api/reset-password") {
    try {
      const body = await req.json();
      const { username, currentPassword, newPassword } = body;

      if (!username || !currentPassword || !newPassword) {
        return Response.json({ error: "All fields are required." }, { status: 400 });
      }

      const cleanUser = username.trim();
      const cleanCurPass = currentPassword.trim();
      const cleanNewPass = newPassword.trim();

      if (!/^[a-zA-Z0-9]{3,16}$/.test(cleanUser)) {
        return Response.json({ error: "Invalid username format." }, { status: 400 });
      }

      if (cleanNewPass.length < 4 || cleanNewPass.length > 16) {
        return Response.json({ error: "New password must be between 4 and 16 characters." }, { status: 400 });
      }

      // Fetch salt and verifier
      const getSql = `SELECT Hex(salt), Hex(verifier) FROM ${dbAuthName}.account WHERE username = '${cleanUser.toUpperCase()}';`;
      const result = await runQuery(getSql);
      if (!result) {
        return Response.json({ error: "Account not found." }, { status: 404 });
      }

      const [saltHex, verifierHex] = result.split(/\s+/);
      if (!saltHex || !verifierHex) {
        return Response.json({ error: "Account data corrupt." }, { status: 500 });
      }

      const saltBytes = new Uint8Array(saltHex.match(/.{1,2}/g)!.map(byte => parseInt(byte, 16)));

      // Verify current password
      const computedVerifier = await calculateVerifier(cleanUser, cleanCurPass, saltBytes);
      const computedVerifierHex = Array.from(computedVerifier).map(b => b.toString(16).padStart(2, "0")).join("").toUpperCase();

      if (computedVerifierHex !== verifierHex.toUpperCase()) {
        return Response.json({ error: "Incorrect current password." }, { status: 400 });
      }

      // Generate new salt and verifier
      const newSalt = new Uint8Array(32);
      crypto.getRandomValues(newSalt);
      const newVerifier = await calculateVerifier(cleanUser, cleanNewPass, newSalt);

      const newSaltHex = Array.from(newSalt).map(b => b.toString(16).padStart(2, "0")).join("");
      const newVerifierHex = Array.from(newVerifier).map(b => b.toString(16).padStart(2, "0")).join("");

      // Update Database
      const updateSql = `UPDATE ${dbAuthName}.account SET salt = X'${newSaltHex}', verifier = X'${newVerifierHex}' WHERE username = '${cleanUser.toUpperCase()}';`;
      await runQuery(updateSql);

      console.log(`[Portal] Password reset for: ${cleanUser.toUpperCase()}`);
      return Response.json({ success: true });
    } catch (e) {
      console.error(e);
      const err = e as any;
      return Response.json({ error: err.message || "Failed to reset password." }, { status: 500 });
    }
  }

  return new Response("Not Found", { status: 404 });
});
