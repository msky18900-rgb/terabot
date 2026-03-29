import httpx
import os
import math
import json
import logging
import re
from auth import get_cookies

logger = logging.getLogger(__name__)

CHUNK_SIZE = 4 * 1024 * 1024  # 4MB chunks
CDNS = ["c-jp", "c-na", "c-eu", "szb-cdata", "kul-cdata"]  # Try different regions if one fails

def build_headers(cookies: dict) -> dict:
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return {
        "Cookie": cookie_str,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Referer": "https://www.terabox.com/",
        "Origin": "https://www.terabox.com",
    }

async def get_jstoken(cookies: dict) -> str:
    """Extract jsToken more reliably using regex."""
    headers = build_headers(cookies)
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        r = await client.get("https://www.terabox.com/main")
        text = r.text

        # Multiple patterns to extract jsToken
        patterns = [
            r'locals\.jsToken["\']?\s*[:=]\s*["\']([^"\']+)',
            r'jsToken["\']?\s*[:=]\s*["\']([^"\']+)',
            r'"jsToken"\s*:\s*"([^"]+)"'
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
    logger.warning("Could not extract jsToken from main page")
    return ""

async def upload_to_terabox(file_path: str, progress_callback=None) -> dict:
    """Full pipeline with better error handling and CDN fallback."""
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    num_chunks = math.ceil(file_size / CHUNK_SIZE)
    remote_path = f"/我的资源/{filename}"

    cookies = await get_cookies()
    jstoken = await get_jstoken(cookies)

    if not jstoken:
        logger.info("jsToken missing → refreshing cookies")
        cookies = await get_cookies(force_refresh=True)
        jstoken = await get_jstoken(cookies)

    # Pre-create
    pre = await pre_create(cookies, jstoken, filename, file_size, num_chunks)
    if pre.get("errno", -1) != 0:
        if pre.get("errno") in [111, 310, -6]:  # common token/cookie issues
            logger.info("Token expired → refreshing")
            cookies = await get_cookies(force_refresh=True)
            jstoken = await get_jstoken(cookies)
            pre = await pre_create(cookies, jstoken, filename, file_size, num_chunks)
        if pre.get("errno", -1) != 0:
            raise Exception(f"Pre-create failed: {pre}")

    upload_id = pre.get("uploadid")
    if not upload_id:
        raise Exception("No uploadid received from precreate")

    block_list = []
    cdn_index = 0

    # Upload chunks
    with open(file_path, "rb") as f:
        for i in range(num_chunks):
            chunk = f.read(CHUNK_SIZE)
            success = False
            for _ in range(3):  # retry per chunk
                try:
                    cdn = CDNS[cdn_index % len(CDNS)]
                    md5 = await upload_chunk(cookies, jstoken, remote_path, upload_id, chunk, i, cdn)
                    block_list.append(md5)
                    success = True
                    break
                except Exception as e:
                    logger.warning(f"Chunk {i} failed on {cdn}: {e}")
                    cdn_index += 1
                    await asyncio.sleep(2)

            if not success:
                raise Exception(f"Failed to upload chunk {i} after retries")

            if progress_callback:
                pct = int(((i + 1) / num_chunks) * 100)
                await progress_callback(pct, i + 1, num_chunks)

    # Finalize
    result = await create_file(cookies, jstoken, remote_path, file_size, upload_id, block_list)
    if result.get("errno", -1) != 0:
        raise Exception(f"Finalize failed: {result}")

    logger.info(f"✅ Upload completed: {filename}")
    return result

# (Keep pre_create, upload_chunk, create_file functions but with small improvements)
async def pre_create(cookies: dict, jstoken: str, filename: str, file_size: int, num_chunks: int) -> dict:
    headers = build_headers(cookies)
    async with httpx.AsyncClient(headers=headers, timeout=60) as client:
        r = await client.post(
            "https://www.terabox.com/api/precreate",
            params={"jsToken": jstoken, "app_id": "250528", "channel": "chunked", "clienttype": "0"},
            data={
                "path": f"/我的资源/{filename}",
                "size": file_size,
                "isdir": "0",
                "block_list": json.dumps(["" for _ in range(num_chunks)]),
                "autoinit": "1",
            }
        )
        return r.json()

async def upload_chunk(cookies: dict, jstoken: str, path: str, upload_id: str, chunk_data: bytes, idx: int, cdn: str = "c-jp") -> str:
    headers = build_headers(cookies)
    async with httpx.AsyncClient(headers=headers, timeout=600) as client:
        r = await client.post(
            f"https://{cdn}.terabox.com/rest/2.0/pcs/superfile2",
            params={
                "method": "upload",
                "jsToken": jstoken,
                "app_id": "250528",
                "channel": "chunked",
                "clienttype": "0",
                "path": path,
                "uploadid": upload_id,
                "partseq": idx,
            },
            files={"file": ("blob", chunk_data, "application/octet-stream")},
        )
        data = r.json()
        if data.get("errno") != 0:
            raise Exception(f"Chunk upload failed: {data}")
        return data.get("md5", "")

async def create_file(cookies: dict, jstoken: str, path: str, file_size: int, upload_id: str, block_list: list) -> dict:
    headers = build_headers(cookies)
    async with httpx.AsyncClient(headers=headers, timeout=60) as client:
        r = await client.post(
            "https://www.terabox.com/api/create",
            params={"jsToken": jstoken, "app_id": "250528", "channel": "chunked", "clienttype": "0"},
            data={
                "path": path,
                "size": file_size,
                "isdir": "0",
                "block_list": json.dumps(block_list),
                "uploadid": upload_id,
            }
        )
        return r.json()
