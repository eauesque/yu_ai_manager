# Development Guide

This is a guide to extend, customize, and debug this software on your own.

---

## Basic Philosophy

This software was built by a human giving instructions and complaints to an AI agent while working.
Every line of code was written by AI.

That means: **you can do the same thing.**

You don't need to be a programmer. You don't need to ask the creator.
All you need is the ability to think clearly, explain precisely, and persist.

You don't need that black screen with white text scrolling by.
First, discard that fixed idea and bias.
We live in a good age where everything can be done visually.

---

## Before You Start

### Read These First

If you are planning to add or modify APIs, read [API Security Guidelines](docs/ja/help/developer/api-security.md) first.

- You cannot open things too widely even with `GET`
- What to keep for `read-only API key`
- Standards for localhost detection, secrets, config APIs, and validation

If you add routes without reading this guideline, you will repeat the same accidents.

### Get YU AI Manager

Just run the installer.
Then follow the screen instructions. That is it.

Remember just one thing:
right now there is no automatic updates. When a new version comes out, run the installer the same way and replace the old one.

### Connect MCP

Open YU AI Manager and check **Settings → API Keys**.
There is a section called **MCP Connection Snippet**. Copy the JSON there with one click.

Next, open Claude Desktop and go to **Settings (gear icon) → Developer → Edit Config**.
Paste the JSON you copied, save, and restart Claude Desktop.

That is it. That is all it takes to connect.

About API Keys: If you are setting it up manually instead of using the Snippet, create a key in **Settings → API Keys**. Keys starting with `sk_...` appear only once right after creation. Always copy them at that moment.

### Verify Your Environment

1. Is YU AI Manager running? — Start it and check
2. Is the MCP server running? — Check in Claude Desktop settings
3. Do you have an AI agent available? — Claude Desktop or equivalent

That is it. Setup complete.

### Enable Git Hooks (for git development/push nodes only, once after cloning)

If you are managing this repository with git (committing and pushing), run this once after cloning.

```bash
git config core.hooksPath .githooks
```

This enables the pre-commit and pre-push checks (lint, type checking, various drift checks) in `.githooks/`.
If you do not set this, the checks will be dormant. Even if the logic is correct, it will not work as a checkpoint, so drift can slip in unchecked (this actually happened before with document indexes drifting massively).

You can verify it like this. `.githooks` should be returned.

```bash
git config --get core.hooksPath
```

Each node needs to do this once (this git setting is local per clone, not shared).

---

## Use MCP

If the MCP server is running, you must use it.

YU AI Manager has help endpoints for AI agents.
Through MCP, you can directly access databases, logs, settings, and **the source code itself**.
Showing it directly through MCP is faster and more accurate than explanations through the browser UI.

Just tell the AI agent:

```
Please connect to YU AI Manager is MCP server.
Check the help endpoints and tell me what you can do.
```

### Reading Source Code Through MCP

YU AI Manager has a source code reference tool built in.

- **source_tree** — Display file structure in a tree
- **source_read** — Read the contents of a specified file
- **source_search** — Full-text search across the entire source code

AI agents can use these to read the source directly in chat.
There is no need for procedures like opening folders in GitHub Desktop and handing them to Claude Code.

When you want to have source reviewed, say:

```
Check the file structure with source_tree,
read related files with source_read.
```

---

## Adding Features

Do not ask the creator for feature additions to core. The answer is no.

Use the extension system.
**All work is done entirely in Claude Desktop chat.** You do not need to leave your desk.

### Step 1: Decide What to Build in Chat

Do not just say make it.

First, organize your thoughts in Claude Desktop chat about what you want to do.
I want this feature. I want to automate this operation. talk it through with the AI while articulating it.

When you are clear about what to build, say:

```
Please create a specification document.
```

The AI creates a spec.

### Step 2: Have It Built Right There

You do not need to move to a workspace. Continue in the same chat:

