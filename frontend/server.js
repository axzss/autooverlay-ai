const { createProxyMiddleware } = require('http-proxy-middleware')
const next = require('next')

const dev = process.env.NODE_ENV !== 'production'
const app = next({ dev })
const handle = app.getRequestHandler()

app.prepare().then(() => {
  const express = require('express')
  const server = express()

  server.use('/api', createProxyMiddleware({
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
    // Express strips the mount path '/api', so re-add it for the backend's
    // include_router(prefix="/api") routes. hpm 2.x streams JSON bodies
    // from req automatically (no manual onProxyReq write needed).
    pathRewrite: { '^/': '/api/' },
    onError: (err, req, res) => {
      console.error('[proxy] error:', err.message)
      res.status(502).send('Bad Gateway: FastAPI backend unreachable')
    },
  }))

  server.use((req, res) => handle(req, res))

  server.listen(3000, (err) => {
    if (err) throw err
    console.log('> Ready on http://localhost:3000')
  })
})
