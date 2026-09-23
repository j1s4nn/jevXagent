"""jevXagent — When JEV Meets LLM Agent.

A local LLM proxy that sits between an LLM agent (e.g. Claude Code) and its
primary LLM API. The primary model keeps global context and complex reasoning;
a fast auxiliary model (JEV) acts as a decision coprocessor for suitable
low-complexity operations.
"""

__version__ = "0.1.0"
