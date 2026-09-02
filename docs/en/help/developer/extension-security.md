# Extension Security Model

This software is designed so that **anyone can create Extensions using AI**.
At the same time, it has built-in mechanisms to protect your system from malicious Extensions.

This page explains how those mechanisms work.
It is written so that even non-technical users can understand it.

---

## Fundamental Principle

Extensions run inside a **protected sandbox**.

Within this sandbox, Extensions have considerable freedom.
Adding pages, displaying data, processing images — that's what Extensions are for.

However, things **outside** the sandbox — the system core, other Extensions, all the files on your PC — are out of reach.
This is not "prohibited by rules." It is **physically unreachable** by design.

---

## Permission Model

Extensions need **permissions** to do anything.

The permission model is designed the same way as smartphone app permissions.

- A camera app requesting access to the camera is perfectly natural
- A camera app requesting access to your contacts is suspicious

Extensions work the same way. If a watermarking Extension is requesting network access, you should be suspicious.

### Approval Flow

1. You install an Extension (or have AI create one for you)
2. YU AI Manager automatically scans the code and inspects what it is trying to do
3. A list of permissions the Extension is requesting is displayed
4. **The Extension will not run until you approve it**

Read the information displayed on the approval screen carefully.
Pay particular attention to permissions highlighted in red.

### After Approving Permissions

The Extension operates within the scope of the permissions you approved.
Permissions you did not approve are completely unavailable to the Extension, no matter what it tries.
It is not "denied when attempted" — it simply **cannot see them at all**.

---

## Three Independent Monitors

Your Extensions are monitored by three independent mechanisms.
These three are independent of each other — even if one is fooled, the other two remain functional.

### 1. Code Scanning

Extension code is automatically analyzed to detect dangerous patterns.
External program execution, direct database manipulation, dynamic code execution — all of these are detected immediately.

### 2. Permission Enforcement

When an Extension calls an API, the system verifies whether it holds a valid "capability token."
Capability tokens are issued only when you approve the corresponding permission.
Extensions cannot forge their own capability tokens.

### 3. Audit Log

All Extension operations are recorded.
These records are stored in an independent location that the Extension itself cannot modify.

If an anomaly is detected — for example, if the Extension attempts an action it did not declare — a notification is automatically sent, and the Extension's capability token is revoked if necessary.

---

## Creating Extensions with AI

When you create an Extension from Claude Desktop, the created Extension is automatically registered at **the most restrictive permission level**.

This is the same principle as not handing a new employee the keys to the vault on their first day.
Start with limited permissions, verify there are no problems, then add permissions as needed.

### What AI-Created Extensions Can Do

**Available without approval:**
- Reading and displaying data
- Adding pages to the UI
- Adding settings screens

**Requires approval:**
- Communication with external services
- Writing to the database
- Reading files

**Impossible regardless of what is attempted:**
- Reading or modifying the system core
- Reading or modifying other Extensions
- Executing external programs
- Forging capability tokens

---

## Periodic Inspection

An Extension is not done once it has been approved.

If the code is modified and the amount of change exceeds a certain threshold, **re-approval** is required.
This prevents the tactic of making small incremental changes until the Extension is something completely different from what was originally approved.

Additionally, automated code re-inspections are performed periodically.
Even if no issues existed at the time of approval, new inspection rules may uncover problems.

---

## What You Must Do

1. **Read the permission approval screen properly** — understand what is being requested before you approve
2. **Reject unnatural permission requests** — image processing should not need network access
3. **Do not ignore notifications** — check them when anomalies are detected
4. **Do not install Extensions from untrusted sources** — this should be obvious

Conversely, if you do just that, you are safe.
The system handles the rest.
