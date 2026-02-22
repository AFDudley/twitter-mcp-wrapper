#!/usr/bin/env python3
"""Extract Twitter cookies from Brave browser."""
import sys
import browser_cookie3


def get_twitter_cookies():
    """Extract ct0 and auth_token cookies from Brave browser."""
    cj = browser_cookie3.brave(domain_name='.x.com')

    cookies = {}
    for c in cj:
        if c.name in ('auth_token', 'ct0'):
            cookies[c.name] = c.value

    if 'auth_token' not in cookies or 'ct0' not in cookies:
        print("Missing required Twitter cookies. Make sure you're logged into Twitter in Brave.", file=sys.stderr)
        sys.exit(1)

    return cookies


if __name__ == "__main__":
    cookies = get_twitter_cookies()
    # Output in format suitable for shell eval
    print(f"TWITTER_CT0={cookies['ct0']}")
    print(f"TWITTER_AUTH_TOKEN={cookies['auth_token']}")
