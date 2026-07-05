# Menambahkan Argo Tunnel (cloudflared)

Perubahan dari repo asli:
1. `Dockerfile` - install `curl` + binary `cloudflared`
2. `entrypoint.sh` - jalankan `cloudflared tunnel run --token "$CF_TUNNEL_TOKEN"` di background, hanya jika env var `CF_TUNNEL_TOKEN` diisi

## Cara pakai

1. Buka Cloudflare Zero Trust dashboard → Networks → Tunnels → Create a tunnel (Cloudflared)
2. Salin token yang diberikan
3. Di Railway, tambahkan environment variable:
   ```
   CF_TUNNEL_TOKEN=eyJ...
   ```
4. Di tab Public Hostname tunnel tsb, tambahkan:
   - Subdomain: bebas (misal `ssh-ws`)
   - Domain: domain kamu di Cloudflare
   - Service: **HTTP** → `localhost:8880`
     (8880 = nilai default `WS_INTERNAL_PORT`; kalau kamu override env var itu, sesuaikan juga di sini)
5. Redeploy service di Railway

## Catatan penting

- Jalur ini **hanya untuk WS**. Jalur SSL/stunnel (raw TLS) tidak bisa lewat Cloudflare Tunnel gratis,
  jadi tetap diakses langsung via IP:port Railway seperti biasa (tidak ada yang berubah di jalur itu).
- Kalau `CF_TUNNEL_TOKEN` tidak diisi, container tetap jalan normal seperti sebelumnya
  (cloudflared tidak start).
