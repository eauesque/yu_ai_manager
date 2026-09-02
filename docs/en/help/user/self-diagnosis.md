# Self-Diagnosis and Reporting When Something Goes Wrong

If YU AI Manager stops working or behaves unexpectedly, you can gather clues about the cause yourself and report them to developers. No command-line or Git knowledge required.

## 1. First, press "Report a Problem"

1. Open the app in your browser and select **Diagnostics** from the menu in the top-right corner.
2. Click the **"Report a Problem"** button.
3. After a moment, a folder named `repair/2026XXXX-HHMMSS/` will be created. It contains the following automatic report set:
   - Environment information, recent logs, and settings (personal information and tokens are already masked)
   - Prompt templates for AI-assisted repair

Click **"Open Folder"** to open the folder in Explorer. Click **"Make ZIP"** to combine everything into a single zip file.

> About masking: usernames, emails, API key-like strings, and IP addresses are automatically replaced with `<REDACTED>`. Since this is not perfect, please review the contents before sharing.

## 2. Share it

Attach the ZIP file to developers, support contacts, or Discord. The **"Copy Message for Discord"** button also prepares a short message ready to paste.

## 3. Temporary fixes you can try yourself

### 3-A. Environment check (doctor)

Click the **"Environment Diagnostics"** button on the Diagnostics screen. It displays the status of Python, GPU, DB, and more in markdown format. Try the `fix_hint` (fix hint) items listed under any red (ERROR) or yellow (WARN) items in order.

### 3-B. Restart in Safe Mode

If normal startup fails, the app crashes, or loading hangs indefinitely, you can start in **Safe Mode**.

- Windows: Double-click `start.bat --safe-mode` (or add ` --safe-mode` to the end of your shortcut)
- macOS / Linux: Run `./start.sh --safe-mode` from the terminal

In Safe Mode, you can do the following:

- Check settings
- Use "Report a Problem" and "Environment Diagnostics"
- Apply a **safe update package (update.zip)** provided by developers (file replacement only; automatic repair scripts are disabled)

Safe Mode continues until the next normal startup. Simply reboot normally to return to normal mode.

### 3-C. Apply an update package (update.zip)

If you receive `update.zip` from developers:

1. Go to Diagnostics screen → **"Apply Update"** section
2. Select the file and confirm the **Verify** indicator turns green
3. Click **Apply** in the confirmation dialog
4. Follow the displayed instructions to restart

> Never apply a zip file with a red Verify indicator. It may be tampered with or intended for a different application.

If anything goes wrong, you can restore to the previous state with **"Rollback Previous Update"**.

## 4. Things you should not do

- Paste raw logs (without masking) to social media or public forums
- Apply `update.zip` files from unknown sources
- Manually edit files in the `data/` folder or `tags.db`

## If you still need help

If the problem persists, report it together with the ZIP file and a description of "what actions caused what to happen." On the developer side, `prompt_for_codex.md` / `prompt_for_claude.md` will be consulted to generate a fix patch proposal.
