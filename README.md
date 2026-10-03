<div align="center">

```
███████╗████████╗██████╗  █████╗ ████████╗ █████╗ ███████╗ ██████╗ █████╗ ███╗   ██╗
██╔════╝╚══██╔══╝██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗██╔════╝██╔════╝██╔══██╗████╗  ██║
███████╗   ██║   ██████╔╝███████║   ██║   ███████║███████╗██║     ███████║██╔██╗ ██║
╚════██║   ██║   ██╔══██╗██╔══██║   ██║   ██╔══██║╚════██║██║     ██╔══██║██║╚██╗██║
███████║   ██║   ██║  ██║██║  ██║   ██║   ██║  ██║███████║╚██████╗██║  ██║██║ ╚████║
╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝
```

### `// TEMPORAL ATTACK-SURFACE RECONSTRUCTION ENGINE //`
#### *Passive-first OSINT · Archive Forensics · Secret Discovery · Attack-Surface Cartography*

<br/>

[![Build](https://img.shields.io/badge/build-passing-00ffa3?style=for-the-badge&logo=githubactions&logoColor=white&labelColor=0a0e14)](#)
[![Python](https://img.shields.io/badge/python-3.9%2B-00c2ff?style=for-the-badge&logo=python&logoColor=white&labelColor=0a0e14)](#)
[![License](https://img.shields.io/badge/license-MIT-ff2d95?style=for-the-badge&labelColor=0a0e14)](#license)
[![Capabilities](https://img.shields.io/badge/capabilities-205%2B-9d4dff?style=for-the-badge&labelColor=0a0e14)](#the-capability-catalog)
[![Phases](https://img.shields.io/badge/pipeline%20phases-47-f5a623?style=for-the-badge&labelColor=0a0e14)](#the-47-phase-pipeline)
[![Mode](https://img.shields.io/badge/mode-CLI%20%2B%20TUI-39ff14?style=for-the-badge&labelColor=0a0e14)](#interfaces)
[![Ethics](https://img.shields.io/badge/scope-authorized%20use%20only-ff3b3b?style=for-the-badge&labelColor=0a0e14)](#-legal--ethical-use)

<br/>

**[Overview](#-overview)** •
**[Architecture](#-system-architecture)** •
**[Capabilities](#the-capability-catalog)** •
**[Offense](#-offensive-capability-profile)** •
**[Defense](#-defensive--protective-behavior)** •
**[Pipeline](#the-47-phase-pipeline)** •
**[Install](#-installation)** •
**[Usage](#-usage)** •
**[Reports](#-report-artifacts)** •
**[Threat Model](#-threat-model)** •
**[Ethics](#-legal--ethical-use)** •
**[Roadmap](#-roadmap)**

</div>

<br/>

<div align="center">

### ░▒▓█ SIGNAL LOCK ACQUIRED █▓▒░

*StrataScan does not attack the present. It interrogates the past to predict the present's weaknesses.*

</div>

---

## 📖 Table of Contents

1. [Overview](#-overview)
2. [Why StrataScan Exists](#-why-stratascan-exists)
3. [System Architecture](#-system-architecture)
4. [Design Philosophy](#-design-philosophy)
5. [The Capability Catalog](#the-capability-catalog)
   - [5.1 Archive & Historical Intelligence](#51-archive--historical-intelligence)
   - [5.2 Network, DNS & Transport Security](#52-network-dns--transport-security)
   - [5.3 Subdomain & Surface Expansion](#53-subdomain--surface-expansion)
   - [5.4 Content, Document & Binary Forensics](#54-content-document--binary-forensics)
   - [5.5 Client-Side & Application Intelligence](#55-client-side--application-intelligence)
   - [5.6 Secret, Credential & Leak Detection](#56-secret-credential--leak-detection)
   - [5.7 Correlation, Diffing & Temporal Analytics](#57-correlation-diffing--temporal-analytics)
   - [5.8 Reporting & Evidence Management](#58-reporting--evidence-management)
6. [Offensive Capability Profile](#-offensive-capability-profile)
7. [Defensive & Protective Behavior](#-defensive--protective-behavior)
8. [The 47-Phase Pipeline](#the-47-phase-pipeline)
9. [Data Flow & Sequence Diagrams](#-data-flow--sequence-diagrams)
10. [Interfaces](#interfaces)
11. [Installation](#-installation)
12. [Usage](#-usage)
13. [Command Reference](#-command-reference)
14. [Report Artifacts](#-report-artifacts)
15. [Threat Model](#-threat-model)
16. [Operational Security Notes](#-operational-security-notes)
17. [Legal & Ethical Use](#-legal--ethical-use)
18. [Comparison to Adjacent Tooling](#-comparison-to-adjacent-tooling)
19. [Roadmap](#-roadmap)
20. [Contributing](#-contributing)
21. [FAQ](#-faq)
22. [License](#license)

---

## 🛰 Overview

**StrataScan** is a reconnaissance and attack-surface reconstruction framework built around a simple but under-exploited insight: *most security posture leaks through history, not through the present moment*. A target's current website might be clean. Its **archived** versions — snapshotted by the Wayback Machine, Common Crawl, and archive.today over years of crawls — routinely are not.

StrataScan treats the public web archive ecosystem as a **forensic timeline of an organization's infrastructure**, layering live-internet verification on top of it. It walks every historical snapshot of a domain, every subdomain that was ever archived, every JavaScript bundle that was ever crawled, every `.env`, `wp-config.php`, source map, and document that an archive crawler ever touched — and cross-references all of it against what is *still true today*.

The result is a single engine that performs:

- **Attack-surface cartography** — every subdomain, endpoint, API route, and form that ever existed for a target, whether it is still live or not.
- **Historical secret archaeology** — credentials, tokens, and keys that were briefly exposed and then "fixed," but remain frozen forever in an archive snapshot.
- **Infrastructure drift analysis** — how DNS, TLS, headers, and CMS fingerprints changed over the target's lifetime, exposing migration windows and legacy exposure.
- **Deletion forensics** — content that was deliberately taken down, when it disappeared, and whether it disappeared because of a security incident.
- **Live-state verification** — every historical finding is checked against the present-day target, separating theoretical risk from exploitable, current risk.

StrataScan is simultaneously an **offensive reconnaissance accelerator** (it answers "what is this target's real, historical, and current attack surface?") and a **defensive audit instrument** (it answers "what has my organization ever leaked, and is it still leaking?"). The two framings are not in tension — they are the same engine pointed at the same data, read by different people with different intent.

> **Operating principle:** StrataScan performs *zero exploitation*. It does not deliver payloads, does not attempt authentication bypass, does not brute-force credentials against live services, and does not modify any remote system. Every active capability it performs — port checks, header pulls, zone-transfer attempts, subdomain brute-forcing — is a **read-only verification** of something already discoverable through public archives, public DNS, or a target's own public-facing configuration.

<br/>

<div align="center">

```
┌──────────────────────────────────────────────────────────────────────┐
│   PAST                         PRESENT                      FUTURE   │
│   ════                         ═══════                      ══════   │
│   Wayback / CDX    ─────▶   Live Verification   ─────▶   Risk Score  │
│   Common Crawl              DNS / TLS / HTTP              Severity   │
│   archive.today              Header Diffing                Report    │
│   Certificate Logs          Secret Scanning              Evidence    │
└──────────────────────────────────────────────────────────────────────┘
```

</div>

---

## 🎯 Why StrataScan Exists

Traditional reconnaissance tooling answers: *"What does this target look like right now?"*

StrataScan answers a different, usually more revealing question: *"What has this target **ever** looked like, and which of those exposures are still reachable, still resolvable, or still cached somewhere an attacker can retrieve?"*

| Traditional Recon | StrataScan |
|---|---|
| Crawls the live site once | Reconstructs every historical state of the site |
| Finds what's exposed *today* | Finds what was *ever* exposed, and checks if it still matters |
| Misses rotated/deleted secrets | Secrets frozen in archive snapshots are **permanent** findings |
| Subdomain lists from brute-force only | Subdomains sourced from 10+ years of crawl history **plus** brute-force |
| No concept of "deletion" as a signal | Deliberate deletions are fingerprinted and dated — a signal in themselves |
| Point-in-time | Longitudinal, diffable, baseline-able across scans |

This asymmetry — defenders forget, but archives don't — is the core thesis of the tool.

