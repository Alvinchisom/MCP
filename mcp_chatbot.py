import asyncio
from contextlib import AsyncExitStack
import json
from typing import Any, Dict, List
from decouple import config
from groq import Groq
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

GROQ_API_KEY = config('GROQ_API_KEY')


class MCP_ChatBot:

  def __init__(self):
    self.sessions: List[ClientSession] = []
    self.exit_stack = AsyncExitStack()
    self.groq = Groq(api_key=GROQ_API_KEY)

    # Tool state
    self.available_tools: List[dict] = []
    self.tool_to_session: Dict[str, ClientSession] = {}

    # Resource state
    self.available_resources: List[dict] = []
    self.resource_to_session: Dict[str, ClientSession] = {}

    # Prompt state
    self.available_prompts: List[dict] = []
    self.prompt_to_session: Dict[str, ClientSession] = {}

  async def connect_to_server(
      self, server_name: str, server_config: dict
  ) -> None:
    """Connect to a single MCP server and discover tools, resources, and prompts."""
    try:
      server_params = StdioServerParameters(**server_config)
      stdio_transport = await self.exit_stack.enter_async_context(
          stdio_client(server_params)
      )
      read, write = stdio_transport
      session = await self.exit_stack.enter_async_context(
          ClientSession(read, write)
      )
      await session.initialize()
      self.sessions.append(session)

      # 1. Discover Tools
      try:
        tools_resp = await session.list_tools()
        print(
            f'\nConnected to {server_name} with tools:',
            [t.name for t in tools_resp.tools],
        )
        for tool in tools_resp.tools:
          self.tool_to_session[tool.name] = session
          self.available_tools.append({
              'type': 'function',
              'function': {
                  'name': tool.name,
                  'description': tool.description,
                  'parameters': tool.inputSchema,
              },
          })
      except Exception:
        pass

      # 2. Discover Resources
      try:
        res_resp = await session.list_resources()
        for resource in res_resp.resources:
          uri_str = str(resource.uri)
          self.resource_to_session[uri_str] = session
          self.available_resources.append({
              'uri': uri_str,
              'name': resource.name,
              'description': getattr(resource, 'description', ''),
          })
      except Exception:
        pass

      # 3. Discover Prompts
      try:
        prompts_resp = await session.list_prompts()
        for prompt in prompts_resp.prompts:
          self.prompt_to_session[prompt.name] = session
          self.available_prompts.append({
              'name': prompt.name,
              'description': prompt.description,
              'arguments': getattr(prompt, 'arguments', []),
          })
      except Exception:
        pass

    except Exception as e:
      print(f'Failed to connect to {server_name}: {e}')

  async def connect_to_servers(self):
    """Connect to all configured MCP servers."""
    try:
      with open('server_config.json', 'r') as file:
        data = json.load(file)

      servers = data.get('mcpServers', {})
      for server_name, server_config in servers.items():
        await self.connect_to_server(server_name, server_config)
    except Exception as e:
      print(f'Error loading server configuration: {e}')
      raise

  async def get_resource(self, resource_uri: str):
    """Fetch and print an MCP resource by URI."""
    session = self.resource_to_session.get(resource_uri)

    # Fallback matching for dynamic URI templates (e.g., papers://{topic})
    if not session and resource_uri.startswith('papers://'):
      for uri, sess in self.resource_to_session.items():
        if uri.startswith('papers://'):
          session = sess
          break
      # If still not mapped, use the primary active session
      if not session and self.sessions:
        session = self.sessions[0]

    if not session:
      print(f"Resource '{resource_uri}' not found.")
      return

    try:
      result = await session.read_resource(uri=resource_uri)
      if result and result.contents:
        print(f'\n--- Resource: {resource_uri} ---')
        for content in result.contents:
          print(getattr(content, 'text', str(content)))
        print('----------------------------------\n')
      else:
        print('No content found in resource.')
    except Exception as e:
      print(f'Error reading resource: {e}')

  def list_prompts(self):
    """List all prompts exposed by connected MCP servers."""
    if not self.available_prompts:
      print('No prompts available.')
      return

    print('\nAvailable prompts:')
    for p in self.available_prompts:
      print(f"  /{p['name']} - {p.get('description', '')}")
      args = p.get('arguments') or []
      if args:
        print('    Arguments:')
        for arg in args:
          arg_name = arg.name if hasattr(arg, 'name') else arg.get('name', '')
          print(f'      - {arg_name}')
    print()

  async def execute_prompt(self, prompt_name: str, args: dict):
    """Execute a prompt template on the MCP server and feed it to the chatbot."""
    session = self.prompt_to_session.get(prompt_name)
    if not session and self.sessions:
      session = self.sessions[0]

    if not session:
      print(f"Prompt '{prompt_name}' not found.")
      return

    try:
      result = await session.get_prompt(prompt_name, arguments=args)
      if result and result.messages:
        prompt_content = result.messages[0].content

        if isinstance(prompt_content, str):
          text = prompt_content
        elif hasattr(prompt_content, 'text'):
          text = prompt_content.text
        else:
          text = ' '.join(
              item.text if hasattr(item, 'text') else str(item)
              for item in prompt_content
          )

        print(f"\nExecuting prompt '{prompt_name}'...")
        await self.process_query(text)
    except Exception as e:
      print(f'Error executing prompt: {e}')

  async def process_query(self, query: str):
    messages = [{'role': 'user', 'content': query}]

    while True:
      api_params = {
          "model": "openai/gpt-oss-120b",
          'messages': messages,
          'max_tokens': 2048,
      }

      if self.available_tools:
        api_params['tools'] = self.available_tools
        api_params['tool_choice'] = 'auto'

      response = self.groq.chat.completions.create(**api_params)
      response_message = response.choices[0].message
      tool_calls = response_message.tool_calls

      if tool_calls:
        messages.append(response_message)
        for tool_call in tool_calls:
          tool_name = tool_call.function.name
          tool_args = json.loads(tool_call.function.arguments)

          print(f'Calling tool {tool_name} with args {tool_args}')
          session = self.tool_to_session.get(tool_name)
          if not session:
            print(f'Error: No session found for tool {tool_name}')
            continue

          result = await session.call_tool(tool_name, arguments=tool_args)
          content_str = '\n'.join(
              [item.text for item in result.content if hasattr(item, 'text')]
          )

          messages.append({
              'role': 'tool',
              'tool_call_id': tool_call.id,
              'name': tool_name,
              'content': content_str,
          })
      else:
        if response_message.content:
          print(f'\nAssistant: {response_message.content}\n')
        break

  async def chat_loop(self):
    """Run an interactive chat loop supporting queries, @resources, and /prompts."""
    print('\nMCP Chatbot Started!')
    print("Type your queries or 'quit' to exit.")
    print("Use '@folders' to see available topics")
    print("Use '@<topic>' to inspect saved papers in that topic")
    print("Type '/prompts' to list prompt templates\n")

    while True:
      try:
        query = input('Query: ').strip()
        if not query:
          continue
        if query.lower() == 'quit':
          break

        # Handle Resource requests (e.g. @folders or @deep_learning)
        if query.startswith('@'):
          target = query[1:].strip()
          if target == 'folders':
            await self.get_resource('papers://folders')
          else:
            await self.get_resource(f'papers://{target}')
          continue

        # Handle Prompt inspection
        if query == '/prompts':
          self.list_prompts()
          continue

        # Handle Prompt execution (e.g. /generate_search_prompt topic=transformers)
        if query.startswith('/'):
          parts = query[1:].split()
          prompt_name = parts[0]
          args = {}
          for part in parts[1:]:
            if '=' in part:
              k, v = part.split('=', 1)
              args[k] = v

          # If user typed only "/generate_search_prompt", ask interactively for arguments
          if not args and prompt_name == 'generate_search_prompt':
            topic_val = input('Enter topic: ').strip()
            num_val = input('Enter number of papers [5]: ').strip() or '5'
            args = {'topic': topic_val, 'num_papers': int(num_val)}

          await self.execute_prompt(prompt_name, args)
          continue

        # Standard natural language query
        await self.process_query(query)

      except Exception as e:
        print(f'\nError: {e}')

  async def cleanup(self):
    await self.exit_stack.aclose()


async def main():
  chatbot = MCP_ChatBot()
  try:
    await chatbot.connect_to_servers()
    await chatbot.chat_loop()
  finally:
    await chatbot.cleanup()


if __name__ == '__main__':
  asyncio.run(main())