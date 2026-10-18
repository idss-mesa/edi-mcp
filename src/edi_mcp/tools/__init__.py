"""Tool families. Importing this package registers every tool."""

from edi_mcp.tools import (  # noqa: F401  (registration side effects)
    core,
    discovery,
)
