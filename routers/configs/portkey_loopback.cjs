// The gateway has no --host option and listens on all interfaces. Preload this to force loopback:
// NODE_OPTIONS=--require=./routers/configs/portkey_loopback.cjs npx -y @portkey-ai/gateway@1.15.2 --port=8787 --headless
const net = require("net");
const listen = net.Server.prototype.listen;

net.Server.prototype.listen = function (first, ...rest) {
  const callback = [first, ...rest].find((arg) => typeof arg === "function");
  const options = typeof first === "object" ? first : { port: first };
  return listen.call(this, { ...options, host: "127.0.0.1" }, callback);
};
