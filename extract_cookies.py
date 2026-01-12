#!/usr/bin/env python3
import json
import browser_cookie3


def get_twitter_cookies():
    cj = browser_cookie3.brave(domain_name='.x.com')
    cookies = []
    for c in cj:
        if c.name in ('auth_token', 'ct0', 'twid'):
            # MCP server expects .twitter.com domain
            cookies.append(f"{c.name}={c.value}; Domain=.twitter.com")

    if len(cookies) < 3:
        raise SystemExit(
            "Missing required Twitter cookies. Make sure you're logged into Twitter in Brave."
        )

    return json.dumps(cookies)


if __name__ == "__main__":
    print(get_twitter_cookies())
