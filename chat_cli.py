#!/usr/bin/env python3
"""멀티턴 LangChain 채팅 CLI.

Usage: python chat_cli.py
명령어: /reset (초기화), /stats (통계), /quit (종료)
"""

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

load_dotenv()
MODEL = "gpt-6-luna"
MAX_TURNS = 3
SYSTEM = "당신은 친절한 AI 어시스턴트입니다. 모르면 '확인 필요'라고만 답하세요."

# 노트북의 LangChain 예제와 같은 모델 설정
llm = ChatOpenAI(model=MODEL, reasoning_effort="none", temperature=0.3)

# 상태: 최근 대화는 role/content dict로 보관하고 호출 직전에 LangChain 메시지로 변환
history = []
usage_log = []


def reset():
    """대화 히스토리 초기화."""
    global history, usage_log
    history.clear()
    usage_log.clear()
    print("(대화 초기화)")


def chat(message: str, temperature: float = 0.3) -> str:
    """사용자 메시지에 대한 챗봇 응답 생성."""
    current_history = [*history, {"role": "user", "content": message}]
    if len(current_history) > MAX_TURNS * 2:
        del current_history[:2]

    messages = [SystemMessage(content=SYSTEM)]
    for item in current_history:
        message_class = HumanMessage if item["role"] == "user" else AIMessage
        messages.append(message_class(content=item["content"]))

    response = llm.bind(temperature=temperature).invoke(messages)
    answer = response.content
    current_history.append({"role": "assistant", "content": answer})
    history[:] = current_history

    # LangChain OpenAI 응답은 usage_metadata를 제공한다. 구버전 호환을 위해
    # response_metadata의 token_usage도 확인한다.
    token_usage = getattr(response, "usage_metadata", None)
    if not token_usage:
        token_usage = getattr(response, "response_metadata", {}).get("token_usage", {})
    usage_log.append(token_usage.get("total_tokens"))

    return answer


def show_stats():
    """토큰 및 비용 통계 출력."""
    if not usage_log:
        print("(아직 메시지 없음)")
        return

    PRICE = 0.30 / 1_000_000  # 입출력 혼합 평균
    print(f"  턴 수: {len(usage_log)}")
    measured_usage = [tokens for tokens in usage_log if tokens is not None]
    if not measured_usage:
        print("  토큰 사용량: 모델 응답에서 제공되지 않음")
        return

    total = sum(measured_usage)
    per_turn = total / len(measured_usage)
    if len(measured_usage) < len(usage_log):
        print(f"  사용량 확인된 턴: {len(measured_usage)}/{len(usage_log)}")
    print(f"  누적 토큰: {total}")
    print(f"  누적 비용: ${total * PRICE:.5f}")
    print(f"  평균 턴당: {per_turn:.1f} tokens")
    print(f"  100턴 추정: ${per_turn * 100 * PRICE:.4f}")


def main():
    """메인 CLI 루프."""
    print("=" * 60)
    print("멀티턴 AI 챗봇 CLI")
    print("=" * 60)
    print("명령어:")
    print("  /reset   - 대화 초기화")
    print("  /stats   - 토큰 및 비용 통계")
    print("  /persona - 페르소나 변경 (구현 예정)")
    print("  /quit    - 종료")
    print("=" * 60)
    print()
    
    reset()
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
            
            if user_input == "/reset":
                reset()
                continue
            
            if user_input == "/stats":
                show_stats()
                continue
            
            if user_input == "/quit":
                print("(대화 종료)")
                break
            
            print("Bot: ", end="", flush=True)
            response = chat(user_input)
            print(response)
            print()
            
        except KeyboardInterrupt:
            print("\n(Ctrl+C로 종료)")
            break
        except Exception as e:
            print(f"오류 발생: {e}")


if __name__ == "__main__":
    main()
