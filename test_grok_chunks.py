#!/usr/bin/env python3
"""
Test script to verify twikit_grok chunking bug hypothesis.

This script manually calls the Grok API and logs each raw HTTP chunk
to see if chunks are being split mid-JSON, causing the garbled output.
"""

import asyncio
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def test_chunking():
    from twikit_grok import Client
    from twikit_grok.constants import Endpoint
    from urllib.parse import urlparse

    client = Client('en-US')
    client.set_cookies({
        'ct0': os.getenv('TWITTER_CT0'),
        'auth_token': os.getenv('TWITTER_AUTH_TOKEN')
    })

    # Create conversation
    conversation = await client.create_grok_conversation()
    print(f"Created conversation: {conversation.id}\n")

    # Prepare request manually (same as grok_add_response does)
    data = {
        'responses': [{
            'message': 'What is the smallest prime number? Answer in one sentence.',
            'sender': 1,
            'promptSource': '',
            'fileAttachments': []
        }],
        'systemPromptName': '',
        'grokModelOptionId': 'grok-2a',
        'conversationId': conversation.id,
        'returnSearchResults': True,
        'returnCitations': True,
        'promptMetadata': {'promptSource': 'NATURAL', 'action': 'INPUT'},
        'imageGenerationCount': 4,
        'requestFeatures': {'eagerTweets': True, 'serverHistory': True}
    }

    headers = client._base_headers.copy()
    headers['content-type'] = 'text/plain;charset=UTF-8'
    tid = client.client_transaction.generate_transaction_id(
        method='POST',
        path=urlparse(Endpoint.GROK_ADD_RESPONSE).path
    )
    headers['X-Client-Transaction-Id'] = tid

    print("=" * 60)
    print("RAW CHUNK ANALYSIS")
    print("=" * 60 + "\n")

    chunk_num = 0
    successful_parses = 0
    failed_parses = 0
    all_message_parts = []
    failed_chunks = []

    async with client.http.stream(
        'POST',
        Endpoint.GROK_ADD_RESPONSE,
        json=data,
        headers=headers,
        timeout=None
    ) as response:
        client._remove_duplicate_ct0_cookie()

        async for chunk in response.aiter_bytes():
            chunk_num += 1
            chunk_len = len(chunk)

            print(f"--- Chunk {chunk_num} ({chunk_len} bytes) ---")

            # Show raw bytes (truncated)
            raw_preview = chunk[:150]
            print(f"Raw bytes: {raw_preview}{'...' if chunk_len > 150 else ''}")

            try:
                decoded = chunk.decode('utf-8')

                # Check if it looks like multiple JSON objects
                stripped = decoded.strip()
                if stripped.count('}{') > 0:
                    print(f"⚠ WARNING: Multiple JSON objects in single chunk!")

                parsed = json.loads(decoded)
                print(f"✓ Valid JSON (keys: {list(parsed.keys())})")

                if 'result' in parsed:
                    result = parsed['result']
                    if 'message' in result:
                        msg_part = result['message']
                        all_message_parts.append(msg_part)
                        print(f"  Message part: {repr(msg_part)}")

                successful_parses += 1

            except UnicodeDecodeError as e:
                print(f"✗ UnicodeDecodeError: {e}")
                failed_parses += 1
                failed_chunks.append(('unicode', chunk))

            except json.JSONDecodeError as e:
                print(f"✗ JSONDecodeError at pos {e.pos}: {e.msg}")
                try:
                    decoded = chunk.decode('utf-8', errors='replace')
                    print(f"  Partial: {repr(decoded[:100])}...")

                    # Check if it starts or ends mid-JSON
                    if not decoded.strip().startswith('{'):
                        print(f"  → Chunk does NOT start with '{{' - likely continuation!")
                    if not decoded.strip().endswith('}'):
                        print(f"  → Chunk does NOT end with '}}' - likely incomplete!")

                except:
                    pass
                failed_parses += 1
                failed_chunks.append(('json', chunk))

            print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total chunks received: {chunk_num}")
    print(f"Successfully parsed:   {successful_parses}")
    print(f"Failed to parse:       {failed_parses}")

    if chunk_num > 0:
        loss_rate = failed_parses / chunk_num * 100
        print(f"Data loss rate:        {loss_rate:.1f}%")

    print()
    print("=" * 60)
    print("RECONSTRUCTED MESSAGE (from successful parses)")
    print("=" * 60)
    reconstructed = ''.join(all_message_parts)
    print(repr(reconstructed))
    print()
    print("Readable:")
    print(reconstructed)

    if failed_chunks:
        print()
        print("=" * 60)
        print("FAILED CHUNKS DETAIL")
        print("=" * 60)
        for i, (error_type, chunk) in enumerate(failed_chunks[:5]):  # Show first 5
            print(f"\nFailed chunk {i+1} ({error_type}):")
            try:
                print(f"  {chunk.decode('utf-8', errors='replace')[:200]}")
            except:
                print(f"  {chunk[:200]}")

    # Hypothesis conclusion
    print()
    print("=" * 60)
    print("HYPOTHESIS TEST RESULT")
    print("=" * 60)
    if failed_parses > 0:
        print("✓ CONFIRMED: Chunks are being split mid-JSON!")
        print("  The garbled output is caused by lost data from failed JSON parses.")
    else:
        print("✗ NOT CONFIRMED: All chunks parsed successfully.")
        print("  The garbled output may have a different cause.")

if __name__ == '__main__':
    asyncio.run(test_chunking())
