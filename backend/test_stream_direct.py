import sys
sys.path.insert(0, ".")
import asyncio
from app.services import llm


async def main():
    print("models:", llm._models())
    try:
        n = 0
        async for d in llm.complete_stream("Say hello in five words.", max_tokens=60):
            n += 1
            print("delta:", repr(d[:60]))
            if n > 5:
                break
        print("deltas received:", n)
    except Exception as e:
        print("STREAM RAISED:", type(e).__name__, str(e)[:300])


asyncio.run(main())
