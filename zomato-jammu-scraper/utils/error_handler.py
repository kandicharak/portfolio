from asyncio import sleep
from functools import wraps

from loguru import logger

class ScrapingError(Exception):
    pass

class NavigationError(ScrapingError):
    pass

class ExtractionError(ScrapingError):
    pass

class AntiBotDetected(ScrapingError):
    pass

def retry_on_failure(max_retries=3, backoff_base=10):
    def decorator_retry(func):
        @wraps(func)
        async def func_retry(*args, **kwargs):
            for i in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except AntiBotDetected as e:
                    logger.error(f"Anti-bot detected: {str(e)}")
                    if i == max_retries:
                        raise
                    await sleep(backoff_base * (2 ** i))
                except NavigationError as e:
                    logger.error(f"Navigation error: {str(e)}")
                    if i == max_retries:
                        raise
                    await sleep(backoff_base * (2 ** i))
                except ExtractionError as e:
                    logger.error(f"Extraction error: {str(e)}")
                    if i == max_retries:
                        raise
                    await sleep(backoff_base * (2 ** i))
        return func_retry
    return decorator_retry

if __name__ == "__main__":
    @retry_on_failure()
    async def test_func():
        logger.info("Running test...")
        return "ok"

    async def main():
        try:
            result = await test_func()
            print("Error handler tests passed")
        except ScrapingError as e:
            print(f"Error handler tests failed: {str(e)}")

    import asyncio
    asyncio.run(main())
