/**
 * LecTrace 前置代理：lectrace.app → Cloud Run。
 *
 * 职责只有四件：
 *  1. 把请求原样转给 Cloud Run（Host 必须改成 run.app 域名，Cloud Run 靠它路由）。
 *  2. 告诉后端浏览器实际访问的域名（X-Forwarded-Host），并用共享密钥 X-Proxy-Auth 证明"这是 Worker 说的"。
 *     客户端直连 run.app 时也能伪造 X-Forwarded-Host，后端只在密钥正确时信任它（见 backend/app/auth.py public_host）。
 *  3. Cookie / Set-Cookie 原样透传：后端下发的是 host-only cookie，浏览器会按 lectrace.app 保存。
 *  4. WebSocket（/ws/*）升级请求原样透传；/api、/ws、/auth 一律不缓存。
 *
 * 环境变量（wrangler.toml / dashboard）：
 *   ORIGIN_HOST         Cloud Run 域名，例如 lectrace-jngknpqwya-an.a.run.app
 *   PROXY_SHARED_SECRET 与后端 PROXY_SHARED_SECRET 相同（用 wrangler secret put 设置，不要写进 toml）
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const publicHost = url.host;
    url.host = env.ORIGIN_HOST;
    url.protocol = "https:";

    const headers = new Headers(request.headers);
    headers.set("Host", env.ORIGIN_HOST);
    headers.set("X-Forwarded-Host", publicHost);
    headers.set("X-Forwarded-Proto", "https");
    // 客户端带来的同名头一律覆盖，防止伪造
    if (env.PROXY_SHARED_SECRET) headers.set("X-Proxy-Auth", env.PROXY_SHARED_SECRET);
    else headers.delete("X-Proxy-Auth");

    const isDynamic = /^\/(api|ws|auth)(\/|$)/.test(url.pathname);
    const init = {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      redirect: "manual", // 后端的 302（/auth/handoff）要原样交给浏览器，不能在 Worker 里跟进
      cf: isDynamic ? { cacheTtl: 0, cacheEverything: false } : undefined,
    };
    const resp = await fetch(url.toString(), init);

    // WebSocket：fetch 返回 101 + webSocket 时必须原样返回，不能改 headers
    if (resp.status === 101) return resp;

    const out = new Response(resp.body, resp);
    if (isDynamic) out.headers.set("Cache-Control", "no-store");
    return out;
  },
};
