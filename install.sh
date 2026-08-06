#!/bin/sh

set -e

INSTALL_DIR="${HOME}/.musterm_app"
SCRIPT_URL="https://raw.githubusercontent.com/ihsannyy/musterm/main"

NC='\033[0m'
C_CYAN='\033[38;5;51m'
C_GREEN='\033[38;5;48m'
C_YELLOW='\033[38;5;226m'
C_RED='\033[38;5;196m'
C_WHITE='\033[38;5;255m'
C_GRAY='\033[38;5;242m'

echo -e "${C_CYAN}"
echo "  ███╗   ███╗██╗   ██╗███████╗████████╗███████╗██████╗ ██╗    ██╗"
echo "  ████╗ ████║██║   ██║██╔════╝╚══██╔══╝██╔════╝██╔══██╗██║    ██║"
echo "  ██╔████╔██║██║   ██║███████╗   ██║   █████╗  ██████╔╝██║    ██║"
echo "  ██║╚██╔╝██║██║   ██║╚════██║   ██║   ██╔══╝  ██╔══██╗██║    ██║"
echo "  ██║ ╚═╝ ██║╚██████╔╝███████║   ██║   ███████╗██║  ██║╚██████╔╝"
echo "  ╚═╝     ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝ ╚══════╝"
echo -e "${NC}"
echo -e "  ${C_GREEN}🚀 Auto-Installing MusTerm to System PATH ($PREFIX/bin)...${NC}"
echo ""

mkdir -p "$INSTALL_DIR"

if [ -f "./musterm.sh" ] && [ -f "./musterm.py" ]; then
    cp -rf ./* "$INSTALL_DIR/"
else
    echo -e "  [*] Downloading MusTerm core files..."
    curl -fsSL "$SCRIPT_URL/musterm.py" -o "$INSTALL_DIR/musterm.py"
    curl -fsSL "$SCRIPT_URL/musterm.sh" -o "$INSTALL_DIR/musterm.sh"
fi

chmod +x "$INSTALL_DIR/musterm.sh" "$INSTALL_DIR/musterm.py"

TARGET_BIN=""
if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ]; then
    TARGET_BIN="$PREFIX/bin"
elif [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
    TARGET_BIN="/usr/local/bin"
elif [ -d "$HOME/.local/bin" ]; then
    TARGET_BIN="$HOME/.local/bin"
elif [ -d "$HOME/bin" ]; then
    TARGET_BIN="$HOME/bin"
else
    TARGET_BIN="/usr/bin"
fi

if [ -n "$TARGET_BIN" ]; then
    echo -e "  [*] Symlinking executable to ${C_CYAN}${TARGET_BIN}/musterm${NC}..."
    ln -sf "$INSTALL_DIR/musterm.sh" "$TARGET_BIN/musterm"
    chmod +x "$TARGET_BIN/musterm"
fi

echo -e "  [*] Checking & installing required packages (python3, mpv, yt-dlp)..."
"$INSTALL_DIR/musterm.sh" --check || true

echo ""
echo -e "  ${C_GREEN}✓ MusTerm successfully installed to your system PATH!${NC}"
echo -e "  ${C_WHITE}You can now type ${C_YELLOW}musterm${C_WHITE} from any directory in your terminal.${NC}"
echo ""
