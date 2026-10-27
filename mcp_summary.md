# Architecture overview - Model Context Protocol

## Scope

The Model Context Protocol (MCP) includes:
- **MCP Specification** – implementation requirements for clients and servers.
- **MCP SDKs** – language‑specific implementations.
- **MCP Development Tools** – e.g., MCP Inspector.
- **MCP Reference Server Implementations**.

MCP focuses solely on the protocol for context exchange; it does **not** dictate how AI applications use LLMs.

## Concepts of MCP

### Participants
- **MCP Host** – the AI application (e.g., Claude Desktop, VS Code) that manages one or more MCP clients.
- **MCP Client** – maintains a dedicated connection to a specific MCP server and obtains context.
- **MCP Server** – provides context (tools, resources, prompts) to clients. Can be local (STDIO) or remote (Streamable HTTP).

### Layers
- **Data layer** – inner layer; JSON‑RPC 2.0 protocol defining discovery, tools, resources, prompts, notifications, etc.
- **Transport layer** – outer layer; handles connection establishment, framing, and authentication. Supports:
  - **STDIO transport** – direct process I/O for local servers.
  - **Streamable HTTP transport** – HTTP POST + optional Server‑Sent Events for remote servers, with OAuth/bearer token auth.

### Data Layer Protocol
- **Stateless requests** – each request includes `_meta` with protocol version, client info, and capabilities.
- **Primitives** (server‑exposed):
  - **Tools** – executable functions (e.g., calculator, weather).
  - **Resources** – data sources (files, DB records, API responses).
  - **Prompts** – reusable interaction templates.
- **Client primitives** (e.g., elicitation for user input).
- **Notifications** – real‑time updates (e.g., tool list changes) via opt‑in subscription streams.

## Example Flow (Data Layer)
1. **Discovery** – client sends `server/discover` to learn server version, capabilities, identity.
2. **Tool discovery** – client calls `tools/list` to retrieve available tools (metadata includes name, title, description, input schema).
3. **Tool execution** – client invokes a tool via `tools/call` with arguments; receives structured `content` response.
4. **Real‑time updates** – client subscribes with `subscriptions/listen` (e.g., `toolsListChanged`). Server sends `notifications/tools/list_changed`, prompting the client to refresh its tool list.

## How AI Applications Use MCP
- Hosts instantiate MCP clients per server.
- Clients cache discovery data, maintain tool/resource registries.
- LLMs query the registry to decide which tool to call.
- Notifications keep the registry up‑to‑date without polling.

---

*This summary captures the key architecture concepts, participants, layers, primitives, and typical request/response patterns described on the MCP documentation page.*
