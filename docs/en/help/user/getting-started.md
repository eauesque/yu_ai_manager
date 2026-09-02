# Getting Started

YU AI Manager is a WebUI application for managing metadata of AI-generated images.

## Installation

### Requirements

- Python 3.11 or later
- Node.js 18 or later (for frontend build)

### Setup

```bash
# Clone the repository
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager

# Install uv (first time only)
pip install uv

# Create Python virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
uv pip install -r requirements.txt

# Build the frontend
pnpm install
pnpm run build

# Optional: Accelerate semantic search (recommended for large libraries)
uv pip install faiss-cpu
```

## Starting the Server

```bash
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
python web_ui.py --db ./tags.db --port 5000
```

Open `http://localhost:5000` in your browser.

## Initial Setup

1. **Register scan folders**: Go to Settings > Scan tab and add folders containing your AI-generated images
2. **Run a scan**: Scanning starts automatically after adding folders
3. **Browse images**: Search and browse images from the main page

## LAN Access

To access from other devices on your network:

1. Go to Settings > **Server** tab and enable "LAN Access"
2. Set up PIN authentication (required for LAN access)  
   In **Settings > Server tab**, enter a numeric PIN (4-8 digits) in the "PIN Authentication Code" field
3. Restart the server

Other devices on the LAN can access the app at `http://<server-IP>:5000`.
