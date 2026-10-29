/**
 * LecTrace 前置代理：lectrace.app → Cloud Run。以线上版本为基础，为域名迁移加了两处：
 *   1. X-Proxy-Auth：共享密钥，后端只在它正确时才信任 X-Forwarded-Host（客户端直连 run.app 伪造无效）。
 *      客户端自带的同名头一律覆盖 / 删除。
 *   2. /api、/ws、/auth 响应加 Cache-Control: no-store，迁移票据的跳转不能被缓存。
 * 其余不变：Host 由 fetch 按目标 URL 重设；redirect: "manual" 让后端的 302（/auth/handoff）原样交给浏览器，
 * Set-Cookie 不丢；WebSocket 101 原样返回；指向 run.app 的 Location 改写成当前域名。
 *
 * 密钥：wrangler secret put PROXY_SHARED_SECRET（值与后端 .env 的 PROXY_SHARED_SECRET 相同），
 * 或在 Dashboard → Settings → Variables 里加一个加密变量。没设时 Worker 不发该头，后端退回按 Host 判断。
 */
const ORIGIN = "https://lectrace-jngknpqwya-an.a.run.app";

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    const target = new URL(incoming.pathname + incoming.search, ORIGIN);

    // 保留 HTTP 方法、请求体和 WebSocket Upgrade 等请求信息
    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.set("X-Forwarded-Host", incoming.host);
    headers.set("X-Forwarded-Proto", "https");
    if (env && env.PROXY_SHARED_SECRET) headers.set("X-Proxy-Auth", env.PROXY_SHARED_SECRET);
    else headers.delete("X-Proxy-Auth");

    const upstreamRequest = new Request(target.toString(), {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD"
        ? undefined
        : request.body,
      redirect: "manual",
    });

    const response = await fetch(upstreamRequest);

    // WebSocket 握手由 Cloudflare 直接透传
    if (response.webSocket) {
      return response;
    }

    const responseHeaders = new Headers(response.headers);

    // 将指向原 Cloud Run 地址的 HTTP 重定向改为当前域名
    const location = responseHeaders.get("location");
    if (location) {
      const redirectURL = new URL(location, ORIGIN);

      if (redirectURL.origin === ORIGIN) {
        redirectURL.protocol = incoming.protocol;
        redirectURL.host = incoming.host;
        responseHeaders.set("location", redirectURL.toString());
      }
    }

    // 动态接口不缓存（登录态、迁移票据）
    if (/^\/(api|ws|auth)(\/|$)/.test(incoming.pathname)) {
      responseHeaders.set("Cache-Control", "no-store");
    }

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  },
};
