// Cube.js entrypoint for the Waibao BI service.
// Run with: node index.js   (port defaults to 4000)

const CubejsServer = require("@cubejs-backend/server-core");
const config = require("./cube.js");

const server = new CubejsServer({
  ...config,
  port: parseInt(process.env.CUBEJS_PORT || "4000", 10),
});

server.listen().then(({ port }) => {
  console.log(`Cube.js BI server listening on http://localhost:${port}`);
});
