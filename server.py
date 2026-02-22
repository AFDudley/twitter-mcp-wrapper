#!/usr/bin/env python3
"""
Twitter MCP Server using twikit

This server provides Twitter functionality through the Model Context Protocol (MCP).
It uses twikit for Twitter API interactions and supports authentication via ct0 and auth_token
cookies provided by the LLM model or environment variables.
"""

import asyncio
import os
import json
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
import mcp.types as types

from twikit import Client
from twikit_grok import Client as GrokClient

# Load environment variables
load_dotenv()

class TwitterMCPServer:
    def __init__(self):
        self.server = Server("twitter-mcp")
        # Read cookies from environment at startup
        self.ct0 = os.getenv("TWITTER_CT0")
        self.auth_token = os.getenv("TWITTER_AUTH_TOKEN")
        if not self.ct0 or not self.auth_token:
            raise ValueError("TWITTER_CT0 and TWITTER_AUTH_TOKEN environment variables are required")
        self._client = None  # Lazy-initialized authenticated client
        self._grok_client = None  # Lazy-initialized Grok client
        self.setup_handlers()

    def setup_handlers(self):
        """Set up MCP server handlers"""
        
        @self.server.list_resources()
        async def handle_list_resources() -> list[Resource]:
            """List available Twitter resources"""
            return [
                Resource(
                    uri="twitter://timeline",
                    name="Twitter Timeline",
                    description="Get tweets from your timeline (requires ct0 and auth_token)",
                    mimeType="application/json"
                ),
                Resource(
                    uri="twitter://user-tweets",
                    name="User Tweets",
                    description="Get tweets from a specific user (requires ct0 and auth_token)",
                    mimeType="application/json"
                ),
                Resource(
                    uri="twitter://search",
                    name="Search Tweets",
                    description="Search for tweets (requires ct0 and auth_token)",
                    mimeType="application/json"
                ),
                Resource(
                    uri="twitter://dm-history",
                    name="DM History",
                    description="Get direct message history with a user (requires ct0 and auth_token)",
                    mimeType="application/json"
                )
            ]

        @self.server.read_resource()
        async def handle_read_resource(uri: types.AnyUrl) -> str:
            """Read a specific Twitter resource"""
            client = await self._get_client()
            
            if uri.scheme != "twitter":
                raise ValueError(f"Unsupported URI scheme: {uri.scheme}")
            
            path = uri.path.lstrip("/")
            
            if path == "timeline":
                tweets = await self._get_timeline(client)
                return json.dumps(tweets, indent=2)
            elif path == "user-tweets":
                # Extract username from query parameters if provided
                username = getattr(uri, 'fragment', None) or "twitter"
                tweets = await self._get_user_tweets(client, username)
                return json.dumps(tweets, indent=2)
            elif path == "search":
                # Extract query from fragment if provided, use 'Latest' product by default
                query = getattr(uri, 'fragment', None) or "python"
                tweets = await self._search_tweets(client, query, product="Latest")
                return json.dumps(tweets, indent=2)
            elif path == "dm-history":
                # Extract username from fragment if provided
                username = getattr(uri, 'fragment', None) or "twitter"
                dm_history = await self._get_dm_history(client, username)
                return json.dumps(dm_history, indent=2)
            else:
                raise ValueError(f"Unknown resource path: {path}")

        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """List available Twitter tools"""
            return [
                Tool(
                    name="tweet",
                    description="Post a tweet",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The text content of the tweet",
                                "maxLength": 280
                            }
                        },
                        "required": ["text"]
                    }
                ),
                Tool(
                    name="get_user_info",
                    description="Get information about a Twitter user",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "username": {
                                "type": "string",
                                "description": "The username (without @) to get info for"
                            }
                        },
                        "required": ["username"]
                    }
                ),
                Tool(
                    name="search_tweets",
                    description="Search for tweets with a specific query",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "count": {
                                "type": "integer",
                                "description": "Number of tweets to return (default: 20)",
                                "default": 20,
                                "minimum": 1,
                                "maximum": 100
                            },
                            "product": {
                                "type": "string",
                                "description": "Type of results to return (e.g., 'Top' or 'Latest')",
                                "enum": ["Top", "Latest"],
                                "default": "Latest"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="get_timeline",
                    description="Get tweets from your timeline",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "count": {
                                "type": "integer",
                                "description": "Number of tweets to return (default: 20)",
                                "default": 20,
                                "minimum": 1,
                                "maximum": 100
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="get_latest_timeline",
                    description="Get latest tweets from your timeline",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "count": {
                                "type": "integer",
                                "description": "Number of tweets to return (default: 20)",
                                "default": 20,
                                "minimum": 1,
                                "maximum": 100
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="like_tweet",
                    description="Like a tweet by ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tweet_id": {
                                "type": "string",
                                "description": "The ID of the tweet to like"
                            }
                        },
                        "required": ["tweet_id"]
                    }
                ),
                Tool(
                    name="retweet",
                    description="Retweet a tweet by ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tweet_id": {
                                "type": "string",
                                "description": "The ID of the tweet to retweet"
                            }
                        },
                        "required": ["tweet_id"]
                    }
                ),
                Tool(
                    name="authenticate",
                    description="Test authentication and return user info",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                Tool(
                    name="send_dm",
                    description="Send a direct message to a user",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "recipient_username": {
                                "type": "string",
                                "description": "The username (without @) of the recipient"
                            },
                            "text": {
                                "type": "string",
                                "description": "The message text to send"
                            }
                        },
                        "required": ["recipient_username", "text"]
                    }
                ),
                Tool(
                    name="get_dm_history",
                    description="Get direct message history with a user",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "recipient_username": {
                                "type": "string",
                                "description": "The username (without @) to get DM history with"
                            },
                            "count": {
                                "type": "integer",
                                "description": "Number of messages to return (default: 20)",
                                "default": 20,
                                "minimum": 1,
                                "maximum": 100
                            }
                        },
                        "required": ["recipient_username"]
                    }
                ),
                Tool(
                    name="add_reaction_to_message",
                    description="Add a reaction (emoji) to a direct message",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "message_id": {
                                "type": "string",
                                "description": "The ID of the message to react to"
                            },
                            "emoji": {
                                "type": "string",
                                "description": "The emoji to react with (e.g., '❤️', '👍', '😂')"
                            },
                            "conversation_id": {
                                "type": "string",
                                "description": "The conversation ID"
                            }
                        },
                        "required": ["message_id", "emoji", "conversation_id"]
                    }
                ),
                Tool(
                    name="delete_dm",
                    description="Delete a direct message",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "message_id": {
                                "type": "string",
                                "description": "The ID of the message to delete"
                            }
                        },
                        "required": ["message_id"]
                    }
                ),
                Tool(
                    name="get_tweet_replies",
                    description="Get replies to a specific tweet",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tweet_id": {
                                "type": "string",
                                "description": "The ID of the tweet to get replies for"
                            },
                            "count": {
                                "type": "integer",
                                "description": "Number of replies to retrieve (default: 20)",
                                "default": 20
                            }
                        },
                        "required": ["tweet_id"]
                    }
                ),
                Tool(
                    name="get_trends",
                    description="Get trending topics on Twitter",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "The category of trends to retrieve",
                                "enum": ["trending", "for-you", "news", "sports", "entertainment"],
                                "default": "trending"
                            },
                            "count": {
                                "type": "integer",
                                "description": "Number of trends to retrieve (default: 20)",
                                "default": 20,
                                "minimum": 1,
                                "maximum": 50
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="ask_grok",
                    description="Ask Grok AI a question",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question to ask Grok"
                            }
                        },
                        "required": ["question"]
                    }
                ),
                Tool(
                    name="debug_grok_chunks",
                    description="Debug tool to analyze Grok API chunk behavior",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question to ask Grok"
                            }
                        },
                        "required": ["question"]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """Handle tool calls"""
            try:
                # Get authenticated client (uses credentials from environment)
                client = await self._get_client()
                
                if name == "authenticate":
                    result = await self._test_authentication(client)
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                
                elif name == "tweet":
                    result = await self._post_tweet(client, arguments["text"])
                    return [types.TextContent(type="text", text=f"Tweet posted successfully: {json.dumps(result, indent=2)}")]
                
                elif name == "get_user_info":
                    result = await self._get_user_info(client, arguments["username"])
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                
                elif name == "search_tweets":
                    count = arguments.get("count", 20)
                    product = arguments.get("product", "Latest")
                    # Ensure the product value is only 'Top' or 'Latest'
                    if product not in ("Top", "Latest"):
                        product = "Latest"
                    
                    result = await self._search_tweets(client, arguments["query"], count, product)
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                
                elif name == "get_timeline":
                    count = arguments.get("count", 20)
                    result = await self._get_timeline(client, count)
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                
                elif name == "get_latest_timeline":
                    count = arguments.get("count", 20)
                    result = await self._get_latest_timeline(client, count)
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                
                elif name == "like_tweet":
                    result = await self._like_tweet(client, arguments["tweet_id"])
                    return [types.TextContent(type="text", text=f"Tweet liked successfully: {json.dumps(result, indent=2)}")]
                
                elif name == "retweet":
                    result = await self._retweet(client, arguments["tweet_id"])
                    return [types.TextContent(type="text", text=f"Tweet retweeted successfully: {json.dumps(result, indent=2)}")]
                
                elif name == "send_dm":
                    result = await self._send_dm(client, arguments["recipient_username"], arguments["text"])
                    return [types.TextContent(type="text", text=f"DM sent successfully: {json.dumps(result, indent=2)}")]
                
                elif name == "get_dm_history":
                    count = arguments.get("count", 20)
                    result = await self._get_dm_history(client, arguments["recipient_username"], count)
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                
                elif name == "add_reaction_to_message":
                    result = await self._add_reaction_to_message(client, arguments["message_id"], arguments["emoji"], arguments["conversation_id"])
                    return [types.TextContent(type="text", text=f"Reaction added successfully: {json.dumps(result, indent=2)}")]
                
                elif name == "delete_dm":
                    result = await self._delete_dm(client, arguments["message_id"])
                    return [types.TextContent(type="text", text=f"DM deleted successfully: {json.dumps(result, indent=2)}")]
                
                elif name == "get_tweet_replies":
                    count = arguments.get("count", 20)
                    result = await self._get_tweet_replies(client, arguments["tweet_id"], count)
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                
                elif name == "get_trends":
                    category = arguments.get("category", "trending")
                    count = arguments.get("count", 20)
                    result = await self._get_trends(client, category, count)
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

                elif name == "ask_grok":
                    grok_client = await self._get_grok_client()
                    message = await self._ask_grok_buffered(grok_client, arguments["question"])
                    return [types.TextContent(type="text", text=message)]

                elif name == "debug_grok_chunks":
                    # Debug tool to analyze raw chunk behavior
                    grok_client = await self._get_grok_client()
                    result = await self._debug_grok_chunks(grok_client, arguments["question"])
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

                else:
                    raise ValueError(f"Unknown tool: {name}")

            except Exception as e:
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    async def _get_client(self) -> Client:
        """Get or create the authenticated client using environment credentials"""
        if self._client is not None:
            return self._client

        # Create new client and authenticate
        client = Client('en-US')

        # Set the cookies from instance variables
        cookies = {
            'ct0': self.ct0,
            'auth_token': self.auth_token
        }
        client.set_cookies(cookies)

        # Test authentication by getting user info
        try:
            user_id = await client.user_id()
            if not user_id:
                raise ValueError("Failed to get user ID")
        except Exception as e:
            raise ValueError(f"Authentication failed with provided cookies: {str(e)}")

        # Cache the authenticated client
        self._client = client
        return client

    async def _get_grok_client(self) -> GrokClient:
        """Get or create the Grok client using environment credentials"""
        if self._grok_client is not None:
            return self._grok_client

        client = GrokClient('en-US')
        client.set_cookies({'ct0': self.ct0, 'auth_token': self.auth_token})

        # Initialize client_transaction by making a request through the
        # normal request() path, which fetches Twitter's home page to set up
        # the transaction ID generator. Without this, transaction IDs are
        # invalid and Grok API returns code 34 errors.
        try:
            await client.user_id()
        except Exception:
            pass

        self._grok_client = client
        return client

    async def _test_authentication(self, client: Client) -> Dict[str, Any]:
        """Test authentication and return user info"""
        user = await client.user()
        return {
            "authenticated": True,
            "user": {
                "id": user.id,
                "username": user.screen_name,
                "name": user.name,
                "followers_count": user.followers_count,
                "following_count": user.following_count,
                "tweet_count": user.statuses_count,
                "verified": user.verified
            }
        }

    async def _post_tweet(self, client: Client, text: str) -> Dict[str, Any]:
        """Post a tweet"""
        tweet = await client.create_tweet(text=text)
        return {
            "id": tweet.id,
            "text": tweet.text,
            "created_at": str(tweet.created_at),
            "author": tweet.user.screen_name
        }

    async def _get_user_info(self, client: Client, username: str) -> Dict[str, Any]:
        """Get user information"""
        user = await client.get_user_by_screen_name(username)
        return {
            "id": user.id,
            "username": user.screen_name,
            "name": user.name,
            "description": user.description,
            "followers_count": user.followers_count,
            "following_count": user.following_count,
            "tweet_count": user.statuses_count,
            "verified": user.verified,
            "created_at": str(user.created_at)
        }

    async def _search_tweets(self, client: Client, query: str, count: int = 20, product: str = "Latest") -> List[Dict[str, Any]]:
        """Search for tweets"""
        tweets = await client.search_tweet(query, product=product, count=count)
        return [
            {
                "id": tweet.id,
                "text": tweet.text,
                "author": tweet.user.screen_name,
                "author_name": tweet.user.name,
                "created_at": str(tweet.created_at),
                "like_count": tweet.favorite_count,
                "retweet_count": tweet.retweet_count,
                "reply_count": tweet.reply_count
            }
            for tweet in tweets
        ]

    async def _get_timeline(self, client: Client, count: int = 20) -> List[Dict[str, Any]]:
        """Get timeline tweets"""
        # Use get_timeline() instead of get_home_timeline()
        tweets = await client.get_timeline(count=count)
        return [
            {
                "id": tweet.id,
                "text": tweet.text,
                "author": tweet.user.screen_name,
                "author_name": tweet.user.name,
                "created_at": str(tweet.created_at),
                "like_count": tweet.favorite_count,
                "retweet_count": tweet.retweet_count,
                "reply_count": tweet.reply_count
            }
            for tweet in tweets
        ]

    async def _get_user_tweets(self, client: Client, username: str, count: int = 20) -> List[Dict[str, Any]]:
        """Get tweets from a specific user"""
        user = await client.get_user_by_screen_name(username)
        tweets = await client.get_user_tweets(user.id, tweet_type='Tweets', count=count)
        return [
            {
                "id": tweet.id,
                "text": tweet.text,
                "author": tweet.user.screen_name,
                "author_name": tweet.user.name,
                "created_at": str(tweet.created_at),
                "like_count": tweet.favorite_count,
                "retweet_count": tweet.retweet_count,
                "reply_count": tweet.reply_count
            }
            for tweet in tweets
        ]

    async def _like_tweet(self, client: Client, tweet_id: str) -> Dict[str, Any]:
        """Like a tweet"""
        result = await client.favorite_tweet(tweet_id)
        return {"success": True, "tweet_id": tweet_id}

    async def _retweet(self, client: Client, tweet_id: str) -> Dict[str, Any]:
        """Retweet a tweet"""
        result = await client.retweet(tweet_id)
        return {"success": True, "tweet_id": tweet_id}

    async def _get_latest_timeline(self, client: Client, count: int = 20) -> List[Dict[str, Any]]:
        """Get latest timeline tweets"""
        # Use get_latest_timeline() instead of get_home_timeline()
        tweets = await client.get_latest_timeline(count=count)
        return [
            {
                "id": tweet.id,
                "text": tweet.text,
                "author": tweet.user.screen_name,
                "author_name": tweet.user.name,
                "created_at": str(tweet.created_at),
                "like_count": tweet.favorite_count,
                "retweet_count": tweet.retweet_count,
                "reply_count": tweet.reply_count
            }
            for tweet in tweets
        ]

    async def _send_dm(self, client: Client, recipient_username: str, text: str) -> Dict[str, Any]:
        """Send a direct message to a user"""
        # First get the user_id from the username
        user = await client.get_user_by_screen_name(recipient_username)
        user_id = user.id
        
        result = await client.send_dm(user_id, text)
        return {
            "success": True,
            "recipient_username": recipient_username,
            "recipient_user_id": user_id,
            "text": text,
            "message_id": result.id,
            "created_at": str(result.time)
        }

    async def _get_dm_history(self, client: Client, recipient_username: str, count: int = 20) -> List[Dict[str, Any]]:
        """Get direct message history with a user"""
        # First get the user_id from the username
        user = await client.get_user_by_screen_name(recipient_username)
        user_id = user.id
        
        result = await client.get_dm_history(user_id)
        messages = []
        for i, message in enumerate(result):
            if i >= count:  # Limit to requested count
                break
            messages.append({
                "id": message.id,
                "text": message.text,
                "time": str(message.time),
                "sender_id": getattr(message, 'sender_id', None),
                "recipient_id": getattr(message, 'recipient_id', None),
                "attachment": getattr(message, 'attachment', None)
            })
        return messages

    async def _add_reaction_to_message(self, client: Client, message_id: str, emoji: str, conversation_id: str) -> Dict[str, Any]:
        """Add a reaction (emoji) to a direct message"""
        result = await client.add_reaction_to_message(message_id, conversation_id, emoji)
        return {
            "success": True,
            "message_id": message_id,
            "emoji": emoji,
            "conversation_id": conversation_id
        }

    async def _delete_dm(self, client: Client, message_id: str) -> Dict[str, Any]:
        """Delete a direct message"""
        result = await client.delete_dm(message_id)
        return {
            "success": True,
            "message_id": message_id
        }

    async def _get_tweet_replies(self, client: Client, tweet_id: str, count: int = 20) -> Dict[str, Any]:
        """Get replies to a specific tweet using conversation search"""
        try:
            # Use search with conversation_id to get replies - more reliable than get_tweet_by_id
            query = f"conversation_id:{tweet_id}"
            results = await client.search_tweet(query, 'Latest', count=min(count + 1, 20))

            original_tweet = None
            replies_data = []

            for tweet in results:
                if tweet.id == tweet_id:
                    # This is the original tweet
                    original_tweet = {
                        "id": tweet.id,
                        "text": tweet.text,
                        "author": tweet.user.screen_name,
                        "reply_count": tweet.reply_count
                    }
                else:
                    # This is a reply
                    replies_data.append({
                        "id": tweet.id,
                        "text": tweet.text,
                        "author_id": tweet.user.id,
                        "author_username": tweet.user.screen_name,
                        "author_name": tweet.user.name,
                        "created_at": str(tweet.created_at),
                        "reply_count": tweet.reply_count,
                        "retweet_count": tweet.retweet_count,
                        "favorite_count": tweet.favorite_count,
                        "in_reply_to": tweet.in_reply_to
                    })
                    if len(replies_data) >= count:
                        break

            # If we didn't find the original tweet in results, fetch it separately
            if original_tweet is None:
                try:
                    tweet = await client.get_tweet_by_id(tweet_id)
                    if tweet:
                        original_tweet = {
                            "id": tweet.id,
                            "text": tweet.text,
                            "author": tweet.user.screen_name,
                            "reply_count": tweet.reply_count
                        }
                except Exception:
                    original_tweet = {"id": tweet_id, "text": "Unable to fetch", "author": "unknown", "reply_count": 0}

            return {
                "original_tweet": original_tweet,
                "replies": replies_data,
                "total_replies_retrieved": len(replies_data)
            }

        except Exception as e:
            return {"error": f"Failed to get tweet replies: {str(e)}"}

    async def _get_trends(self, client: Client, category: str, count: int) -> List[Dict[str, Any]]:
        """Get trending topics on Twitter"""
        trends = await client.get_trends(category, count)
        return [
            {
                "name": trend.name,
                "tweets_count": trend.tweets_count,
                "domain_context": trend.domain_context,
                "grouped_trends": trend.grouped_trends
            }
            for trend in trends
        ]

    async def _ask_grok_buffered(self, grok_client, question: str) -> str:
        """Ask Grok with proper buffered streaming to avoid mid-JSON chunk splits."""
        from twikit_grok.constants import Endpoint
        from urllib.parse import urlparse
        from copy import deepcopy

        conversation = await grok_client.create_grok_conversation()

        responses = deepcopy(conversation.history) if conversation.history else []
        responses.append({
            'message': question,
            'sender': 1,
            'promptSource': '',
            'fileAttachments': []
        })

        data = {
            'responses': responses,
            'systemPromptName': '',
            'grokModelOptionId': 'grok-2a',
            'conversationId': conversation.id,
            'returnSearchResults': True,
            'returnCitations': True,
            'promptMetadata': {'promptSource': 'NATURAL', 'action': 'INPUT'},
            'imageGenerationCount': 4,
            'requestFeatures': {'eagerTweets': True, 'serverHistory': True}
        }

        headers = grok_client._base_headers.copy()
        headers['content-type'] = 'text/plain;charset=UTF-8'
        tid = grok_client.client_transaction.generate_transaction_id(
            method='POST',
            path=urlparse(Endpoint.GROK_ADD_RESPONSE).path
        )
        headers['X-Client-Transaction-Id'] = tid

        message_parts = []
        buffer = b''

        async with grok_client.http.stream(
            'POST',
            Endpoint.GROK_ADD_RESPONSE,
            json=data,
            headers=headers,
            timeout=None
        ) as response:
            grok_client._remove_duplicate_ct0_cookie()

            async for chunk in response.aiter_bytes():
                buffer += chunk
                # Try to extract complete JSON objects from the buffer
                while buffer:
                    buffer = buffer.lstrip()
                    if not buffer:
                        break
                    if buffer[0:1] != b'{':
                        # Skip non-JSON prefix bytes
                        idx = buffer.find(b'{')
                        if idx == -1:
                            buffer = b''
                            break
                        buffer = buffer[idx:]
                    # Try to parse a JSON object from the start of the buffer
                    try:
                        decoded = buffer.decode('utf-8')
                    except UnicodeDecodeError:
                        break  # Need more bytes
                    try:
                        parsed = json.loads(decoded)
                        # Entire buffer was one JSON object
                        if 'result' in parsed and 'message' in parsed['result']:
                            message_parts.append(parsed['result']['message'])
                        buffer = b''
                    except json.JSONDecodeError as e:
                        # Could be incomplete JSON or multiple objects concatenated
                        # Try to find where the first complete object ends using
                        # brace counting
                        depth = 0
                        in_string = False
                        escape_next = False
                        end_pos = None
                        for i, ch in enumerate(decoded):
                            if escape_next:
                                escape_next = False
                                continue
                            if ch == '\\' and in_string:
                                escape_next = True
                                continue
                            if ch == '"' and not escape_next:
                                in_string = not in_string
                                continue
                            if in_string:
                                continue
                            if ch == '{':
                                depth += 1
                            elif ch == '}':
                                depth -= 1
                                if depth == 0:
                                    end_pos = i + 1
                                    break
                        if end_pos is not None:
                            obj_str = decoded[:end_pos]
                            try:
                                parsed = json.loads(obj_str)
                                if 'result' in parsed and 'message' in parsed['result']:
                                    message_parts.append(parsed['result']['message'])
                            except json.JSONDecodeError:
                                pass
                            buffer = buffer[len(obj_str.encode('utf-8')):]
                        else:
                            # Incomplete object, wait for more data
                            break

        return ''.join(message_parts) if message_parts else "No response from Grok"

    async def _debug_grok_chunks(self, grok_client, question: str) -> Dict[str, Any]:
        """Debug method to analyze raw chunk behavior from Grok API"""
        from twikit_grok.constants import Endpoint
        from urllib.parse import urlparse
        from copy import deepcopy

        conversation = await grok_client.create_grok_conversation()

        # Prepare request (same as twikit_grok does internally)
        responses = deepcopy(conversation.history) if conversation.history else []
        responses.append({
            'message': question,
            'sender': 1,
            'promptSource': '',
            'fileAttachments': []
        })

        data = {
            'responses': responses,
            'systemPromptName': '',
            'grokModelOptionId': 'grok-2a',
            'conversationId': conversation.id,
            'returnSearchResults': True,
            'returnCitations': True,
            'promptMetadata': {'promptSource': 'NATURAL', 'action': 'INPUT'},
            'imageGenerationCount': 4,
            'requestFeatures': {'eagerTweets': True, 'serverHistory': True}
        }

        headers = grok_client._base_headers.copy()
        headers['content-type'] = 'text/plain;charset=UTF-8'
        tid = grok_client.client_transaction.generate_transaction_id(
            method='POST',
            path=urlparse(Endpoint.GROK_ADD_RESPONSE).path
        )
        headers['X-Client-Transaction-Id'] = tid

        # Collect raw chunk data
        chunks_info = []
        successful_parses = 0
        failed_parses = 0
        message_parts = []

        async with grok_client.http.stream(
            'POST',
            Endpoint.GROK_ADD_RESPONSE,
            json=data,
            headers=headers,
            timeout=None
        ) as response:
            grok_client._remove_duplicate_ct0_cookie()

            async for chunk in response.aiter_bytes():
                chunk_info = {
                    "chunk_num": len(chunks_info) + 1,
                    "size_bytes": len(chunk),
                    "raw_preview": chunk[:100].decode('utf-8', errors='replace'),
                }

                try:
                    decoded = chunk.decode('utf-8')
                    parsed = json.loads(decoded)
                    chunk_info["parse_status"] = "success"
                    chunk_info["keys"] = list(parsed.keys())

                    if 'result' in parsed and 'message' in parsed['result']:
                        msg = parsed['result']['message']
                        chunk_info["message_fragment"] = msg
                        message_parts.append(msg)

                    successful_parses += 1

                except UnicodeDecodeError as e:
                    chunk_info["parse_status"] = "unicode_error"
                    chunk_info["error"] = str(e)
                    failed_parses += 1

                except json.JSONDecodeError as e:
                    chunk_info["parse_status"] = "json_error"
                    chunk_info["error"] = f"{e.msg} at position {e.pos}"
                    try:
                        decoded = chunk.decode('utf-8', errors='replace')
                        chunk_info["starts_with_brace"] = decoded.strip().startswith('{')
                        chunk_info["ends_with_brace"] = decoded.strip().endswith('}')
                    except:
                        pass
                    failed_parses += 1

                chunks_info.append(chunk_info)

        reconstructed = ''.join(message_parts)

        return {
            "hypothesis_test": {
                "total_chunks": len(chunks_info),
                "successful_parses": successful_parses,
                "failed_parses": failed_parses,
                "data_loss_rate_percent": round(failed_parses / len(chunks_info) * 100, 1) if chunks_info else 0,
                "confirmed": failed_parses > 0
            },
            "reconstructed_message": reconstructed,
            "chunks": chunks_info
        }

    async def run(self):
        """Run the MCP server"""
        # Import here to avoid issues with event loop
        from mcp.server.stdio import stdio_server
        
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="twitter-mcp",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    )
                )
            )

async def main():
    """Main entry point"""
    server = TwitterMCPServer()
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())