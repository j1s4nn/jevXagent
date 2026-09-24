"""CLI entry point"""
import asyncio
import sys
import signal
from pathlib import Path

import uvicorn

from .adapters import ClaudeCodeAdapter, CodexAdapter, KiloAdapter, ClineAdapter
from .config import Config, get_config_path


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
        print("\nNo supported agents found.")
        print("Supported: Claude Code, Codex, Kilo Code, Cline")
        sys.exit(1)

    print(f"\nFound {len(agents)} agent(s):")
    for i, agent in enumerate(agents, 1):
        print(f"  {i}. {agent.name}")

    # Select agent
    while True:
        try:
            choice = int(input(f"\nSelect agent (1-{len(agents)}): "))
            if 1 <= choice <= len(agents):
                selected = agents[choice - 1]
                break
        except (ValueError, KeyboardInterrupt):
            print("\nAborted")
            sys.exit(1)

    print(f"\nSelected: {selected.name}")

    # Try to read agent config
    agent_api_key, agent_base_url = selected.get_api_config()

    if agent_api_key:
        print(f"Found API key in {selected.name} settings")
    else:
        agent_api_key = input("Agent API key: ").strip()

    if not agent_base_url:
        if selected.transport == "anthropic":
            agent_base_url = "https://api.anthropic.com"
        else:
            agent_base_url = "https://api.openai.com/v1"

    agent_model = input("Agent model (e.g. claude-sonnet-4-20250514): ").strip()

    # Jev config
    print("\nJev Configuration:")
    jev_api_key = input("Jev API key: ").strip()
    jev_base_url = input("Jev base URL [https://api.typesafe.ai/v1]: ").strip() or "https://api.typesafe.ai/v1"
    jev_model = input("Jev model [jev-1]: ").strip() or "jev-1"

    # Stats path
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


def main():
    """Main entry point"""
    config_path = get_config_path()

    # Check for existing config
    if config_path.exists():
        print(f"Loading config from {config_path}")
        config = Config.load(config_path)
    else:
        print("No config found, starting setup...\n")
        config = prompt_config()
        config.save(config_path)
        print(f"\nConfig saved to {config_path}")

    # Display startup banner
    print("\n" + "=" * 50)
    print("jevXagent v0.2")
    print("=" * 50)
    print(f"Mode: Project")
    print(f"Agent: {config.agent_type}")
    print(f"Jev: {'ON' if config.jev_enabled else 'OFF'}")
    print(f"Proxy: http://{config.proxy.host}:{config.proxy.port}")
    print(f"Stats: {config.stats_path}")
    print()
    print("Ctrl+S  Save statistics")
    print("Ctrl+C  Stop jevXagent")
    print("=" * 50)
    print(f"\nSet agent to use: {config.proxy.host}:{config.proxy.port}")
    print(f"Environment: ANTHROPIC_BASE_URL=http://{config.proxy.host}:{config.proxy.port}")
    print("\nProxy running. Waiting for requests...\n")

    # Start server
    from .proxy import create_app

    app = create_app(config)

    uvicorn.run(
        app,
        host=config.proxy.host,
        port=config.proxy.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
