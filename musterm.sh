#!/bin/sh

if [ -z "$BASH_VERSION" ]; then
    if command -v bash >/dev/null 2>&1; then
        exec bash "$0" "$@"
    else
        echo "Error: bash is required to run MusTerm." >&2
        exit 1
    fi
fi

export TERM="${TERM:-xterm-256color}"
MUST_DIR="${HOME}/.config/musterm"

REAL_SCRIPT="$0"
if [ -h "$0" ]; then
    if command -v readlink >/dev/null 2>&1; then
        REAL_SCRIPT="$(readlink -f "$0" 2>/dev/null || readlink "$0" 2>/dev/null || echo "$0")"
    fi
fi
SCRIPT_DIR="$(cd "$(dirname "$REAL_SCRIPT")" && pwd)"
PYTHON_TUI="${SCRIPT_DIR}/musterm.py"
mkdir -p "$MUST_DIR"

NC='\033[0m'
BOLD='\033[1m'
C_CYAN='\033[38;5;51m'
C_MAGENTA='\033[38;5;201m'
C_PURPLE='\033[38;5;141m'
C_PINK='\033[38;5;213m'
C_GREEN='\033[38;5;48m'
C_YELLOW='\033[38;5;226m'
C_RED='\033[38;5;196m'
C_WHITE='\033[38;5;255m'
C_GRAY='\033[38;5;242m'

BG_CYAN='\033[48;5;51m\033[38;5;16m\033[1m'
BG_MAGENTA='\033[48;5;201m\033[38;5;16m\033[1m'
BG_GREEN='\033[48;5;48m\033[38;5;16m\033[1m'

show_banner() {
    clear 2>/dev/null || true
    echo -e "${C_CYAN}  ███╗   ███╗██╗   ██╗███████╗████████╗███████╗██████╗ ███╗   ███╗${NC}"
    echo -e "${C_MAGENTA}  ████╗ ████║██║   ██║██╔════╝╚══██╔══╝██╔════╝██╔══██╗████╗ ████║${NC}"
    echo -e "${C_PURPLE}  ██╔████╔██║██║   ██║███████╗   ██║   █████╗  ██████╔╝██╔████╔██║${NC}"
    echo -e "${C_PINK}  ██║╚██╔╝██║██║   ██║╚════██║   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║${NC}"
    echo -e "${C_BLUE}  ██║ ╚═╝ ██║╚██████╔╝███████║   ██║   ███████╗██║  ██║██║ ╚═╝ ██║${NC}"
    echo -e "${C_CYAN}  ╚═╝     ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝${NC}"
    echo -e "       ${BG_MAGENTA} 🎵 MUSTERM MUSIC PLAYER & CUSTOM TUI 🎵 ${NC}"
    echo -e "  ${C_GRAY}─────────────────────────────────────────────────────────────${NC}"
}

print_info() { echo -e " ${BG_CYAN} INFO ${NC} ${C_CYAN}$1${NC}"; }
print_success() { echo -e " ${BG_GREEN} SUCCESS ${NC} ${C_GREEN}$1${NC}"; }
print_warn() { echo -e " ${BG_MAGENTA} WARN ${NC} ${C_YELLOW}$1${NC}"; }
print_error() { echo -e " ${C_RED}✖ Error: $1${NC}"; }

detect_pkg_manager() {
    if command -v pkg &>/dev/null; then echo "pkg"
    elif command -v apt-get &>/dev/null; then echo "apt"
    elif command -v brew &>/dev/null; then echo "brew"
    elif command -v pacman &>/dev/null; then echo "pacman"
    elif command -v dnf &>/dev/null; then echo "dnf"
    elif command -v apk &>/dev/null; then echo "apk"
    elif command -v xbps-install &>/dev/null; then echo "xbps"
    else echo "unknown"
    fi
}

install_package() {
    local cmd="$1"
    local pkg_name="$2"
    local pm
    pm=$(detect_pkg_manager)

    case "$pm" in
        pkg) pkg install "$pkg_name" -y ;;
        apt) 
            if [ "$(id -u)" -eq 0 ]; then apt-get update -qq && apt-get install -y "$pkg_name"
            else sudo apt-get update -qq && sudo apt-get install -y "$pkg_name"; fi
            ;;
        brew) brew install "$pkg_name" ;;
        pacman)
            if [ "$(id -u)" -eq 0 ]; then pacman -S --noconfirm "$pkg_name"
            else sudo pacman -S --noconfirm "$pkg_name"; fi
            ;;
        dnf)
            if [ "$(id -u)" -eq 0 ]; then dnf install -y "$pkg_name"
            else sudo dnf install -y "$pkg_name"; fi
            ;;
        apk)
            if [ "$(id -u)" -eq 0 ]; then apk add "$pkg_name"
            else sudo apk add "$pkg_name"; fi
            ;;
        *)
            return 1
            ;;
    esac
}

musterm_spinner() {
    local msg="$1"
    local spin_chars="⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏"
    set -- $spin_chars
    local i=0
    printf "\033[?25l"
    while true; do
        eval "local char=\${$((i + 1))}"
        printf "\r  \033[38;5;51m%s\033[0m  \033[1m%s\033[0m..." "$char" "$msg"
        i=$(( (i + 1) % 10 ))
        sleep 0.1
    done
}

