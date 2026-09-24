from .registry import DISCLAIMER, all_specs, all_tool_names, call_tool, langchain_tools

__all__ = ["DISCLAIMER", "TOOL_SPECS", "all_specs", "all_tool_names", "call_tool", "langchain_tools"]


def __getattr__(name: str):
    if name == "TOOL_SPECS":
        from .registry import base_specs

        return base_specs()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
