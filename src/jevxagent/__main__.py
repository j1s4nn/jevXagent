"""CLI entry point"""
import asyncio
import sys
import signal
import threading
from pathlib import Path

import uvicorn

from .adapters import ClaudeCodeAdapter, CodexAdapter, KiloAdapter, ClineAdapter
from .config import Config, get_config_path

# Global reference for signal handler
_proxy_server = None


def detect_agents():
    """Detect installed agents"""
    adapters = [
        ClaudeCodeAdapter(),
        CodexAdapter(),
        KiloAdapter(),
        ClineAdapter(),
    ]

    detected = [adapter for adapter in adapters if adapter.detect()]
    return detected


def prompt_config() -> Config:
    """Interactive configuration"""
    print("jevXagent Configuration")
    print("=" * 50)

    # Detect agents
    print("\nDetecting installed agents...")
    agents = detect_agents()

    if not agents:
        print("\n❌ No supported agents found.")
        print("Supported: Claude Code, Codex, Kilo Code, Cline")
        print("\nPlease install one of the supported agents and try again.")
        sys.exit(1)

    print(f"\n✓ Found {len(agents)} agent(s):")
    for i, agent in enumerate(agents, 1):
        print(f"  {i}. {agent.name}")

    # Select agent
    while True:
        try:
            choice = int(input(f"\nSelect agent (1-{len(agents)}): "))
            if 1 <= choice <= len(agents):
                selected = agents[choice - 1]
                break
            else:
                print(f"Please enter a number between 1 and {len(agents)}")
        except ValueError:
            print("Please enter a valid number")
        except KeyboardInterrupt:
            print("\n\nAborted")
            sys.exit(1)

    print(f"\n✓ Selected: {selected.name}")

    # Try to read agent config
    try:
        agent_api_key, agent_base_url = selected.get_api_config()
    except Exception as e:
        print(f"Warning: Could not read agent config: {e}")
        agent_api_key, agent_base_url = None, None

    if agent_api_key:
        print(f"✓ Found API key in {selected.name} settings")
        use_found = input("Use found API key? [Y/n]: ").strip().lower()
        if use_found and use_found != 'y':
            agent_api_key = None

    if not agent_api_key:
        while True:
            agent_api_key = input("Agent API key: ").strip()
            if agent_api_key:
                break
            print("API key cannot be empty")

    if not agent_base_url:
        if selected.transport == "anthropic":
            agent_base_url = "https://api.anthropic.com"
        else:
            agent_base_url = "https://api.openai.com/v1"

    agent_model = input(f"Agent model (e.g. claude-sonnet-4-20250514): ").strip()
    while not agent_model:
        print("Model name cannot be empty")
        agent_model = input(f"Agent model: ").strip()

    # Jev config
    print("\n" + "=" * 50)
    print("Jev Configuration")
    print("=" * 50)

    while True:
        jev_api_key = input("Jev API key: ").strip()
        if jev_api_key:
            break
        print("API key cannot be empty")

    jev_base_url = input("Jev base URL [https://api.typesafe.ai/v1]: ").strip() or "https://api.typesafe.ai/v1"
    jev_model = input("Jev model [jev-1]: ").strip() or "jev-1"

    # Stats path
    print("\n" + "=" * 50)
    print("Statistics Configuration")
    print("=" * 50)
    default_stats = Path.cwd() / "jevxagent_stats.jsonl"
    stats_input = input(f"Stats path [{default_stats}]: ").strip()
    stats_path = Path(stats_input) if stats_input else default_stats

    config = Config(
        jev={
            "api_key": jev_api_key,
            "base_url": jev_base_url,
            "model": jev_model,
            "timeout": 0.8,
        },
        agent={
            "api_key": agent_api_key,
            "base_url": agent_base_url,
            "model": agent_model,
        },
        proxy={
            "host": "127.0.0.1",
            "port": 9099,
        },
        jev_enabled=True,
        stats_path=stats_path,
        agent_type=selected.name.lower().replace(" ", "-"),
    )

    return config


def setup_signal_handlers(proxy_server):
    """Setup Ctrl+C and Ctrl+S handlers"""
    global _proxy_server
    _proxy_server = proxy_server

    def signal_handler(signum, frame):
        if signum == signal.SIGINT:
            # Ctrl+C
            print("\n\nShutting down jevXagent...")
            if _proxy_server:
                _proxy_server.save_stats_snapshot()
            sys.exit(0)

    # Register Ctrl+C handler
    signal.signal(signal.SIGINT, signal_handler)

    # For Windows, we need a separate thread to listen for 's' key
    if sys.platform == 'win32':
        def listen_for_save():
            import msvcrt
            while True:
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key == b'\x13':  # Ctrl+S
                        if _proxy_server:
                            _proxy_server.save_stats_snapshot()

        save_thread = threading.Thread(target=listen_for_save, daemon=True)
        save_thread.start()


def main():
    """Main entry point"""
    config_path = get_config_path()

    # Check for existing config
    if config_path.exists():
        print(f"Loading config from {config_path}")
        try:
            config = Config.load(config_path)
        except Exception as e:
            print(f"Error loading config: {e}")
            print("Please delete the config file and run again.")
            sys.exit(1)
    else:
        print("No config found, starting setup...\n")
        config = prompt_config()
        config.save(config_path)
        print(f"\n✓ Config saved to {config_path}")

    # Validate configuration
    print("\nValidating configuration...")
    validation_errors = []

    if not config.jev.api_key:
        validation_errors.append("Jev API key is missing")
    if not config.agent.api_key:
        validation_errors.append("Agent API key is missing")
    if not config.agent.model:
        validation_errors.append("Agent model is missing")

    if validation_errors:
        print("\n❌ Configuration errors:")
        for error in validation_errors:
            print(f"  - {error}")
        print("\nPlease reconfigure:")
        print(f"  rm {config_path}")
        print(f"  jevxagent")
        sys.exit(1)

    print("✓ Configuration valid")

    # Display startup banner
    print("\n" + "=" * 50)
    print("jevXagent v0.2")
    print("=" * 50)
    print(f"Mode: Project")
    print(f"Agent: {config.agent_type}")
    print(f"Agent Model: {config.agent.model}")
    print(f"Jev: {'ON' if config.jev_enabled else 'OFF'}")
    print(f"Jev Model: {config.jev.model}")
    print(f"Proxy: http://{config.proxy.host}:{config.proxy.port}")
    print(f"Stats: {config.stats_path}")
    print()
    print("Ctrl+S  Save statistics snapshot")
    print("Ctrl+C  Stop jevXagent")
    print("=" * 50)
    print(f"\n📝 Configure your agent to use the proxy:")
    print(f"   export ANTHROPIC_BASE_URL=http://{config.proxy.host}:{config.proxy.port}")
    print(f"   (or OPENAI_BASE_URL for OpenAI-based agents)")
    print("\n🚀 Proxy running. Waiting for requests...\n")

    # Start server
    from .proxy import create_app

    app = create_app(config)

    # Setup signal handlers
    if hasattr(app.state, 'proxy'):
        setup_signal_handlers(app.state.proxy)

    try:
        uvicorn.run(
            app,
            host=config.proxy.host,
            port=config.proxy.port,
            log_level="warning",
        )
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
