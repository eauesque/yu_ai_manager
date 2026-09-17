# Troubleshooting

## Common Issues

### Server won't start

- Verify the Python virtual environment is activated: `source venv/bin/activate`
- Verify dependencies are installed: `uv pip install -r requirements.txt`
- Check if the port is already in use: `ss -tlnp | grep 5000`

### Images not displaying

- The thumbnail API requires the actual image file to exist on disk
- Verify that paths in the `files` table match the actual file paths
- Verify that the scan root paths are correct

### Cannot access from LAN

- Verify "LAN Access" is enabled in Settings > Server
- Verify PIN authentication is configured (required for LAN access)
- Verify the port is open in your firewall
- Verify the server's IP address is correct

### MCP connection errors

- Verify `YU_BASE_URL` is correct
- Verify the server is running
- Verify the API key is valid
- For LAN connections, verify the HTTP/SSE endpoint (`/mcp`) is accessible

### Scanning is slow

- Turning off `compute_hash` will speed things up
- For remote paths, adjust the Remote FS timeout settings
- Initial scans with a large number of files will take time

### Slow thumbnail generation

- During scans, disk I/O can become saturated, slowing thumbnail generation. A pre-warm pass runs automatically after the scan completes
- **pyvips (optional)**: For libraries with many large JPEG images, libvips shrink-on-load provides faster thumbnail generation
  - Linux: `sudo apt install libvips-dev && uv pip install pyvips`
  - macOS: `brew install vips && uv pip install pyvips`
  - Windows: Download the DLL from the [libvips releases page](https://github.com/libvips/libvips/releases), add it to PATH, then `uv pip install pyvips`
  - Auto-detected if installed; falls back to Pillow otherwise
- **Pillow-SIMD (optional)**: 2–4x faster image resizing via ARM NEON / x86 AVX2
  - `uv pip install pillow-simd` (drop-in replacement for Pillow)
  - ARM NEON optimized build: `CC="cc -mfpu=neon" uv pip install --force-reinstall pillow-simd`
  - Build tools (gcc, etc.) are required on platforms without pre-built wheels

## Debugging

- Check server logs in Settings > Logs tab
- MCP debug mode: Set `YU_DEBUG_MODE=1` to enable additional tools
- DB integrity check: `python db_health.py`