```
The spec is ready. Please implement it as an extension.
Create the template with create_extension, write code with write_extension_file.
Verify there are no problems with validate_extension.
```

The AI directly creates and edits extension files through MCP.
Everything is completed on your desk with just chat.

**However, whether to follow it or not is your decision.**

Use the AI is suggestions as reference. But you have no obligation to follow them.
You have the purpose, not the AI.
Do not hand over your judgment.

Once agreed, have it implemented. If there is something wrong, say so. Iterate until it works.

Once the extension is done, restart YU AI Manager.
A new extension will appear in Settings → Extensions. Check the permissions and approve it to make it work.

### Step 3: Share It (Optional)

You are welcome to share something useful.
Whether others use it is up to them. We made, you decide.

---

## Reporting Bugs

### Step 1: Get Logs

Open YU AI Manager and check **Settings → Logs**.
Copy the logs before and after the problem occurred.

If you cannot find the logs, explain the following precisely:
- What did you do?
- What did you think would happen?
- What actually happened?

Something is weird is not an explanation.

### Step 2: Take a Screenshot or Video

If the problem is visual and you cannot explain it in words:

- **Screenshot**: `Windows + Shift + S`
- **Screen recording**: `Windows + Shift + R`

For Mac: Screenshot is `Cmd + Shift + 4`, recording is `Cmd + Shift + 5`

You can drag images straight into chat.
A single image is far more valuable than a thousand confused words.

**You can also show what is happening inside the browser.**

Press `F12` in the browser. A panel opens on the side.
You do not need to understand it yet. Just remember it.

When an AI agent tells you open F12 and check for errors, that is here.
If you see red and yellow things, select and copy everything, then pass it straight to the agent.
That is all.

### Step 3: Post on GitHub

Put the logs and screenshots in a GitHub issue.
The creator might see it. Someday. No guarantees.

If you want to fix it right now, go to the next section.

---

## Fix Bugs Yourself (Recommended)

It is faster than waiting for the creator. Really.

### Tools

**Claude Desktop chat + MCP.** That is all.

Thinking, investigating, fixing everything is done here.
You can read and write extension files through MCP and run code scans too.
You do not need anything else.

### Debug Flow

Explain the problem in Claude Desktop chat.
Logs, screenshots, what you were doing, what you expected throw it all in.

With MCP, the AI can read the source directly and check the status. Tell it:

```
When I click [X] in YU AI Manager, [Y] happens. It should become [Z].
Check the backend logs and status through MCP.
Read related source code with source_tree and source_read.
Identify the cause and fix it.
```

The AI identifies the cause and presents a fix.
Apply the fix with write_extension_file, verify with validate_extension.
Restart YU AI Manager and test that it works.

### What to Pass to the AI Agent

1. **Error logs** The actual text, not a paraphrase
2. **Screenshot or video** If it is a visual bug
3. **What you were doing** The operation when the problem occurred
4. **What you expected** How it should have worked
5. **Purpose** Not just the symptom, but why it is needed

### When the AI Does not Understand

AI is not human. It will not always fill in the parts you left out.

- It might ask back answer precisely
- It might not work as you thought tell it exactly what is different
- If irrelevant answers keep coming, try different wording
- If you realize information is missing, add it
- If words do not convey it, pass the relevant files

This is iterative work. It works. Keep going.

It is basically the same as giving instructions to people. Except reputation, mood, and emotion do not matter, so it is much simpler.

---

## Clean Up What is Visible First

Fix the invisible bugs after cleaning up the visible mess.
Spreading pesticide on a weedy field does not make sense. First, level the ground.

You have implemented something. It looks like it works. But whether the wrapper is really working correctly is something you often cannot figure out just by clicking your mouse. You overlook things. When you get used to it, you stop noticing.

Use Playwright. AI agents will actually operate the browser and check the UI thoroughly.

Tell the AI agent:

```
Use Playwright to operate YU AI Manager and do UI/UX bug finding,
and evaluation and improvement suggestions from a UX perspective.
```

