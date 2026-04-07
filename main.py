import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions


async def main():
    res = []
    async for message in query(
        prompt="who stole the cookies from the cookie jar? Look at the clues",
        options=ClaudeAgentOptions(allowed_tools=["Read", "Edit", "Bash"]),
    ):  
        if hasattr(message, "content") and isinstance(message.content, list) and len(message.content) > 0:
            print(message.content[0])  # Claude thinks, finds the bug, and says what it is
        res.append(message)
    return res


asyncio.run(main())