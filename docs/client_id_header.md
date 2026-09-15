## What should the value of `CLIENT_ID_HEADER` be?

Depends on deployment.

**Rule:** Use the name of the header your proxy sets with the real client IP.

- **No proxy (local, `streamlit run` direct):**  
  Leave unset. Connection IP used.

- **nginx / Caddy / Traefik / Apache in front:**  
  Use `X-Forwarded-For`.

  Proxy must append:

  ```nginx
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  ```

Code takes the last entry, so client-supplied prefix is ignored.

* **nginx with `$remote_addr` only:**
  Use `X-Real-IP`.

  Single value, overwritten by proxy. Safer than `X-Forwarded-For` since there's no chain.

* **Cloudflare:**
  Use `CF-Connecting-IP`.

* **AWS ALB / GCP LB / Azure Front Door:**
  Use `X-Forwarded-For` (they append).

## Security Requirements

Two conditions must hold, or clients can spoof the header:

1. Exactly **one trusted proxy layer** between the internet and the app.
2. The app port must **not be reachable directly** — only via the proxy. Bind Streamlit to `127.0.0.1` or firewall it.

## If You Have Two Proxies

If two proxies are chained (for example, **Cloudflare → nginx**), the last entry is nginx's view of Cloudflare's IP, not the real client.

In that case:

* Use `CF-Connecting-IP` and have nginx pass it through, **or**
* Configure nginx `real_ip_header` and use `X-Real-IP`.

## Recommended Single-nginx Setup

For a typical single-nginx setup:

```env
CLIENT_ID_HEADER=X-Real-IP
```

With nginx:

```nginx
proxy_set_header X-Real-IP $remote_addr;
```

<br>
