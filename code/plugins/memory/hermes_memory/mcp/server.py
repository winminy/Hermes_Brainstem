from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
import json

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
import jsonschema
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage

from plugins.memory.hermes_memory.core.scheduler import RegisteredScheduler, build_scheduler
from plugins.memory.hermes_memory.mcp.errors import raise_internal_error, raise_invalid_params, raise_method_not_found
from plugins.memory.hermes_memory.mcp.services import HermesMemoryServices
from plugins.memory.hermes_memory.mcp.tools import build_inbox_submit_tool, build_search_tool, build_status_tool, build_sync_tool


class HermesMemoryMCPApplication:
    def __init__(
        self,
        *,
        services: HermesMemoryServices | None = None,
        scheduler_factory: Callable[[HermesMemoryServices], RegisteredScheduler] | None = None,
    ) -> None:
        self.services = services or HermesMemoryServices()
        self._scheduler_factory = scheduler_factory or (lambda services: build_scheduler(services=services))
        settings = self.services.config.settings.mcp
        self.server = Server(settings.server_name, version=settings.server_version, instructions=settings.instructions)
        base_tools = [build_search_tool(self.services), build_sync_tool(self.services), build_inbox_submit_tool(self.services)]
        self._tools = tuple(base_tools + [build_status_tool(self.services, tool_names=tuple(tool.name for tool in base_tools) + ('status',))])
        self._tool_map = {tool.name: tool for tool in self._tools}
        self.server.request_handlers[types.ListToolsRequest] = self._handle_list_tools
        self.server.request_handlers[types.CallToolRequest] = self._handle_call_tool

    async def _handle_list_tools(self, request: types.ListToolsRequest) -> types.ServerResult:
        del request
        return types.ServerResult(types.ListToolsResult(tools=[tool.definition() for tool in self._tools]))

    async def _handle_call_tool(self, request: types.CallToolRequest) -> types.ServerResult:
        tool_name = request.params.name
        arguments = request.params.arguments or {}
        tool = self._tool_map.get(tool_name)
        if tool is None:
            raise_method_not_found(f'Unknown tool: {tool_name}', data={'tool': tool_name})
        try:
            jsonschema.validate(instance=arguments, schema=tool.input_schema)
        except jsonschema.ValidationError as exc:
            raise_invalid_params(f'Input validation error: {exc.message}', data={'tool': tool_name, 'path': list(exc.absolute_path)})
        result = tool.handler(arguments)
        try:
            jsonschema.validate(instance=result, schema=tool.output_schema)
        except jsonschema.ValidationError as exc:
            raise_internal_error(f'Output validation error: {exc.message}', data={'tool': tool_name, 'path': list(exc.absolute_path)})
        return types.ServerResult(
            types.CallToolResult(
                content=[types.TextContent(type='text', text=json.dumps(result, ensure_ascii=False, indent=2))],
                structuredContent=result,
                isError=False,
            )
        )

    async def run_stdio(self) -> None:
        async with stdio_server() as (read_stream, write_stream):
            await self.run_with_streams(read_stream, write_stream)

    async def run_with_streams(
        self,
        read_stream: MemoryObjectReceiveStream[SessionMessage | Exception],
        write_stream: MemoryObjectSendStream[SessionMessage],
    ) -> None:
        async with self.scheduler_lifespan():
            await self.server.run(read_stream, write_stream, self.server.create_initialization_options())

    @asynccontextmanager
    async def scheduler_lifespan(self) -> AsyncIterator[None]:
        registered = self._scheduler_factory(self.services)
        scheduler = registered.scheduler
        scheduler.start()
        try:
            yield
        finally:
            scheduler.shutdown()


def create_server(*, services: HermesMemoryServices | None = None) -> Server:
    return HermesMemoryMCPApplication(services=services).server


def main() -> None:
    anyio.run(HermesMemoryMCPApplication().run_stdio)


if __name__ == '__main__':
    main()
