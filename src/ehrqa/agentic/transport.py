"""One HTTP request with a total deadline, not only network inactivity limits."""
import asyncio
import httpx


def post_json(base_url,headers,payload,*,timeout_s=120,transport=None):
    async def request():
        async with httpx.AsyncClient(base_url=base_url,headers=headers,timeout=timeout_s,
                                    follow_redirects=False,transport=transport) as client:
            return await client.post('/chat/completions',json=payload)
    async def bounded():
        return await asyncio.wait_for(request(),timeout=timeout_s)
    return asyncio.run(bounded())
