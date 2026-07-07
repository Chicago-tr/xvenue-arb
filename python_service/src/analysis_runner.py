import asyncio
import time

from spark import run_spark


async def continuous_analysis():
    while True:
        try:
            print(f"[{time.strftime('%H:%M:%S')}] Starting Spark analysis...")
            start_time = time.time()

            run_spark()

            elapsed = time.time() - start_time
            print(f"[{time.strftime('%H:%M:%S')}] Analysis complete ({elapsed:.1f}s)")
            await asyncio.sleep(max(0, 7 - elapsed))

        except KeyboardInterrupt:
            print(" Shutting down...")
            break
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Analysis failed: {e}")
            await asyncio.sleep(10)


if __name__ == "__main__":
    print(" Continuous Spark analysis (7s cycle)")
    asyncio.run(continuous_analysis())