musterm_run_quiet() {
    local label="$1"
    shift
    local logfile="/tmp/musterm_install_$$.log"
    local spin_pid=""

    musterm_spinner "$label" &
    spin_pid=$!

    local rc=0
    "$@" > "$logfile" 2>&1 || rc=$?

    kill -KILL "$spin_pid" 2>/dev/null || true
    wait "$spin_pid" 2>/dev/null || true
    printf "\033[?25h"
    printf "\r\033[K"

    if [ "$rc" -eq 0 ]; then
        echo -e "  ${C_GREEN}✓${NC} ${C_WHITE}${label}${NC} ${C_GRAY}successfully configured${NC}"
        rm -f "$logfile"
        return 0
    else
        echo -e "  ${C_RED}✖${NC} ${C_WHITE}${label}${NC} ${C_RED}failed!${NC}"
        if [ -s "$logfile" ]; then
            echo -e "  ${C_GRAY}Last 10 lines of log:${NC}"
            tail -n 10 "$logfile" 2>/dev/null | while read -r line; do
                echo -e "    ${C_GRAY}${line}${NC}"
            done
        fi
        rm -f "$logfile"
        return 1
    fi
}

auto_setup_path() {
    local target_bin=""
    if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ]; then
        target_bin="$PREFIX/bin"
    elif [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
        target_bin="/usr/local/bin"
    elif [ -d "$HOME/.local/bin" ]; then
        target_bin="$HOME/.local/bin"
    elif [ -d "$HOME/bin" ]; then
        target_bin="$HOME/bin"
    fi

    if [ -n "$target_bin" ]; then
        local target_symlink="$target_bin/musterm"
        if [ ! -L "$target_symlink" ] || [ "$(readlink -f "$target_symlink" 2>/dev/null)" != "$SCRIPT_DIR/musterm.sh" ]; then
            ln -sf "$SCRIPT_DIR/musterm.sh" "$target_symlink" 2>/dev/null || true
            chmod +x "$target_symlink" 2>/dev/null || true
            chmod +x "$SCRIPT_DIR/musterm.py" 2>/dev/null || true
            chmod +x "$SCRIPT_DIR/musterm.sh" 2>/dev/null || true
        fi
    fi
}

check_dependencies() {
    show_banner
    print_info "Checking system environment & TUI dependencies..."
    echo ""

    local req_deps="python3:python yt-dlp:yt-dlp mpv:mpv"

    for item in $req_deps; do
        local cmd="${item%%:*}"
        local pkg="${item##*:}"
        if ! command -v "$cmd" &>/dev/null; then
            musterm_run_quiet "Installing $cmd ($pkg)" install_package "$cmd" "$pkg" || { print_error "Required dependency '$cmd' missing."; exit 1; }
        else
            echo -e "  ${C_GREEN}✓${NC} ${C_WHITE}$cmd${NC} ${C_GRAY}is installed${NC}"
        fi
    done

    if command -v pulseaudio &>/dev/null; then
        pulseaudio --start >/dev/null 2>&1 || true
    fi

    auto_setup_path
    echo ""
    echo -e "  ${C_GREEN}✓${NC} ${C_WHITE}Environment check complete! Launching MusTerm...${NC}"
    sleep 0.5
}

clear_history_log() {
    show_banner
    local hist_log="$MUST_DIR/history.log"
    if [ -f "$hist_log" ]; then
        rm -f "$hist_log"
        print_success "Playback history log cleared successfully! ($hist_log)"
    else
        print_info "Playback history log is already empty."
    fi
    echo ""
    exit 0
}

show_help() {
    show_banner
    echo -e "${C_CYAN}USAGE GUIDE:${NC}"
    echo -e "  musterm [OPTIONS]"
    echo ""
    echo -e "${C_CYAN}OPTIONS:${NC}"
    echo -e "  ${C_GREEN}(no args)${NC}              Launch Full Custom TUI App"
    echo -e "  ${C_GREEN}-cl, --clear-history${NC}   Clear playback history log file"
    echo -e "  ${C_GREEN}-c, --check${NC}           Check and repair system dependencies & setup PATH"
    echo -e "  ${C_GREEN}-h, --help${NC}            Show this help manual"
    echo ""
    echo -e "${C_CYAN}TUI CONTROLS:${NC}"
    echo -e "  ${C_YELLOW}1 - 6 / Tab${NC}           Switch tabs (Search, Radio, History, Lyrics, Visualizer, Help)"
    echo -e "  ${C_YELLOW}c (in History tab)${NC}    Clear playback history instantly"
    echo -e "  ${C_YELLOW}s or /${NC}                Activate live search box"
    echo -e "  ${C_YELLOW}↑ / ↓ or k / j${NC}        Navigate tracks / radios / lyrics"
    echo -e "  ${C_YELLOW}Enter${NC}                 Play selected item"
    echo -e "  ${C_YELLOW}Space${NC}                 Pause / Resume playback"
    echo -e "  ${C_YELLOW}+ / -${NC}                 Adjust volume"
    echo -e "  ${C_YELLOW}q / Esc${NC}               Exit TUI"
    echo ""
    exit 0
}

main() {
    auto_setup_path

    if [ "$#" -gt 0 ]; then
        case "$1" in
            -h|--help) show_help ;;
            -cl|--clear-history|--clean) clear_history_log ;;
            -c|--check|--install) check_dependencies ;;
        esac
    fi

    if ! command -v yt-dlp &>/dev/null || ! command -v mpv &>/dev/null || ! command -v python3 &>/dev/null; then
        check_dependencies
    fi

    if [ "$#" -eq 0 ]; then
        if command -v pulseaudio &>/dev/null; then
            pulseaudio --start >/dev/null 2>&1 || true
        fi
        python3 "$PYTHON_TUI"
    else
        case "$1" in
            -h|--help) show_help ;;
            -cl|--clear-history|--clean) clear_history_log ;;
            -c|--check|--install) check_dependencies ;;
            *)
                if command -v pulseaudio &>/dev/null; then
                    pulseaudio --start >/dev/null 2>&1 || true
                fi
                python3 "$PYTHON_TUI"
                ;;
        esac
    fi
}

main "$@"
