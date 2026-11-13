"""MCP 도서관 서버에 연결해 자연어 질문을 받는 대화형 클라이언트.

실행: python mcp_demo/library_client.py
명령어: /reset (대화 초기화), /quit (종료)
"""
import asyncio
import re
import sys
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import Field, create_model

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

MODEL = "gpt-6-luna"
MAX_TURNS = 3
SYSTEM = "너는 도서관 도우미다. 도서 검색이나 회원 대출 현황 질문에는 연결된 MCP 도구를 사용해 정확히 답한다."

# 같은 폴더의 서버를 현재 파이썬으로 실행 (CWD 와 무관하게 동작)
SERVER = Path(__file__).resolve().parent / "library_server.py"
SERVER_PARAMS = StdioServerParameters(command=sys.executable, args=[str(SERVER)])


def _text(result) -> str:
    """call_tool 결과에서 사람이 읽을 텍스트만 뽑는다."""
    parts = []
    for item in getattr(result, "content", []) or []:
        parts.append(getattr(item, "text", str(item)))
    return "\n".join(parts) if parts else str(result)


def _args_model(tool) -> type:
    """MCP 도구의 JSON Schema 입력 정의를 Pydantic 모델로 변환한다."""
    schema = getattr(tool, "inputSchema", {}) or {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    json_types = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "object": dict,
        "array": list,
    }

    fields = {}
    for name, definition in properties.items():
        annotation = json_types.get(definition.get("type"), Any)
        description = definition.get("description", "")
        if name in required:
            fields[name] = (annotation, Field(..., description=description))
        else:
            fields[name] = (Optional[annotation], Field(None, description=description))

    model_name = re.sub(r"\W", "_", tool.name.title()) + "Args"
    return create_model(model_name, **fields)


def _make_mcp_tool(session: ClientSession, mcp_tool) -> StructuredTool:
    """MCP 도구 하나를 LangChain 에이전트가 호출할 수 있게 감싼다."""
    async def call_mcp(**arguments):
        result = await session.call_tool(mcp_tool.name, arguments)
        text = _text(result)
        if getattr(result, "isError", False):
            raise RuntimeError(text)
        return text

    return StructuredTool.from_function(
        name=mcp_tool.name,
        description=mcp_tool.description or f"MCP tool: {mcp_tool.name}",
        args_schema=_args_model(mcp_tool),
        coroutine=call_mcp,
    )


def _message_text(message) -> str:
    """LangChain 메시지에서 텍스트 답변을 꺼낸다."""
    text = getattr(message, "text", None)
    if text:
        return text

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


async def main() -> None:
    print(f"==> MCP 도서관 서버 연결: {SERVER.name}")
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            server_name = info.serverInfo.name
            mcp_tools = (await session.list_tools()).tools
            if not mcp_tools:
                print(f"서버 {server_name}에서 사용할 수 있는 도구가 없습니다.")
                return

            tools = [_make_mcp_tool(session, tool) for tool in mcp_tools]
            llm = ChatOpenAI(model=MODEL, reasoning_effort="none", temperature=0)
            agent = create_agent(llm, tools, system_prompt=SYSTEM)

            print(f"==> 연결됨 — 서버: {server_name}")
            print("사용 가능한 도구:")
            for tool in mcp_tools:
                print(f"  - {tool.name}: {tool.description}")
            print("질문을 입력하세요. /reset 으로 대화를 초기화하고 /quit 으로 종료합니다.\n")

            history = []
            while True:
                try:
                    question = input("You: ").strip()
                except EOFError:
                    print()
                    break

                if not question:
                    continue
                if question == "/reset":
                    history.clear()
                    print("(대화 초기화)\n")
                    continue
                if question == "/quit":
                    print("(대화 종료)")
                    break

                current_history = [*history, {"role": "user", "content": question}]
                if len(current_history) > MAX_TURNS * 2:
                    del current_history[:2]

                try:
                    result = await agent.ainvoke({"messages": current_history})
                    answer = _message_text(result["messages"][-1])
                    current_history.append({"role": "assistant", "content": answer})
                    history = current_history
                    print(f"Bot: {answer}\n")
                except Exception as error:
                    print(f"오류 발생: {error}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n(Ctrl+C로 종료)")
