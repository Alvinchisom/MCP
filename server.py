from mcp.server.fastmcp import FastMCP
# from mcp.server.mcpserver import MCPServer

mcp = FastMCP('mcp_creative')
# mcp = MCPServer('mcp_creative')

@mcp.tool()
def creative_add(num1:int,num2:int) -> int:

    "Use this tool to add two numbers."
    return (num1 + num2 - 1)

if __name__ == '__main__':
    mcp.run(transport='stdio')