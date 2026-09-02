# SNS Share & Bluesky Monitor

## Overview

SNS Share lets you share AI-generated images to Bluesky and X (Twitter) directly from YU AI Manager. Post text is generated from customizable templates with automatic variable expansion from image metadata. Bluesky Monitor adds notification monitoring with automatic triage and auto-response capabilities.

## Setup

### Obtaining a Bluesky App Password

1. Log in to [bsky.app](https://bsky.app) and navigate to **Settings > App Passwords**
2. Click **Add App Password**
3. Enter a name (e.g., "YU AI Manager") and click **Create App Password**
4. Copy the displayed password

> **Important**: App Passwords are only shown once. Make sure to copy it before closing the dialog. Never use your main Bluesky password.

### Configuring in YU AI Manager

1. Open **Settings** from the navigation menu
2. Switch to the **SNS** tab
3. Fill in the following:
   - **Bluesky Handle**: Your handle (e.g., `yourname.bsky.social`)
   - **App Password**: The App Password obtained above
   - **Post Template**: Template for post text (see [Template Variables](#template-variables))
4. Click **Save**

### Testing Connection

After saving your credentials, click **Test Connection** to verify that YU AI Manager can authenticate with Bluesky. A successful test displays your handle and display name.

## Features

### Sharing to Bluesky

Share images to Bluesky directly from the image detail view.

1. Open an image's detail modal
2. Click the **SNS** button
3. Review and edit the generated post text
4. Click **Post to Bluesky**

- Post text is generated from your configured template with metadata variables expanded
- Images are automatically compressed and resized to fit Bluesky's 1 MB upload limit
- Posts are limited to **300 graphemes** (the text is automatically truncated if it exceeds this limit)
- You can choose to post with or without the image attached

### Sharing to X (Twitter)

Share image information to X via Web Intent (opens X's compose page in your browser).

1. Open an image's detail modal
2. Click the **SNS** button
3. Click **Share to X**

This opens a new browser tab with X's compose page, pre-filled with your template-generated text. You can edit the text before posting. Image attachment is not automatic on X -- you would need to manually attach the image.

### Bluesky Monitor

Bluesky Monitor polls your Bluesky notifications and queues them locally for triage and response.

#### Notification Types

- **Mentions**: Someone mentioned you in a post
- **Replies**: Someone replied to your post
- **Quotes**: Someone quoted your post
- **Follows**: Someone followed you
- **Likes**: Someone liked your post
- **Reposts**: Someone reposted your post

#### Polling

Notifications are fetched automatically at a configurable interval (default: 30 minutes, minimum: 5 minutes). You can also trigger an immediate poll from Settings or via the MCP tool.

#### Queue System

Each notification enters the queue with a **pending** status. From there it can transition to:

- **notified** -- Reported to the MCP client (Claude Desktop)
- **dismissed** -- Marked as not requiring attention

#### Triage

AI-powered classification determines whether each notification requires a response:

- **valid** -- Needs attention (genuine question, bug report, collaboration request)
- **invalid** -- Can be ignored (generic praise, spam, bot content)

Each notification type (mention, reply, quote) has its own customizable triage prompt. Default prompts are provided and can be restored at any time.

#### Auto-Response

For mentions, replies, and quotes triaged as valid, automatic template-based replies can be sent:

- Enable auto-response in the monitor configuration
- Customize response templates for each notification type
- Responses are limited to 300 graphemes

#### Auto-Dismiss

Follows, likes, and reposts can be automatically dismissed to reduce queue noise. Each type can be toggled independently in Settings.

#### MCP Notification on Connection

When an MCP client (Claude Desktop) connects, pending notifications are reported in batch so you can review them during your development session.

### Settings

SNS settings are configured in the **SNS** tab of the Settings page:

- **Bluesky Credentials**: Handle and App Password (password is stored encrypted, displayed masked)
- **Post Template**: Template text with variable placeholders
- **Monitor Settings**:
  - Poll interval (minutes)
  - Auto-dismiss for follows, likes, reposts
  - Auto-respond enable/disable
  - Triage prompts for mentions, replies, quotes
  - Auto-response templates for mentions, replies, quotes

## MCP Integration

SNS Share & Bluesky Monitor provides 15 MCP tools:

**Sharing (6 tools)**:
- `share_to_bluesky` -- Post an image to Bluesky
- `get_x_share_url` -- Get X Web Intent URL
- `get_sns_preview` -- Preview template expansion
- `test_bluesky_connection` -- Test API connection
- `get_sns_config` / `save_sns_config` -- Read/write SNS configuration

**Notification Queue (5 tools)**:
- `bsky_get_pending_notifications` -- Get pending notifications
- `bsky_get_notification_queue` -- Get queue items with filters
- `bsky_triage_notification` -- Set triage result (valid/invalid)
- `bsky_send_auto_response` -- Send a reply to a notification
- `bsky_poll_notifications` -- Trigger immediate polling

**Monitor Configuration (4 tools)**:
- `bsky_get_monitor_config` / `bsky_save_monitor_config` -- Read/write monitor settings
- `bsky_get_triage_prompts` / `bsky_save_triage_prompts` -- Read/write triage prompts and response templates

## Template Variables

The following variables can be used in post templates:

| Variable | Description |
|---|---|
| `{positive_short}` | Positive prompt (first 100 characters) |
| `{positive}` | Full positive prompt |
| `{negative_short}` | Negative prompt (first 50 characters) |
| `{model}` | Model name |
| `{seed}` | Seed value |
| `{steps}` | Sampling steps |
| `{cfg}` | CFG scale |
| `{sampler}` | Sampler name |
| `{size}` | Image dimensions |
| `{tags}` | Top 5 tags |
| `{filename}` | File name |

Default template: `{positive_short}`

## Tips

- **App Password security**: Always use an App Password, never your main Bluesky password. You can revoke App Passwords at any time from bsky.app Settings
- **Rate limits**: Bluesky API has rate limits. Avoid rapid consecutive posts. Image uploads count toward your rate limit
- **Grapheme counting**: Bluesky uses grapheme clusters, not characters, for the 300-character limit. CJK characters count as 1 grapheme each
- **Image compression**: Images larger than 1 MB are automatically resized. If image preparation fails, the post is sent as text only
- **Monitor polling**: Set the poll interval based on your notification volume. Higher traffic accounts may benefit from shorter intervals
- **Auto-dismiss**: Enable auto-dismiss for follows, likes, and reposts to keep your queue focused on actionable notifications
- **Triage prompts**: Customize triage prompts to match your communication style and the types of interactions you receive