The AI will move the browser and pick up collapsed layouts, non-functional buttons, unnatural operation flows, unclear navigation and report them. You will get not just bug fixes but suggestions like this is hard to use.

Whether you accept them is your call, but listen to everything once.

Once this is done, move on to the invisible part.

---

## Kill All Invisible Bugs

You can fix visible bugs. The problem is invisible ones.

Think about under the refrigerator. There is one cockroach you can see from the front.
But when you move the refrigerator, there's another world underneath.
Software is the same. Bugs that don't show in logs, bugs that don't reproduce, bugs that nobody's stepped on yet — they definitely exist. It's almost impossible for humans to find them all.

MCP debug is the pesticide for that.

### How to Do It

Tell the AI agent:

```
Connect to YU AI Manager is MCP and debug the entire source code.
Understand the file structure with source_tree, read them in order with source_read.
Report all potential bugs, consistency issues, and places that could error.
```

The AI reads the source, checks the actual state of the system through MCP, and unearths hidden problems.
When the report comes, have them fix it.

### Ask Relentlessly

Do not stop after one round.

When the AI says that is all, reply:

```
Is there anything else?
```

Repeat this. The AI will dig a little deeper each time.
When they really say there is nothing else, it is probably actually nothing.

Stubbornness is not a virtue. But persistence against bugs is justice.

---

## Do a Security Review Before Publishing

If you are planning to publish an extension, pass it through a security review first.

It is not hard. It is quick.

Just tell the AI agent:

```
Do a security review of this extension (or code).
Check the settings and sandbox information of YU AI Manager through MCP.
Read the relevant files with source_read and report all problems.
```

YU AI Manager has a code scanning feature for extensions built in.
It runs automatically when loading an extension. Restart the server and have it load the extension once.

The scan automatically detects:
- Dangerous modules (`subprocess`, `ctypes`, `importlib`)
- Direct DB operations (`sqlite3` use SandboxedDB)
- Dynamic code execution (`eval`, `exec`, `__import__`)
- Network access (`requests`, `urllib`, etc.)

If there are serious problems, loading the extension is rejected. If it is just warnings, it loads, but is logged.
Check the logs and fix all problems.

If you are releasing code that runs on someone else is system, take that much responsibility.

For details on the security model, read [extension Security Model](docs/ja/help/developer/extension-security.md).

---

## Do not Touch Core

If you use an extension, you stay in a protected world.
If you change the thing that protects core and built-in extensions never forget that it affects everything, and **you yourself might be harmed**.

If you are using the Tauri version, or even if not, you cannot touch core and built-in extensions from Claude Desktop.
It is not that you should not it is **impossible as a capability**.
The path does not exist in the API. You cannot touch what you cannot see.

If you really need to touch them, use the Python version. That is all.

---

## About Patience

AI agents are powerful, but not magic. Some problems require multiple attempts.

When you feel frustrated:
- Take a step back
- Re-read what you told them
- Think about what information is missing
- Try from a different angle

The problem will be solved. What is needed is not anger, but clear thinking.

---

## In Closing

AI is heavy machinery for intelligence.

Heavy machinery, if you cannot operate it, is just a lump of iron. A person who can operate it riding it does the work of dozens. But what to dig, where to build that is still a human decision. Even as tools get smarter, purpose stays with you.

The creator built this software in 18 days while telling AI what to do.
Every feature, every fix, every design decision came from conversation.

Conversely, if you follow what is written in this document, you can build something that size.

The basics are all tedious things.
But that's the first step in stacking the stones of a dike.
How to stack stones, angle corrections you will develop those skills as you go.
Complex and difficult problems will eventually become something you can solve.

But if the basics are neglected, even something not very large will collapse.

Do not dismiss what is written above.
To solidify the ground, solidifying the ground of your own technical knowledge is most important.

The tools are here. The documentation is here.

**Go for it.**
